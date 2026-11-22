"""Dates and repetitions, as Orgaia's packages/core/src/dates.ts and recur.ts compute them.

Dates are local wall-clock strings: YYYY-MM-DD, times HH:mm, date-times YYYY-MM-DDTHH:mm.
"""

from __future__ import annotations

import calendar
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any


def parse_ymd(s: str) -> date:
    y, m, d = (s[:10].split("-") + ["1", "1"])[:3]
    return date(int(y), int(m or 1), int(d or 1))


def ymd(d: date) -> str:
    return d.isoformat()


def add_days(s: str, n: int) -> str:
    return ymd(parse_ymd(s) + timedelta(days=n))


def days_between(a: str, b: str) -> int:
    return (parse_ymd(b) - parse_ymd(a)).days


def weekday(s: str) -> int:
    """0 = Sunday, as JavaScript's getDay."""
    return (parse_ymd(s).weekday() + 1) % 7


def week_start(s: str, first_day: int = 1) -> str:
    return add_days(s, -((weekday(s) - first_day + 7) % 7))


def add_months(s: str, n: int, anchor_day: int | None = None) -> str:
    d = parse_ymd(s)
    day = anchor_day if anchor_day is not None else d.day
    total = d.year * 12 + (d.month - 1) + n
    year, month = divmod(total, 12)
    last = calendar.monthrange(year, month + 1)[1]
    return ymd(date(year, month + 1, min(day, last)))


def to_min(t: str) -> int:
    parts = (t or "0:0").split(":")
    try:
        return int(parts[0] or 0) * 60 + int(parts[1] if len(parts) > 1 and parts[1] else 0)
    except ValueError:
        return 0


def date_of(dt: str) -> str:
    return dt[:10]


def time_of(dt: str) -> str:
    return dt[11:16] if len(dt) > 10 else "00:00"


def _step(repeat: dict[str, Any]) -> int:
    try:
        return max(1, int(repeat.get("interval") or 1))
    except (TypeError, ValueError):
        return 1


def base_date(item: dict[str, Any]) -> str | None:
    """The date a repeating item is anchored on: its slot if it has one, otherwise its deadline."""
    start = item.get("start")
    if isinstance(start, str) and start:
        return start[:10]
    due = item.get("dueDate")
    return due if isinstance(due, str) and due else None


def _nth(repeat: dict[str, Any], base: str, n: int) -> str:
    freq, step = repeat.get("freq"), _step(repeat)
    if freq == "day":
        return add_days(base, n * step)
    if freq == "week":
        return add_days(base, n * step * 7)
    back = _back(repeat)
    anchor = add_days(base, back) if back else base
    day = parse_ymd(anchor).day
    d = add_months(anchor, n * step * (1 if freq == "month" else 12), day)
    return add_days(d, -back) if back else d


def _back(repeat: dict[str, Any]) -> int:
    """Days a monthly or yearly series lies before the one it follows (``back`` in the app's Repeat)."""
    back = repeat.get("back")
    if repeat.get("freq") not in ("month", "year") or not isinstance(back, int) or isinstance(back, bool) or back <= 0:
        return 0
    return min(366, back)


def _first_index(repeat: dict[str, Any], base: str, start: str) -> int:
    freq, step = repeat.get("freq"), _step(repeat)
    days = days_between(base, start)
    if days <= 0:
        return 0
    if freq == "day":
        return -(-days // step)
    if freq == "week":
        return -(-days // (step * 7))
    back = _back(repeat)
    b, f = parse_ymd(add_days(base, back)), parse_ymd(add_days(start, back))
    months = (f.year - b.year) * 12 + (f.month - b.month)
    per = step if freq == "month" else step * 12
    return max(0, months // per - 1)


def _weekdays(repeat: dict[str, Any]) -> list[int] | None:
    days = repeat.get("days") if repeat.get("freq") == "week" else None
    if not isinstance(days, list) or not days:
        return None
    clean = {d for d in days if isinstance(d, int) and 0 <= d <= 6}
    return sorted(clean, key=lambda x: (x + 6) % 7) or None


def _on_weekday(repeat: dict[str, Any], base: str, days: list[int], d: str) -> bool:
    if d < base or weekday(d) not in days:
        return False
    return (days_between(week_start(base), week_start(d)) // 7) % _step(repeat) == 0


# Most dates one call works out; far more than any series shown has.
_GUARD = 20000


def occurrence_dates(item: dict[str, Any], start: str, end: str) -> list[str]:
    """All occurrence dates of an item within [start, end]. Non-repeating items yield their base date."""
    base = base_date(item)
    if not base:
        return []
    repeat = item.get("repeat")
    if not isinstance(repeat, dict):
        return [base] if start <= base <= end else []
    until = repeat.get("until") if isinstance(repeat.get("until"), str) else None
    out: list[str] = []
    days = _weekdays(repeat)
    if days:
        stop = until if until and until < end else end
        first = start if start > base else base
        step = _step(repeat)
        # Week by week, and only the weeks that are on, so a long gap between dates never runs into the guard.
        week = week_start(first)
        off = (days_between(week_start(base), week) // 7) % step
        if off:
            week = add_days(week, (step - off) * 7)
        guard = 0
        while week <= stop and guard < _GUARD:
            for wd in days:
                d = add_days(week, (wd + 6) % 7)
                if first <= d <= stop:
                    out.append(d)
            week, guard = add_days(week, step * 7), guard + 1
        return out
    n, guard = _first_index(repeat, base, start), 0
    while guard < _GUARD:
        d = _nth(repeat, base, n)
        if d > end or (until and d > until):
            break
        if d >= start:
            out.append(d)
        n, guard = n + 1, guard + 1
    return out


def occurrence_index(item: dict[str, Any], d: str) -> int:
    base = base_date(item)
    repeat = item.get("repeat")
    if not base or not isinstance(repeat, dict) or d < base:
        return -1
    days = _weekdays(repeat)
    if days:
        if not _on_weekday(repeat, base, days, d):
            return -1

        def pos(x: str) -> int:
            return len([w for w in days if (w + 6) % 7 < (weekday(x) + 6) % 7])

        weeks = days_between(week_start(base), week_start(d)) // 7 // _step(repeat)
        return weeks * len(days) + pos(d) - pos(base)
    n = _first_index(repeat, base, d)
    for _ in range(4):
        x = _nth(repeat, base, n)
        if x == d:
            return n
        if x > d:
            return -1
        n += 1
    return -1


def rotation_assignee(item: dict[str, Any], d: str, away: Callable[[str], bool] | None = None) -> str | None:
    """Whose turn it is on a date. With ``away``, the turn passes on to the next who is not away that day."""
    rota = item.get("rotation")
    if not isinstance(rota, list) or not rota:
        return None
    n = occurrence_index(item, d)
    if n < 0:
        return None
    if away:
        for k in range(len(rota)):
            p = rota[(n + k) % len(rota)]
            if not away(p):
                return p
    return rota[n % len(rota)]
