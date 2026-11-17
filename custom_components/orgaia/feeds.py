"""Fetches the group's subscribed calendars, as the app does on every device.

The address is part of the group (so the whole family gets the school calendar), but the entries are
fetched straight from the school or club and kept only here, in their own storage file. They never go
through the sync service. A calendar is fetched again after a few hours; when that fails, the entries
of the last good fetch stay.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN, STORAGE_VERSION
from .protocol.ics import FeedEvent, feed_url, parse_ics
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
            # No cookies, no referrer: the school's server learns only that a calendar asked.
            async with session.get(
                url, timeout=TIMEOUT, headers={"accept": "text/calendar, text/plain, */*"}, allow_redirects=True
            ) as res:
                if res.status != 200:
                    return None, f"status {res.status}"
                body = await res.content.read(MAX_BYTES + 1)
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
