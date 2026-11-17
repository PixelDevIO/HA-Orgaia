"""One device per group and one per person of the group; every entity belongs to one of them."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_PERSONS, DOMAIN, NAME, VERSION
from .coordinator import OrgaiaConfigEntry, OrgaiaCoordinator
from .protocol.view import SpaceView


def space_key(entry: OrgaiaConfigEntry) -> str:
    return entry.unique_id or entry.entry_id


def person_device_key(entry: OrgaiaConfigEntry, person_id: str) -> str:
    return f"{space_key(entry)}_{person_id}"


def person_entity(entry: OrgaiaConfigEntry, person_id: str) -> str | None:
    """The Home Assistant person an Orgaia person is mapped to in the options, if any."""
    return (entry.options.get(CONF_PERSONS) or {}).get(person_id) or None


class OrgaiaEntity(CoordinatorEntity[OrgaiaCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: OrgaiaCoordinator, key: str, person_id: str | None = None) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self.person_id = person_id
        if person_id is None:
            self._attr_unique_id = f"{space_key(entry)}_{key}"
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, space_key(entry))},
                name=entry.title,
                manufacturer=NAME,
                model="Gruppe",
                sw_version=VERSION,
                entry_type=DeviceEntryType.SERVICE,
            )
        else:
            person = coordinator.data.person_by_id.get(person_id) or {}
            self._attr_unique_id = f"{person_device_key(entry, person_id)}_{key}"
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, person_device_key(entry, person_id))},
                name=f"{person.get('name') or person_id} ({entry.title})",
                manufacturer=NAME,
                model="Person",
                sw_version=VERSION,
                entry_type=DeviceEntryType.SERVICE,
            )

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        if self.person_id is None:
            return True
        person = self.coordinator.data.person_by_id.get(self.person_id)
        return person is not None and not person["removed"]


def active_person_ids(view: SpaceView) -> list[str]:
    return [p["id"] for p in view.active_persons()]


def track_dynamic(
    hass: HomeAssistant,
    entry: OrgaiaConfigEntry,
    keys: Callable[[SpaceView], Iterable[str]],
    make: Callable[[str], list[OrgaiaEntity]],
    async_add_entities: AddConfigEntryEntitiesCallback,
    domain: str,
) -> None:
    """Adds entities for lists or persons that appear, and removes those of lists or persons that are gone."""
    coordinator = entry.runtime_data
    known: dict[str, list[OrgaiaEntity]] = {}

    @callback
    def _sync() -> None:
        current = list(dict.fromkeys(keys(coordinator.data)))
        new: list[OrgaiaEntity] = []
        for key in current:
            if key not in known:
                known[key] = make(key)
                new.extend(known[key])
        if new:
            async_add_entities(new)
        registry = er.async_get(hass)
        for key in [k for k in known if k not in current]:
            for entity in known.pop(key):
                if entity_id := registry.async_get_entity_id(domain, DOMAIN, entity.unique_id or ""):
                    registry.async_remove(entity_id)

    _sync()
    entry.async_on_unload(coordinator.async_add_listener(_sync))
