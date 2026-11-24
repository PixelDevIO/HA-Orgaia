"""Subscribed calendars in the iCalendar format (RFC 5545), as Orgaia's packages/core/src/ics.ts.

Schools, clubs and waste collection services publish them. Only what a family calendar needs: events
with their time, place and description, repetitions, exceptions and moved occurrences. Repeating events
are spread out into single entries for a window of days, so that the rest only sees plain appointments.

Every device fetches a subscribed calendar itself; the entries never go through the sync service. The
test vectors pin the result to the app's.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta, tzinfo
import ipaddress
import re
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

MAX_OCCURRENCES = 2000
MAX_STEPS = 20000
DAY_MS = 86400000
DAYS = ["SU", "MO", "TU", "WE", "TH", "FR", "SA"]


@dataclass(frozen=True)
class FeedEvent:
    """One entry of a subscribed calendar, in local wall-clock time ``YYYY-MM-DDTHH:mm``."""

    uid: str
    title: str
    start: str
    all_day: bool
    end: str | None = None
    location: str | None = None
    note: str | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"uid": self.uid, "title": self.title, "allDay": self.all_day, "start": self.start}
        for key, value in (("end", self.end), ("location", self.location), ("note", self.note)):
            if value is not None:
                out[key] = value
        return out

    @staticmethod
    def from_json(raw: dict[str, Any]) -> FeedEvent:
        return FeedEvent(
            uid=str(raw["uid"]),
            title=str(raw["title"]),
            start=str(raw["start"]),
            all_day=bool(raw.get("allDay")),
            end=raw.get("end"),
            location=raw.get("location"),
            note=raw.get("note"),
        )


@dataclass(frozen=True)
class Stamp:
    """Wall-clock parts in the zone the calendar gives."""

    y: int
    mo: int
    d: int
    h: int
    mi: int
    s: int
    date_only: bool
    utc: bool
    tz: str | None = None


@dataclass
class VEvent:
    uid: str | None = None
    summary: str = ""
    location: str | None = None
    description: str | None = None
    start: Stamp | None = None
    end: Stamp | None = None
    duration: int | None = None
    rrule: dict[str, str] | None = None
    rdates: list[Stamp] = field(default_factory=list)
    exdates: list[Stamp] = field(default_factory=list)
    recurrence_id: Stamp | None = None
    cancelled: bool = False


# --- Reading -----------------------------------------------------------------------------------


def _unfold(text: str) -> list[str]:
    return re.sub(r"\n[ \t]", "", text.replace("\r\n", "\n").replace("\r", "\n")).split("\n")


def _parse_line(line: str) -> tuple[str, dict[str, str], str] | None:
    # The value starts after the first colon that is not inside a quoted parameter.
    quoted = False
    split = -1
    for i, c in enumerate(line):
        if c == '"':
            quoted = not quoted
        elif c == ":" and not quoted:
            split = i
            break
    if split < 0:
        return None
    raw_name, *raw_params = line[:split].split(";")
    params: dict[str, str] = {}
    for p in raw_params:
        eq = p.find("=")
        if eq > 0:
            params[p[:eq].upper()] = re.sub(r'^"|"$', "", p[eq + 1 :])
    return raw_name.upper(), params, line[split + 1 :]


def _unescape(v: str) -> str:
    return re.sub(r"\\([\\;,nN])", lambda m: "\n" if m.group(1) in "nN" else m.group(1), v).strip()


def _parse_stamp(value: str, params: dict[str, str]) -> Stamp | None:
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})?(Z)?)?", value.strip())
    if not m:
        return None
    date_only = not m.group(4) or params.get("VALUE") == "DATE"
    utc = bool(m.group(7))
    return Stamp(
        y=int(m.group(1)),
        mo=int(m.group(2)),
        d=int(m.group(3)),
        h=0 if date_only else int(m.group(4)),
        mi=0 if date_only else int(m.group(5)),
        s=0 if date_only else int(m.group(6) or 0),
        date_only=date_only,
        utc=utc,
        tz=params.get("TZID") if not utc and not date_only else None,
    )


def _parse_duration(v: str) -> int | None:
    m = re.fullmatch(r"([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", v.strip())
    if not m:
        return None
    g = [int(x or 0) for x in m.groups()[1:]]
    ms = ((g[0] * 7 + g[1]) * 86400 + g[2] * 3600 + g[3] * 60 + g[4]) * 1000
    return -ms if m.group(1) == "-" else ms


def _parse_events(text: str) -> list[VEvent]:
    out: list[VEvent] = []
    cur: VEvent | None = None
    depth = 0
    for line in _unfold(text):
        p = _parse_line(line)
        if not p:
            continue
        name, params, value = p
        if name == "BEGIN":
            if value.upper() == "VEVENT" and cur is None:
                cur = VEvent()
                depth = 0
            elif cur is not None:
                depth += 1
            continue
        if name == "END":
            if cur is not None and depth > 0:
                depth -= 1
            elif cur is not None and value.upper() == "VEVENT":
                if cur.start is not None:
                    out.append(cur)
                cur = None
            continue
        # Alarms and other nested parts are not ours.
        if cur is None or depth > 0:
            continue
        if name == "UID":
            cur.uid = value.strip()
        elif name == "SUMMARY":
            cur.summary = _unescape(value)
        elif name == "LOCATION":
            cur.location = _unescape(value)
        elif name == "DESCRIPTION":
            cur.description = _unescape(value)
        elif name == "DTSTART":
            cur.start = _parse_stamp(value, params)
        elif name == "DTEND":
            cur.end = _parse_stamp(value, params)
        elif name == "DURATION":
            cur.duration = _parse_duration(value)
        elif name == "RRULE":
            rule: dict[str, str] = {}
            for part in value.split(";"):
                k, _, v = part.partition("=")
                if k and v:
                    rule[k.upper()] = v.split("=")[0].upper()
            cur.rrule = rule
        elif name in ("RDATE", "EXDATE"):
            for v in value.split(","):
                st = _parse_stamp(v, params)
                if st:
                    (cur.rdates if name == "RDATE" else cur.exdates).append(st)
        elif name == "RECURRENCE-ID":
            cur.recurrence_id = _parse_stamp(value, params)
        elif name == "STATUS":
            cur.cancelled = value.strip().upper() == "CANCELLED"
    # Events without a UID still need a stable key.
    for i, e in enumerate(out):
        if not e.uid:
            e.uid = f"noid-{i}-{e.summary}"
    return out


# --- Time zones --------------------------------------------------------------------------------


# Outlook and Exchange name zones their own way; the common ones, as the names the system knows.
WINDOWS_ZONES = {
    "w. europe standard time": "Europe/Berlin",
    "central europe standard time": "Europe/Budapest",
    "central european standard time": "Europe/Warsaw",
    "romance standard time": "Europe/Paris",
    "gmt standard time": "Europe/London",
    "greenwich standard time": "Atlantic/Reykjavik",
    "e. europe standard time": "Europe/Chisinau",
    "fle standard time": "Europe/Helsinki",
    "gtb standard time": "Europe/Bucharest",
    "turkey standard time": "Europe/Istanbul",
    "russian standard time": "Europe/Moscow",
    "eastern standard time": "America/New_York",
    "central standard time": "America/Chicago",
    "mountain standard time": "America/Denver",
    "pacific standard time": "America/Los_Angeles",
}


def _zone(tz: str) -> ZoneInfo | None:
    try:
        return ZoneInfo(WINDOWS_ZONES.get(tz.strip().lower(), tz))
    except (ValueError, OSError, KeyError):
        return None


def _wall_key(st: Stamp) -> int:
    """A sortable number for comparing stamps in the calendar's own wall-clock time."""
    return calendar.timegm((st.y, st.mo, st.d, st.h, st.mi, st.s)) * 1000


