"""On/off states for automations: school, care, work, on call, away, child without care, holidays, busy, shopping."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_change

from .coordinator import OrgaiaConfigEntry, OrgaiaCoordinator
from .entity import OrgaiaEntity, OrgaiaPlanEntity, person_entity, person_ids_for, plan_list_ids, track_dynamic
from .protocol.people import absence_on, care_gaps
from .protocol.plans import (
    at_school,
    at_work,
    holiday_on,
    in_care,
    is_plan_item,
    next_holiday,
    on_call,
    school_day,
    school_off_for,
)
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


def care_timetables(view: SpaceView) -> list[str]:
    """Timetables with care after school (reliable school or OGS): only those get an "in care" sensor."""
    return [
        lst["id"]
        for lst in view.lists
        if lst["type"] == "timetable" and lst.get("timetable") and lst["timetable"].get("care")
    ]


def gap_groups(view: SpaceView) -> list[str]:
    """Groups with a timetable and a roster: only there can a child be on its own while everybody works."""
    types = {lst["type"] for lst in view.lists if lst.get("timetable") or lst.get("roster")}
    return ["care_gap"] if {"timetable", "roster"} <= types else []


def clock(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def gaps_on(view: SpaceView, date: str) -> list[dict[str, Any]]:
    """The hours of a day a child is neither at school nor in care while every grown-up works."""
    return [
        {
            "child": (view.person_by_id.get(g["childId"]) or {}).get("name"),
            "start": clock(g["start"]),
            "end": clock(g["end"]),
        }
        for g in care_gaps(view, date)
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
        care_timetables,
        lambda list_id: [OrgaiaInCareSensor(coordinator, list_id)],
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
        person_ids_for(entry),
        lambda person_id: [
            OrgaiaBusySensor(coordinator, person_id),
            OrgaiaShoppingSensor(coordinator, person_id),
            OrgaiaAwaySensor(coordinator, person_id),
        ],
        async_add_entities,
        "binary_sensor",
    )
    track_dynamic(
        hass, entry, gap_groups, lambda _key: [OrgaiaCareGapSensor(coordinator)], async_add_entities, "binary_sensor"
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
    # Off until somebody wants it: a new group starts with the few entities a household looks at.
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:school"

    def __init__(self, coordinator: OrgaiaCoordinator, list_id: str) -> None:
        super().__init__(coordinator, list_id, "now")

    def _until(self) -> str | None:
        plan = self.plan
        if plan is None:
            return None
        off = school_off_for(self.coordinator.data, plan["timetable"])
        return at_school(plan, off, today(), minute_of_day(local_now()))

    @property
    def is_on(self) -> bool:
        return self._until() is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {"until": self._until()}
        plan = self.plan
        if plan is not None:
            # Care after school today, so that an automation knows school ends but the child is not home yet.
            care = school_day(plan, school_off_for(self.coordinator.data, plan["timetable"]), today()).get("care")
            attrs["care_until"] = care["end"] if care else None
        if self.person_id is not None:
            attrs["person_entity"] = person_entity(self.coordinator.config_entry, self.person_id)
        return attrs


class OrgaiaInCareSensor(OrgaiaPlanEntity, _ByTheMinute):
    """On from the end of school to the end of care (reliable school or OGS) today."""

    plan_type = "timetable"
    _attr_translation_key = "in_care"
    # Off until somebody wants it: a new group starts with the few entities a household looks at.
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:account-child-outline"

    def __init__(self, coordinator: OrgaiaCoordinator, list_id: str) -> None:
        super().__init__(coordinator, list_id, "care")

    def _until(self) -> str | None:
        plan = self.plan
        if plan is None:
            return None
        off = school_off_for(self.coordinator.data, plan["timetable"])
        return in_care(plan, off, today(), minute_of_day(local_now()))

    @property
    def is_on(self) -> bool:
        return self._until() is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        plan = self.plan
        kind = plan["timetable"]["care"]["kind"] if plan is not None and plan["timetable"].get("care") else None
        attrs: dict[str, Any] = {
            "until": self._until(),
            "kind": {"vs": "reliable_school", "ogs": "ogs"}.get(kind or ""),
        }
        if self.person_id is not None:
            attrs["person_entity"] = person_entity(self.coordinator.config_entry, self.person_id)
        return attrs


class OrgaiaAtWorkSensor(OrgaiaPlanEntity, _ByTheMinute):
    """On during the working time of the roster, a night shift into the next morning included."""

    plan_type = "roster"
    _attr_translation_key = "at_work"
    # Off until somebody wants it: a new group starts with the few entities a household looks at.
    _attr_entity_registry_enabled_default = False
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
    # Off until somebody wants it: a new group starts with the few entities a household looks at.
    _attr_entity_registry_enabled_default = False
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
    # Off until somebody wants it: a new group starts with the few entities a household looks at.
    _attr_entity_registry_enabled_default = False
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
    # Off until somebody wants it: a new group starts with the few entities a household looks at.
    _attr_entity_registry_enabled_default = False
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


class OrgaiaAwaySensor(OrgaiaEntity, _ByTheMinute):
    """On on the days the person is entered as away in the app (trip, class trip, hospital)."""

    _attr_translation_key = "away"
    # Off until somebody wants it: a new group starts with the few entities a household looks at.
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:bag-suitcase"
    _unrecorded_attributes = frozenset({"note", "next"})

    def __init__(self, coordinator: OrgaiaCoordinator, person_id: str) -> None:
        super().__init__(coordinator, "away", person_id)

    def _person(self) -> dict[str, Any] | None:
        return self.coordinator.data.person_by_id.get(self.person_id or "")

    @property
    def is_on(self) -> bool:
        return absence_on(self._person(), today()) is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        day = today()
        person = self._person()
        now = absence_on(person, day)
        later = sorted((a for a in (person or {}).get("absences") or [] if a["from"] > day), key=lambda a: a["from"])
        nxt = later[0] if later else None
        return {
            "from": now["from"] if now else None,
            "until": now["to"] if now else None,
            "note": now.get("note") if now else None,
            "next": {"from": nxt["from"], "to": nxt["to"], "note": nxt.get("note")} if nxt else None,
            "person_entity": person_entity(self.coordinator.config_entry, self.person_id or ""),
        }


class OrgaiaCareGapSensor(OrgaiaEntity, _ByTheMinute):
    """On while a child is neither at school nor in care and every grown-up of the group works.

    As in the app under "Who is home when": only when every grown-up has a roster, between 7 and 19 o'clock.
    """

    _attr_translation_key = "care_gap"
    # Off until somebody wants it: a new group starts with the few entities a household looks at.
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:human-child"
    _unrecorded_attributes = frozenset({"today", "tomorrow", "children"})

    def __init__(self, coordinator: OrgaiaCoordinator) -> None:
        super().__init__(coordinator, "care_gap")

    def _now(self) -> list[dict[str, Any]]:
        minute = clock(minute_of_day(local_now()))
        return [g for g in gaps_on(self.coordinator.data, today()) if g["start"] <= minute < g["end"]]

    @property
    def is_on(self) -> bool:
        return bool(self._now())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        view = self.coordinator.data
        day = today()
        running = self._now()
        return {
            "children": [g["child"] for g in running],
            "until": max((g["end"] for g in running), default=None),
            "today": gaps_on(view, day),
            "tomorrow": gaps_on(view, add_days(day, 1)),
        }


class OrgaiaCanWriteSensor(OrgaiaEntity, BinarySensorEntity):
    """Whether an admin allowed this Home Assistant to tick off and add, in the app under Group › Home Assistant."""

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
    # Off until somebody wants it: a new group starts with the few entities a household looks at.
    _attr_entity_registry_enabled_default = False
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
