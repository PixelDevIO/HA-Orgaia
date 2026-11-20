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

from .calendar import DONE_MARK, LOOKAHEAD_DAYS, events_between
from .client.engine import STATUS_NEEDS_PLUS, STATUS_OFFLINE, STATUS_OK, STATUS_REMOVED, STATUS_UPDATE
from .const import MAX_TITLES
from .coordinator import OrgaiaConfigEntry, OrgaiaCoordinator
from .entity import OrgaiaEntity, OrgaiaPlanEntity, person_entity, person_ids_for, plan_list_ids, track_dynamic
from .protocol.people import upcoming_occasions, with_occasion
from .protocol.plans import (
    STATUS_AWAY,
    STATUS_FREE,
    STATUS_HOLIDAY,
    exams_ahead,
    labels_for,
    pack_on,
    school_day,
    school_off_for,
    work_day,
    work_minutes,
)
from .protocol.recur import add_days, week_start
from .protocol.shopping import STATE_READY
from .report import day_report, short_text, speech
from .summary import Counts, counts, drives_between, shopping_trips
from .util import from_ms, local_now, minute_of_day, to_date, to_datetime, today

# What a day without school or work reads as; times read "07:55–13:15".
DAY_LABELS = {
    "de": {STATUS_FREE: "frei", STATUS_HOLIDAY: "Ferien", STATUS_AWAY: "weg"},
    "en": {STATUS_FREE: "off", STATUS_HOLIDAY: "holidays", STATUS_AWAY: "away"},
}
# How many days ahead birthdays and anniversaries are listed.
OCCASION_DAYS = 30
# How many days ahead a roster's sensor lists.
WORK_AHEAD_DAYS = 7


def day_label(language: str | None, status: str) -> str:
    labels = DAY_LABELS.get((language or "de").split("-")[0].lower(), DAY_LABELS["en"])
    return labels.get(status, status)


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
    entities += [
        OrgaiaShoppingWaitingSensor(coordinator),
        OrgaiaNextEventSensor(coordinator),
        OrgaiaConnectionSensor(coordinator),
        OrgaiaTodaySensor(coordinator),
        OrgaiaOpenDrivesSensor(coordinator),
        OrgaiaOccasionsSensor(coordinator),
    ]
    async_add_entities(entities)
    track_dynamic(
        hass,
        entry,
        plan_list_ids("timetable"),
        lambda list_id: [OrgaiaSchoolSensor(coordinator, list_id)],
        async_add_entities,
        "sensor",
    )
    track_dynamic(
        hass,
        entry,
        plan_list_ids("roster"),
        lambda list_id: [OrgaiaWorkSensor(coordinator, list_id)],
        async_add_entities,
        "sensor",
    )
    track_dynamic(
        hass,
        entry,
        person_ids_for(entry),
        lambda person_id: [
            *(OrgaiaCountSensor(coordinator, d, person_id) for d in COUNTS if d.key != "shopping"),
            OrgaiaNextTaskSensor(coordinator, person_id),
            OrgaiaNextEventSensor(coordinator, person_id),
            OrgaiaTodaySensor(coordinator, person_id),
        ],
        async_add_entities,
        "sensor",
    )


class OrgaiaCountSensor(OrgaiaEntity, SensorEntity):
    entity_description: CountDescription
    _attr_state_class = SensorStateClass.MEASUREMENT
    # What the tasks are called stays out of the recorder's database and so out of backups.
    _unrecorded_attributes = frozenset({"titles"})

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


class OrgaiaShoppingWaitingSensor(OrgaiaEntity, SensorEntity):
    """Shopping lists that were released and that nobody has taken over yet."""

    _attr_translation_key = "shopping_waiting"
    _attr_icon = "mdi:cart-arrow-right"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _unrecorded_attributes = frozenset({"lists"})

    def __init__(self, coordinator: OrgaiaCoordinator) -> None:
        super().__init__(coordinator, "shopping_waiting")

    def _lists(self) -> list[str]:
        return [lst["name"] for lst, trip in shopping_trips(self.coordinator.data) if trip.state == STATE_READY]

    @property
    def native_value(self) -> int:
        return len(self._lists())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"lists": self._lists()[:MAX_TITLES]}


def _span_text(start: str, end: str) -> str:
    return f"{start}–{end}"


