"""Timetables and rosters, as Orgaia's packages/core/src/timetable.ts, roster.ts and their readers.

A timetable is a list of one person whose lessons and subjects are fields of the list; a roster is a
list of one person with a fixed week or shifts entered day by day. Neither stores entries: every
device works out the same read-only repeating entries from them (what to pack the day before, the
school day, the working time). Ticks of packing tasks are stored as for any series.

Ids must match the app's to the character, so that ticks and exceptions stored by the app find their
entry here; the test vectors pin that down.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Any

from .plan_read import ANCHOR, ROSTER_AHEAD, ROSTER_BACK, RS_PREFIX, TT_PREFIX, _fnv, own_time, thing_key
from .recur import add_days, days_between, week_start, weekday
from .view import SpaceView, occ_id


@dataclass(frozen=True)
class PlanLabels:
    """Titles the app takes from the person's language: ``pack`` holds ``{thing}``."""

    pack: str = "{thing} einpacken"
    school: str = "Schule"
    work: str = "Arbeit"


LABELS = {
    "de": PlanLabels("{thing} einpacken", "Schule", "Arbeit"),
    "en": PlanLabels("Pack {thing}", "School", "Work"),
}


def labels_for(language: str | None) -> PlanLabels:
    return LABELS.get((language or "de").split("-")[0].lower(), LABELS["en"])


# --- Timetables -------------------------------------------------------------------------------


def _order(wd: int) -> int:
    """Position in a week that starts on Monday."""
    return (wd + 6) % 7


def _other(week: str) -> str:
    return "B" if week == "A" else "A"


def week_of(tt: dict[str, Any], date: str) -> str | None:
    if not tt["abStart"]:
        return None
    weeks = round(days_between(week_start(tt["abStart"]), week_start(date)) / 7)
    return "A" if weeks % 2 == 0 else "B"


def _cell_key(wd: int, n: int, week: str | None = None) -> str:
    return f"{wd}.{n}" + (f".{week}" if week else "")


def lesson_at(tt: dict[str, Any], wd: int, n: int, week: str | None) -> str | None:
    own = tt["cells"].get(_cell_key(wd, n, week)) if week and tt["abStart"] else None
    sid = own if own is not None else tt["cells"].get(_cell_key(wd, n))
    return sid if sid and any(s["id"] == sid for s in tt["subjects"]) else None


def lessons_of(tt: dict[str, Any], wd: int, week: str | None) -> list[dict[str, Any]]:
    out = []
    for i, p in enumerate(tt["periods"]):
        sid = lesson_at(tt, wd, i + 1, week)
        subject = next((s for s in tt["subjects"] if s["id"] == sid), None) if sid else None
        if subject:
            out.append({"n": i + 1, "start": p["start"], "end": p["end"], "subject": subject})
    return out


def things_of(tt: dict[str, Any], wd: int, week: str | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}

    def add(name: str, lesson: str | None = None) -> None:
        key = thing_key(name)
        if not key:
            return
        cur = out.get(key) or {"name": name.strip(), "lessons": []}
        if lesson and lesson not in cur["lessons"]:
            cur["lessons"].append(lesson)
        out[key] = cur

    for lesson in lessons_of(tt, wd, week):
        for thing in lesson["subject"]["things"]:
            add(thing, lesson["subject"]["name"])
    for thing in tt["dayThings"].get(wd, []):
        add(thing)
    return out


def _pack_back(tt: dict[str, Any], wd: int) -> int:
    return 3 if wd == 1 and tt["packMon"] == "fri" else 1


def _series_base(tt: dict[str, Any], week: str | None) -> str:
    if not week or not tt["abStart"]:
        return ANCHOR
    base = week_start(tt["abStart"])
    if week == "B":
        base = add_days(base, 7)
    ahead = days_between(ANCHOR, base)
    return add_days(base, -14 * math.ceil(ahead / 14)) if ahead > 0 else base


