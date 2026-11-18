"""On/off states for automations: at school, at work, school holidays."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_change

from .coordinator import OrgaiaConfigEntry, OrgaiaCoordinator
from .entity import OrgaiaEntity, OrgaiaPlanEntity, person_entity, plan_list_ids, track_dynamic
from .protocol.plans import at_school, at_work, holiday_on, next_holiday
from .util import local_now, minute_of_day, today


async def async_setup_entry(
    hass: HomeAssistant, entry: OrgaiaConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([OrgaiaSchoolHolidaysSensor(coordinator)])
    track_dynamic(
        hass,
        entry,
        plan_list_ids("timetable"),
        lambda list_id: [OrgaiaAtSchoolSensor(coordinator, list_id)],
        async_add_entities,
        "binary_sensor",
    )
    track_dynamic(
        hass,
        entry,
        plan_list_ids("roster"),
        lambda list_id: [OrgaiaAtWorkSensor(coordinator, list_id)],
        async_add_entities,
        "binary_sensor",
    )


class _ByTheMinute(BinarySensorEntity):
    """These follow the clock: they are looked at again at every full minute."""

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def tick(_now: datetime) -> None:
            self.async_write_ha_state()

        self.async_on_remove(async_track_time_change(self.hass, tick, second=0))


class OrgaiaAtSchoolSensor(OrgaiaPlanEntity, _ByTheMinute):
    """On from the first to the last lesson of today."""

    plan_type = "timetable"
    _attr_translation_key = "at_school"
    _attr_icon = "mdi:school"

    def __init__(self, coordinator: OrgaiaCoordinator, list_id: str) -> None:
        super().__init__(coordinator, list_id, "now")

    def _until(self) -> str | None:
        plan = self.plan
        if plan is None:
            return None
        off = self.coordinator.data.meta.get("schoolOff") or []
        return at_school(plan, off, today(), minute_of_day(local_now()))

    @property
    def is_on(self) -> bool:
        return self._until() is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {"until": self._until()}
        if self.person_id is not None:
            attrs["person_entity"] = person_entity(self.coordinator.config_entry, self.person_id)
        return attrs


class OrgaiaAtWorkSensor(OrgaiaPlanEntity, _ByTheMinute):
    """On during the working time of the roster, a night shift into the next morning included."""

    plan_type = "roster"
    _attr_translation_key = "at_work"
    _attr_icon = "mdi:briefcase"

    def __init__(self, coordinator: OrgaiaCoordinator, list_id: str) -> None:
        super().__init__(coordinator, list_id, "now")

    def _until(self) -> str | None:
        plan = self.plan
        return at_work(plan, today(), minute_of_day(local_now())) if plan else None

    @property
    def is_on(self) -> bool:
        return self._until() is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {"until": self._until()}
        if self.person_id is not None:
            attrs["person_entity"] = person_entity(self.coordinator.config_entry, self.person_id)
        return attrs


class OrgaiaSchoolHolidaysSensor(OrgaiaEntity, _ByTheMinute):
    """On during the school holidays the group entered."""

    _attr_translation_key = "school_holidays"
    _attr_icon = "mdi:beach"
    _unrecorded_attributes = frozenset({"name", "next"})

    def __init__(self, coordinator: OrgaiaCoordinator) -> None:
        super().__init__(coordinator, "school_holidays")

    def _off(self) -> list[dict[str, Any]]:
        return self.coordinator.data.meta.get("schoolOff") or []

    @property
    def is_on(self) -> bool:
        return holiday_on(self._off(), today()) is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        day = today()
        now, nxt = holiday_on(self._off(), day), next_holiday(self._off(), day)
        return {
            "name": now["name"] if now else None,
            "until": now["to"] if now else None,
            "next": {"name": nxt["name"], "from": nxt["from"], "to": nxt["to"]} if nxt else None,
        }
