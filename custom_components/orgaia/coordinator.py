"""Connects one Orgaia group to Home Assistant: live updates, a fallback poll, storage and repair hints."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import json
import logging
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client.api import ApiError
from .client.engine import STATUS_NEEDS_PLUS, STATUS_REMOVED, STATUS_UPDATE, GroupEngine
from .const import DOMAIN
from .protocol.view import SpaceView

_LOGGER = logging.getLogger(__name__)

# Without the live connection (or when it misses something) the group is read again this often.
FALLBACK_INTERVAL = timedelta(minutes=15)
SAVE_DELAY = 10

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

    @property
    def status(self) -> str:
        return self.engine.status

    async def _async_update_data(self) -> SpaceView:
        try:
            await self.engine.sync()
        except ApiError as err:
            self._update_issues()
            if self.engine.status == STATUS_REMOVED:
                raise ConfigEntryAuthFailed("removed from the group") from err
            raise UpdateFailed(f"Orgaia: {err.code}") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Orgaia not reachable: {err}") from err
        if self.engine.status == STATUS_REMOVED:
            self._update_issues()
            raise ConfigEntryAuthFailed("removed from the group")
        self._update_issues()
        self.store.async_delay_save(self.engine.to_dict, SAVE_DELAY)
        return self.engine.view()

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
