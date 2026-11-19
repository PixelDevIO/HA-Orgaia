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
    exam: str = "Klassenarbeit {subject}"
    learn: str = "Für {subject} lernen"
    standby: str = "Bereitschaft"


LABELS = {
    "de": PlanLabels("{thing} einpacken", "Schule", "Arbeit", "Klassenarbeit {subject}", "Für {subject} lernen", "Bereitschaft"),
    "en": PlanLabels("Pack {thing}", "School", "Work", "{subject} test", "Study for {subject}", "On call"),
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


def lessons_on_day(tt: dict[str, Any], date: str) -> list[dict[str, Any]]:
    """The lessons of a day as they really are, with a single day that differs taken into account."""
    ex = next((d for d in tt.get("days") or [] if d["date"] == date), None)
    if ex and ex.get("free"):
        return []
    all_ = lessons_of(tt, weekday(date), week_of(tt, date))
    if not ex:
        return all_
    return [x for x in all_ if ex.get("from", 1) <= x["n"] <= ex.get("to", 99)]


def things_on_day(tt: dict[str, Any], date: str) -> dict[str, dict[str, Any]]:
    """What has to come along on a date, with a single day that differs taken into account."""
    ex = next((d for d in tt.get("days") or [] if d["date"] == date), None)
    wd = weekday(date)
    if not ex:
        return things_of(tt, wd, week_of(tt, date))
    out: dict[str, dict[str, Any]] = {}

    def add(name: str, lesson: str | None = None) -> None:
        key = thing_key(name)
        if not key:
            return
        cur = out.get(key) or {"name": name.strip(), "lessons": []}
        if lesson and lesson not in cur["lessons"]:
            cur["lessons"].append(lesson)
        out[key] = cur

    if not ex.get("free"):
        for lesson in lessons_on_day(tt, date):
            for thing in lesson["subject"]["things"]:
                add(thing, lesson["subject"]["name"])
        for thing in tt["dayThings"].get(wd, []):
            add(thing)
    for thing in ex.get("things") or []:
        add(thing)
    return out


def timetable_holds(tt: dict[str, Any], date: str) -> bool:
    """Whether the timetable holds on a date (a half-year has a first and a last day)."""
    return (not tt.get("validFrom") or date >= tt["validFrom"]) and (not tt.get("validUntil") or date <= tt["validUntil"])


def school_day_of(tt: dict[str, Any], date: str) -> dict[str, Any] | None:
    """The single day that differs on a date, if one was entered."""
    return next((d for d in tt.get("days") or [] if d["date"] == date), None)


def _start_from(base: str, step: int, start: str | None) -> str:
    """The first date of a series that starts at ``base`` every ``step`` weeks, moved on to begin at ``start``."""
    if not start or start <= base:
        return base
    weeks = math.ceil(days_between(week_start(base), week_start(start)) / 7 / step) * step
    moved = add_days(base, weeks * 7)
    return start if moved == week_start(start) else moved


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
    # A half-year: packing begins the day before its first school day and ends before the first one after it.
    valid_from, valid_until = tt.get("validFrom"), tt.get("validUntil")
    pack_from = add_days(valid_from, -_pack_back(tt, weekday(valid_from))) if valid_from else None
    after = add_days(valid_until, 1) if valid_until else None
    pack_until = add_days(after, -_pack_back(tt, weekday(after)) - 1) if after else None
    for pid, p in pack.items():
        week = "A" if pid.endswith("~A") else "B" if pid.endswith("~B") else None
        item: dict[str, Any] = {
            "id": pid,
            "listId": lst["id"],
            "kind": "task",
            "title": labels.pack.replace("{thing}", p["name"]),
            "assignees": list(who),
            "dueDate": _start_from(_series_base(tt, week), 2 if week else 1, pack_from),
        }
        if tt["packTime"]:
            item["dueTime"] = tt["packTime"]
            item["remind"] = 0
        item["repeat"] = {"freq": "week", "interval": 2 if week else 1, "days": sorted(p["days"])}
        if pack_until:
            item["repeat"]["until"] = pack_until
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
        base = _start_from(_series_base(tt, s["week"]), 2 if s["week"] else 1, valid_from)
        s["days"].sort()
        repeat: dict[str, Any] = {"freq": "week", "interval": 2 if s["week"] else 1, "days": list(s["days"])}
        if valid_until:
            repeat["until"] = valid_until
        items.append(
            {
                "id": sid,
                "listId": lst["id"],
                "kind": "event",
                "title": labels.school,
                "assignees": list(who),
                "start": f"{base}T{s['start']}",
                "end": f"{base}T{s['end']}",
                "repeat": repeat,
                "fromTimetable": lst["id"],
            }
        )

    skips: list[tuple[str, str]] = []
    first, last = add_days(today, -14), add_days(today, 400)

    # Single days that differ: what is no longer needed is not packed, what is new is packed once, and
    # the school day keeps only its periods. A day in the holidays or outside the half-year stays as it is.
    for ex in tt.get("days") or []:
        d = ex["date"]
        if d < first or d > last or holiday_on(off, d) or not timetable_holds(tt, d):
            continue
        wd = weekday(d)
        week = week_of(tt, d)
        usual = things_of(tt, wd, week)
        now = things_on_day(tt, d)
        pack_on_date = add_days(d, -_pack_back(tt, wd))
        for key in usual:
            if key not in now:
                skips.append((pack_id_on(key, wd, week)[0], pack_on_date))
        for key, t in now.items():
            if key in usual:
                continue
            once: dict[str, Any] = {
                "id": f"{TT_PREFIX}{lst['id']}~o{_fnv(key)}~{d}",
                "listId": lst["id"],
                "kind": "task",
                "title": labels.pack.replace("{thing}", t["name"]),
                "assignees": list(who),
                "dueDate": pack_on_date,
            }
            if tt["packTime"]:
                once["dueTime"] = tt["packTime"]
                once["remind"] = 0
            # One date only, but as a series, so that it is ticked off like every other packing task.
            once["repeat"] = {"freq": "day", "interval": 1, "until": pack_on_date}
            once["fromTimetable"] = lst["id"]
            if t["lessons"]:
                once["forLessons"] = t["lessons"]
            items.append(once)
        if tt["noCal"]:
            continue
        for sid, s in school.items():
            if wd in s["days"] and s["week"] == (week if tt["abStart"] else None):
                skips.append((sid, d))
        ls = lessons_on_day(tt, d)
        if not ls:
            continue
        changed: dict[str, Any] = {
            "id": f"{TT_PREFIX}{lst['id']}~x{d}",
            "listId": lst["id"],
            "kind": "event",
            "title": labels.school,
            "assignees": list(who),
            "start": f"{d}T{ls[0]['start']}",
            "end": f"{d}T{max(x['end'] for x in ls)}",
            "fromTimetable": lst["id"],
        }
        if ex.get("note"):
            changed["note"] = ex["note"]
        items.append(changed)

    # Class tests: in the calendar at the subject's lesson that day, and a task to learn on the days before.
    for e in tt.get("exams") or []:
        if e["date"] < first or e["date"] > last:
            continue
        subject = next((x for x in tt["subjects"] if x["id"] == e["subjectId"]), None)
        if not subject:
            continue
        lesson = next((x for x in lessons_on_day(tt, e["date"]) if x["subject"]["id"] == subject["id"]), None)
        test: dict[str, Any] = {
            "id": f"{TT_PREFIX}{lst['id']}~e{e['id']}",
            "listId": lst["id"],
            "kind": "event",
            "title": labels.exam.replace("{subject}", subject["name"]),
            "assignees": list(who),
            "start": f"{e['date']}T{lesson['start']}" if lesson else e["date"],
            "end": f"{e['date']}T{lesson['end']}" if lesson else e["date"],
        }
        if not lesson:
            test["allDay"] = True
        if e.get("note"):
            test["note"] = e["note"]
        test["fromTimetable"] = lst["id"]
        items.append(test)
        if e["learn"] > 0:
            items.append(
                {
                    "id": f"{TT_PREFIX}{lst['id']}~l{e['id']}",
                    "listId": lst["id"],
                    "kind": "task",
                    "title": labels.learn.replace("{subject}", subject["name"]),
                    "assignees": list(who),
                    "dueDate": add_days(e["date"], -e["learn"]),
                    "repeat": {"freq": "day", "interval": 1, "until": add_days(e["date"], -1)},
                    "fromTimetable": lst["id"],
                    "forLessons": [subject["name"]],
                }
            )

    # Holidays: no school, nothing to pack for it. Only around today.
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
            standby = bool(shift and shift.get("standby"))
            item = {
                **base(),
                "id": f"{RS_PREFIX}{lst['id']}~d{date}" + (f"~{i}" if i else ""),
                "title": labels.standby
                if standby and r["busyOnly"]
                else labels.work
                if r["busyOnly"] or not shift
                else shift["name"],
            }
            if shift and not r["busyOnly"]:
                item["shiftCode"] = shift["code"]
            if standby:
                item["standby"] = True
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
    # All timetables first, then all rosters, as the app adds them.
    for lst in view.lists:
        if lst["type"] == "timetable" and lst.get("timetable"):
            items, sk = timetable_items(lst, off, labels, today)
            extra.extend(items)
            skips.extend(sk)
    for lst in view.lists:
        if lst["type"] == "roster" and lst.get("roster"):
            items, sk = roster_items(lst, labels, today)
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


# --- One day of a plan, for sensors and dashboards ---------------------------------------------

STATUS_SCHOOL = "school"
STATUS_WORK = "work"
STATUS_FREE = "free"
STATUS_HOLIDAY = "holiday"
STATUS_STANDBY = "standby"


def holiday_on(off: list[dict[str, Any]], date: str) -> dict[str, Any] | None:
    """The school holiday a day lies in, if any."""
    return next((o for o in off if o["from"] <= date <= o["to"]), None)


def next_holiday(off: list[dict[str, Any]], date: str) -> dict[str, Any] | None:
    """The first school holiday that begins after a day."""
    return next((o for o in off if o["from"] > date), None)


def school_day(lst: dict[str, Any], off: list[dict[str, Any]], date: str) -> dict[str, Any]:
    """A timetable on one day: the lessons with their subjects, from when to when, or why there is no school.

    A single day that differs (free, shorter) counts, and a half-year timetable outside its dates has none.
    """
    tt = lst["timetable"]
    week = week_of(tt, date)
    holiday = holiday_on(off, date)
    holds = timetable_holds(tt, date)
    ex = school_day_of(tt, date)
    lessons = [] if holiday or not holds else lessons_on_day(tt, date)
    out: dict[str, Any] = {
        "date": date,
        "status": STATUS_HOLIDAY if holiday else STATUS_SCHOOL if lessons else STATUS_FREE,
        "start": None,
        "end": None,
        "lessons": [
            {
                "period": lesson["n"],
                "start": lesson["start"],
                "end": lesson["end"],
                "subject": lesson["subject"]["name"],
                **({"room": lesson["subject"]["room"]} if lesson["subject"].get("room") else {}),
            }
            for lesson in lessons
        ],
    }
    if week:
        out["week"] = week
    if holiday and holiday["name"]:
        out["holiday"] = holiday["name"]
    if ex and not holiday and holds:
        out["changed"] = True
        if ex.get("note"):
            out["note"] = ex["note"]
    exams = [
        e for e in tt.get("exams") or [] if e["date"] == date and any(x["id"] == e["subjectId"] for x in tt["subjects"])
    ]
    if exams:
        out["exams"] = [
            {
                "subject": next(x["name"] for x in tt["subjects"] if x["id"] == e["subjectId"]),
                **({"note": e["note"]} if e.get("note") else {}),
            }
            for e in exams
        ]
    if lessons:
        out["start"] = lessons[0]["start"]
        out["end"] = max(lesson["end"] for lesson in lessons)
    return out


def exams_ahead(lst: dict[str, Any], date: str, days: int = 14) -> list[dict[str, Any]]:
    """Class tests from a date on, for a few days: date, subject, note, and whether to learn today."""
    tt = lst["timetable"]
    last = add_days(date, days)
    out = []
    for e in tt.get("exams") or []:
        if e["date"] < date or e["date"] > last:
            continue
        subject = next((x for x in tt["subjects"] if x["id"] == e["subjectId"]), None)
        if not subject:
            continue
        out.append(
            {
                "date": e["date"],
                "subject": subject["name"],
                **({"note": e["note"]} if e.get("note") else {}),
                "learn_today": e["learn"] > 0 and add_days(e["date"], -e["learn"]) <= date < e["date"],
            }
        )
    return out


def pack_on(lst: dict[str, Any], off: list[dict[str, Any]], date: str) -> list[str]:
    """What is packed on a day, for the school day after it (Monday's things on Sunday, or on Friday)."""
    tt = lst["timetable"]
    out: dict[str, str] = {}
    for ahead in (1, 3):
        target = add_days(date, ahead)
        wd = weekday(target)
        if _pack_back(tt, wd) != ahead or holiday_on(off, target) or not timetable_holds(tt, target):
            continue
        for key, thing in things_on_day(tt, target).items():
            out.setdefault(key, thing["name"])
    return list(out.values())


def work_day(lst: dict[str, Any], date: str) -> dict[str, Any]:
    """A roster on one day: the working times, and the shift when one was entered."""
    r = lst["roster"]
    day = work_on(r, date)
    shift = day.get("shift")
    spans = [{"start": s["start"], "end": s["end"], "overnight": s["end"] <= s["start"]} for s in day["spans"]]
    standby = bool(spans and shift and shift.get("standby"))
    out: dict[str, Any] = {
        "date": date,
        "status": STATUS_STANDBY if standby else STATUS_WORK if spans else STATUS_FREE,
        "spans": spans,
    }
    if shift and not r["busyOnly"]:
        out["shift"] = shift["name"]
        out["code"] = shift["code"]
    if standby:
        out["standby"] = True
    return out


def span_minutes(span: dict[str, str]) -> int:
    d = _minutes(span["end"]) - _minutes(span["start"])
    return d if d > 0 else d + 24 * 60


def work_minutes(r: dict[str, Any], start: str, end: str) -> int:
    """Minutes of work from ``start`` to ``end`` (both included), on call left out."""
    total = 0
    d = start
    guard = 0
    while d <= end and guard < 400:
        day = work_on(r, d)
        if not (day.get("shift") or {}).get("standby"):
            total += sum(span_minutes(x) for x in day["spans"])
        d = add_days(d, 1)
        guard += 1
    return total


def _minutes(clock: str) -> int:
    return int(clock[:2]) * 60 + int(clock[3:5])


def at_school(lst: dict[str, Any], off: list[dict[str, Any]], date: str, minute: int) -> str | None:
    """When school ends today, while it is on; None otherwise."""
    day = school_day(lst, off, date)
    if day["start"] and _minutes(day["start"]) <= minute < _minutes(day["end"]):
        return day["end"]
    return None


def _on_span(lst: dict[str, Any], date: str, minute: int, standby: bool) -> str | None:
    before = work_day(lst, add_days(date, -1))
    if bool(before.get("standby")) == standby:
        for span in before["spans"]:
            if span["overnight"] and minute < _minutes(span["end"]):
                return span["end"]
    day = work_day(lst, date)
    if bool(day.get("standby")) == standby:
        for span in day["spans"]:
            if _minutes(span["start"]) <= minute and (span["overnight"] or minute < _minutes(span["end"])):
                return span["end"]
    return None


def at_work(lst: dict[str, Any], date: str, minute: int) -> str | None:
    """When work ends, while it is on (a night shift of yesterday counts until its end); None otherwise.

    On call is not work: it has :func:`on_call`.
    """
    return _on_span(lst, date, minute, False)


def on_call(lst: dict[str, Any], date: str, minute: int) -> str | None:
    """When being on call ends, while it is on; None otherwise."""
    return _on_span(lst, date, minute, True)
