"""What Home Assistant shows of a group, worked out from its view. Free of Home Assistant, so it is easy to test."""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from typing import Any

from .protocol.agenda import Occurrence, current_occurrence, is_overdue, occurrences_between, resolve_occurrence
from .protocol.recur import add_days, date_of, occurrence_dates, parse_ymd, to_min
from .protocol.view import SpaceView, occ_id


@dataclass
class TodoEntry:
    """One line of a to-do list: a one-off task, or the current occurrence of a repeating one."""

    uid: str
    item_id: str
    list_id: str
    occ_date: str | None
    title: str
    done: bool
    done_at: Any
    done_by: str | None
    due: str | None
    note: str | None
    assignees: list[str]
    persons: list[str]
    subtasks: list[tuple[str, bool]] = field(default_factory=list)


# Lists whose tasks belong to people: task lists, and timetables with their packing tasks.
TASK_LISTS = ("tasks", "timetable")
# Lists that become to-do lists. Feeds and rosters only hold appointments.
TODO_LISTS = ("tasks", "shopping", "timetable")


def todo_lists(view: SpaceView) -> list[dict[str, Any]]:
    """Lists that become to-do lists: task and shopping lists and timetables, not feeds or rosters."""
    return [lst for lst in view.lists if lst["type"] in TODO_LISTS]


def _repeat_due_today(view: SpaceView, item: dict[str, Any], today: str) -> list[Occurrence]:
    """Today's occurrence of a repeating task that has a deadline but no time slot, if it has one."""
    out = []
    for d in occurrence_dates(item, today, today):
        r = resolve_occurrence(view, item, d)
        if not r.skip:
            out.append(r)
    return out


def _deadline_passed(item: dict[str, Any], minute: int) -> bool:
    return bool(item.get("dueTime")) and to_min(item["dueTime"]) < minute


def _due(item: dict[str, Any]) -> str | None:
    if item.get("dueDate"):
        return item["dueDate"] + (f"T{item['dueTime']}" if item.get("dueTime") else "")
    return item.get("start") or None


def _done_mark(view: SpaceView, item: dict[str, Any], occ_date: str | None) -> dict[str, Any] | None:
    mark = (view.occs.get(occ_id(item["id"], occ_date)) or {}).get("done") if occ_date else item.get("done")
    return mark if isinstance(mark, dict) else None


def _entry(view: SpaceView, item: dict[str, Any], today: str) -> TodoEntry | None:
    subs = [(s["title"], s["done"]) for s in view.subs_by_item.get(item["id"], [])]
    if item.get("repeat"):
        if item.get("fromTimetable"):
            # Packing is about today, as on the app's Today page: a day that was missed is not owed later.
            cur = {"date": today} if _repeat_due_today(view, item, today) else None
        else:
            cur = current_occurrence(view, item, today)
        if cur is None:
            return None
        r = resolve_occurrence(view, item, cur["date"])
        mark = _done_mark(view, item, cur["date"])
        return TodoEntry(
            uid=f"{item['id']}|{cur['date']}",
            item_id=item["id"],
            list_id=item["listId"],
            occ_date=cur["date"],
            title=r.item["title"],
            done=r.done,
            done_at=(mark or {}).get("at"),
            done_by=(mark or {}).get("by"),
            due=r.start if item.get("start") else cur["date"] + (f"T{item['dueTime']}" if item.get("dueTime") else ""),
            note=r.item.get("note"),
            assignees=list(r.assignees),
            persons=view.names(r.assignees),
            subtasks=subs,
        )
    mark = _done_mark(view, item, None)
    return TodoEntry(
        uid=item["id"],
        item_id=item["id"],
        list_id=item["listId"],
        occ_date=None,
        title=item["title"],
        done=bool(item.get("done")),
        done_at=(mark or {}).get("at"),
        done_by=(mark or {}).get("by"),
        due=_due(item),
        note=item.get("note"),
        assignees=list(item["assignees"]),
        persons=view.names(item["assignees"]),
        subtasks=subs,
    )


def todo_entries(
    view: SpaceView,
    today: str,
    keep_done_days: int,
    list_id: str | None = None,
    person: str | None = None,
) -> list[TodoEntry]:
    """Tasks of one list, or of one person across all task lists. Old ticks drop out."""
    oldest_ms = _days_ago_ms(today, keep_done_days)
    out: list[TodoEntry] = []
    for item in view.items:
        if item["kind"] != "task":
            continue
        if list_id is not None and item["listId"] != list_id:
            continue
        ltype = view.list_by_id.get(item["listId"], {}).get("type")
        if ltype not in TODO_LISTS or (person is not None and ltype not in TASK_LISTS):
            continue
        entry = _entry(view, item, today)
        if entry is None or (person is not None and person not in entry.assignees):
            continue
        if (
            entry.done
            and entry.occ_date is None
            and isinstance(entry.done_at, (int, float))
            and entry.done_at < oldest_ms
        ):
            continue
        out.append(entry)
    return out


