"""Entries of subscribed calendars as read-only appointments, as Orgaia's ``feedItems`` and ``withFeedItems``.

Each device fetches a subscribed calendar itself (see ``ics``); only the address and who it is for are
part of the group. The entries are never stored in the group and never fire "created" or "changed".
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from .ics import FeedEvent
from .plan_read import _fnv
from .view import SpaceView

FEED_PREFIX = "feed~"


def is_feed_item(item: dict[str, Any]) -> bool:
    return str(item.get("id", "")).startswith(FEED_PREFIX)


def feed_items(list_id: str, events: list[FeedEvent], persons: list[str]) -> list[dict[str, Any]]:
    used: set[str] = set()
    out = []
    for e in events:
        item_id = f"{FEED_PREFIX}{list_id}~{_fnv(e.uid)}"
        n = 2
        while item_id in used:
            item_id = f"{FEED_PREFIX}{list_id}~{_fnv(e.uid)}-{n}"
            n += 1
        used.add(item_id)
        item: dict[str, Any] = {
            "id": item_id,
            "listId": list_id,
            "kind": "event",
            "title": e.title,
            "start": e.start,
            "allDay": e.all_day,
            "assignees": list(persons),
            "done": None,
        }
        if e.end:
            item["end"] = e.end
        if e.location:
            item["location"] = e.location
        if e.note:
            item["note"] = e.note
        out.append(item)
    return out


def with_feed_items(view: SpaceView, by_list: dict[str, list[FeedEvent]]) -> SpaceView:
    """A copy of the view that also holds the entries of its subscribed calendars."""
    extra: list[dict[str, Any]] = []
    for lst in view.lists:
        if lst["type"] != "feed":
            continue
        events = by_list.get(lst["id"])
        if events:
            extra.extend(feed_items(lst["id"], events, lst.get("feedFor") or []))
    if not extra:
        return view
    items = [*view.items, *extra]
    return replace(view, items=items, item_by_id={i["id"]: i for i in items})
