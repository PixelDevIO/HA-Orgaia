"""Calendars: the group's, and one per person with what they take part in.

Appointments and tasks with a time slot, repetitions and exceptions included.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import OrgaiaConfigEntry, OrgaiaCoordinator
from .entity import OrgaiaEntity, active_person_ids, track_dynamic
from .protocol.agenda import DEFAULT_DURATION, Occurrence
from .protocol.recur import add_days, date_of
from .protocol.view import SpaceView
from .summary import calendar_occurrences
from .util import local_now, to_date, to_datetime

# How far ahead the calendar looks for the next appointment.
LOOKAHEAD_DAYS = 60


async def async_setup_entry(
    hass: HomeAssistant, entry: OrgaiaConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([OrgaiaCalendar(coordinator)])
    track_dynamic(
        hass,
        entry,
        active_person_ids,
        lambda person_id: [OrgaiaCalendar(coordinator, person_id)],
        async_add_entities,
        "calendar",
    )


def to_event(view: SpaceView, occ: Occurrence) -> CalendarEvent:
    item = occ.item
    uid = f"{item['id']}|{occ.occ_date}" if occ.occ_date else item["id"]
    parts = []
    if occ.assignees:
        parts.append("👤 " + ", ".join(view.names(occ.assignees)))
    if item.get("note"):
        parts.append(item["note"])
    description = "\n\n".join(parts) or None
    location = item.get("location") if isinstance(item.get("location"), str) else None
    if item.get("allDay"):
        first = date_of(occ.start)
        last = date_of(occ.end) if occ.end else first
        return CalendarEvent(
            start=to_date(first),
            end=to_date(add_days(max(first, last), 1)),
            summary=item["title"],
            description=description,
            location=location,
            uid=uid,
        )
    start = to_datetime(occ.start)
    end = to_datetime(occ.end) if occ.end else start + timedelta(minutes=DEFAULT_DURATION)
    if end <= start:
        end = start + timedelta(minutes=15)
    return CalendarEvent(
        start=start, end=end, summary=item["title"], description=description, location=location, uid=uid
    )


def events_between(view: SpaceView, start: datetime, end: datetime, person: str | None = None) -> list[CalendarEvent]:
    first, last = start.date().isoformat(), end.date().isoformat()
    out = []
    for occ in calendar_occurrences(view, add_days(first, -1), last, person):
        ev = to_event(view, occ)
        if ev.end_datetime_local > start and ev.start_datetime_local < end:
            out.append(ev)
    return out


class OrgaiaCalendar(OrgaiaEntity, CalendarEntity):
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

    def _update_next(self) -> None:
        now = local_now()
        events = events_between(self.coordinator.data, now, now + timedelta(days=LOOKAHEAD_DAYS), self.person_id)
        self._event = events[0] if events else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return events_between(self.coordinator.data, start_date, end_date, self.person_id)