class OrgaiaSchoolSensor(OrgaiaPlanEntity, SensorEntity):
    """A timetable today: from when to when, with every lesson, and what to pack."""

    plan_type = "timetable"
    _attr_translation_key = "school_today"
    _attr_icon = "mdi:school-outline"
    # Subjects and things say a lot about a child: they stay out of the recorder's database.
    _unrecorded_attributes = frozenset(
        {"lessons", "tomorrow", "pack_today", "pack_tomorrow", "holiday", "plan", "note", "exams", "exams_ahead"}
    )

    def __init__(self, coordinator: OrgaiaCoordinator, list_id: str) -> None:
        super().__init__(coordinator, list_id, "today")

    def _day(self, ahead: int = 0) -> dict[str, Any] | None:
        plan = self.plan
        if plan is None:
            return None
        return school_day(plan, school_off_for(self.coordinator.data, plan["timetable"]), add_days(today(), ahead))

    def _text(self, day: dict[str, Any]) -> str:
        if day["start"]:
            return _span_text(day["start"], day["end"])
        return day_label(self.hass.config.language if self.hass else None, day["status"])

    @property
    def native_value(self) -> str | None:
        day = self._day()
        return self._text(day) if day else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        plan, day, nxt = self.plan, self._day(), self._day(1)
        if plan is None or day is None or nxt is None:
            return {}
        off = school_off_for(self.coordinator.data, plan["timetable"])
        attrs: dict[str, Any] = {
            "plan": plan["name"],
            "status": day["status"],
            "start": day["start"],
            "end": day["end"],
            "lessons": day["lessons"],
            "pack_today": pack_on(plan, off, day["date"]),
            "pack_tomorrow": pack_on(plan, off, nxt["date"]),
            "tomorrow": {
                **{k: nxt[k] for k in ("status", "start", "end", "lessons")},
                **{k: nxt[k] for k in ("changed", "note", "exams", "care") if k in nxt},
                "text": self._text(nxt),
            },
            # Class tests of the next two weeks, and whether today is a day to learn for one.
            "exams_ahead": exams_ahead(plan, day["date"]),
        }
        # Care after school (reliable school or OGS): {"kind", "start", "end"}, or None on a day without.
        attrs["care"] = day.get("care")
        for key in ("week", "holiday", "away", "changed", "note", "exams"):
            if key in day:
                attrs[key] = day[key]
        if self.person_id is not None:
            attrs["person_entity"] = person_entity(self.coordinator.config_entry, self.person_id)
        return attrs


