"""One device per group and one per person of the group; every entity belongs to one of them."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    COMPLETED_DAYS,
    CONF_COMPLETED_DAYS,
    CONF_LISTS,
    CONF_PERSON_DEVICES,
    CONF_PERSONS,
    DOMAIN,
    NAME,
    VERSION,
)
from .coordinator import OrgaiaConfigEntry, OrgaiaCoordinator
from .protocol.view import SpaceView


def space_key(entry: OrgaiaConfigEntry) -> str:
    return entry.unique_id or entry.entry_id


def person_device_key(entry: OrgaiaConfigEntry, person_id: str) -> str:
    return f"{space_key(entry)}_{person_id}"


def person_entity(entry: OrgaiaConfigEntry, person_id: str) -> str | None:
    """The Home Assistant person an Orgaia person is mapped to in the options, if any."""
    return (entry.options.get(CONF_PERSONS) or {}).get(person_id) or None


def group_device_name(coordinator: OrgaiaCoordinator) -> str:
    """The group's name as Orgaia has it now, so a rename in the app reaches Home Assistant."""
    return coordinator.data.name or coordinator.config_entry.title


def person_device_name(coordinator: OrgaiaCoordinator, person_id: str) -> str:
    person = coordinator.data.person_by_id.get(person_id) or {}
    return f"{person.get('name') or person_id} ({group_device_name(coordinator)})"


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
                name=group_device_name(coordinator),
                manufacturer=NAME,
                model="Gruppe",
                sw_version=VERSION,
                entry_type=DeviceEntryType.SERVICE,
            )
        else:
            self._attr_unique_id = f"{person_device_key(entry, person_id)}_{key}"
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, person_device_key(entry, person_id))},
                name=person_device_name(coordinator, person_id),
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


def person_ids_for(entry: OrgaiaConfigEntry) -> Callable[[SpaceView], list[str]]:
    """The people that get a device with entities of their own: all, unless switched off in the options."""
    if entry.options.get(CONF_PERSON_DEVICES, True) is False:
        return lambda _view: []
    return active_person_ids


def list_shown(entry: OrgaiaConfigEntry, list_id: str) -> bool:
    """Whether a list becomes a to-do list: all, unless some were chosen in the options."""
    chosen = entry.options.get(CONF_LISTS) or []
    return not chosen or list_id in chosen


def completed_days(entry: OrgaiaConfigEntry) -> int:
    """How many days ticked-off tasks stay in the to-do lists."""
    days = entry.options.get(CONF_COMPLETED_DAYS)
    return int(days) if isinstance(days, (int, float)) and 0 <= days <= 365 else COMPLETED_DAYS


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


def plan_list_ids(list_type: str) -> Callable[[SpaceView], list[str]]:
    """The timetables or rosters of a group."""
    return lambda view: [lst["id"] for lst in view.lists if lst["type"] == list_type and lst.get(list_type)]


class OrgaiaPlanEntity(OrgaiaEntity):
    """Something read from one timetable or roster. It belongs to the person the plan is for."""

    plan_type = "timetable"

    def __init__(self, coordinator: OrgaiaCoordinator, list_id: str, key: str) -> None:
        self.list_id = list_id
        plan = (coordinator.data.list_by_id.get(list_id) or {}).get(self.plan_type) or {}
        person = plan.get("personId")
        if (
            person not in coordinator.data.person_by_id
            or coordinator.config_entry.options.get(CONF_PERSON_DEVICES, True) is False
        ):
            person = None
        super().__init__(coordinator, f"{self.plan_type}_{list_id}_{key}", person)

    @property
    def plan(self) -> dict[str, Any] | None:
        """The list of the plan, while it exists."""
        lst = self.coordinator.data.list_by_id.get(self.list_id)
        return lst if lst and lst["type"] == self.plan_type and lst.get(self.plan_type) else None

    @property
    def available(self) -> bool:
        return super().available and self.plan is not None
