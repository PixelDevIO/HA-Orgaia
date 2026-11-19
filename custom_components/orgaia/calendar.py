"""Calendars: the group's, and one per person with what they take part in.

Appointments and tasks with a time slot, repetitions and exceptions included.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import time
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEntityFeature, CalendarEvent
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import OrgaiaConfigEntry, OrgaiaCoordinator
from .entity import OrgaiaPlanEntity, person_ids_for, plan_list_ids, track_dynamic
from .protocol import actions
from .protocol.actions import ActionError
from .protocol.agenda import DEFAULT_DURATION, Deadline, Occurrence
from .protocol.plans import school_day
from .protocol.recur import add_days, date_of
from .protocol.view import SpaceView, occ_id
from .summary import calendar_deadlines, calendar_occurrences
from .util import local_now, to_date, to_datetime
from .writing import Writer, fail

# How far ahead the calendar looks for the next appointment.
LOOKAHEAD_DAYS = 60

# The drives an appointment needs, as the app names them: who drives there and back, or nobody yet.
DRIVE_LABELS = {
    "de": ("Hinfahrt", "Rückfahrt", "noch offen"),
    "en": ("Drive there", "Drive back", "nobody yet"),
}


# What a deadline is called in the description, and a released shopping list in the calendar.
DEADLINE_LABELS = {
    "de": ("Frist", "Einkaufen"),
    "en": ("Due", "Shopping"),
}
DONE_MARK = "✓ "


def _lang(language: str | None) -> str:
    return (language or "de").split("-")[0].lower()


async def async_setup_entry(
    hass: HomeAssistant, entry: OrgaiaConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([OrgaiaCalendar(coordinator)])
    track_dynamic(
        hass,
        entry,
        person_ids_for(entry),
        lambda person_id: [OrgaiaCalendar(coordinator, person_id)],
        async_add_entities,
        "calendar",
    )
    track_dynamic(
        hass,
        entry,
        plan_list_ids("timetable"),
        lambda list_id: [OrgaiaTimetableCalendar(coordinator, list_id)],
        async_add_entities,
        "calendar",
    )


def drives(view: SpaceView, occ: Occurrence, language: str | None = None) -> str | None:
    """The line about drives, for appointments that need one there or back."""
    item = occ.item
    if item["kind"] != "event" or not (item.get("needTo") or item.get("needFrom")):
        return None
    there, back, nobody = DRIVE_LABELS.get(_lang(language), DRIVE_LABELS["en"])
    raw = view.occs.get(occ_id(item["id"], occ.occ_date)) if occ.occ_date else None
    out = []
    for need, field, label in (("needTo", "driveTo", there), ("needFrom", "driveFrom", back)):
        if not item.get(need):
            continue
        who = raw[field] if raw and field in raw else item.get(field)
        name = view.names([who]) if isinstance(who, str) else []
        out.append(f"{label}: {name[0] if name else nobody}")
    return "🚗 " + " · ".join(out)


def to_event(view: SpaceView, occ: Occurrence, language: str | None = None) -> CalendarEvent:
    item = occ.item
    uid = f"{item['id']}|{occ.occ_date}" if occ.occ_date else item["id"]
    parts = []
    if occ.assignees:
        parts.append("👤 " + ", ".join(view.names(occ.assignees)))
    if line := drives(view, occ, language):
        parts.append(line)
    if item.get("note"):
        parts.append(item["note"])
    description = "\n\n".join(parts) or None
    location = item.get("location") if isinstance(item.get("location"), str) else None
    # A planned task that is ticked off reads as done, not as still to do.
    summary = (DONE_MARK if item["kind"] == "task" and occ.done else "") + item["title"]
    if item.get("allDay"):
        first = date_of(occ.start)
        last = date_of(occ.end) if occ.end else first
        return CalendarEvent(
            start=to_date(first),
            end=to_date(add_days(max(first, last), 1)),
            summary=summary,
            description=description,
            location=location,
            uid=uid,
        )
    start = to_datetime(occ.start)
    end = to_datetime(occ.end) if occ.end else start + timedelta(minutes=DEFAULT_DURATION)
    if end <= start:
        end = start + timedelta(minutes=15)
    return CalendarEvent(start=start, end=end, summary=summary, description=description, location=location, uid=uid)


def deadline_event(view: SpaceView, d: Deadline, language: str | None = None) -> CalendarEvent:
    """A task on the day it is due: the whole day, or a quarter of an hour up to its time."""
    item = d.item
    due, shopping = DEADLINE_LABELS.get(_lang(language), DEADLINE_LABELS["en"])
    trip = bool(item.get("fromTrip"))
    parts = [f"🛒 {shopping}" if trip else f"⚑ {due}"]
    names = view.names(item.get("assignees") or [])
    if names:
        parts.append("👤 " + ", ".join(names))
    if item.get("note"):
        parts.append(item["note"])
    summary = (DONE_MARK if d.done else "") + (f"{shopping}: {item['title']}" if trip else item["title"])
    uid = f"due|{item['id']}|{d.date}"
    if d.time:
        end = to_datetime(f"{d.date}T{d.time}")
        return CalendarEvent(
            start=end - timedelta(minutes=15), end=end, summary=summary, description="\n\n".join(parts), uid=uid
        )
    return CalendarEvent(
        start=to_date(d.date),
        end=to_date(add_days(d.date, 1)),
        summary=summary,
        description="\n\n".join(parts),
        uid=uid,
    )


def events_between(
    view: SpaceView,
    start: datetime,
    end: datetime,
    person: str | None = None,
    language: str | None = None,
    with_deadlines: bool = False,
) -> list[CalendarEvent]:
    """What happens between two moments. With deadlines, also what is only due then."""
    first, last = start.date().isoformat(), end.date().isoformat()
    out = []
    for occ in calendar_occurrences(view, add_days(first, -1), last, person):
        ev = to_event(view, occ, language)
        if ev.end_datetime_local > start and ev.start_datetime_local < end:
            out.append(ev)
    if with_deadlines:
        for d in calendar_deadlines(view, add_days(first, -1), last, person):
            ev = deadline_event(view, d, language)
            if ev.end_datetime_local > start and ev.start_datetime_local < end:
                out.append(ev)
        out.sort(key=lambda e: e.start_datetime_local)
    return out


def _local(value: datetime) -> str:
    return dt_util.as_local(value).strftime("%Y-%m-%dT%H:%M")


class OrgaiaCalendar(Writer, CalendarEntity):
    """The group's appointments, or one person's. New ones can be made here when writing is allowed."""

    _attr_translation_key = "calendar"

    def __init__(self, coordinator: OrgaiaCoordinator, person_id: str | None = None) -> None:
        super().__init__(coordinator, "calendar", person_id)
        self._event: CalendarEvent | None = None
        self._update_next()

    @property
    def event(self) -> CalendarEvent | None:
        return self._event

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_next()
        super()._handle_coordinator_update()

    def _language(self) -> str | None:
        # Not yet known while the entity is being made.
        return self.hass.config.language if self.hass else None

    def _update_next(self) -> None:
        now = local_now()
        events = events_between(
            self.coordinator.data, now, now + timedelta(days=LOOKAHEAD_DAYS), self.person_id, self._language()
        )
        self._event = events[0] if events else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return events_between(
            self.coordinator.data, start_date, end_date, self.person_id, hass.config.language, with_deadlines=True
        )

    @property
    def supported_features(self) -> CalendarEntityFeature:
        return CalendarEntityFeature.CREATE_EVENT if self.coordinator.engine.can_write else CalendarEntityFeature(0)

    async def async_create_event(self, **kwargs: Any) -> None:
        """A new appointment, made in the name of the person the user is.

        On a person's calendar that person takes part; on the group's nobody in particular.
        """
        person = self._person()
        start, end = kwargs["dtstart"], kwargs.get("dtend")
        all_day = not isinstance(start, datetime)
        if all_day:
            first: date = start
            # Home Assistant's end of a whole day is the next morning; the app names the last day.
            last = end - timedelta(days=1) if isinstance(end, date) and not isinstance(end, datetime) else first
            begin, finish = first.isoformat(), max(first, last).isoformat()
        else:
            begin = _local(start)
            finish = _local(end) if isinstance(end, datetime) else None
        view = self.coordinator.data
        try:
            changes = actions.add_event(
                view,
                kwargs.get("summary") or "",
                begin,
                finish,
                all_day,
                person,
                int(time.time() * 1000),
                self.coordinator.engine.new_id,
                assignees=[self.person_id] if self.person_id else None,
                note=kwargs.get("description"),
                location=kwargs.get("location"),
                rrule=kwargs.get("rrule"),
            )
        except ActionError as err:
            raise fail(err.reason) from err
        await self._write(changes, person)


# A timetable's calendar never looks further than this in one go.
MAX_LESSON_DAYS = 400


def lessons_between(lst: dict, off: list[dict], start: datetime, end: datetime) -> list[CalendarEvent]:
    """Every lesson of a timetable between two moments, holidays left out."""
    out: list[CalendarEvent] = []
    day = add_days(start.date().isoformat(), -1)
    last = end.date().isoformat()
    for _ in range(MAX_LESSON_DAYS):
        if day > last:
            break
        for lesson in school_day(lst, off, day)["lessons"]:
            begins, ends = to_datetime(f"{day}T{lesson['start']}"), to_datetime(f"{day}T{lesson['end']}")
            if ends <= begins:
                ends = begins + timedelta(minutes=15)
            if ends > start and begins < end:
                out.append(
                    CalendarEvent(
                        start=begins,
                        end=ends,
                        summary=lesson["subject"],
                        description=f"{lesson['period']}.",
                        location=lesson.get("room"),
                        uid=f"{lst['id']}|{day}|{lesson['period']}",
                    )
                )
        day = add_days(day, 1)
    return out


class OrgaiaTimetableCalendar(OrgaiaPlanEntity, CalendarEntity):
    """A timetable lesson by lesson, for a day or week view on a dashboard."""

    plan_type = "timetable"
    _attr_translation_key = "timetable"
    _attr_icon = "mdi:timetable"

    def __init__(self, coordinator: OrgaiaCoordinator, list_id: str) -> None:
        super().__init__(coordinator, list_id, "lessons")

    def _between(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        plan = self.plan
        if plan is None:
            return []
        return lessons_between(plan, self.coordinator.data.meta.get("schoolOff") or [], start, end)

    @property
    def event(self) -> CalendarEvent | None:
        now = local_now()
        events = self._between(now, now + timedelta(days=14))
        return events[0] if events else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return self._between(start_date, end_date)
