"""Fetches the group's subscribed calendars, as the app does on every device.

The address is part of the group (so the whole family gets the school calendar), but the entries are
fetched straight from the school or club and kept only here, in their own storage file. They never go
through the sync service. A calendar is fetched again after a few hours; when that fails, the entries
of the last good fetch stay.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
import time
from typing import Any
from urllib.parse import urljoin, urlsplit

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN, STORAGE_VERSION
from .protocol.ics import FeedEvent, feed_url, is_private_ip, parse_ics
from .protocol.recur import add_days
from .protocol.view import SpaceView

_LOGGER = logging.getLogger(__name__)

# How long fetched entries count as fresh.
FRESH_SECONDS = 6 * 3600
# Entries from this far back and ahead are kept.
PAST_DAYS = 62
AHEAD_DAYS = 400
MAX_BYTES = 3 * 1024 * 1024
TIMEOUT = aiohttp.ClientTimeout(total=30)
MAX_REDIRECTS = 5


class FeedCache:
    """Entries per subscribed list, with the address they were fetched from."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self.store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}.feeds", private=True)
        self._data: dict[str, dict[str, Any]] = {}
        self._events: dict[str, list[FeedEvent]] = {}
        self.version = 0

    async def load(self) -> None:
        saved = await self.store.async_load()
        if isinstance(saved, dict):
            self._data = {k: v for k, v in saved.items() if isinstance(v, dict)}
            self._events = {}
            for list_id, cached in self._data.items():
                try:
                    self._events[list_id] = [FeedEvent.from_json(e) for e in cached.get("events") or []]
                except (KeyError, TypeError):
                    # A broken entry is fetched again.
                    self._data[list_id] = {}
        self.version += 1

    def events(self, view: SpaceView) -> dict[str, list[FeedEvent]]:
        """Entries per subscribed list; those of an address that was changed since are left out."""
        out = {}
        for lst in view.lists:
            if lst["type"] != "feed":
                continue
            cached = self._data.get(lst["id"]) or {}
            if cached.get("url") == lst.get("url") and lst["id"] in self._events:
                out[lst["id"]] = self._events[lst["id"]]
        return out

    def status(self) -> list[dict[str, Any]]:
        """For diagnostics: per subscribed list when it was fetched, and the last error. No address, no entries."""
        return [
            {
                "events": len(c.get("events") or []),
                "fetched_at": c.get("fetchedAt") or None,
                "error": c.get("error"),
                "error_at": c.get("errorAt"),
            }
            for c in self._data.values()
        ]

    def stale(self, view: SpaceView, now: float | None = None) -> list[dict[str, Any]]:
        now = time.time() if now is None else now
        out = []
        for lst in view.lists:
            if lst["type"] != "feed" or not lst.get("url"):
                continue
            cached = self._data.get(lst["id"]) or {}
            last = max(cached.get("fetchedAt") or 0, cached.get("errorAt") or 0)
            if cached.get("url") != lst["url"] or now - last >= FRESH_SECONDS:
                out.append(lst)
        return out

    async def refresh(self, view: SpaceView) -> bool:
        """Fetches every subscribed calendar that is not fresh. Returns True when entries changed."""
        lists = self.stale(view)
        if not lists:
            return False
        results = await asyncio.gather(*(self._fetch(lst["url"]) for lst in lists))
        changed = False
        for lst, (events, error) in zip(lists, results, strict=True):
            before = self._data.get(lst["id"]) or {}
            if events is not None:
                self._data[lst["id"]] = {
                    "url": lst["url"],
                    "fetchedAt": time.time(),
                    "events": [e.to_json() for e in events],
                }
                self._events[lst["id"]] = events
                changed = True
            elif before.get("url") == lst["url"]:
                self._data[lst["id"]] = {**before, "error": error, "errorAt": time.time()}
            else:
                self._data[lst["id"]] = {"url": lst["url"], "fetchedAt": 0, "events": [], "error": error}
                self._data[lst["id"]]["errorAt"] = time.time()
                self._events[lst["id"]] = []
                changed = True
        # Lists that are gone take their entries along.
        for list_id in [k for k in self._data if not any(lst["id"] == k for lst in view.lists)]:
            del self._data[list_id]
            self._events.pop(list_id, None)
            changed = True
        self.store.async_delay_save(lambda: self._data, 5)
        if changed:
            self.version += 1
        return changed

    async def _fetch(self, raw: str) -> tuple[list[FeedEvent] | None, str | None]:
        url = feed_url(raw)
        if not url:
            return None, "address"
        session = async_get_clientsession(self.hass)
        try:
            # Redirects are followed by hand, so that none leads into the home network.
            for _ in range(MAX_REDIRECTS + 1):
                if not await self._public(url):
                    return None, "address"
                # No cookies, no referrer: the school's server learns only that a calendar asked.
                async with session.get(
                    url, timeout=TIMEOUT, headers={"accept": "text/calendar, text/plain, */*"}, allow_redirects=False
                ) as res:
                    if res.status in (301, 302, 303, 307, 308) and res.headers.get("location"):
                        nxt = feed_url(urljoin(url, res.headers["location"]))
                        if not nxt:
                            return None, "address"
                        url = nxt
                        continue
                    if res.status != 200:
                        return None, f"status {res.status}"
                    body = await res.content.read(MAX_BYTES + 1)
                    break
            else:
                return None, "status redirects"
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.debug("Calendar %s not reachable: %s", url, err)
            return None, "network"
        if len(body) > MAX_BYTES:
            return None, "size"
        text = body.decode("utf-8", errors="replace")
        if "BEGIN:VCALENDAR" not in text.upper():
            return None, "format"
        today = dt_util.now().date().isoformat()
        events = await self.hass.async_add_executor_job(
            parse_ics, text, add_days(today, -PAST_DAYS), add_days(today, AHEAD_DAYS), dt_util.get_default_time_zone()
        )
        return events, None

    async def _public(self, url: str) -> bool:
        """Whether every address the host name stands for is on the internet, not in the home network."""
        host = urlsplit(url).hostname or ""
        try:
            infos = await self.hass.loop.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        except OSError:
            # Not resolvable: the request fails on its own.
            return True
        for info in infos:
            try:
                if is_private_ip(ipaddress.ip_address(info[4][0].split("%")[0])):
                    _LOGGER.warning("Calendar address %s points into the local network; not fetched", host)
                    return False
            except ValueError:
                return False
        return True