def timetable_items(
    lst: dict[str, Any], off: list[dict[str, Any]], labels: PlanLabels, today: str
) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    tt = lst["timetable"]
    who = [tt["personId"]] if tt["personId"] else []
    weeks: list[str | None] = ["A", "B"] if tt["abStart"] else [None]
    items: list[dict[str, Any]] = []

    def pack_id(key: str, week: str | None) -> str:
        return f"{TT_PREFIX}{lst['id']}~p{_fnv(key)}" + (f"~{week}" if week else "")

    def pack_id_on(key: str, wd: int, week: str | None) -> tuple[str, int]:
        pw = (wd - _pack_back(tt, wd) + 7) % 7
        pweek = _other(week) if week and _order(pw) > _order(wd) else week
        return pack_id(key, pweek), pw

    pack: dict[str, dict[str, Any]] = {}
    for week in weeks:
        for wd in range(7):
            for key, t in things_of(tt, wd, week).items():
                pid, pw = pack_id_on(key, wd, week)
                cur = pack.get(pid) or {"name": t["name"], "lessons": [], "days": set()}
                cur["days"].add(pw)
                for lesson in t["lessons"]:
                    if lesson not in cur["lessons"]:
                        cur["lessons"].append(lesson)
                pack[pid] = cur
    for pid, p in pack.items():
        week = "A" if pid.endswith("~A") else "B" if pid.endswith("~B") else None
        item: dict[str, Any] = {
            "id": pid,
            "listId": lst["id"],
            "kind": "task",
            "title": labels.pack.replace("{thing}", p["name"]),
            "assignees": list(who),
            "dueDate": _series_base(tt, week),
        }
        if tt["packTime"]:
            item["dueTime"] = tt["packTime"]
            item["remind"] = 0
        item["repeat"] = {"freq": "week", "interval": 2 if week else 1, "days": sorted(p["days"])}
        item["fromTimetable"] = lst["id"]
        item["forLessons"] = p["lessons"]
        items.append(item)

    school: dict[str, dict[str, Any]] = {}
    if not tt["noCal"]:
        for week in weeks:
            for wd in range(7):
                ls = lessons_of(tt, wd, week)
                if not ls:
                    continue
                start = ls[0]["start"]
                end = ls[0]["end"]
                for lesson in ls:
                    if lesson["end"] > end:
                        end = lesson["end"]
                sid = f"{TT_PREFIX}{lst['id']}~s{start.replace(':', '', 1)}{end.replace(':', '', 1)}" + (
                    f"~{week}" if week else ""
                )
                cur = school.get(sid) or {"start": start, "end": end, "week": week, "days": []}
                cur["days"].append(wd)
                school[sid] = cur
    for sid, s in school.items():
        base = _series_base(tt, s["week"])
        s["days"].sort()
        items.append(
            {
                "id": sid,
                "listId": lst["id"],
                "kind": "event",
                "title": labels.school,
                "assignees": list(who),
                "start": f"{base}T{s['start']}",
                "end": f"{base}T{s['end']}",
                "repeat": {"freq": "week", "interval": 2 if s["week"] else 1, "days": list(s["days"])},
                "fromTimetable": lst["id"],
            }
        )

    # Holidays: no school, nothing to pack for it. Only around today.
    skips: list[tuple[str, str]] = []
    first, last = add_days(today, -14), add_days(today, 400)
    for o in off:
        if o["to"] < first or o["from"] > last:
            continue
        d = first if o["from"] < first else o["from"]
        guard = 0
        while d <= o["to"] and d <= last and guard < 400:
            wd = weekday(d)
            week = week_of(tt, d)
            for key in things_of(tt, wd, week):
                skips.append((pack_id_on(key, wd, week)[0], add_days(d, -_pack_back(tt, wd))))
            for sid, s in school.items():
                if wd in s["days"]:
                    skips.append((sid, d))
            d = add_days(d, 1)
            guard += 1
    return items, skips


# --- Rosters ----------------------------------------------------------------------------------


def work_on(r: dict[str, Any], date: str) -> dict[str, Any]:
    value = r["days"].get(date)
    if value is not None:
        if value == "":
            return {"spans": [], "own": True}
        time = own_time(value)
        if time:
            return {"spans": [time], "own": True}
        shift = next((s for s in r["shifts"] if s["id"] == value), None)
        if shift:
            spans = [{"start": shift["start"], "end": shift["end"]}] if shift.get("start") and shift.get("end") else []
            return {"spans": spans, "shift": shift, "own": True}
        if r["mode"] == "shifts":
            return {"spans": [], "own": True}
    if r["mode"] != "week":
        return {"spans": [], "own": False}
    if any(o["from"] <= date <= o["to"] for o in r["off"]):
        return {"spans": [], "own": False}
    return {"spans": r["week"].get(weekday(date), []), "own": False}