class OrgaiaWorkSensor(OrgaiaPlanEntity, SensorEntity):
    """A roster today: the shift or the working time, and the days ahead."""

    plan_type = "roster"
    _attr_translation_key = "work_today"
    _attr_icon = "mdi:briefcase-clock-outline"
    _unrecorded_attributes = frozenset({"spans", "shift", "code", "tomorrow", "next_days", "plan"})

    def _language(self) -> str | None:
        return self.hass.config.language if self.hass else None

    def __init__(self, coordinator: OrgaiaCoordinator, list_id: str) -> None:
        super().__init__(coordinator, list_id, "today")

    def _text(self, day: dict[str, Any]) -> str:
        if not day["spans"]:
            return day_label(self.hass.config.language if self.hass else None, STATUS_FREE)
        times = ", ".join(_span_text(s["start"], s["end"]) for s in day["spans"])
        if day.get("shift"):
            return f"{day['shift']} {times}"
        if day.get("standby"):
            return f"{labels_for(self._language()).standby} {times}"
        return times

    def _days(self) -> list[dict[str, Any]]:
        plan = self.plan
        if plan is None:
            return []
        first = today()
        days = [work_day(plan, add_days(first, n)) for n in range(WORK_AHEAD_DAYS)]
        return [{**d, "text": self._text(d)} for d in days]

    @property
    def native_value(self) -> str | None:
        days = self._days()
        return days[0]["text"][:255] if days else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        plan, days = self.plan, self._days()
        if plan is None or not days:
            return {}
        day = days[0]
        attrs: dict[str, Any] = {
            "plan": plan["name"],
            "status": day["status"],
            "spans": day["spans"],
            "start": day["spans"][0]["start"] if day["spans"] else None,
            "end": day["spans"][-1]["end"] if day["spans"] else None,
            "tomorrow": days[1],
            "next_days": days,
            "standby": bool(day.get("standby")),
            # Working hours of this week, Monday to Sunday, on call left out.
            "hours_week": round(
                work_minutes(plan["roster"], week_start(days[0]["date"]), add_days(week_start(days[0]["date"]), 6))
                / 60,
                2,
            ),
        }
        for key in ("shift", "code"):
            if key in day:
                attrs[key] = day[key]
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
    _unrecorded_attributes = frozenset({"title", "location"})

    def __init__(self, coordinator: OrgaiaCoordinator, person_id: str | None = None) -> None:
        super().__init__(coordinator, "next_event", person_id)

    def _next(self):
        now = local_now()
        upcoming = [
            e
            for e in events_between(self.coordinator.data, now, now + timedelta(days=LOOKAHEAD_DAYS), self.person_id)
            # What is ticked off already is not what comes next.
            if e.start_datetime_local >= now and not e.summary.startswith(DONE_MARK)
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
        attrs: dict[str, Any] = {
            "title": ev.summary,
            "location": ev.location,
            "all_day": ev.all_day,
            "end": ev.end_datetime_local.isoformat(),
        }
        if self.person_id is not None:
            attrs["person_entity"] = person_entity(self.coordinator.config_entry, self.person_id)
        return attrs


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


class OrgaiaTodaySensor(OrgaiaEntity, SensorEntity):
    """The day in short ("2 Termine, 3 Aufgaben"), and in sentences for a loudspeaker in ``speech``."""

    _attr_translation_key = "today"
    _attr_icon = "mdi:calendar-today-outline"
    # Titles and names stay out of the recorder's database; only the short count is kept.
    _unrecorded_attributes = frozenset({"speech", "appointments", "due", "overdue", "school", "work", "shopping"})

    def __init__(self, coordinator: OrgaiaCoordinator, person_id: str | None = None) -> None:
        super().__init__(coordinator, "today", person_id)

    def _report(self) -> dict[str, Any]:
        now = local_now()
        return day_report(self.coordinator.data, today(), today(), minute_of_day(now), self.person_id)

    def _language(self) -> str | None:
        return self.hass.config.language if self.hass else None

    @property
    def native_value(self) -> str:
        return short_text(self._report(), self._language())[:255]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        r = self._report()
        attrs: dict[str, Any] = {
            "speech": speech(r, self._language(), today()),
            **{k: r[k] for k in ("appointments", "due", "overdue", "school", "work", "shopping")},
        }
        if self.person_id is not None:
            attrs["person_entity"] = person_entity(self.coordinator.config_entry, self.person_id)
        return attrs


class OrgaiaOpenDrivesSensor(OrgaiaEntity, SensorEntity):
    """Appointments of the next 7 days that need taking there or picking up, and nobody does it yet."""

    _attr_translation_key = "open_drives"
    _attr_icon = "mdi:car-clock"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _unrecorded_attributes = frozenset({"drives"})

    def __init__(self, coordinator: OrgaiaCoordinator) -> None:
        super().__init__(coordinator, "open_drives")

    def _drives(self) -> list[dict[str, Any]]:
        view = self.coordinator.data
        first = today()
        return [
            {
                "title": d.occ.item["title"],
                "item": d.occ.item["id"],
                "date": d.occ.start[:10],
                "start": d.occ.start[11:16] if len(d.occ.start) > 10 else None,
                "missing": d.missing,
                "persons": view.names(d.occ.assignees),
            }
            for d in drives_between(view, first, add_days(first, 6), open_only=True)
        ]

    @property
    def native_value(self) -> int:
        return len(self._drives())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"drives": self._drives()[:MAX_TITLES]}


class OrgaiaOccasionsSensor(OrgaiaEntity, SensorEntity):
    """Birthdays and anniversaries of the next 30 days; ``today`` holds those of today with the age."""

    _attr_translation_key = "occasions"
    _attr_icon = "mdi:cake-variant-outline"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _unrecorded_attributes = frozenset({"today", "upcoming"})

    def __init__(self, coordinator: OrgaiaCoordinator) -> None:
        super().__init__(coordinator, "occasions")

    def _upcoming(self) -> list[dict[str, Any]]:
        day = today()
        first = to_date(day)
        return [
            {
                "title": o["item"]["title"],
                "text": with_occasion(o["item"], o["date"])["title"],
                "kind": o["item"]["occasion"],
                "date": o["date"],
                "years": o["years"],
                "in_days": (to_date(o["date"]) - first).days,
            }
            for o in upcoming_occasions(self.coordinator.data, day, OCCASION_DAYS)
        ]

    @property
    def native_value(self) -> int:
        return len(self._upcoming())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        upcoming = self._upcoming()
        return {
            "today": [o["text"] for o in upcoming if o["in_days"] == 0],
            "upcoming": upcoming[:MAX_TITLES],
        }