def _instant(st: Stamp) -> int | None:
    """The instant a stamp stands for, or None for "floating" times that mean the same everywhere."""
    if st.date_only:
        return None
    if st.utc:
        return _wall_key(st)
    zone = _zone(st.tz) if st.tz else None
    if zone is None:
        return None
    return int(datetime(st.y, st.mo, st.d, st.h, st.mi, st.s, tzinfo=zone).timestamp() * 1000)


def _local_text(st: Stamp, local: tzinfo) -> str:
    at = _instant(st)
    if at is None:
        return f"{st.y:04d}-{st.mo:02d}-{st.d:02d}T{st.h:02d}:{st.mi:02d}"
    return datetime.fromtimestamp(at / 1000, UTC).astimezone(local).strftime("%Y-%m-%dT%H:%M")


def _same_moment(a: Stamp, b: Stamp) -> bool:
    if a.date_only or b.date_only:
        return (a.y, a.mo, a.d) == (b.y, b.mo, b.d)
    ia, ib = _instant(a), _instant(b)
    if ia is not None and ib is not None:
        return ia == ib
    return _wall_key(a) == _wall_key(b)


def _with_date(st: Stamp, day: date) -> Stamp:
    return replace(st, y=day.year, mo=day.month, d=day.day)


def _shift_wall(st: Stamp, ms: int) -> Stamp:
    d = datetime(1970, 1, 1) + timedelta(milliseconds=_wall_key(st) + ms)
    return replace(st, y=d.year, mo=d.month, d=d.day, h=d.hour, mi=d.minute, s=d.second)


