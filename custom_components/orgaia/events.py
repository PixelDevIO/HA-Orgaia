"""Turns changes of the group into ``orgaia_event`` events for automations.

Events come from comparing two views of the group, not from single changes, so nothing fires twice and
nothing fires for what was already there when Home Assistant started.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import logging
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval

from .const import COMPLETED_DAYS, DOMAIN, EVENT_ORGAIA
from .coordinator import OrgaiaConfigEntry
from .entity import person_entity, space_key
from .protocol.recur import add_days
from .protocol.view import SpaceView
from .summary import TodoEntry, calendar_occurrences, overdue_entries, todo_entries
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

EVENT_TYPES = [
    TASK_CREATED,
    TASK_ASSIGNED,
    TASK_COMPLETED,
    TASK_REOPENED,
    TASK_OVERDUE,
    EVENT_CREATED,
    EVENT_CHANGED,
    EVENT_STARTING,
]

TICK = timedelta(minutes=1)
LATE_START = timedelta(minutes=5)


@dataclass(frozen=True)
class _Task:
    item_id: str
    done: bool
    assignees: tuple[str, ...]


def _appointment(item: dict[str, Any]) -> str:
    """What makes an appointment "changed": time, place, title, repetition and who takes part."""
    keys = ("title", "start", "end", "allDay", "location", "repeat", "assignees")
    return json.dumps({k: item.get(k) for k in keys}, sort_keys=True, default=str)


class EventTracker:
    """Remembers the last view and fires an event for every difference that matters to automations."""

    def __init__(self, hass: HomeAssistant, entry: OrgaiaConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.coordinator = entry.runtime_data
        self._tasks: dict[str, _Task] = {}
        self._entries: dict[str, TodoEntry] = {}
        self._items: set[str] = set()
        self._appointments: dict[str, str] = {}
        self._overdue: set[str] = set()
        self._persons: set[str] = set()
        self._day = ""
        self._last_tick = local_now()

    @callback
    def start(self) -> CALLBACK_TYPE:
        self._remember(self.coordinator.data)
        self._overdue = self._overdue_now(self.coordinator.data)
        self._day = local_now().date().isoformat()
        unsub_update = self.coordinator.async_add_listener(self._on_update)
        unsub_tick = async_track_time_interval(self.hass, self._on_tick, TICK)

        def stop() -> None:
            unsub_update()
            unsub_tick()

        return stop

    # --- Snapshots ---------------------------------------------------------------------------

    def _remember(self, view: SpaceView) -> None:
        today = local_now().date().isoformat()
        entries = todo_entries(view, today, COMPLETED_DAYS)
        self._entries = {e.uid: e for e in entries}
        self._tasks = {e.uid: _Task(e.item_id, e.done, tuple(e.assignees)) for e in entries}
        self._items = {i["id"] for i in view.items}
        self._appointments = {i["id"]: _appointment(i) for i in view.items if i["kind"] == "event"}
        self._persons = {p["id"] for p in view.active_persons()}

    def _overdue_now(self, view: SpaceView) -> set[str]:
        now = local_now()
        return {e.uid for e in overdue_entries(view, now.date().isoformat(), minute_of_day(now))}

    # --- Changes of the group ----------------------------------------------------------------

    @callback
    def _on_update(self) -> None:
        if not self.coordinator.last_update_success:
            return
        view = self.coordinator.data
        old_tasks, old_items, old_appointments, old_persons = (
            self._tasks,
            self._items,
            self._appointments,
            self._persons,
        )
        self._remember(view)
        for uid, task in self._tasks.items():
            entry = self._entries[uid]
            before = old_tasks.get(uid)
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
            if item_id not in old_items:
                self._fire_appointment(view, EVENT_CREATED, item)
            elif old_appointments.get(item_id) not in (None, fingerprint):
                self._fire_appointment(view, EVENT_CHANGED, item)
        self._check_overdue(view)

    # --- Time passing ------------------------------------------------------------------------

    @callback
    def _on_tick(self, now: datetime) -> None:
        now = local_now()
        view = self.coordinator.data
        # An appointment that began long ago (Home Assistant was busy or the clock jumped) is not "starting".
        start, self._last_tick = max(self._last_tick, now - LATE_START), now
        today = now.date().isoformat()
        for occ in calendar_occurrences(view, add_days(today, -1), today):
            if occ.item["kind"] != "event":
                continue
            begins = to_datetime(occ.start)
            if start < begins <= now:
                self._fire_appointment(
                    view,
                    EVENT_STARTING,
                    occ.item,
                    occ_date=occ.occ_date,
                    start=occ.start,
                    end=occ.end,
                    assignees=occ.assignees,
                )
        changed = self._check_overdue(view)
        if today != self._day:
            self._day = today
            changed = True
        if changed:
            # Counts and lists depend on the time of day too.
            self.coordinator.async_update_listeners()

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
        self._fire(data)

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
