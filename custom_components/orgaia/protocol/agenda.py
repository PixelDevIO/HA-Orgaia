"""Days, deadlines and occurrences, as Orgaia's packages/core/src/agenda.ts computes them."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .recur import add_days, date_of, days_between, occurrence_dates, rotation_assignee, time_of, to_min
from .view import SpaceView, occ_id

DEFAULT_DURATION = 60


def with_overrides(item: dict[str, Any], occ: dict[str, Any] | None) -> dict[str, Any]:
    """The entry as it reads on one occurrence: title, place and note may differ from the series."""
    if not occ or all(occ.get(k) is None for k in ("title", "location", "note")):
        return item
    out = dict(item)
    for k in ("title", "location", "note"):
        if occ.get(k) is not None:
            out[k] = occ[k]
    return out


def span_of(item: dict[str, Any]) -> int:
    """Number of days an entry reaches beyond its first day."""
    start, end = item.get("start"), item.get("end")
    if not (isinstance(start, str) and start and isinstance(end, str) and end):
        return 0
    return max(0, days_between(date_of(start), date_of(end)))


@dataclass
class Occurrence:
    """One time an entry happens, with what this one time changes."""

    item: dict[str, Any]
    occ_date: str | None
    start: str
    end: str | None
    assignees: list[str]
    done: bool
    skip: bool


def resolve_occurrence(view: SpaceView, item: dict[str, Any], occ_date: str | None) -> Occurrence:
    occ = view.occs.get(occ_id(item["id"], occ_date)) if occ_date else None
    assignees = list(item.get("assignees") or [])
    if occ_date:
        turn = rotation_assignee(item, occ_date)
        if turn:
            assignees = [turn]
    if occ and isinstance(occ.get("assignees"), list):
        assignees = list(occ["assignees"])
    poll = item.get("poll") if isinstance(item.get("poll"), dict) else None
    chosen = poll.get("chosen") if poll and poll.get("chosen") and poll.get("chosen") != "cancel" else None
    rsvps = item.get("rsvps") or {}
    occ_rsvps = (occ or {}).get("rsvps") or {}

    def says(p: str) -> Any:
        r = occ_rsvps.get(p) or rsvps.get(p)
        if isinstance(r, dict):
            return r.get("a")
        votes = item.get("votes") or {}
        return (votes.get(p) or {}).get(chosen) if chosen else None

    if item.get("rsvps") or (occ or {}).get("rsvps") or chosen:
        assignees = [p for p in assignees if says(p) != "no"]
    start_time = time_of(item["start"]) if item.get("start") else "00:00"
    end_time = time_of(item["end"]) if item.get("end") else None
    span = span_of(item)
    d = occ_date or (date_of(item["start"]) if item.get("start") else "")
    start = (occ or {}).get("start") or f"{d}T{start_time}"
    end = (occ or {}).get("end") or (f"{add_days(d, span) if span else d}T{end_time}" if end_time else None)
    done = bool((occ or {}).get("done")) if occ_date else bool(item.get("done"))
    return Occurrence(with_overrides(item, occ), occ_date, start, end, assignees, done, bool((occ or {}).get("skip")))


@dataclass
class Block:
    """Something with a time slot on one day: a planned task or an appointment."""

    item: dict[str, Any]
    kind: str
    date: str
    occ_date: str | None
    start: int
    end: int
    all_day: bool
    persons: list[str]
    done: bool


def _push_blocks(out: list[Block], view: SpaceView, item: dict[str, Any], occ_date: str | None, day: str) -> None:
    r = resolve_occurrence(view, item, occ_date)
    if r.skip:
        return
    whole = bool(item.get("allDay"))
    first = date_of(r.start)
    last = date_of(r.end) if r.end else first
    to_midnight = not whole and bool(r.end) and last > first and to_min(time_of(r.end or "")) == 0
    if to_midnight:
        last = add_days(last, -1)
    if last < first:
        last = first
    if day < first or day > last:
        return
    multi = last > first
    start = 0 if whole or day > first else to_min(time_of(r.start))
    if whole or day < last or to_midnight:
        end = 24 * 60
    else:
        end = to_min(time_of(r.end)) if r.end else start + DEFAULT_DURATION
    if end <= start:
        end = min(24 * 60, start + 15)
    all_day = whole or (multi and start == 0 and end == 24 * 60)
    out.append(Block(r.item, item["kind"], day, occ_date, start, end, all_day, r.assignees, r.done))


def blocks_for_day(view: SpaceView, day: str) -> list[Block]:
    out: list[Block] = []
    for item in view.items:
        if not item.get("start"):
            continue
        if not item.get("repeat"):
            _push_blocks(out, view, item, None, day)
            continue
        seen: set[str] = set()
        for d in occurrence_dates(item, add_days(day, -span_of(item)), day):
            seen.add(d)
            _push_blocks(out, view, item, d, day)
        for occ in view.occs.values():
            if occ["itemId"] == item["id"] and occ["date"] not in seen and occ.get("start"):
                _push_blocks(out, view, item, occ["date"], day)
    out.sort(key=lambda b: (b.start, b.end))
    return out


def is_overdue(item: dict[str, Any], today: str, minute: int) -> bool:
    if item["kind"] != "task" or item.get("done") or item.get("repeat") or not item.get("dueDate"):
        return False
    if item["dueDate"] < today:
        return True
    return item["dueDate"] == today and bool(item.get("dueTime")) and to_min(item["dueTime"]) < minute


def current_occurrence(view: SpaceView, item: dict[str, Any], today: str) -> dict[str, Any] | None:
    """The occurrence of a repeating entry a plain list shows and ticks off: the latest up to today, else the next."""
    repeat = item.get("repeat")
    if not repeat:
        return None
    try:
        step = max(1, int(repeat.get("interval") or 1))
    except (TypeError, ValueError):
        step = 1
    span = {"day": 1, "week": 7, "month": 31, "year": 366}.get(repeat.get("freq"), 366) * step

    def kept(d: str) -> bool:
        return not (view.occs.get(occ_id(item["id"], d)) or {}).get("skip")

    past = [d for d in occurrence_dates(item, add_days(today, -span * 6), today) if kept(d)]
    if past:
        d = past[-1]
    else:
        upcoming = [d for d in occurrence_dates(item, today, add_days(today, span * 6)) if kept(d)]
        if not upcoming:
            return None
        d = upcoming[0]
    return {"date": d, "done": bool((view.occs.get(occ_id(item["id"], d)) or {}).get("done"))}


def open_counts(view: SpaceView, today: str) -> dict[str, int]:
    """Open tasks per person: unfinished one-off tasks plus today's unfinished repeating ones with a slot."""
    counts: dict[str, int] = {}

    def add(ids: list[str]) -> None:
        for p in ids:
            counts[p] = counts.get(p, 0) + 1

    for item in view.items:
        if item["kind"] != "task" or item.get("repeat") or item.get("done"):
            continue
        if view.list_by_id.get(item["listId"], {}).get("type") == "shopping":
            continue
        add(item.get("assignees") or [])
    for b in blocks_for_day(view, today):
        if b.kind == "task" and b.occ_date and not b.done:
            add(b.persons)
    return counts


def occurrences_between(view: SpaceView, item: dict[str, Any], start: str, end: str) -> list[Occurrence]:
    """Every time an entry with a slot happens between two dates (inclusive).

    Exceptions are applied and skipped occurrences left out.
    """
    if not item.get("start"):
        return []
    if not item.get("repeat"):
        r = resolve_occurrence(view, item, None)
        return [] if r.skip else [r]
    span = span_of(item)
    dates = set(occurrence_dates(item, add_days(start, -span), end))
    for occ in view.occs.values():
        if occ["itemId"] == item["id"] and occ.get("start"):
            dates.add(occ["date"])
    out = []
    for d in sorted(dates):
        r = resolve_occurrence(view, item, d)
        if not r.skip:
            out.append(r)
    return out
