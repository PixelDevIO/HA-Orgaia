"""Turns changes of the group into ``orgaia_event`` events for automations.

Events come from comparing two views of the group, not from single changes, so nothing fires twice and
nothing fires for what was already there when Home Assistant started.

After a short restart (up to ``CATCH_UP``) the group as it was when Home Assistant stopped is the first
view: what changed meanwhile and appointments that began meanwhile fire once Home Assistant runs, with
``late: true``. After a longer break nothing is caught up, so no automation acts on old news.

What changed while the service could not be reached for more than a quarter of an hour fires with
``late: true`` as well, once it is read.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
import json
import logging
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.start import async_at_started

from .const import COMPLETED_DAYS, DOMAIN, EVENT_ORGAIA
from .coordinator import OrgaiaConfigEntry
from .entity import person_entity, space_key
from .protocol.feeds import is_feed_item
from .protocol.plans import is_plan_item
from .protocol.recur import add_days
from .protocol.shopping import Trip, trip_of
from .protocol.view import SpaceView
from .summary import TodoEntry, calendar_occurrences, drives_between, overdue_entries, shopping_trips, todo_entries
from .util import local_now, minute_of_day, to_datetime

_LOGGER = logging.getLogger(__name__)

TASK_CREATED = "task_created"
TASK_ASSIGNED = "task_assigned"
TASK_COMPLETED = "task_completed"
TASK_REOPENED = "task_reopened"
TASK_OVERDUE = "task_overdue"
EVENT_CREATED = "event_created"
EVENT_CHANGED = "event_changed"
EVENT_STARTING = "event_starting"
SHOPPING_RELEASED = "shopping_released"
SHOPPING_TAKEN = "shopping_taken"
SHOPPING_DONE = "shopping_done"
DRIVE_NEEDED = "drive_needed"
DRIVE_TAKEN = "drive_taken"
RSVP_CHANGED = "rsvp_changed"
POLL_DECIDED = "poll_decided"

EVENT_TYPES = [
    TASK_CREATED,
    TASK_ASSIGNED,
    TASK_COMPLETED,
    TASK_REOPENED,
    TASK_OVERDUE,
    EVENT_CREATED,
    EVENT_CHANGED,
    EVENT_STARTING,
    SHOPPING_RELEASED,
    SHOPPING_TAKEN,
    SHOPPING_DONE,
    DRIVE_NEEDED,
    DRIVE_TAKEN,
    RSVP_CHANGED,
    POLL_DECIDED,
]

# How far ahead drives are watched for "nobody drives yet".
DRIVE_DAYS = 14

TICK = timedelta(minutes=1)
LATE_START = timedelta(minutes=5)
# How long Home Assistant may have been away for what happened meanwhile to still fire.
CATCH_UP = timedelta(minutes=15)


@dataclass(frozen=True)
class _Task:
    item_id: str
    done: bool
    assignees: tuple[str, ...]


def _appointment(item: dict[str, Any]) -> str:
    """What makes an appointment "changed": time, place, title, repetition and who takes part."""
    keys = ("title", "start", "end", "allDay", "location", "repeat", "assignees")
    return json.dumps({k: item.get(k) for k in keys}, sort_keys=True, default=str)


def _trip_mark(lst: dict[str, Any], trip: Trip) -> tuple[Any, Any, Any]:
    return ((trip.ready or {}).get("at"), trip.shopper, (lst.get("lastTrip") or {}).get("at"))


def _round(item: dict[str, Any]) -> tuple[Any, Any] | None:
    """When and by whom a task that comes back was last done."""
    mark = item.get("lastDone")
    return (mark.get("at"), mark.get("by")) if isinstance(mark, dict) else None


class EventTracker:
    """Remembers the last view and fires an event for every difference that matters to automations."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: OrgaiaConfigEntry,
        before: SpaceView | None = None,
        stopped: datetime | None = None,
    ) -> None:
        self.hass = hass
        # The group as it was when Home Assistant stopped, if that was only a short while ago.
        self._before = before if before is not None and stopped is not None else None
        self._stopped = stopped
        self._late = False
        self.entry = entry
        self.coordinator = entry.runtime_data
        self._tasks: dict[str, _Task] = {}
        self._entries: dict[str, TodoEntry] = {}
        self._items: set[str] = set()
        self._appointments: dict[str, str] = {}
        self._overdue: set[str] = set()
        # Tasks that come back never stay done: each round leaves only `lastDone` behind.
        self._rounds: dict[str, Any] = {}
        self._persons: set[str] = set()
        # Per shopping list: when it was released, who shops, when the last trip ended.
        self._trips: dict[str, tuple[Any, Any, Any]] = {}
        # Per appointment, day and way (there, back): who drives.
        self._drives: dict[tuple[str, str, str], str | None] = {}
        # Per appointment, day (or "" for the series) and person: their answer.
        self._rsvps: dict[tuple[str, str, str], str] = {}
        # Per appointment with a vote: the option that was fixed.
        self._polls: dict[str, Any] = {}
        self._day = ""
        self._last_tick = local_now()

    @callback
    def start(self) -> CALLBACK_TYPE:
        now = local_now()
        catch_up = self._before is not None and self._stopped is not None and now - self._stopped <= CATCH_UP
        self._remember(self._before if catch_up else self.coordinator.data)
        self._overdue = self._overdue_now(self._before if catch_up else self.coordinator.data)
        self._day = now.date().isoformat()
        self._before = None
        unsub_update = self.coordinator.async_add_listener(self._on_update)
        unsub_tick = async_track_time_interval(self.hass, self._on_tick, TICK)
        unsub_started = async_at_started(self.hass, self._catch_up) if catch_up else None

        def stop() -> None:
            unsub_update()
            unsub_tick()
            if unsub_started:
                unsub_started()

        return stop

    @callback
    def _catch_up(self, _hass: HomeAssistant) -> None:
        """Once automations are loaded: what changed and began while Home Assistant was away."""
        self._late = True
        try:
            self._on_update()
            if self._stopped is not None:
                self._fire_starting(local_now(), self._stopped)
        finally:
            self._late = False

    # --- Snapshots ---------------------------------------------------------------------------

    def _remember(self, view: SpaceView) -> None:
        today = local_now().date().isoformat()
        entries = todo_entries(view, today, COMPLETED_DAYS)
        self._entries = {e.uid: e for e in entries}
        self._tasks = {e.uid: _Task(e.item_id, e.done, tuple(e.assignees)) for e in entries}
        self._items = {i["id"] for i in view.items}
        self._rounds = {i["id"]: _round(i) for i in view.items if i.get("again") and i["kind"] == "task"}
        self._appointments = {i["id"]: _appointment(i) for i in view.items if i["kind"] == "event"}
        self._persons = {p["id"] for p in view.active_persons()}
        self._trips = {lst["id"]: _trip_mark(lst, trip) for lst, trip in shopping_trips(view)}
        self._drives = {}
        for d in drives_between(view, today, add_days(today, DRIVE_DAYS - 1)):
            day = d.occ.start[:10]
            if d.need_to:
                self._drives[(d.occ.item["id"], day, "to")] = d.driver_to
            if d.need_from:
                self._drives[(d.occ.item["id"], day, "from")] = d.driver_from
        self._rsvps = {}
        for i in view.items:
            if i["kind"] != "event":
                continue
            for pid, r in (i.get("rsvps") or {}).items():
                if isinstance(r, dict) and isinstance(r.get("a"), str):
                    self._rsvps[(i["id"], "", pid)] = r["a"]
        for o in view.occs.values():
            for pid, r in (o.get("rsvps") or {}).items():
                if isinstance(r, dict) and isinstance(r.get("a"), str):
                    self._rsvps[(o["itemId"], o["date"], pid)] = r["a"]
        self._polls = {
            i["id"]: i["poll"].get("chosen")
            for i in view.items
            if isinstance(i.get("poll"), dict) and i["kind"] == "event"
        }

    def _overdue_now(self, view: SpaceView) -> set[str]:
        now = local_now()
        return {e.uid for e in overdue_entries(view, now.date().isoformat(), minute_of_day(now))}

    # --- Changes of the group ----------------------------------------------------------------

    @callback
    def _on_update(self) -> None:
        if not self.coordinator.last_update_success:
            return
        view = self.coordinator.data
        if self.coordinator.late and not self._late:
            # The service was out of reach for a while: what changed meanwhile is old news.
            self._late = True
            try:
                self._on_update()
            finally:
                self._late = False
            return
        old_tasks, old_entries, old_items, old_appointments, old_persons, old_rounds, old_trips = (
            self._tasks,
            self._entries,
            self._items,
            self._appointments,
            self._persons,
            self._rounds,
            self._trips,
        )
        old_drives, old_rsvps, old_polls = self._drives, self._rsvps, self._polls
        self._remember(view)
        self._check_trips(view, old_trips)
        self._check_drives(view, old_drives, old_items)
        self._check_rsvps(view, old_rsvps, old_persons)
        self._check_polls(view, old_polls)
        self._check_rounds(view, old_rounds, old_entries)
        for uid, task in self._tasks.items():
            entry = self._entries[uid]
            before = old_tasks.get(uid)
            if is_plan_item(view.item_by_id.get(task.item_id) or {}):
                # Packing tasks come and go with the timetable; only ticking them off is news.
                if before is not None and task.done != before.done:
                    self._fire_task(view, TASK_COMPLETED if task.done else TASK_REOPENED, entry)
                continue
            if task.item_id not in old_items:
                self._fire_task(view, TASK_CREATED, entry)
                continue
            if before is None:
                # The next occurrence of a repeating task, or an old tick back in view: nothing new.
                continue
            if task.done != before.done:
                self._fire_task(view, TASK_COMPLETED if task.done else TASK_REOPENED, entry)
            # Someone who just joined gets every "everyone" task at once; that is not an assignment.
            added = [p for p in task.assignees if p not in before.assignees and p in old_persons]
            if added and not task.done:
                self._fire_task(view, TASK_ASSIGNED, entry, assigned=added)
        for item_id, fingerprint in self._appointments.items():
            item = view.item_by_id[item_id]
            if is_plan_item(item) or is_feed_item(item):
                # School days, working time and subscribed calendars follow their source, nobody "made" them.
                continue
            if item_id not in old_items:
                self._fire_appointment(view, EVENT_CREATED, item)
            elif old_appointments.get(item_id) not in (None, fingerprint):
                self._fire_appointment(view, EVENT_CHANGED, item)
        self._check_overdue(view)

    def _check_trips(self, view: SpaceView, old: dict[str, tuple[Any, Any, Any]]) -> None:
        """A shopping list was released, somebody took it over, or the shopping is done."""
        for lst, trip in shopping_trips(view):
            before = old.get(lst["id"])
            if before is None:
                # A list that is new here says nothing about what happened to it before.
                continue
            released, shopper, finished = _trip_mark(lst, trip)
            if finished and finished != before[2]:
                self._fire_trip(view, SHOPPING_DONE, lst, trip)
            if released and released != before[0]:
                self._fire_trip(view, SHOPPING_RELEASED, lst, trip)
            if shopper and (shopper != before[1] or released != before[0]):
                self._fire_trip(view, SHOPPING_TAKEN, lst, trip)

    def _check_drives(self, view: SpaceView, old: dict[tuple[str, str, str], str | None], old_items: set[str]) -> None:
        """Somebody took over a drive, or a drive now needs somebody (new, or the driver stepped back)."""
        for key, driver in self._drives.items():
            item_id, day, way = key
            if item_id not in old_items:
                # A new appointment that needs a drive nobody does yet.
                if driver is None:
                    self._fire_drive(view, DRIVE_NEEDED, item_id, day, way, None)
                continue
            if key not in old:
                # The day moved into the watched days, or the appointment now needs a drive.
                if driver is None and day != add_days(local_now().date().isoformat(), DRIVE_DAYS - 1):
                    self._fire_drive(view, DRIVE_NEEDED, item_id, day, way, None)
                continue
            before = old[key]
            if driver == before:
                continue
            if driver is None:
                self._fire_drive(view, DRIVE_NEEDED, item_id, day, way, before)
            else:
                self._fire_drive(view, DRIVE_TAKEN, item_id, day, way, before)

    def _check_rsvps(self, view: SpaceView, old: dict[tuple[str, str, str], str], old_persons: set[str]) -> None:
        """Somebody said yes, maybe or no to an appointment."""
        for key, answer in self._rsvps.items():
            if old.get(key) == answer:
                continue
            item_id, day, pid = key
            item = view.item_by_id.get(item_id)
            if item is None:
                continue
            names, entities = self._people(view, [pid])
            assignees, assignee_entities = self._people(view, item.get("assignees") or [])
            answers = {p: a for (i, d, p), a in self._rsvps.items() if i == item_id and d in ("", day)}
            self._fire(
                {
                    **self._base(RSVP_CHANGED),
                    "item_id": item_id,
                    "date": day or None,
                    "title": item["title"],
                    "start": item.get("start"),
                    "answer": answer,
                    "before": old.get(key),
                    "person": names[0] if names else None,
                    "person_entity": entities[0] if entities else None,
                    "assignees": assignees,
                    "assignee_entities": assignee_entities,
                    # Whether everybody who takes part has answered now.
                    "all_answered": all(p in answers for p in item.get("assignees") or []),
                }
            )

    def _check_polls(self, view: SpaceView, old: dict[str, Any]) -> None:
        """A time found by vote was fixed (or the vote was called off)."""
        for item_id, chosen in self._polls.items():
            if not chosen or old.get(item_id) == chosen or item_id not in old:
                continue
            item = view.item_by_id[item_id]
            option = next(
                (o for o in (item["poll"].get("options") or []) if isinstance(o, dict) and o.get("id") == chosen), None
            )
            names, entities = self._people(view, item.get("assignees") or [])
            self._fire(
                {
                    **self._base(POLL_DECIDED),
                    "item_id": item_id,
                    "title": item["title"],
                    "cancelled": chosen == "cancel",
                    "start": (option or {}).get("start") or item.get("start"),
                    "end": (option or {}).get("end") or item.get("end"),
                    "location": item.get("location"),
                    "assignees": names,
                    "assignee_entities": entities,
                }
            )

    def _check_rounds(self, view: SpaceView, old_rounds: dict[str, Any], old_entries: dict[str, TodoEntry]) -> None:
        """A task that comes back was done (a new `lastDone`) or that was taken back (an older one)."""
        for item_id, mark in self._rounds.items():
            if item_id not in old_rounds or old_rounds[item_id] == mark:
                continue
            item = view.item_by_id[item_id]
            before = old_entries.get(item_id)
            if mark and (not old_rounds[item_id] or mark[0] > old_rounds[item_id][0]):
                # Describe the round that was finished: its due date and who had it, not the next one.
                base = before or next((e for e in self._entries.values() if e.item_id == item_id), None)
                if base is None:
                    continue
                entry = replace(base, done=True, done_at=mark[0], done_by=mark[1])
                self._fire_task(view, TASK_COMPLETED, entry)
            else:
                entry = self._entries.get(item_id) or before
                if entry is not None and not item.get("done"):
                    self._fire_task(view, TASK_REOPENED, entry)

    # --- Time passing ------------------------------------------------------------------------

    @callback
    def _on_tick(self, now: datetime) -> None:
        now = local_now()
        view = self.coordinator.data
        # An appointment that began long ago (Home Assistant was busy or the clock jumped) is not "starting".
        since = max(self._last_tick, now - LATE_START)
        # "Next appointment" and the calendars' on/off follow the clock, not only changes of the group.
        changed = self._boundary_passed(view, since, now)
        self._fire_starting(now, since)
        today = now.date().isoformat()
        if today != self._day:
            self._day = today
            # Packing tasks, school days and shifts are worked out around today.
            self.coordinator.data = view = self.coordinator.build_view()
            changed = True
        changed = self._check_overdue(view) or changed
        if changed:
            # Counts and lists depend on the time of day too.
            self.coordinator.async_update_listeners()

    def _boundary_passed(self, view: SpaceView, since: datetime, now: datetime) -> bool:
        """Whether anything in the calendar began or ended after ``since`` and up to ``now``."""
        for occ in calendar_occurrences(view, add_days(since.date().isoformat(), -1), now.date().isoformat()):
            if since < to_datetime(occ.start) <= now:
                return True
            if occ.end and not occ.item.get("allDay") and since < to_datetime(occ.end) <= now:
                return True
        return False

    def _fire_starting(self, now: datetime, since: datetime) -> None:
        """Appointments that began after ``since`` and up to ``now``."""
        self._last_tick = now
        view = self.coordinator.data
        today = now.date().isoformat()
        for occ in calendar_occurrences(view, add_days(since.date().isoformat(), -1), today):
            if occ.item["kind"] != "event":
                continue
            begins = to_datetime(occ.start)
            if since < begins <= now:
                self._fire_appointment(
                    view,
                    EVENT_STARTING,
                    occ.item,
                    occ_date=occ.occ_date,
                    start=occ.start,
                    end=occ.end,
                    assignees=occ.assignees,
                )

    def _check_overdue(self, view: SpaceView) -> bool:
        late = self._overdue_now(view)
        new = late - self._overdue
        changed = late != self._overdue
        self._overdue = late
        if new:
            now = local_now()
            for entry in overdue_entries(view, now.date().isoformat(), minute_of_day(now)):
                if entry.uid in new:
                    self._fire_task(view, TASK_OVERDUE, entry)
        return changed

    # --- Firing ------------------------------------------------------------------------------

    def _base(self, event_type: str) -> dict[str, Any]:
        device = dr.async_get(self.hass).async_get_device(identifiers={(DOMAIN, space_key(self.entry))})
        return {
            "type": event_type,
            "device_id": device.id if device else None,
            "config_entry_id": self.entry.entry_id,
            "group": self.entry.title,
            **({"late": True} if self._late else {}),
        }

    def _people(self, view: SpaceView, ids: list[str]) -> tuple[list[str], list[str]]:
        names = view.names(ids)
        entities = [e for p in ids if (e := person_entity(self.entry, p))]
        return names, entities

    def _fire_task(self, view: SpaceView, event_type: str, e: TodoEntry, assigned: list[str] | None = None) -> None:
        lst = view.list_by_id.get(e.list_id) or {}
        names, entities = self._people(view, e.assignees)
        data = {
            **self._base(event_type),
            "item_id": e.item_id,
            "date": e.occ_date,
            "title": e.title,
            "list": lst.get("name"),
            "list_type": lst.get("type"),
            "due": e.due,
            "assignees": names,
            "assignee_entities": entities,
        }
        if event_type == TASK_COMPLETED and e.done_by:
            by = view.person_by_id.get(e.done_by)
            data["completed_by"] = by["name"] if by else None
            data["completed_by_entity"] = person_entity(self.entry, e.done_by)
        if assigned is not None:
            data["assigned"], data["assigned_entities"] = self._people(view, assigned)
        if lst.get("type") == "shopping":
            # Whether somebody is out shopping right now, so an article added late can reach them.
            trip = trip_of(view, lst)
            data["shopping_state"] = trip.state
            data["added_late"] = e.late
            shopper = view.person_by_id.get(trip.shopper or "")
            data["shopper"] = shopper["name"] if shopper else None
            data["shopper_entity"] = person_entity(self.entry, trip.shopper) if trip.shopper else None
        self._fire(data)

    def _fire_trip(self, view: SpaceView, event_type: str, lst: dict[str, Any], trip: Trip) -> None:
        ready = trip.ready or {}
        last = lst.get("lastTrip") or {}
        asked, asked_entities = self._people(view, ready.get("for") or [])
        data: dict[str, Any] = {
            **self._base(event_type),
            "list": lst["name"],
            "list_id": lst["id"],
            "list_type": "shopping",
            "open": trip.open,
        }
        if event_type == SHOPPING_DONE:
            by = view.person_by_id.get(last.get("by") or "")
            data.update(
                {
                    "bought": last.get("n", 0),
                    "left": last.get("left", 0),
                    "not_got": last.get("missed", 0),
                    "released_by": (view.person_by_id.get(last.get("from") or "") or {}).get("name"),
                    "released_by_entity": person_entity(self.entry, last["from"]) if last.get("from") else None,
                    "shopper": by["name"] if by else None,
                    "shopper_entity": person_entity(self.entry, last.get("by") or ""),
                }
            )
        else:
            by = view.person_by_id.get(ready.get("by") or "")
            shopper = view.person_by_id.get(trip.shopper or "")
            data.update(
                {
                    "released_by": by["name"] if by else None,
                    "due": ready.get("due"),
                    "note": ready.get("note"),
                    "assignees": asked,
                    "assignee_entities": asked_entities,
                    "shopper": shopper["name"] if shopper else None,
                    "shopper_entity": person_entity(self.entry, trip.shopper) if trip.shopper else None,
                }
            )
        self._fire(data)

    def _fire_drive(
        self, view: SpaceView, event_type: str, item_id: str, day: str, way: str, before: str | None
    ) -> None:
        item = view.item_by_id.get(item_id)
        if item is None:
            return
        driver = self._drives.get((item_id, day, way))
        names, entities = self._people(view, item.get("assignees") or [])
        by, by_entity = self._people(view, [driver] if driver else [])
        was, was_entity = self._people(view, [before] if before else [])
        self._fire(
            {
                **self._base(event_type),
                "item_id": item_id,
                "date": day,
                "title": item["title"],
                "start": item.get("start"),
                "location": item.get("location"),
                # "to": taking there, "from": picking up.
                "way": way,
                "driver": by[0] if by else None,
                "driver_entity": by_entity[0] if by_entity else None,
                "previous_driver": was[0] if was else None,
                "previous_driver_entity": was_entity[0] if was_entity else None,
                "assignees": names,
                "assignee_entities": entities,
            }
        )

    def _fire_appointment(
        self,
        view: SpaceView,
        event_type: str,
        item: dict[str, Any],
        occ_date: str | None = None,
        start: str | None = None,
        end: str | None = None,
        assignees: list[str] | None = None,
    ) -> None:
        names, entities = self._people(view, assignees if assignees is not None else item["assignees"])
        lst = view.list_by_id.get(item["listId"]) or {}
        self._fire(
            {
                **self._base(event_type),
                "item_id": item["id"],
                "date": occ_date,
                "title": item["title"],
                "list": lst.get("name"),
                "start": start or item.get("start"),
                "end": end if start else item.get("end"),
                "all_day": bool(item.get("allDay")),
                "location": item.get("location"),
                "repeats": bool(item.get("repeat")),
                "assignees": names,
                "assignee_entities": entities,
            }
        )

    def _fire(self, data: dict[str, Any]) -> None:
        _LOGGER.debug("Orgaia event %s", data["type"])
        self.hass.bus.async_fire(EVENT_ORGAIA, data)
