"""What can be done to a group from Home Assistant, as packages/core/src/actions.ts and shopping-trip.ts.

Every function works out the fields to set and returns them as changes; nothing is sent here. All of
it happens in the name of a person of the group: at Home Assistant somebody first says who they are.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .recur import add_days, add_months, days_between, parse_ymd
from .shopping import STATE_OFF, TAKE_PREFIX, has_gate, trip_of
from .view import DONE_PREFIX, SpaceView, each_done, occ_id

# One kind of entity, its id and the fields to set.
Change = tuple[str, str, dict[str, Any]]

# Marks a tick as made at Home Assistant: the app then says "via Home Assistant" next to the name.
VIA = "ha"
MAX_TITLE = 200


class ActionError(Exception):
    """It cannot be done, and why: ``not_a_task``, ``needs_date``, ``not_assigned``, ``not_shopping``, …"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _mark(person: str, now: int) -> dict[str, Any]:
    return {"by": person, "at": now, "via": VIA}


def next_again(again: dict[str, Any], start: str) -> str:
    """The date a task that comes back is due next, counted from ``start``."""
    try:
        step = max(1, int(again.get("interval") or 1))
    except (TypeError, ValueError):
        step = 1
    freq = again.get("freq")
    if freq == "day":
        return add_days(start, step)
    if freq == "week":
        return add_days(start, step * 7)
    return add_months(start, step if freq == "month" else step * 12, parse_ymd(start).day)


def _come_back(
    view: SpaceView, item: dict[str, Any], mark: dict[str, Any], today: str, extra: dict[str, Any] | None = None
) -> list[Change]:
    """Done with a task that comes back: it stays open and moves on, due one interval after today."""
    due = next_again(item["again"], today)
    inherited = item.get("fromList") or []
    fields: dict[str, Any] = {
        **(extra or {}),
        "done": None,
        "lastDone": mark,
        "dueDate": due,
        "start": None,
        "end": None,
        "plannedBy": None,
    }
    if item.get("from") and item.get("dueDate") and "from" not in inherited:
        fields["from"] = add_days(due, -max(0, days_between(item["from"], item["dueDate"])))
    elif item.get("from"):
        fields["from"] = None
    rota = [p for p in item.get("rotation") or [] if isinstance(p, str)]
    if len(rota) > 1:
        first = (item.get("assignees") or [""])[0]
        at = rota.index(first) if first in rota else -1
        fields["assignees"] = [rota[(at + 1) % len(rota)]]
    out: list[Change] = [("item", item["id"], fields)]
    out.extend(("sub", sub["id"], {"done": False}) for sub in view.subs_by_item.get(item["id"], []) if sub["done"])
    return out


def set_done(
    view: SpaceView,
    item: dict[str, Any],
    done: bool,
    occ_date: str | None,
    person: str,
    now: int,
    today: str,
) -> list[Change]:
    """Ticks a task off, or opens it again. Of a repeating task only one day is ticked off."""
    if item.get("kind") != "task":
        raise ActionError("not_a_task")
    repeat = bool(item.get("repeat"))
    if repeat and not occ_date:
        raise ActionError("needs_date")
    mark = _mark(person, now) if done else None
    # "Each for themselves": everybody ticks off their own part; the whole is done once all did.
    if item.get("mode") == "each":
        if person not in (item.get("assignees") or []):
            raise ActionError("not_assigned")
        field = DONE_PREFIX + person
        if repeat:
            return [("occ", occ_id(item["id"], occ_date or ""), {field: mark})]
        out: list[Change] = [("item", item["id"], {field: mark})]
        marks = {**(item.get("doneBy") or {}), person: mark}
        if item.get("again") and mark and each_done(item.get("assignees") or [], marks):
            # The last one done: a task that comes back starts its next round for everybody.
            out.extend(_come_back(view, item, mark, today, {DONE_PREFIX + p: None for p in marks}))
        return out
    if isinstance(item.get("again"), dict) and mark and not repeat:
        return _come_back(view, item, mark, today)
    out = []
    bundle = [b for b in item.get("bundle") or [] if isinstance(b, str)]
    if bundle and not repeat:
        # A work block: ticking it off ticks off what is in it.
        for part_id in bundle:
            part = view.item_by_id.get(part_id)
            if part and not part.get("repeat") and not part.get("bundle") and bool(part.get("done")) != done:
                out.extend(set_done(view, part, done, None, person, now, today))
    if repeat:
        out.append(("occ", occ_id(item["id"], occ_date or ""), {"done": mark}))
    else:
        out.append(("item", item["id"], {"done": mark}))
    return out