def _end_date(date: str, span: dict[str, str]) -> str:
    return add_days(date, 1) if span["end"] <= span["start"] else date


def roster_items(
    lst: dict[str, Any], labels: PlanLabels, today: str
) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    r = lst["roster"]
    items: list[dict[str, Any]] = []
    skips: list[tuple[str, str]] = []
    if r["noCal"]:
        return items, skips
    who = [r["personId"]] if r["personId"] else []

    def base() -> dict[str, Any]:
        return {"listId": lst["id"], "kind": "event", "assignees": list(who), "fromRoster": lst["id"]}

    first, last = add_days(today, -ROSTER_BACK), add_days(today, ROSTER_AHEAD)
    series: dict[str, dict[str, Any]] = {}
    if r["mode"] == "week":
        for wd in range(7):
            for span in r["week"].get(wd, []):
                sid = f"{RS_PREFIX}{lst['id']}~w{span['start'].replace(':', '', 1)}{span['end'].replace(':', '', 1)}"
                cur = series.get(sid) or {"span": span, "days": []}
                cur["days"].append(wd)
                series[sid] = cur
        for sid, s in series.items():
            s["days"].sort()
            items.append(
                {
                    **base(),
                    "id": sid,
                    "title": labels.work,
                    "start": f"{ANCHOR}T{s['span']['start']}",
                    "end": f"{_end_date(ANCHOR, s['span'])}T{s['span']['end']}",
                    "repeat": {"freq": "week", "interval": 1, "days": list(s["days"])},
                }
            )
        replaced: dict[str, None] = {d: None for d in r["days"] if first <= d <= last}
        for o in r["off"]:
            if o["to"] < first or o["from"] > last:
                continue
            d = first if o["from"] < first else o["from"]
            guard = 0
            while d <= o["to"] and d <= last and guard < ROSTER_AHEAD + ROSTER_BACK:
                replaced[d] = None
                d = add_days(d, 1)
                guard += 1
        for date in replaced:
            wd = weekday(date)
            for sid, s in series.items():
                if wd in s["days"]:
                    skips.append((sid, date))

    for date in sorted(r["days"]):
        if date < first or date > last:
            continue
        day = work_on(r, date)
        shift = day.get("shift")
        for i, span in enumerate(day["spans"]):
            item = {
                **base(),
                "id": f"{RS_PREFIX}{lst['id']}~d{date}" + (f"~{i}" if i else ""),
                "title": labels.work if r["busyOnly"] or not shift else shift["name"],
            }
            if shift and not r["busyOnly"]:
                item["shiftCode"] = shift["code"]
            item["start"] = f"{date}T{span['start']}"
            item["end"] = f"{_end_date(date, span)}T{span['end']}"
            items.append(item)
    return items, skips


# --- Into the view ----------------------------------------------------------------------------


def is_plan_item(item: dict[str, Any]) -> bool:
    """Worked out from a timetable or roster: never created, changed or assigned by a person."""
    return bool(item.get("fromTimetable") or item.get("fromRoster"))


def with_plan_items(view: SpaceView, labels: PlanLabels, today: str) -> SpaceView:
    """A copy of the view that also holds what its timetables and rosters stand for."""
    extra: list[dict[str, Any]] = []
    skips: list[tuple[str, str]] = []
    off = view.meta.get("schoolOff") or []
    for lst in view.lists:
        if lst["type"] == "timetable" and lst.get("timetable"):
            items, sk = timetable_items(lst, off, labels, today)
        elif lst["type"] == "roster" and lst.get("roster"):
            items, sk = roster_items(lst, labels, today)
        else:
            continue
        extra.extend(items)
        skips.extend(sk)
    if not extra:
        return view
    occs = dict(view.occs)
    for item_id, date in skips:
        oid = occ_id(item_id, date)
        occs[oid] = {**(occs.get(oid) or {"id": oid, "itemId": item_id, "date": date}), "skip": True}
    for item in extra:
        item.setdefault("done", None)
    items = [*view.items, *extra]
    return replace(view, items=items, occs=occs, item_by_id={i["id"]: i for i in items})
