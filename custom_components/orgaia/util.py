"""Turns Orgaia's wall-clock dates and times into Home Assistant's, in Home Assistant's time zone."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from homeassistant.util import dt as dt_util

from .protocol.recur import parse_ymd, to_min


def local_now() -> datetime:
    return dt_util.now()


def today() -> str:
    return local_now().date().isoformat()


def minute_of_day(now: datetime | None = None) -> int:
    now = now or local_now()
    return now.hour * 60 + now.minute


def to_date(s: str) -> date:
    return parse_ymd(s)


def to_datetime(s: str) -> datetime:
    """``YYYY-MM-DDTHH:mm`` (or only a date, meaning midnight) as an aware datetime."""
    day = parse_ymd(s)
    minutes = to_min(s[11:16]) if len(s) > 10 else 0
    naive = datetime(day.year, day.month, day.day) + timedelta(minutes=minutes)
    return naive.replace(tzinfo=dt_util.get_default_time_zone())


def from_ms(ms: object) -> datetime | None:
    if isinstance(ms, bool) or not isinstance(ms, (int, float)) or ms <= 0:
        return None
    return dt_util.utc_from_timestamp(ms / 1000)