def _clean(title: str) -> str:
    clean = " ".join(title.split())[:MAX_TITLE]
    if not clean:
        raise ActionError("empty")
    return clean


def add_article(
    view: SpaceView,
    list_id: str,
    title: str,
    qty: str | None,
    person: str,
    now: int,
    new_id: Callable[[], str],
) -> list[Change]:
    """Puts an article on a shopping list, or opens it again when it is there as bought.

    On a list that was already released it is marked as new, so whoever shops sees it came later.
    """
    lst = view.list_by_id.get(list_id)
    if not lst or lst["type"] != "shopping":
        raise ActionError("not_shopping")
    clean = _clean(title)
    amount = qty.strip()[:40] if isinstance(qty, str) and qty.strip() else None
    late = {"late": now, "lateBy": person} if lst.get("ready") else {}
    existing = next(
        (i for i in view.items if i["listId"] == list_id and i["title"].casefold() == clean.casefold()), None
    )
    if existing:
        # Something still open on the list is not new just because somebody put it on again.
        fields = {"done": None, "qty": amount or existing.get("qty") or None, "order": now}
        return [("item", existing["id"], {**fields, **(late if existing.get("done") else {})})]
    fields = {"kind": "task", "createdAt": now, "createdBy": person, "listId": list_id, "title": clean, "order": now}
    if amount:
        fields["qty"] = amount
    return [("item", new_id(), {**fields, **late})]


def add_task(
    view: SpaceView,
    list_id: str,
    title: str,
    person: str,
    now: int,
    new_id: Callable[[], str],
    due: str | None = None,
    assignees: list[str] | None = None,
) -> list[Change]:
    """A new task on a task list."""
    lst = view.list_by_id.get(list_id)
    if not lst or lst["type"] != "tasks":
        raise ActionError("not_tasks")
    fields: dict[str, Any] = {
        "kind": "task",
        "createdAt": now,
        "createdBy": person,
        "listId": list_id,
        "title": _clean(title),
    }
    if due:
        fields["dueDate"] = due
    if assignees:
        fields["assignees"] = assignees
    return [("item", new_id(), fields)]


def _shopping(view: SpaceView, list_id: str) -> dict[str, Any]:
    lst = view.list_by_id.get(list_id)
    if not lst or lst["type"] != "shopping":
        raise ActionError("not_shopping")
    if not has_gate(view, lst) or trip_of(view, lst).state == STATE_OFF:
        raise ActionError("no_release")
    return lst


def release_list(
    view: SpaceView,
    list_id: str,
    person: str,
    now: int,
    due: str | None = None,
    for_persons: list[str] | None = None,
    note: str | None = None,
) -> list[Change]:
    """Says the list is complete: from now on it is something to do."""
    lst = _shopping(view, list_id)
    if not trip_of(view, lst).open:
        raise ActionError("nothing_to_buy")
    ready: dict[str, Any] = {"by": person, "at": now}
    if due:
        ready["due"] = due
    if for_persons:
        ready["for"] = for_persons
    if note and note.strip():
        ready["note"] = note.strip()[:200]
    return [("list", list_id, {"ready": ready})]


def withdraw_release(view: SpaceView, list_id: str) -> list[Change]:
    """Takes the release back: the list is being written again."""
    _shopping(view, list_id)
    return [("list", list_id, {"ready": None})]


def take_trip(view: SpaceView, list_id: str, person: str, now: int) -> list[Change]:
    """ "I'll do it". Whoever said it first shops."""
    lst = _shopping(view, list_id)
    ready = lst.get("ready")
    if not ready:
        raise ActionError("not_released")
    if person in (lst.get("takes") or {}):
        return []
    return [("list", list_id, {TAKE_PREFIX + person: {"at": now, "r": ready["at"]}})]


def drop_trip(view: SpaceView, list_id: str, person: str) -> list[Change]:
    """ "Not after all": the list is open for the others again. What was ticked off stays ticked off."""
    _shopping(view, list_id)
    return [("list", list_id, {TAKE_PREFIX + person: None})]


def finish_trip(view: SpaceView, list_id: str, person: str, now: int) -> list[Change]:
    """Ends the trip: what was bought goes, what was not stays, and the list is being written again."""
    lst = _shopping(view, list_id)
    if not lst.get("ready"):
        raise ActionError("not_released")
    items = [i for i in view.items if i["listId"] == list_id]
    bought = [i for i in items if i.get("done")]
    out: list[Change] = [("item", i["id"], {"deleted": True, "deletedAt": None}) for i in bought]
    last = {"by": person, "at": now, "n": len(bought), "left": len(items) - len(bought)}
    out.append(("list", list_id, {"ready": None, "lastTrip": last}))
    return out
