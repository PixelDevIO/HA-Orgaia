"""Counts for dashboards and automations, per group and per person, the next appointment, and the connection."""

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
from .entity import OrgaiaEntity, active_person_ids, person_entity, track_dynamic
from .summary import Counts, counts
from .util import from_ms, local_now, minute_of_day, to_date, to_datetime


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
    track_dynamic(
        hass,
        entry,
        active_person_ids,
        lambda person_id: [
            *(OrgaiaCountSensor(coordinator, d, person_id) for d in COUNTS if d.key != "shopping"),
            OrgaiaNextTaskSensor(coordinator, person_id),
        ],
        async_add_entities,
        "sensor",
    )


class OrgaiaCountSensor(OrgaiaEntity, SensorEntity):
    entity_description: CountDescription
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: OrgaiaCoordinator, description: CountDescription, person_id: str | None = None
    ) -> None:
        super().__init__(coordinator, description.key, person_id)
        self.entity_description = description

    def _titles(self) -> list[str]:
        now = local_now()
        c = counts(self.coordinator.data, now.date().isoformat(), minute_of_day(now), self.person_id)
        return self.entity_description.pick(c)

    @property
    def native_value(self) -> int:
        return len(self._titles())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {"titles": self._titles()[:MAX_TITLES]}
        if self.person_id is not None:
            attrs["person_entity"] = person_entity(self.coordinator.config_entry, self.person_id)
        return attrs


class OrgaiaNextTaskSensor(OrgaiaEntity, SensorEntity):
    """The open task of a person that is due next; tasks without a due date or time slot are left out."""

    _attr_translation_key = "next_task"
    _attr_icon = "mdi:clipboard-text-clock-outline"

    def __init__(self, coordinator: OrgaiaCoordinator, person_id: str) -> None:
        super().__init__(coordinator, "next_task", person_id)

    def _next(self) -> tuple[str, str] | None:
        now = local_now()
        return counts(self.coordinator.data, now.date().isoformat(), minute_of_day(now), self.person_id).next

    @property
    def native_value(self) -> str | None:
        nxt = self._next()
        return nxt[1][:255] if nxt else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        nxt = self._next()
        due = None
        if nxt:
            due = (to_datetime(nxt[0]) if len(nxt[0]) > 10 else to_date(nxt[0])).isoformat()
        return {"due": due, "person_entity": person_entity(self.coordinator.config_entry, self.person_id or "")}


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
    _unrecorded_attributes = frozenset({"last_sync"})

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

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """When the group was last read: what a wall display shows while offline is as of then."""
        synced = from_ms(self.coordinator.engine.synced_at)
        return {"last_sync": synced.isoformat() if synced else None}
