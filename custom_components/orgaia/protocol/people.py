"""People's own dates, as Orgaia's packages/core computes them (absence.ts, occasion.ts, home-times.ts).

Days somebody is away, birthdays and anniversaries with the age, who is where on a day, and the hours a
child is out of school while every grown-up of the group works.
"""

from __future__ import annotations

from dataclasses import replace
import re
from typing import Any

from . import plans
from .recur import add_days, occurrence_dates, rotation_assignee
from .view import SpaceView, locale_key, occ_id

ABSENCE_ITEM_PREFIX = "aw~"
OCCASIONS = ("birthday", "anniversary")
_YMD = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# --- Absences ---------------------------------------------------------------------------------


def absence_on(person: dict[str, Any] | None, date: str) -> dict[str, Any] | None:
    """The absence of a person that covers a date, if any."""
    for a in (person or {}).get("absences") or []:
        if a["from"] <= date <= a["to"]:
            return a
    return None


def is_away(view: SpaceView, person_id: str, date: str) -> bool:
    return absence_on(view.person_by_id.get(person_id), date) is not None


def turn_of(view: SpaceView, item: dict[str, Any], date: str) -> str | None:
    """Whose turn a rotating task is on a date, passing over whoever is away."""
    if not any(p.get("absences") for p in view.persons):
        return rotation_assignee(item, date)
    return rotation_assignee(item, date, lambda p: is_away(view, p, date))


