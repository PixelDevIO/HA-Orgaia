"""Reads timetables and rosters from the fields of their list, as Orgaia's timetable-read.ts and roster-read.ts.

Another member could send anything, so every field is checked.
"""

from __future__ import annotations

import re
from typing import Any

from .model import _base36

SUBJECT_PREFIX = "subj."
LESSON_PREFIX = "les."
DAY_PREFIX = "day."
WEEK_PREFIX = "wk."
SHIFT_PREFIX = "shift."
ROSTER_DAY_PREFIX = "d."
ROSTER_OFF_PREFIX = "off."

TT_PREFIX = "tt~"
RS_PREFIX = "rs~"
# First Monday the worked-out series count from.
ANCHOR = "2024-01-01"
# How far around today single roster days become entries.
ROSTER_BACK = 120
ROSTER_AHEAD = 500

_TIME = re.compile(r"[0-9]{2}:[0-9]{2}")
_CLOCK = re.compile(r"([01][0-9]|2[0-3]):[0-5][0-9]")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_OWN = re.compile(r"([0-9]{2}:[0-9]{2})-([0-9]{2}:[0-9]{2})")

DEFAULT_PERIODS = [
    {"start": "07:55", "end": "08:40"},
    {"start": "08:45", "end": "09:30"},
    {"start": "09:50", "end": "10:35"},
    {"start": "10:40", "end": "11:25"},
    {"start": "11:40", "end": "12:25"},
    {"start": "12:30", "end": "13:15"},
    {"start": "13:30", "end": "14:15"},
    {"start": "14:15", "end": "15:00"},
]


def _is_date(x: Any) -> bool:
    return isinstance(x, str) and _DATE.fullmatch(x) is not None


def _things(x: Any) -> list[str]:
    return [v.strip() for v in x if isinstance(v, str) and v.strip()] if isinstance(x, list) else []


def _day_number(suffix: str) -> int | None:
    """JavaScript's Number() for a weekday key: "" is 0, anything not a whole number is out."""
    s = suffix.strip()
    if not s:
        return 0
    try:
        return int(s)
    except ValueError:
        return None


def _fnv(text: str) -> str:
    """32-bit FNV-1a over UTF-16 code units, in base 36, as the app's ``hash``."""
    h = 0x811C9DC5
    data = text.encode("utf-16-le")
    for i in range(0, len(data), 2):
        h ^= data[i] | (data[i + 1] << 8)
        h = (h * 0x01000193) & 0xFFFFFFFF
    return _base36(h, 1)


def thing_key(name: str) -> str:
    """ "Sportzeug" and "sportzeug " are packed once."""
    return re.sub(r"\s+", " ", name.strip().lower())


# --- Reading ----------------------------------------------------------------------------------


def read_school_off(x: Any) -> list[dict[str, Any]]:
    if not isinstance(x, list):
        return []
    out = [
        {
            "id": o["id"],
            "name": o.get("name") if isinstance(o.get("name"), str) else "",
            "from": o["from"],
            "to": o["from"] if o["to"] < o["from"] else o["to"],
        }
        for o in x
        if isinstance(o, dict) and isinstance(o.get("id"), str) and _is_date(o.get("from")) and _is_date(o.get("to"))
    ]
    out.sort(key=lambda o: o["from"])
    return out


