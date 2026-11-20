"""Connects one Orgaia group to Home Assistant: live updates, a fallback poll, storage and repair hints."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import json
import logging
import random
import time
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client.api import ApiError
from .client.engine import (
    STATUS_NEEDS_PLUS,
    STATUS_OFFLINE,
    STATUS_OK,
    STATUS_REMOVED,
    STATUS_UPDATE,
    Change,
    GroupEngine,
    WriteError,
)
from .const import DOMAIN
from .feeds import FeedCache
from .protocol.feeds import with_feed_items
from .protocol.people import with_absence_items
from .protocol.plans import labels_for, with_plan_items
from .protocol.view import SpaceView
from .util import today

_LOGGER = logging.getLogger(__name__)

# Without the live connection (or when it misses something) the group is read again this often.
FALLBACK_INTERVAL = timedelta(minutes=15)
# While the live connection stands it says when something changed: the group is then only read
# again this often, to be safe.
LIVE_INTERVAL = 60 * 60.0
# The whole group is one file: write it at most once a minute, and only when the group changed.
# Home Assistant writes what is still pending when it stops.
SAVE_DELAY = 60
# A live connection that held this long was a real one: the next attempt starts without a long wait.
LIVE_STABLE = 30.0
# After the service was out of reach for longer than this, what changed meanwhile counts as old news.
LATE_AFTER = 15 * 60.0

type OrgaiaConfigEntry = ConfigEntry[OrgaiaCoordinator]


def away_label(language: str | None) -> str:
    """What an absence reads as in the calendar, as in the app."""
    return "{name} weg" if (language or "de").split("-")[0].lower() == "de" else "{name} away"


def spread(delay: float) -> float:
    """A waiting time that differs between installations: up to twice as long, plus a few seconds."""
    return delay * random.uniform(1.0, 2.0) + random.uniform(0.0, 4.0)


def storage_key(entry_id: str) -> str:
    return f"{DOMAIN}.{entry_id}"


class OrgaiaCoordinator(DataUpdateCoordinator[SpaceView]):
    """Holds the group's engine and tells the entities when the group changed."""

    config_entry: OrgaiaConfigEntry

    def __init__(self, hass: HomeAssistant, entry: OrgaiaConfigEntry, engine: GroupEngine, store: Store) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=f"{DOMAIN} {entry.title}", update_interval=FALLBACK_INTERVAL
        )
        self.engine = engine
        self.store = store
        # For diagnostics: how the live connection fares.
        self.live_since: float | None = None
        self.live_reconnects = 0
        self.live_error: str | None = None
        # A change was refused because no admin allowed writing: a repair hint says where to switch it on.
        self.write_refused = False
        self.feeds = FeedCache(hass, entry.entry_id)
        self._feeds_busy = False
        self._view_key: tuple[int, int, str, str] | None = None
        self._view: SpaceView | None = None
        self._saved: tuple[Any, ...] | None = None
        self._offline_since: float | None = None
        # True while the entities hear about a first read after a long time without the service.
        self.late = False
        # The live connection stands: the service tells when there is something to fetch.
        self.live = False
        self._wanted = True
        self._read_at: float | None = None

    @property
    def status(self) -> str:
        return self.engine.status

    def build_view(self) -> SpaceView:
        """The group as the app shows it today: with what its timetables and rosters stand for."""
        day = today()
        language = self.hass.config.language
        key = (self.engine.version, self.feeds.version, day, language)
        if self._view is None or self._view_key != key:
            view = self.engine.view()
            view = with_feed_items(view, self.feeds.events(view))
            view = with_plan_items(view, labels_for(language), day)
            self._view = with_absence_items(view, away_label(language), day)
            self._view_key = key
        return self._view

    @callback
    def refresh_feeds(self) -> None:
        """Fetches subscribed calendars that are due, in the background; the view follows when they changed."""
        if self._feeds_busy or not self.feeds.stale(self.engine.view()):
            return
        self._feeds_busy = True

        async def run() -> None:
            try:
                if await self.feeds.refresh(self.engine.view()):
                    self.async_set_updated_data(self.build_view())
            finally:
                self._feeds_busy = False

        self.config_entry.async_create_background_task(self.hass, run(), f"{DOMAIN} feeds")

    def _keep_showing(self, err: Exception) -> SpaceView:
        """The service or the internet is gone: the group stays on screen as it was, the status says offline.

        Only on the very first start without anything read yet is there nothing to show.
        """
        self.engine.status = STATUS_OFFLINE
        if self._offline_since is None:
            self._offline_since = time.monotonic()
        if not self.engine.cursor and not self.engine.state.get("item"):
            raise UpdateFailed(f"Orgaia not reachable: {err}") from err
        if self.last_update_success:
            _LOGGER.warning("Orgaia not reachable, showing the last state: %s", err)
        return self.build_view()

    async def fetch(self) -> None:
        """Reads the group now, whatever the live connection says."""
        self._wanted = True
        await self.async_request_refresh()

    async def _async_update_data(self) -> SpaceView:
        self.late = False
        if (
            self.live
            and not self._wanted
            and self._read_at is not None
            and time.monotonic() - self._read_at < LIVE_INTERVAL
            and self.engine.status == STATUS_OK
        ):
            # Nothing was announced: the quarter-hourly look only moves on what depends on the time of day.
            return self.build_view()
        self._wanted = False
        try:
            if not self.live and self.engine.keys:
                # Without the live connection nobody says that an admin allowed or forbade writing.
                await self.engine.refresh_space()
            await self.engine.sync()
        except ApiError as err:
            self._update_issues()
            if self.engine.status == STATUS_REMOVED:
                raise ConfigEntryAuthFailed("removed from the group") from err
            if err.status >= 500 or err.status == 429:
                return self._keep_showing(err)
            raise UpdateFailed(f"Orgaia: {err.code}") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            return self._keep_showing(err)
        if self.engine.status == STATUS_REMOVED:
            self._update_issues()
            raise ConfigEntryAuthFailed("removed from the group")
        self.late = self._offline_since is not None and time.monotonic() - self._offline_since > LATE_AFTER
        self._offline_since = None
        self._read_at = time.monotonic()
        self._update_issues()
        self._save()
        self.refresh_feeds()
        return self.build_view()

    async def write(self, changes: list[Change], person_id: str) -> None:
        """Makes changes in a person's name and shows them at once. Raises WriteError when it did not work."""
        try:
            await self.engine.write(changes, person_id)
        except WriteError as err:
            if err.reason == "read_only":
                self.write_refused = True
            raise
        finally:
            # Also after a refusal: it may have told that writing is no longer allowed.
            self._update_issues()
            self.async_set_updated_data(self.build_view())
            self._save()

    @callback
    def save_on_stop(self, _event: Event) -> None:
        """Home Assistant stops: note when, so a quick restart can catch up on what happened meanwhile."""
        self.engine.stopped_at = int(time.time() * 1000)
        # Written by Home Assistant's final write, after this.
        self.store.async_delay_save(self.engine.to_dict, 0)

    def _save(self) -> None:
        """Writes the group to disk when anything in it changed since the last time."""
        e = self.engine
        mark = (e.version, e.cursor, e.epoch, e.status, len(e.keys), json.dumps([e.members, e.plan], sort_keys=True))
        if mark != self._saved:
            self._saved = mark
            self.store.async_delay_save(e.to_dict, SAVE_DELAY)

    def _update_issues(self) -> None:
        """Repair hints for what only the person can fix: Plus ended, or the integration is too old."""
        for status, key in ((STATUS_NEEDS_PLUS, "needs_plus"), (STATUS_UPDATE, "update_required")):
            issue_id = f"{key}_{self.config_entry.entry_id}"
            if self.engine.status == status:
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    issue_id,
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key=key,
                    translation_placeholders={"group": self.config_entry.title},
                )
            else:
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        issue_id = f"write_not_allowed_{self.config_entry.entry_id}"
        if self.engine.can_write:
            self.write_refused = False
        if self.write_refused:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="write_not_allowed",
                translation_placeholders={"group": self.config_entry.title},
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    async def run_live(self) -> None:
        """Keeps the live connection open. It only says that something changed; the changes are then fetched."""
        delay = 1.0
        while True:
            opened: float | None = None
            try:
                ws = await self.engine.api.ws_connect()
                opened = time.monotonic()
                async with ws:
                    self.live = True
                    self.live_since = time.time()
                    self.live_error = None
                    # Whatever happened while the connection was down.
                    await self.fetch()
                    async for msg in ws:
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            continue
                        try:
                            event: dict[str, Any] = json.loads(msg.data)
                        except ValueError:
                            continue
                        if not isinstance(event, dict):
                            continue
                        if await self.engine.on_event(event) or self.engine.status == STATUS_REMOVED:
                            await self.fetch()
            except asyncio.CancelledError:
                self.live = False
                raise
            except ApiError as err:
                _LOGGER.debug("Live connection refused: %s", err)
                self.live_error = f"refused {err.status} {err.code}"
                if err.status in (402, 426):
                    delay = 3600.0
            except (aiohttp.ClientError, TimeoutError, OSError) as err:
                _LOGGER.debug("Live connection lost: %s", err)
                self.live_error = type(err).__name__
            except Exception:
                # Anything unexpected must not end live updates until the next restart.
                _LOGGER.exception("Live connection failed, trying again")
            self.live = False
            self.live_since = None
            self.live_reconnects += 1
            # A connection the service closes right away (too many, or refused) does not count as one:
            # only one that held starts the waiting time over.
            if opened is not None and time.monotonic() - opened >= LIVE_STABLE:
                delay = 1.0
            # Not all at the same moment: after the service restarts, every Home Assistant comes back.
            await asyncio.sleep(spread(delay))
            delay = min(delay * 2, 60.0) if delay < 60 else delay
