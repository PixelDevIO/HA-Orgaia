"""Orgaia: a family group's lists, tasks and appointments in Home Assistant, end-to-end encrypted."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .board import async_setup_board, group_loaded, notify_boards
from .client.engine import GroupEngine
from .const import CARD_URL, CONF_SPACE, DOMAIN, STORAGE_VERSION, VERSION
from .coordinator import OrgaiaConfigEntry, OrgaiaCoordinator, storage_key
from .entity import active_person_ids, person_device_key
from .events import EventTracker
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.CALENDAR, Platform.SENSOR, Platform.TODO]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async_setup_services(hass)
    async_setup_board(hass)
    await _serve_card(hass)
    return True


async def _serve_card(hass: HomeAssistant) -> None:
    """The Orgaia card comes with the integration: every dashboard can use it without adding a resource."""
    if hass.http is None:
        return
    card = Path(__file__).parent / "www" / "orgaia-card.js"
    await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(card), False)])
    # The version in the address makes browsers fetch the card again after an update.
    url = f"{CARD_URL}?v={VERSION}"
    if await _register_resource(hass, url):
        return
    if "frontend" in hass.config.components:
        from homeassistant.components.frontend import add_extra_js_url  # noqa: PLC0415

        add_extra_js_url(hass, url)


async def _register_resource(hass: HomeAssistant, url: str) -> bool:
    """Lists the card among the dashboard resources, where the card picker finds it for sure.

    Dashboards whose resources are written in YAML cannot be added to; the card is then loaded with the frontend.
    """
    lovelace = hass.data.get("lovelace")
    resources = getattr(lovelace, "resources", None)
    if resources is None or getattr(lovelace, "resource_mode", None) != "storage":
        return False
    try:
        if not resources.loaded:
            await resources.async_load()
            resources.loaded = True
        mine = [r for r in resources.async_items() if str(r.get("url", "")).split("?")[0] == CARD_URL]
        if not mine:
            await resources.async_create_item({"res_type": "module", "url": url})
        for i, r in enumerate(mine):
            if i:
                await resources.async_delete_item(r["id"])
            elif r["url"] != url:
                await resources.async_update_item(r["id"], {"res_type": "module", "url": url})
    except Exception:  # noqa: BLE001 - the card is a convenience; the integration works without it
        _LOGGER.warning("Could not list the Orgaia card among the dashboard resources", exc_info=True)
        return False
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
    await coordinator.feeds.load()
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
    entry.async_on_unload(coordinator.async_add_listener(lambda: notify_boards(hass)))
    group_loaded(hass, entry, True)
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
        group_loaded(hass, entry, False)
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
    await Store(hass, STORAGE_VERSION, f"{storage_key(entry.entry_id)}.feeds", private=True).async_remove()
