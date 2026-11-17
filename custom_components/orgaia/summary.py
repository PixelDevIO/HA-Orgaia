"""What Home Assistant shows of a group, worked out from its view. Free of Home Assistant, so it is easy to test."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from typing import Any

from .protocol.agenda import Occurrence, current_occurrence, is_overdue, occurrences_between, resolve_occurrence
from .protocol.recur import add_days, date_of, parse_ymd
from .protocol.view import SpaceView


@dataclass
class TodoEntry:
    """One line of a to-do list."""

    uid: str
    title: str
    done: bool
    done_at: Any
    due: str | None
    note: str | None
    persons: list[str]
    subtasks: list[tuple[str, bool]]


def todo_lists(view: SpaceView) -> list[dict[str, Any]]:
    """Lists that become to-do lists: task and shopping lists, not feeds."""
    return [lst for lst in view.lists if lst["type"] in ("tasks", "shopping")]


def _due(item: dict[str, Any]) -> str | None:
    if item.get("dueDate"):
        return item["dueDate"] + (f"T{item['dueTime']}" if item.get("dueTime") else "")
    return item.get("start") or None


def todo_entries(view: SpaceView, list_id: str, today: str, keep_done_days: int) -> list[TodoEntry]:
    """The tasks of one list. Repeating ones show their current occurrence; old ticks drop out."""
    oldest_ms = None
    out: list[TodoEntry] = []
    for item in view.items:
        if item["listId"] != list_id or item["kind"] != "task":
            continue
        subs = [(s["title"], s["done"]) for s in view.subs_by_item.get(item["id"], [])]
        if item.get("repeat"):
            cur = current_occurrence(view, item, today)
            if cur is None:
                continue
            r = resolve_occurrence(view, item, cur["date"])
            done = r.done
            due = r.start if item.get("start") else cur["date"]
            out.append(
                TodoEntry(
                    f"{item['id']}|{cur['date']}",
                    r.item["title"],
                    done,
                    None,
                    due,
                    r.item.get("note"),
                    view.names(r.assignees),
                    subs,
                )
            )
            continue
        done_mark = item.get("done")
        if done_mark:
            at = done_mark.get("at") if isinstance(done_mark, dict) else None
            if oldest_ms is None:
                oldest_ms = _days_ago_ms(today, keep_done_days)
            if isinstance(at, (int, float)) and at < oldest_ms:
                continue
        else:
            at = None
        out.append(
            TodoEntry(
                item["id"],
                item["title"],
                bool(done_mark),
                at,
                _due(item),
                item.get("note"),
                view.names(item["assignees"]),
                subs,
            )
        )
    return out


def _days_ago_ms(today: str, days: int) -> float:
    return calendar.timegm(parse_ymd(add_days(today, -days)).timetuple()) * 1000.0


def calendar_occurrences(view: SpaceView, start: str, end: str) -> list[Occurrence]:
    """Appointments and planned tasks between two dates (inclusive), sorted by start."""
    out: list[Occurrence] = []
    for item in view.items:
        if not item.get("start"):
            continue
        if view.list_by_id.get(item["listId"], {}).get("type") == "shopping":
            continue
        for occ in occurrences_between(view, item, start, end):
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


def counts(view: SpaceView, today: str, minute: int) -> Counts:
    """Open tasks (with today's repeating ones), what is due today, what is late, and the shopping still to buy."""
    c = Counts([], [], [], [])
    for item in view.items:
        if item["kind"] != "task":
            continue
        ltype = view.list_by_id.get(item["listId"], {}).get("type")
        if item.get("repeat"):
            if ltype == "shopping":
                continue
            for occ in occurrences_between(view, item, today, today) if item.get("start") else []:
                if not occ.done and date_of(occ.start) == today:
                    c.open.append(occ.item["title"])
                    c.due_today.append(occ.item["title"])
            continue
        if item.get("done"):
            continue
        if ltype == "shopping":
            c.shopping.append(item["title"])
            continue
        c.open.append(item["title"])
        due = _due(item)
        if due and date_of(due) == today:
            c.due_today.append(item["title"])
        if is_overdue(item, today, minute):
            c.overdue.append(item["title"])
    return c
