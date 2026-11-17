"""Counts for dashboards and automations, the next appointment, and how the connection to Orgaia is doing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .calendar import LOOKAHEAD_DAYS, events_between
from .client.engine import STATUS_NEEDS_PLUS, STATUS_OFFLINE, STATUS_OK, STATUS_REMOVED, STATUS_UPDATE
from .const import MAX_TITLES
from .coordinator import OrgaiaConfigEntry, OrgaiaCoordinator
from .entity import OrgaiaEntity
from .summary import Counts, counts
from .util import local_now, minute_of_day


@dataclass(frozen=True, kw_only=True)
class CountDescription(SensorEntityDescription):
    pick: Callable[[Counts], list[str]]


COUNTS: tuple[CountDescription, ...] = (
    CountDescription(
        key="open_tasks", translation_key="open_tasks", icon="mdi:checkbox-blank-outline", pick=lambda c: c.open
    ),
    CountDescription(
        key="due_today", translation_key="due_today", icon="mdi:calendar-today", pick=lambda c: c.due_today
    ),
    CountDescription(key="overdue", translation_key="overdue", icon="mdi:calendar-alert", pick=lambda c: c.overdue),
    CountDescription(key="shopping", translation_key="shopping", icon="mdi:cart-outline", pick=lambda c: c.shopping),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: OrgaiaConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [OrgaiaCountSensor(coordinator, d) for d in COUNTS]
    entities += [OrgaiaNextEventSensor(coordinator), OrgaiaConnectionSensor(coordinator)]
    async_add_entities(entities)


class OrgaiaCountSensor(OrgaiaEntity, SensorEntity):
    entity_description: CountDescription
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: OrgaiaCoordinator, description: CountDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    def _titles(self) -> list[str]:
        now = local_now()
        return self.entity_description.pick(counts(self.coordinator.data, now.date().isoformat(), minute_of_day(now)))

    @property
    def native_value(self) -> int:
        return len(self._titles())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"titles": self._titles()[:MAX_TITLES]}


class OrgaiaNextEventSensor(OrgaiaEntity, SensorEntity):
    _attr_translation_key = "next_event"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: OrgaiaCoordinator) -> None:
        super().__init__(coordinator, "next_event")

    def _next(self):
        now = local_now()
        upcoming = [
            e
            for e in events_between(self.coordinator.data, now, now + timedelta(days=LOOKAHEAD_DAYS))
            if e.start_datetime_local >= now
        ]
        return upcoming[0] if upcoming else None

    @property
    def native_value(self):
        ev = self._next()
        return ev.start_datetime_local if ev else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        ev = self._next()
        if ev is None:
            return {}
        return {
            "title": ev.summary,
            "location": ev.location,
            "all_day": ev.all_day,
            "end": ev.end_datetime_local.isoformat(),
        }


class OrgaiaConnectionSensor(OrgaiaEntity, SensorEntity):
    """Stays available when the group cannot be read, so it can tell why."""

    _attr_translation_key = "connection"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_options = [STATUS_OK, STATUS_OFFLINE, STATUS_NEEDS_PLUS, STATUS_UPDATE, STATUS_REMOVED]

    def __init__(self, coordinator: OrgaiaCoordinator) -> None:
        super().__init__(coordinator, "connection")

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> str:
        status = self.coordinator.status
        if status == STATUS_OK and not self.coordinator.last_update_success:
            return STATUS_OFFLINE
        return status if status in self._attr_options else STATUS_OFFLINE