# --- Repetition --------------------------------------------------------------------------------


def _js_day(d: date) -> int:
    """Weekday as JavaScript counts it: Sunday 0."""
    return (d.weekday() + 1) % 7


def _by_days(rule: dict[str, str]) -> list[tuple[int, int]]:
    out = []
    for x in (rule.get("BYDAY") or "").split(","):
        m = re.fullmatch(r"([+-]?\d{1,2})?(SU|MO|TU|WE|TH|FR|SA)", x.strip())
        if m:
            out.append((DAYS.index(m.group(2)), int(m.group(1)) if m.group(1) else 0))
    return out


def _nums(v: str | None) -> list[int]:
    out = []
    for x in (v or "").split(","):
        try:
            n = int(x)
        except ValueError:
            continue
        if n:
            out.append(n)
    return out


def _days_in_month(y: int, m0: int) -> int:
    return calendar.monthrange(y, m0 + 1)[1]


def _month_days(y: int, m0: int, rule: dict[str, str], start_day: int) -> list[date]:
    """Days of one month that match the rule, in order."""
    length = _days_in_month(y, m0)
    out: set[int] = set()
    bd = _by_days(rule)
    md = _nums(rule.get("BYMONTHDAY"))
    for n in md:
        out.add(n if n > 0 else length + n + 1)
    if bd:
        matches: list[int] = []
        for wd, nth in bd:
            every = [d for d in range(1, length + 1) if _js_day(date(y, m0 + 1, d)) == wd]
            if not nth:
                matches.extend(every)
            else:
                idx = nth - 1 if nth > 0 else len(every) + nth
                if 0 <= idx < len(every):
                    matches.append(every[idx])
        if md:
            # Both given: a day has to fit both.
            both = [d for d in matches if d in out]
            out = set(both)
        else:
            out.update(matches)
    if not md and not bd:
        out.add(start_day)
    days = [d for d in sorted(out) if 1 <= d <= length]
    # BYSETPOS picks from what matched: "the 2nd Thursday" as Outlook writes it, or "the last working day".
    pos = _nums(rule.get("BYSETPOS"))
    if pos:
        picked = {
            days[n - 1 if n > 0 else len(days) + n] for n in pos if 0 <= (n - 1 if n > 0 else len(days) + n) < len(days)
        }
        days = sorted(picked)
    return [date(y, m0 + 1, d) for d in days]


