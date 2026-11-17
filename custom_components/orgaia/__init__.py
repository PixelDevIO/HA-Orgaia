"""Orgaia: a family group's lists, tasks and appointments in Home Assistant, end-to-end encrypted."""

from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .client.engine import GroupEngine
from .const import CONF_SPACE, DOMAIN, STORAGE_VERSION
from .coordinator import OrgaiaConfigEntry, OrgaiaCoordinator, storage_key

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CALENDAR, Platform.SENSOR, Platform.TODO]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    return True


async def _load_engine(hass: HomeAssistant, entry: OrgaiaConfigEntry, store: Store) -> GroupEngine:
    """The engine from what was saved last, or from the setup data on the first start."""
    saved = await store.async_load()
    data = saved if isinstance(saved, dict) and saved.get("seed") == entry.data.get("seed") else dict(entry.data)
    engine = GroupEngine(async_get_clientsession(hass), data)
    engine.space_id = engine.space_id or entry.data.get(CONF_SPACE)
    return engine


async def async_setup_entry(hass: HomeAssistant, entry: OrgaiaConfigEntry) -> bool:
    store: Store = Store(hass, STORAGE_VERSION, storage_key(entry.entry_id), private=True)
    engine = await _load_engine(hass, entry, store)
    coordinator = OrgaiaCoordinator(hass, entry, engine, store)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_create_background_task(hass, coordinator.run_live(), f"{DOMAIN} live {entry.entry_id}")
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OrgaiaConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator = entry.runtime_data
        await coordinator.store.async_save(coordinator.engine.to_dict())
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: OrgaiaConfigEntry) -> None:
    """Leaves the group, so the admins see Home Assistant is gone, then forgets everything."""
    store: Store = Store(hass, STORAGE_VERSION, storage_key(entry.entry_id), private=True)
    try:
        engine = await _load_engine(hass, entry, store)
        await engine.leave()
    except Exception as err:  # noqa: BLE001 - removing must work even when the service is not reachable
        _LOGGER.warning("Could not leave the Orgaia group; an admin can remove Home Assistant in the app: %s", err)
    await store.async_remove()