def _days_ago_ms(today: str, days: int) -> float:
    return calendar.timegm(parse_ymd(add_days(today, -days)).timetuple()) * 1000.0


def calendar_occurrences(view: SpaceView, start: str, end: str, person: str | None = None) -> list[Occurrence]:
    """Appointments and planned tasks between two dates (inclusive), sorted by start. Optionally of one person."""
    out: list[Occurrence] = []
    for item in view.items:
        if not item.get("start"):
            continue
        if view.list_by_id.get(item["listId"], {}).get("type") == "shopping":
            continue
        for occ in occurrences_between(view, item, start, end):
            if person is not None and person not in occ.assignees:
                continue
            last = date_of(occ.end) if occ.end else date_of(occ.start)
            if date_of(occ.start) <= end and last >= start:
                out.append(occ)
    out.sort(key=lambda o: o.start)
    return out


@dataclass
class Counts:
    open: list[str]
    due_today: list[str]
    overdue: list[str]
    shopping: list[str]
    # The open task due next: (due, title), due as YYYY-MM-DD or YYYY-MM-DDTHH:mm.
    next: tuple[str, str] | None = None


def _repeat_overdue(occ: Occurrence, today: str, minute: int) -> bool:
    """A repeating task's occurrence of today with a time that has passed and is not done."""
    return date_of(occ.start) == today and len(occ.start) > 10 and to_min(occ.start[11:16]) < minute


def counts(view: SpaceView, today: str, minute: int, person: str | None = None) -> Counts:
    """Open tasks (with today's repeating ones), what is due today, what is late, and the shopping still to buy.

    With a person, only their tasks count, and shopping is left out.
    """
    c = Counts([], [], [], [])
    upcoming: list[tuple[str, str]] = []
    for item in view.items:
        if item["kind"] != "task":
            continue
        ltype = view.list_by_id.get(item["listId"], {}).get("type")
        if item.get("repeat"):
            if ltype == "shopping":
                continue
            if not item.get("start"):
                for occ in _repeat_due_today(view, item, today):
                    if occ.done or (person is not None and person not in occ.assignees):
                        continue
                    title = occ.item["title"]
                    c.open.append(title)
                    c.due_today.append(title)
                    if _deadline_passed(item, minute):
                        c.overdue.append(title)
                    upcoming.append((today + (f"T{item['dueTime']}" if item.get("dueTime") else ""), title))
                continue
            for occ in occurrences_between(view, item, today, today):
                if occ.done or date_of(occ.start) != today:
                    continue
                if person is not None and person not in occ.assignees:
                    continue
                c.open.append(occ.item["title"])
                c.due_today.append(occ.item["title"])
                if _repeat_overdue(occ, today, minute):
                    c.overdue.append(occ.item["title"])
                upcoming.append((occ.start, occ.item["title"]))
            continue
        if item.get("done"):
            continue
        if ltype == "shopping":
            if person is None:
                c.shopping.append(item["title"])
            continue
        if person is not None and person not in item["assignees"]:
            continue
        c.open.append(item["title"])
        due = _due(item)
        if due:
            upcoming.append((due, item["title"]))
        if due and date_of(due) == today:
            c.due_today.append(item["title"])
        if is_overdue(item, today, minute):
            c.overdue.append(item["title"])
    if upcoming:
        c.next = min(upcoming)
    return c


def overdue_entries(view: SpaceView, today: str, minute: int) -> list[TodoEntry]:
    """Tasks that are late right now: one-off tasks past due, and today's repeating ones past their time."""
    out: list[TodoEntry] = []
    for item in view.items:
        if item["kind"] != "task" or view.list_by_id.get(item["listId"], {}).get("type") not in TASK_LISTS:
            continue
        if item.get("repeat"):
            if not item.get("start"):
                if _deadline_passed(item, minute) and any(not o.done for o in _repeat_due_today(view, item, today)):
                    entry = _entry(view, item, today)
                    if entry is not None:
                        out.append(entry)
                continue
            for occ in occurrences_between(view, item, today, today):
                if not occ.done and _repeat_overdue(occ, today, minute):
                    entry = _entry(view, item, today)
                    if entry is not None:
                        out.append(entry)
            continue
        if is_overdue(item, today, minute):
            entry = _entry(view, item, today)
            if entry is not None:
                out.append(entry)
    return out