def _expand(ev: VEvent, from_wall: int, until_wall: int) -> list[Stamp]:
    """Start stamps of the occurrences between ``from_wall`` and ``until_wall``.

    Those before are counted (for COUNT) but not kept, so a daily series that began years ago still
    has its dates of today.
    """
    rule = ev.rrule
    first = ev.start
    assert first is not None
    out: list[Stamp] = []
    if rule is None:
        out.append(first)
    else:
        freq = rule.get("FREQ")
        try:
            interval = max(1, int(rule.get("INTERVAL") or 1))
        except ValueError:
            interval = 1
        try:
            count = max(1, int(rule["COUNT"])) if rule.get("COUNT") else None
        except ValueError:
            count = None
        until = _parse_stamp(rule["UNTIL"], {}) if rule.get("UNTIL") else None
        # UNTIL in UTC is an instant; a date or a local time is compared on the wall clock.
        until_key = None
        if until:
            until_key = (
                calendar.timegm((until.y, until.mo, until.d, 23, 59, 59)) * 1000
                if until.date_only
                else _wall_key(until)
            )
        until_utc = bool(until and until.utc and not until.date_only)
        months = _nums(rule.get("BYMONTH"))
        bd = _by_days(rule)
        first_day = date(first.y, first.mo, first.d)
        start_key = _wall_key(first)
        n = 0
        steps = 0

        def take(day: date) -> bool:
            nonlocal n
            st = _with_date(first, day)
            key = _wall_key(st)
            if key < start_key:
                return True
            if until_key is not None:
                at = (_instant(st) if until_utc else None) or key
                if at > until_key:
                    return False
            if key > until_wall or (count is not None and n >= count) or len(out) >= MAX_OCCURRENCES:
                return False
            n += 1
            if key >= from_wall:
                out.append(st)
            return True

        def skip(unit: int) -> int:
            """Without a number of dates nothing before the window needs counting: begin shortly before it."""
            if count is not None or from_wall <= start_key:
                return 0
            return max(0, (from_wall - start_key) // (unit * interval * DAY_MS) - 1) * interval

        going = True
        if freq == "DAILY":
            i = skip(1)
            while going and steps < MAX_STEPS:
                steps += 1
                day = first_day + timedelta(days=i)
                i += interval
                if months and day.month not in months:
                    continue
                if bd and not any(wd == _js_day(day) for wd, _ in bd):
                    continue
                going = take(day)
        elif freq == "WEEKLY":
            wkst = DAYS.index(rule.get("WKST", "MO")) if rule.get("WKST", "MO") in DAYS else 1
            week_days = sorted([wd for wd, _ in bd] if bd else [_js_day(first_day)], key=lambda wd: (wd - wkst + 7) % 7)
            week_start = first_day - timedelta(days=(_js_day(first_day) - wkst + 7) % 7)
            w = skip(7)
            while going and steps < MAX_STEPS:
                steps += 1
                for wd in week_days:
                    day = week_start + timedelta(days=w * 7 + (wd - wkst + 7) % 7)
                    if months and day.month not in months:
                        continue
                    going = take(day)
                    if not going:
                        break
                w += interval
        elif freq == "MONTHLY":
            m = 0
            while going and steps < MAX_STEPS:
                steps += 1
                y = first.y + (first.mo - 1 + m) // 12
                m0 = (first.mo - 1 + m) % 12
                m += interval
                if months and m0 + 1 not in months:
                    continue
                for day in _month_days(y, m0, rule, first.d):
                    going = take(day)
                    if not going:
                        break
        elif freq == "YEARLY":
            yr = 0
            while going and steps < MAX_STEPS:
                steps += 1
                y = first.y + yr
                yr += interval
                for mo in months or [first.mo]:
                    if rule.get("BYDAY") or rule.get("BYMONTHDAY"):
                        days = _month_days(y, mo - 1, rule, first.d)
                    elif first.d <= _days_in_month(y, mo - 1):
                        days = [date(y, mo, first.d)]
                    else:
                        days = []
                    for day in days:
                        going = take(day)
                        if not going:
                            break
                    if not going:
                        break
        else:
            out.append(first)
    for r in ev.rdates:
        if not any(_same_moment(o, r) for o in out):
            out.append(replace(first, y=r.y, mo=r.mo, d=r.d) if r.date_only and not first.date_only else r)
    return [o for o in out if not any(_same_moment(o, x) for x in ev.exdates)]


# --- Output ------------------------------------------------------------------------------------


def _feed_event(ev: VEvent, start: Stamp, uid: str, local: tzinfo) -> FeedEvent:
    assert ev.start is not None
    all_day = start.date_only
    if ev.end is not None:
        if ev.recurrence_id is not None:
            length = _wall_key(ev.end) - _wall_key(ev.start)
        else:
            e = _instant(ev.end)
            s = _instant(ev.start)
            length = (e if e is not None else _wall_key(ev.end)) - (s if s is not None else _wall_key(ev.start))
    elif ev.duration is not None:
        length = ev.duration
    else:
        length = DAY_MS if all_day else 0
    base = {"uid": uid, "title": ev.summary or "—", "all_day": all_day, "location": ev.location or None}
    base["note"] = ev.description or None
    if all_day:
        day = date(start.y, start.mo, start.d)
        days = max(1, round(length / DAY_MS))
        end = f"{(day + timedelta(days=days - 1)).isoformat()}T00:00" if days > 1 else None
        return FeedEvent(start=f"{day.isoformat()}T00:00", end=end, **base)
    s_text = _local_text(start, local)
    e_text = _local_text(_shift_wall(start, length), local) if length > 0 else None
    # Shifting on the wall clock keeps the length right across a change to summer time.
    return FeedEvent(start=s_text, end=e_text if e_text and e_text > s_text else None, **base)


def parse_ics(text: str, start: str, end: str, local: tzinfo) -> list[FeedEvent]:
    """All events that touch the days ``start`` to ``end`` (inclusive), in the local time of ``local``."""
    events = _parse_events(text)
    masters = [e for e in events if e.recurrence_id is None]
    moved = [e for e in events if e.recurrence_id is not None]
    to_key = calendar.timegm(date.fromisoformat(end).timetuple()) * 1000 + DAY_MS - 1000 + 2 * DAY_MS
    from_key = calendar.timegm(date.fromisoformat(start).timetuple()) * 1000 - 2 * DAY_MS
    out: list[FeedEvent] = []
    for ev in masters:
        if ev.cancelled:
            continue
        overrides = [m for m in moved if m.uid == ev.uid]
        # An entry that began before the window may still reach into it.
        length = (
            (_wall_key(ev.end) - _wall_key(ev.start))
            if ev.end is not None and ev.start is not None
            else (ev.duration or 0)
        )
        for st in _expand(ev, from_key - max(0, length), to_key):
            if any(_same_moment(o.recurrence_id, st) for o in overrides if o.recurrence_id):
                continue
            uid = f"{ev.uid}@{_local_text(st, local)}" if ev.rrule is not None or ev.rdates else str(ev.uid)
            out.append(_feed_event(ev, st, uid, local))
    for o in moved:
        if o.cancelled or o.recurrence_id is None or o.start is None:
            continue
        out.append(_feed_event(o, o.start, f"{o.uid}@{_local_text(o.recurrence_id, local)}", local))
    out = [e for e in out if e.start[:10] <= end and (e.end or e.start)[:10] >= start]
    out.sort(key=lambda e: (e.start, e.title))
    return out


def feed_url(raw: str) -> str | None:
    """Only HTTPS: ``webcal://`` and ``http://`` become ``https://``. Never an address in the home network."""
    v = re.sub(r"^(webcals?|https?)://", "https://", raw.strip(), flags=re.IGNORECASE)
    if not re.match(r"^https://[^\s/]+\.[^\s]+", v, flags=re.IGNORECASE):
        return None
    try:
        host = (urlsplit(v).hostname or "").lower()
    except ValueError:
        return None
    return None if is_private_host(host) else v


_LOCAL_SUFFIXES = (
    ".localhost",
    ".local",
    ".lan",
    ".home",
    ".internal",
    ".intranet",
    ".corp",
    ".home.arpa",
    ".fritz.box",
)


def is_private_host(host: str) -> bool:
    """Names and addresses inside a home network or on the machine itself, as the app's ``isPrivateHost``."""
    h = host.strip("[]").rstrip(".").lower()
    if "." not in h and ":" not in h:
        return True
    if h in ("localhost", "fritz.box", "speedport.ip") or h.endswith(_LOCAL_SUFFIXES):
        return True
    try:
        return is_private_ip(ipaddress.ip_address(h))
    except ValueError:
        return False


def is_private_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Not a public internet address: private, loopback, link-local, carrier-grade NAT, multicast, reserved."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return not ip.is_global or ip.is_multicast
