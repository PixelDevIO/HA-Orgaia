"""Orgaia: a family group's lists, tasks and appointments in Home Assistant, end-to-end encrypted."""

from __future__ import annotations

import logging

from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .client.engine import GroupEngine
from .const import CONF_SPACE, DOMAIN, STORAGE_VERSION
from .coordinator import OrgaiaConfigEntry, OrgaiaCoordinator, storage_key
from .entity import active_person_ids, person_device_key
from .events import EventTracker

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
    # The group as Home Assistant left it when it last stopped, to catch up on what changed meanwhile.
    stopped, engine.stopped_at = engine.stopped_at, None
    before = coordinator.build_view() if stopped is not None and engine.state.get("item") else None
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_create_background_task(hass, coordinator.run_live(), f"{DOMAIN} live {entry.entry_id}")
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(
        EventTracker(hass, entry, before, dt_util.utc_from_timestamp(stopped / 1000) if stopped else None).start()
    )
    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, coordinator.save_on_stop))
    entry.async_on_unload(coordinator.async_add_listener(lambda: _remove_gone_persons(hass, entry)))
    entry.async_on_unload(entry.add_update_listener(_options_changed))
    return True


async def _options_changed(hass: HomeAssistant, entry: OrgaiaConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


@callback
def _remove_gone_persons(hass: HomeAssistant, entry: OrgaiaConfigEntry) -> None:
    """A person who left the group takes their device (and so their entities) along."""
    active = {person_device_key(entry, p) for p in active_person_ids(entry.runtime_data.data)}
    registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        if device.model != "Person":
            continue
        keys = {ident for domain, ident in device.identifiers if domain == DOMAIN}
        if not keys & active:
            registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: OrgaiaConfigEntry, device: dr.DeviceEntry
) -> bool:
    """A person's device can be deleted by hand once the person is no longer in the group."""
    if device.model != "Person":
        return False
    active = {person_device_key(entry, p) for p in active_person_ids(entry.runtime_data.data)}
    return not any(ident in active for domain, ident in device.identifiers if domain == DOMAIN)


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