def read_timetable(raw: dict[str, Any]) -> dict[str, Any]:
    periods = DEFAULT_PERIODS
    if isinstance(raw.get("periods"), list):
        periods = [
            {"start": p["start"], "end": p["end"]}
            for p in raw["periods"]
            if isinstance(p, dict)
            and isinstance(p.get("start"), str)
            and isinstance(p.get("end"), str)
            and _TIME.fullmatch(p["start"])
            and _TIME.fullmatch(p["end"])
        ][:12]
    subjects: list[dict[str, Any]] = []
    cells: dict[str, str] = {}
    day_things: dict[int, list[str]] = {}
    for k, v in raw.items():
        if k.startswith(SUBJECT_PREFIX):
            if not isinstance(v, dict) or not isinstance(v.get("name"), str) or v.get("deleted"):
                continue
            subject = {"id": k[len(SUBJECT_PREFIX) :], "name": v["name"], "things": _things(v.get("things"))}
            if isinstance(v.get("room"), str) and v["room"]:
                subject["room"] = v["room"]
            subjects.append(subject)
        elif k.startswith(LESSON_PREFIX):
            if isinstance(v, str):
                cells[k[len(LESSON_PREFIX) :]] = v
        elif k.startswith(DAY_PREFIX):
            d = _day_number(k[len(DAY_PREFIX) :])
            things = _things(v)
            if d is not None and 0 <= d <= 6 and things:
                day_things[d] = things
    pack_time = raw.get("packTime")
    return {
        "personId": raw["ttFor"] if isinstance(raw.get("ttFor"), str) and raw["ttFor"] else None,
        "periods": periods,
        "subjects": subjects,
        "cells": cells,
        "dayThings": day_things,
        "abStart": raw["abStart"] if _is_date(raw.get("abStart")) else None,
        "packMon": "fri" if raw.get("packMon") == "fri" else "sun",
        "packTime": pack_time if isinstance(pack_time, str) and _TIME.fullmatch(pack_time) else None,
        "noCal": raw.get("noCal") is True,
    }


def _is_clock(x: Any) -> bool:
    return isinstance(x, str) and _CLOCK.fullmatch(x) is not None


def _span(x: Any) -> dict[str, str] | None:
    if isinstance(x, dict) and _is_clock(x.get("start")) and _is_clock(x.get("end")) and x["start"] != x["end"]:
        return {"start": x["start"], "end": x["end"]}
    return None


def own_time(value: str) -> dict[str, str] | None:
    m = _OWN.fullmatch(value)
    if m and _is_clock(m[1]) and _is_clock(m[2]) and m[1] != m[2]:
        return {"start": m[1], "end": m[2]}
    return None


def read_roster(raw: dict[str, Any]) -> dict[str, Any]:
    week: dict[int, list[dict[str, str]]] = {}
    shifts: list[dict[str, Any]] = []
    days: dict[str, str] = {}
    off: list[dict[str, Any]] = []
    for k, v in raw.items():
        if k.startswith(WEEK_PREFIX):
            d = _day_number(k[len(WEEK_PREFIX) :])
            spans = [s for s in (_span(x) for x in v) if s][:2] if isinstance(v, list) else []
            if d is not None and 0 <= d <= 6 and spans:
                week[d] = spans
        elif k.startswith(SHIFT_PREFIX):
            if not isinstance(v, dict) or not isinstance(v.get("name"), str) or not v["name"].strip():
                continue
            name = v["name"].strip()
            code = v.get("code")
            shift: dict[str, Any] = {
                "id": k[len(SHIFT_PREFIX) :],
                "name": name,
                "code": code.strip()[:3] if isinstance(code, str) and code.strip() else name[:1].upper(),
            }
            if _is_clock(v.get("start")) and _is_clock(v.get("end")) and v["start"] != v["end"]:
                shift["start"], shift["end"] = v["start"], v["end"]
            shifts.append(shift)
        elif k.startswith(ROSTER_DAY_PREFIX):
            date = k[len(ROSTER_DAY_PREFIX) :]
            if _is_date(date) and isinstance(v, str):
                days[date] = v
        elif k.startswith(ROSTER_OFF_PREFIX):
            if not isinstance(v, dict) or not _is_date(v.get("from")) or not _is_date(v.get("to")):
                continue
            off.append(
                {
                    "id": k[len(ROSTER_OFF_PREFIX) :],
                    "name": v["name"] if isinstance(v.get("name"), str) else "",
                    "from": v["from"],
                    "to": v["from"] if v["to"] < v["from"] else v["to"],
                }
            )
    off.sort(key=lambda o: o["from"])
    return {
        "personId": raw["rsFor"] if isinstance(raw.get("rsFor"), str) and raw["rsFor"] else None,
        "mode": "shifts" if raw.get("mode") == "shifts" else "week",
        "week": week,
        "shifts": shifts,
        "days": days,
        "off": off,
        "busyOnly": raw.get("busyOnly") is True,
        "noCal": raw.get("noCal") is True,
    }
