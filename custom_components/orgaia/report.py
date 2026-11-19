"""One day of a group in a few lines: for a morning announcement, a wall display, or a voice assistant.

``day_report`` gathers what happens on a day (appointments, what is due, school, work, packing,
shopping and drives) and ``speech`` turns it into sentences in German or English.
"""

from __future__ import annotations

from typing import Any

from .protocol.plans import pack_on, school_day, work_day
from .protocol.recur import add_days, date_of
from .protocol.shopping import STATE_GOING, STATE_READY
from .protocol.view import SpaceView
from .summary import calendar_deadlines, calendar_occurrences, counts, drive_of, shopping_trips

TEXT = {
    "de": {
        "today": "Heute",
        "tomorrow": "Morgen",
        "nothing": "nichts geplant",
        "appointments": ("Termin", "Termine"),
        "tasks": ("Aufgabe", "Aufgaben"),
        "overdue": "überfällig",
        "due": "Fällig",
        "school": "{who} hat Schule von {start} bis {end}",
        "no_school": "{who} hat keine Schule",
        "holiday": "{who} hat Ferien",
        "exam": "{who} schreibt {subject}",
        "work": "{who} arbeitet {text}",
        "standby": "{who} hat Bereitschaft {text}",
        "pack": "{who} packt ein: {things}",
        "shopping_ready": "Die Liste {list} wartet auf jemanden, der einkauft",
        "shopping_going": "{who} kauft ein ({list})",
        "drive_open": "Für {title} fährt noch niemand",
        "and": "und",
    },
    "en": {
        "today": "Today",
        "tomorrow": "Tomorrow",
        "nothing": "nothing planned",
        "appointments": ("appointment", "appointments"),
        "tasks": ("task", "tasks"),
        "overdue": "overdue",
        "due": "Due",
        "school": "{who} has school from {start} to {end}",
        "no_school": "{who} has no school",
        "holiday": "{who} is on holiday",
        "exam": "{who} has a {subject} test",
        "work": "{who} works {text}",
        "standby": "{who} is on call {text}",
        "pack": "{who} packs: {things}",
        "shopping_ready": "The list {list} waits for somebody to do the shopping",
        "shopping_going": "{who} is doing the shopping ({list})",
        "drive_open": "Nobody drives for {title} yet",
        "and": "and",
    },
}


def texts(language: str | None) -> dict[str, Any]:
    return TEXT.get((language or "de").split("-")[0].lower(), TEXT["en"])


def _who(view: SpaceView, person: str | None) -> str:
    return (view.person_by_id.get(person or "") or {}).get("name") or ""


def day_report(view: SpaceView, day: str, today: str, minute: int, person: str | None = None) -> dict[str, Any]:
    """Everything of one day, as plain data. With ``person``, only what concerns them."""
    off = view.meta.get("schoolOff") or []
    appointments = []
    for occ in calendar_occurrences(view, day, day, person):
        item = occ.item
        if occ.skip or item.get("kind") != "event" or item.get("fromRoster") or item.get("fromTimetable"):
            continue
        if date_of(occ.start) != day and not item.get("allDay"):
            continue
        entry: dict[str, Any] = {
            "title": item["title"],
            "start": None if item.get("allDay") else occ.start[11:16],
            "end": occ.end[11:16] if occ.end and len(occ.end) > 10 and not item.get("allDay") else None,
            "all_day": bool(item.get("allDay")),
            "persons": view.names(occ.assignees),
        }
        if isinstance(item.get("location"), str) and item["location"]:
            entry["location"] = item["location"]
        drive = drive_of(view, occ)
        if drive:
            entry["drive_to"] = _who(view, drive.driver_to) if drive.need_to else None
            entry["drive_from"] = _who(view, drive.driver_from) if drive.need_from else None
            entry["drive_missing"] = drive.missing
        appointments.append(entry)

    due = [
        {
            "title": d.item["title"],
            "time": d.time,
            "persons": view.names(d.item.get("assignees") or []),
            "done": d.done,
        }
        for d in calendar_deadlines(view, day, day, person)
        if not d.item.get("fromTrip")
    ]
    c = counts(view, today, minute, person)

    school, work = [], []
    for lst in view.lists:
        if lst["type"] == "timetable" and lst.get("timetable"):
            who = lst["timetable"].get("personId")
            if person is not None and who != person:
                continue
            s = school_day(lst, off, day)
            school.append(
                {
                    "person": _who(view, who) or lst["name"],
                    "status": s["status"],
                    "start": s["start"],
                    "end": s["end"],
                    "lessons": [x["subject"] for x in s["lessons"]],
                    "exams": [x["subject"] for x in s.get("exams") or []],
                    "note": s.get("note"),
                    "pack": pack_on(lst, off, day),
                }
            )
        elif lst["type"] == "roster" and lst.get("roster"):
            who = lst["roster"].get("personId")
            if person is not None and who != person:
                continue
            w = work_day(lst, day)
            if w["spans"]:
                work.append(
                    {
                        "person": _who(view, who) or lst["name"],
                        "standby": bool(w.get("standby")),
                        "shift": w.get("shift"),
                        "spans": [f"{x['start']}–{x['end']}" for x in w["spans"]],
                    }
                )

    shopping = []
    for lst, trip in shopping_trips(view):
        if trip.state not in (STATE_READY, STATE_GOING):
            continue
        if person is not None and trip.shopper not in (None, person):
            continue
        shopping.append(
            {"list": lst["name"], "state": trip.state, "open": trip.open, "shopper": _who(view, trip.shopper) or None}
        )

    return {
        "date": day,
        "person": _who(view, person) or None,
        "appointments": appointments,
        "due": due,
        "overdue": c.overdue if day == today else [],
        "school": school,
        "work": work,
        "shopping": shopping,
    }


