"""Releasing a shopping list, as Orgaia's packages/core/src/shopping-read.ts and shopping-trip.ts.

A shopping list of a group is written by everybody until somebody says it is complete. Only then is
it something to do: whoever is out anyway takes it over, and ends the trip when done.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

TAKE_PREFIX = "take."
TRIP_PREFIX = "trip~"

_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

# off: no release for this list. draft: still being written. ready: released, nobody goes yet.
# going: somebody took it over.
STATE_OFF = "off"
STATE_DRAFT = "draft"
STATE_READY = "ready"
STATE_GOING = "going"


def _num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x == x and x not in (float("inf"), -float("inf"))


def read_trip(raw: dict[str, Any]) -> dict[str, Any]:
    """The release of a shopping list from its fields. Another member could send anything, so all is checked."""
    out: dict[str, Any] = {}
    if raw.get("gate") is False:
        out["gate"] = False
    r = raw.get("ready")
    if isinstance(r, dict) and isinstance(r.get("by"), str) and _num(r.get("at")):
        ready: dict[str, Any] = {"by": r["by"], "at": r["at"]}
        if isinstance(r.get("due"), str) and _DATE.fullmatch(r["due"]):
            ready["due"] = r["due"]
        who = [p for p in r["for"] if isinstance(p, str)] if isinstance(r.get("for"), list) else []
        if who:
            ready["for"] = who
        if isinstance(r.get("note"), str) and r["note"].strip():
            ready["note"] = r["note"].strip()[:200]
        out["ready"] = ready
        # Only answers to this very release count.
        takes = {
            k[len(TAKE_PREFIX) :]: {"at": v["at"], "r": v["r"]}
            for k, v in raw.items()
            if k.startswith(TAKE_PREFIX) and isinstance(v, dict) and _num(v.get("at")) and v.get("r") == r["at"]
        }
        if takes:
            out["takes"] = takes
    last = raw.get("lastTrip")
    if isinstance(last, dict) and isinstance(last.get("by"), str) and _num(last.get("at")):
        out["lastTrip"] = {
            "by": last["by"],
            "at": last["at"],
            "n": int(last["n"]) if _num(last.get("n")) else 0,
            "left": int(last["left"]) if _num(last.get("left")) else 0,
        }
    return out


@dataclass(frozen=True)
class Trip:
    state: str
    open: int
    bought: int
    ready: dict[str, Any] | None = None
    # Person id of who shops, and since when.
    shopper: str | None = None
    since: float | None = None


def has_gate(view: Any, lst: dict[str, Any]) -> bool:
    """Whether a list can be released at all."""
    return view.kind == "group" and lst["type"] == "shopping" and lst.get("gate") is not False


def shopper_of(view: Any, lst: dict[str, Any]) -> tuple[str, float] | None:
    """Who took the list over: the first to say so; two at the same moment are settled by their ids."""
    best: tuple[str, float] | None = None
    for pid, take in (lst.get("takes") or {}).items():
        p = view.person_by_id.get(pid)
        if not p or p["removed"]:
            continue
        if best is None or take["at"] < best[1] or (take["at"] == best[1] and pid < best[0]):
            best = (pid, take["at"])
    return best


def trip_of(view: Any, lst: dict[str, Any]) -> Trip:
    items = [i for i in view.items if i["listId"] == lst["id"]]
    n_open = sum(1 for i in items if not i.get("done"))
    bought = len(items) - n_open
    if not has_gate(view, lst):
        return Trip(STATE_OFF, n_open, bought)
    ready = lst.get("ready")
    if not ready:
        return Trip(STATE_DRAFT, n_open, bought)
    shopper = shopper_of(view, lst)
    if shopper:
        return Trip(STATE_GOING, n_open, bought, ready, shopper[0], shopper[1])
    return Trip(STATE_READY, n_open, bought, ready)


def trip_overdue(trip: Trip, today: str) -> bool:
    """Past its day without anybody having bought it."""
    due = (trip.ready or {}).get("due")
    return trip.state in (STATE_READY, STATE_GOING) and bool(due) and due < today


def is_late(item: dict[str, Any], trip: Trip) -> bool:
    """An article that came onto the list after it was released."""
    late = item.get("late")
    return bool(trip.ready) and not item.get("done") and _num(late) and late >= trip.ready["at"]