def away_people(view: SpaceView, date: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """People of the group who are away on a date, with their absence."""
    out = []
    for person in view.persons:
        if person["removed"]:
            continue
        absence = absence_on(person, date)
        if absence:
            out.append((person, absence))
    return out


def is_absence_item(item: dict[str, Any]) -> bool:
    return str(item.get("id", "")).startswith(ABSENCE_ITEM_PREFIX)


def with_absence_items(view: SpaceView, away_label: str, today: str) -> SpaceView:
    """Adds an all-day calendar entry for every absence that has not ended long ago. ``away_label`` holds ``{name}``."""
    if view.kind != "group" or not any(p.get("absences") for p in view.persons):
        return view
    since = add_days(today, -400)
    extra: list[dict[str, Any]] = []
    for p in view.persons:
        if p["removed"]:
            continue
        for a in p.get("absences") or []:
            if a["to"] < since:
                continue
            title = away_label.replace("{name}", p["name"])
            item: dict[str, Any] = {
                "id": f"{ABSENCE_ITEM_PREFIX}{p['id']}~{a['id']}",
                "listId": "",
                "kind": "event",
                "title": f"{title} · {a['note']}" if a.get("note") else title,
                "start": f"{a['from']}T00:00",
            }
            if a["to"] > a["from"]:
                item["end"] = f"{a['to']}T00:00"
            item.update({"allDay": True, "assignees": [p["id"]], "fromAbsence": p["id"]})
            extra.append(item)
    if not extra:
        return view
    items = [*view.items, *extra]
    return replace(view, items=items, item_by_id={i["id"]: i for i in items})


# --- Birthdays and anniversaries --------------------------------------------------------------


def occasion_years(item: dict[str, Any], date: str) -> int | None:
    """How old somebody turns, or how many years it is, on an occurrence; None without a year."""
    year = item.get("year")
    if not item.get("occasion") or not isinstance(year, (int, float)) or isinstance(year, bool) or not year:
        return None
    n = int(date[:4]) - int(year)
    return n if n > 0 else None


def with_occasion(item: dict[str, Any], date: str) -> dict[str, Any]:
    """The entry as it reads on one occurrence: with the age or number of years after its title."""
    n = occasion_years(item, date)
    return {**item, "title": f"{item['title']} ({n})"} if n else item


def upcoming_occasions(view: SpaceView, today: str, days: int = 14) -> list[dict[str, Any]]:
    """Birthdays and anniversaries in the next ``days`` days, starting today, soonest first."""
    to = add_days(today, days - 1)
    out: list[dict[str, Any]] = []
    for item in view.items:
        if not item.get("occasion") or not item.get("start"):
            continue
        for date in occurrence_dates(item, today, to):
            if (view.occs.get(occ_id(item["id"], date)) or {}).get("skip"):
                continue
            out.append({"item": item, "date": date, "years": occasion_years(item, date)})
    out.sort(key=lambda o: (o["date"], locale_key(o["item"]["title"])))
    return out


# --- Who is where -----------------------------------------------------------------------------


def _min(clock: str) -> int:
    return int(clock[:2]) * 60 + int(clock[3:5])


def _timetables(view: SpaceView) -> list[dict[str, Any]]:
    return [lst for lst in view.lists if lst["type"] == "timetable" and lst.get("timetable")]


def _rosters(view: SpaceView) -> list[dict[str, Any]]:
    return [lst for lst in view.lists if lst["type"] == "roster" and lst.get("roster")]


def away_on(view: SpaceView, date: str) -> list[dict[str, Any]]:
    """Times people of a group are at work, at school or away for the day on a date (minutes of the day)."""
    out: list[dict[str, Any]] = []
    for p in view.persons:
        a = None if p["removed"] else absence_on(p, date)
        if a:
            out.append({"personId": p["id"], "start": 0, "end": 24 * 60, "what": "absent", "label": a.get("note")})
    for lst in _rosters(view):
        r = lst["roster"]
        who = r.get("personId")
        if not who:
            continue
        # A night shift from the day before still runs in the morning.
        before = plans.work_on(r, add_days(date, -1))
        for s in before["spans"]:
            if s["end"] <= s["start"]:
                shift = before.get("shift")
                what = "standby" if shift and shift.get("standby") else "work"
                out.append(
                    {
                        "personId": who,
                        "start": 0,
                        "end": _min(s["end"]),
                        "what": what,
                        "label": shift["name"] if shift else None,
                    }
                )
        day = plans.work_on(r, date)
        for s in day["spans"]:
            shift = day.get("shift")
            what = "standby" if shift and shift.get("standby") else "work"
            end = 24 * 60 if s["end"] <= s["start"] else _min(s["end"])
            out.append(
                {
                    "personId": who,
                    "start": _min(s["start"]),
                    "end": end,
                    "what": what,
                    "label": shift["name"] if shift else None,
                }
            )
    for lst in _timetables(view):
        tt = lst["timetable"]
        who = tt.get("personId")
        if not who or not plans.timetable_holds(tt, date) or plans.holiday_on(plans.school_off_for(view, tt), date):
            continue
        ls = plans.lessons_on_day(tt, date)
        if not ls:
            continue
        out.append(
            {
                "personId": who,
                "start": _min(ls[0]["start"]),
                "end": max(_min(x["end"]) for x in ls),
                "what": "school",
                "label": None,
            }
        )
        c = plans.care_on_day(tt, date)
        if c:
            out.append(
                {
                    "personId": who,
                    "start": _min(c["start"]),
                    "end": _min(c["end"]),
                    "what": "care",
                    "label": None,
                    "care": c["kind"],
                }
            )
    # Python's sort is stable, like JavaScript's.
    out.sort(key=lambda a: a["start"])
    return out


def care_gaps(view: SpaceView, date: str, start: int = 7 * 60, end: int = 19 * 60) -> list[dict[str, Any]]:
    """Times a child is neither at school nor in care after it while every grown-up of the group is at work.

    Only when every grown-up has a roster: of anybody else nobody knows, so they count as there.
    """
    children: list[str] = []
    for lst in _timetables(view):
        who = lst["timetable"].get("personId")
        if who and who not in children:
            children.append(who)
    adults = [p["id"] for p in view.persons if not p["removed"] and p["id"] not in children and not p["child"]]
    with_roster = {lst["roster"].get("personId") for lst in _rosters(view)}
    if not children or not adults or any(a not in with_roster for a in adults):
        return []
    away = away_on(view, date)

    def busy(who: str, what: str, m: int) -> bool:
        return any(a["personId"] == who and a["what"] in (what, "absent") and a["start"] <= m < a["end"] for a in away)

    gaps: list[dict[str, Any]] = []
    for child in children:
        begun: int | None = None
        gone = absence_on(view.person_by_id.get(child), date) is not None
        for m in range(start, end + 1, 5):
            alone = (
                m < end
                and not busy(child, "school", m)
                and not busy(child, "care", m)
                and not gone
                and all(busy(a, "work", m) for a in adults)
            )
            if alone and begun is None:
                begun = m
            if not alone and begun is not None:
                gaps.append({"date": date, "childId": child, "start": begun, "end": m, "adults": adults})
                begun = None
    return gaps