def _count(n: int, words: tuple[str, str]) -> str:
    return f"{n} {words[0] if n == 1 else words[1]}"


def _join(parts: list[str], word: str) -> str:
    if len(parts) < 2:
        return "".join(parts)
    return ", ".join(parts[:-1]) + f" {word} " + parts[-1]


def short_text(report: dict[str, Any], language: str | None) -> str:
    """ "2 Termine, 3 Aufgaben": what a tile shows."""
    t = texts(language)
    open_due = [d for d in report["due"] if not d["done"]]
    parts = []
    if report["appointments"]:
        parts.append(_count(len(report["appointments"]), t["appointments"]))
    if open_due:
        parts.append(_count(len(open_due), t["tasks"]))
    if report["overdue"]:
        parts.append(f"{len(report['overdue'])} {t['overdue']}")
    return ", ".join(parts) or t["nothing"]


def speech(report: dict[str, Any], language: str | None, today: str) -> str:
    """The day in a few sentences, for a loudspeaker."""
    t = texts(language)
    when = (
        t["today"]
        if report["date"] == today
        else t["tomorrow"]
        if report["date"] == add_days(today, 1)
        else report["date"]
    )
    sentences = []
    events = []
    for a in report["appointments"]:
        text = a["title"] if a["all_day"] else f"{a['start']} {a['title']}"
        if a["persons"] and not report["person"]:
            text += f" ({', '.join(a['persons'])})"
        events.append(text)
    sentences.append(f"{when}: {_join(events, t['and'])}" if events else f"{when}: {t['nothing']}")
    open_due = [d["title"] for d in report["due"] if not d["done"]]
    if open_due:
        sentences.append(f"{t['due']}: {_join(open_due, t['and'])}")
    for s in report["school"]:
        if s["status"] == "school":
            sentences.append(t["school"].format(who=s["person"], start=s["start"], end=s["end"]))
        elif s["status"] == "holiday":
            sentences.append(t["holiday"].format(who=s["person"]))
        for subject in s["exams"]:
            sentences.append(t["exam"].format(who=s["person"], subject=subject))
        if s["pack"]:
            sentences.append(t["pack"].format(who=s["person"], things=_join(s["pack"], t["and"])))
    for w in report["work"]:
        text = (f"{w['shift']} " if w["shift"] else "") + ", ".join(w["spans"])
        sentences.append(t["standby" if w["standby"] else "work"].format(who=w["person"], text=text))
    for sh in report["shopping"]:
        if sh["state"] == STATE_GOING and sh["shopper"]:
            sentences.append(t["shopping_going"].format(who=sh["shopper"], list=sh["list"]))
        else:
            sentences.append(t["shopping_ready"].format(list=sh["list"]))
    for a in report["appointments"]:
        if a.get("drive_missing"):
            sentences.append(t["drive_open"].format(title=a["title"]))
    return ". ".join(sentences) + "."
