"""On/off states for automations: at school, at work, on call, school holidays, busy, out shopping, may write."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_change

from .coordinator import OrgaiaConfigEntry, OrgaiaCoordinator
from .entity import OrgaiaEntity, OrgaiaPlanEntity, active_person_ids, person_entity, plan_list_ids, track_dynamic
from .protocol.plans import at_school, at_work, holiday_on, is_plan_item, next_holiday, on_call
from .protocol.recur import add_days
from .protocol.shopping import STATE_GOING
from .protocol.view import SpaceView
from .summary import calendar_occurrences, shopping_trips
from .util import local_now, minute_of_day, to_datetime, today


def standby_rosters(view: SpaceView) -> list[str]:
    """Rosters with an on-call shift: only those get an "on call" sensor."""
    return [
        lst["id"]
        for lst in view.lists
        if lst["type"] == "roster" and lst.get("roster") and any(s.get("standby") for s in lst["roster"]["shifts"])
    ]


def running_appointments(view: SpaceView, person: str) -> list[dict[str, Any]]:
    """Appointments of a person that are on right now; whole days, plans and planned tasks left out."""
    now = local_now()
    day = now.date().isoformat()
    out = []
    for occ in calendar_occurrences(view, add_days(day, -1), day, person):
        item = occ.item
        if item.get("kind") != "event" or item.get("allDay") or is_plan_item(item) or not occ.end:
            continue
        if to_datetime(occ.start) <= now < to_datetime(occ.end):
            out.append({"title": item["title"], "until": occ.end[11:16] if len(occ.end) > 10 else None})
    return out


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
    track_dynamic(
        hass,
        entry,
        standby_rosters,
        lambda list_id: [OrgaiaOnCallSensor(coordinator, list_id)],
        async_add_entities,
        "binary_sensor",
    )
    track_dynamic(
        hass,
        entry,
        active_person_ids,
        lambda person_id: [OrgaiaBusySensor(coordinator, person_id), OrgaiaShoppingSensor(coordinator, person_id)],
        async_add_entities,
        "binary_sensor",
    )
    async_add_entities([OrgaiaCanWriteSensor(coordinator)])


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


class OrgaiaOnCallSensor(OrgaiaPlanEntity, _ByTheMinute):
    """On while an on-call shift of the roster runs. On call is not work, so "at work" stays off."""

    plan_type = "roster"
    _attr_translation_key = "on_call"
    _attr_icon = "mdi:phone-alert"

    def __init__(self, coordinator: OrgaiaCoordinator, list_id: str) -> None:
        super().__init__(coordinator, list_id, "on_call")

    def _until(self) -> str | None:
        plan = self.plan
        return on_call(plan, today(), minute_of_day(local_now())) if plan else None

    @property
    def is_on(self) -> bool:
        return self._until() is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {"until": self._until()}
        if self.person_id is not None:
            attrs["person_entity"] = person_entity(self.coordinator.config_entry, self.person_id)
        return attrs


class OrgaiaBusySensor(OrgaiaEntity, _ByTheMinute):
    """On while an appointment of the person is on: for "do not disturb" and the like."""

    _attr_translation_key = "busy"
    _attr_icon = "mdi:account-clock"
    _unrecorded_attributes = frozenset({"titles"})

    def __init__(self, coordinator: OrgaiaCoordinator, person_id: str) -> None:
        super().__init__(coordinator, "busy", person_id)

    def _running(self) -> list[dict[str, Any]]:
        return running_appointments(self.coordinator.data, self.person_id or "")

    @property
    def is_on(self) -> bool:
        return bool(self._running())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        running = self._running()
        ends = [r["until"] for r in running if r["until"]]
        return {
            "titles": [r["title"] for r in running],
            "until": max(ends) if ends else None,
            "person_entity": person_entity(self.coordinator.config_entry, self.person_id or ""),
        }


class OrgaiaShoppingSensor(OrgaiaEntity, BinarySensorEntity):
    """On while the person has taken over a shopping list ("I'll do it") and not finished it yet."""

    _attr_translation_key = "out_shopping"
    _attr_icon = "mdi:cart-arrow-right"

    def __init__(self, coordinator: OrgaiaCoordinator, person_id: str) -> None:
        super().__init__(coordinator, "out_shopping", person_id)

    def _lists(self) -> list[dict[str, Any]]:
        return [
            {"list": lst["name"], "open": trip.open, "since": trip.since}
            for lst, trip in shopping_trips(self.coordinator.data)
            if trip.state == STATE_GOING and trip.shopper == self.person_id
        ]

    @property
    def is_on(self) -> bool:
        return bool(self._lists())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        lists = self._lists()
        return {
            "lists": [x["list"] for x in lists],
            "open": sum(x["open"] for x in lists),
            "person_entity": person_entity(self.coordinator.config_entry, self.person_id or ""),
        }


class OrgaiaCanWriteSensor(OrgaiaEntity, BinarySensorEntity):
    """Whether an admin allowed this Home Assistant to tick off and add, in the app under Manage › Home Assistant."""

    _attr_translation_key = "can_write"
    _attr_icon = "mdi:pencil-lock-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: OrgaiaCoordinator) -> None:
        super().__init__(coordinator, "can_write")

    @property
    def is_on(self) -> bool:
        return self.coordinator.engine.can_write


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
