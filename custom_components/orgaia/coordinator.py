"""Connects one Orgaia group to Home Assistant: live updates, a fallback poll, storage and repair hints."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import json
import logging
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
from .client.engine import STATUS_NEEDS_PLUS, STATUS_OFFLINE, STATUS_REMOVED, STATUS_UPDATE, GroupEngine
from .const import DOMAIN
from .protocol.plans import labels_for, with_plan_items
from .protocol.view import SpaceView
from .util import today

_LOGGER = logging.getLogger(__name__)

# Without the live connection (or when it misses something) the group is read again this often.
FALLBACK_INTERVAL = timedelta(minutes=15)
# The whole group is one file: write it at most once a minute, and only when the group changed.
# Home Assistant writes what is still pending when it stops.
SAVE_DELAY = 60

type OrgaiaConfigEntry = ConfigEntry[OrgaiaCoordinator]


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
        self._view_key: tuple[int, str, str] | None = None
        self._view: SpaceView | None = None
        self._saved: tuple[Any, ...] | None = None

    @property
    def status(self) -> str:
        return self.engine.status

    def build_view(self) -> SpaceView:
        """The group as the app shows it today: with what its timetables and rosters stand for."""
        day = today()
        language = self.hass.config.language
        key = (self.engine.version, day, language)
        if self._view is None or self._view_key != key:
            self._view = with_plan_items(self.engine.view(), labels_for(language), day)
            self._view_key = key
        return self._view

    def _keep_showing(self, err: Exception) -> SpaceView:
        """The service or the internet is gone: the group stays on screen as it was, the status says offline.

        Only on the very first start without anything read yet is there nothing to show.
        """
        self.engine.status = STATUS_OFFLINE
        if not self.engine.cursor and not self.engine.state.get("item"):
            raise UpdateFailed(f"Orgaia not reachable: {err}") from err
        if self.last_update_success:
            _LOGGER.warning("Orgaia not reachable, showing the last state: %s", err)
        return self.build_view()

    async def _async_update_data(self) -> SpaceView:
        try:
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
        self._update_issues()
        self._save()
        return self.build_view()

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

    async def run_live(self) -> None:
        """Keeps the live connection open. It only says that something changed; the changes are then fetched."""
        delay = 1.0
        while True:
            try:
                ws = await self.engine.api.ws_connect()
                delay = 1.0
                async with ws:
                    # Whatever happened while the connection was down.
                    await self.async_request_refresh()
                    async for msg in ws:
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            continue
                        try:
                            event: dict[str, Any] = json.loads(msg.data)
                        except ValueError:
                            continue
                        if await self.engine.on_event(event):
                            await self.async_request_refresh()
                        elif self.engine.status == STATUS_REMOVED:
                            await self.async_request_refresh()
            except asyncio.CancelledError:
                raise
            except ApiError as err:
                _LOGGER.debug("Live connection refused: %s", err)
                if err.status in (402, 426):
                    delay = 3600.0
            except (aiohttp.ClientError, TimeoutError, OSError) as err:
                _LOGGER.debug("Live connection lost: %s", err)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60.0) if delay < 60 else delay
