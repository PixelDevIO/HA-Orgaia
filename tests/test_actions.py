"""What a tick or a new article sets, worked out as the app does it (packages/core/src/actions.ts)."""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.orgaia.protocol import actions
from custom_components.orgaia.protocol.actions import ActionError, Change
from custom_components.orgaia.protocol.model import Clock, apply_op, empty_state
from custom_components.orgaia.protocol.view import SpaceView, build_view

NOW = 1_795_000_000_000
TODAY = "2026-11-17"


class Group:
    """A group in memory: changes are applied the way they would come back from the service."""

    def __init__(self) -> None:
        self.state = empty_state()
        self.clock = Clock("test0000")
        self.n = 0
        self.set("person", "anna", {"name": "Anna", "order": 1})
        self.set("person", "ben", {"name": "Ben", "order": 2})
        self.set("list", "todo", {"name": "Haushalt", "type": "tasks", "order": 1})
        self.set("list", "shop", {"name": "Einkauf", "type": "shopping", "order": 2})

    def set(self, kind: str, eid: str, fields: dict[str, Any]) -> None:
        apply_op(self.state, {"ts": self.clock.tick(), "k": kind, "e": eid, "set": fields})

    def apply(self, changes: list[Change]) -> None:
        for kind, eid, fields in changes:
            self.set(kind, eid, fields)

    def new_id(self) -> str:
        self.n += 1
        return f"new{self.n}"

    @property
    def view(self) -> SpaceView:
        return build_view("space", "group", self.state)

    def item(self, eid: str) -> dict[str, Any]:
        return self.view.item_by_id[eid]


def test_tick_names_the_person_and_where() -> None:
    g = Group()
    g.set("item", "t1", {"title": "Keller", "listId": "todo"})
    changes = actions.set_done(g.view, g.item("t1"), True, None, "ben", NOW, TODAY)
    assert changes == [("item", "t1", {"done": {"by": "ben", "at": NOW, "via": "ha"}})]
    g.apply(changes)
    assert g.item("t1")["done"]["by"] == "ben"
    g.apply(actions.set_done(g.view, g.item("t1"), False, None, "anna", NOW, TODAY))
    assert g.item("t1")["done"] is None


def test_series_ticks_one_day_only() -> None:
    g = Group()
    g.set("item", "t1", {"title": "Müll", "listId": "todo", "start": f"{TODAY}T19:00", "repeat": {"freq": "day"}})
    with pytest.raises(ActionError, match="needs_date"):
        actions.set_done(g.view, g.item("t1"), True, None, "ben", NOW, TODAY)
    changes = actions.set_done(g.view, g.item("t1"), True, TODAY, "ben", NOW, TODAY)
    assert changes == [("occ", f"t1|{TODAY}", {"done": {"by": "ben", "at": NOW, "via": "ha"}})]


def test_appointments_cannot_be_ticked() -> None:
    g = Group()
    g.set("item", "e1", {"title": "Elternabend", "listId": "todo", "kind": "event", "start": f"{TODAY}T19:00"})
    with pytest.raises(ActionError, match="not_a_task"):
        actions.set_done(g.view, g.item("e1"), True, None, "ben", NOW, TODAY)


def test_each_for_themselves() -> None:
    g = Group()
    g.set("item", "t1", {"title": "Zimmer", "listId": "todo", "mode": "each", "assignees": ["anna", "ben"]})
    g.set("person", "cleo", {"name": "Cleo", "order": 3})
    with pytest.raises(ActionError, match="not_assigned"):
        actions.set_done(g.view, g.item("t1"), True, None, "cleo", NOW, TODAY)
    g.apply(actions.set_done(g.view, g.item("t1"), True, None, "ben", NOW, TODAY))
    assert g.item("t1")["done"] is None and "ben" in g.item("t1")["doneBy"]
    g.apply(actions.set_done(g.view, g.item("t1"), True, None, "anna", NOW + 1, TODAY))
    assert g.item("t1")["done"]["by"] == "anna"


def test_task_that_comes_back_moves_on() -> None:
    g = Group()
    g.set(
        "item",
        "t1",
        {
            "title": "Bad putzen",
            "listId": "todo",
            "again": {"freq": "week", "interval": 2},
            "dueDate": "2026-11-15",
            "from": "2026-11-13",
            "assignees": ["anna"],
            "rotation": ["anna", "ben"],
            "start": "2026-11-15T10:00",
        },
    )
    g.set("sub", "s1", {"title": "Spiegel", "itemId": "t1", "done": True, "order": 1})
    g.apply(actions.set_done(g.view, g.item("t1"), True, None, "anna", NOW, TODAY))
    item = g.item("t1")
    # Open again, two weeks after today, with the same lead time, and it is Ben's turn.
    assert item["done"] is None and item["lastDone"]["by"] == "anna" and item["lastDone"]["via"] == "ha"
    assert item["dueDate"] == "2026-12-01" and item["from"] == "2026-11-29"
    assert item["assignees"] == ["ben"] and not item.get("start")
    assert g.view.subs_by_item["t1"][0]["done"] is False


def test_each_and_coming_back_starts_over_for_all() -> None:
    g = Group()
    g.set(
        "item",
        "t1",
        {
            "title": "Zimmer",
            "listId": "todo",
            "mode": "each",
            "assignees": ["anna", "ben"],
            "again": {"freq": "day", "interval": 1},
        },
    )
    g.apply(actions.set_done(g.view, g.item("t1"), True, None, "ben", NOW, TODAY))
    g.apply(actions.set_done(g.view, g.item("t1"), True, None, "anna", NOW + 1, TODAY))
    item = g.item("t1")
    assert item["done"] is None and not item.get("doneBy") and item["dueDate"] == "2026-11-18"


def test_work_block_ticks_its_parts() -> None:
    g = Group()
    g.set("item", "a", {"title": "Saugen", "listId": "todo"})
    g.set("item", "b", {"title": "Wischen", "listId": "todo", "done": {"by": "anna", "at": 1}})
    g.set("item", "block", {"title": "Putzen", "listId": "todo", "bundle": ["a", "b"]})
    changes = actions.set_done(g.view, g.item("block"), True, None, "ben", NOW, TODAY)
    assert [c[1] for c in changes] == ["a", "block"]


def test_articles() -> None:
    g = Group()
    g.apply(actions.add_article(g.view, "shop", "  Milch ", "2 l", "ben", NOW, g.new_id))
    milk = g.item("new1")
    assert milk["title"] == "Milch" and milk["qty"] == "2 l" and milk["createdBy"] == "ben" and "late" not in milk
    # Typed again while it is still open: no second line.
    assert actions.add_article(g.view, "shop", "milch", None, "anna", NOW, g.new_id)[0][1] == "new1"
    with pytest.raises(ActionError, match="not_shopping"):
        actions.add_article(g.view, "todo", "Milch", None, "ben", NOW, g.new_id)
    with pytest.raises(ActionError, match="empty"):
        actions.add_article(g.view, "shop", "   ", None, "ben", NOW, g.new_id)
    with pytest.raises(ActionError, match="not_tasks"):
        actions.add_task(g.view, "shop", "Keller", "ben", NOW, g.new_id)
    g.apply(actions.add_task(g.view, "todo", "Keller", "ben", NOW, g.new_id, "2026-11-20", ["anna"]))
    assert g.item("new2")["dueDate"] == "2026-11-20" and g.item("new2")["assignees"] == ["anna"]


def test_shopping_from_release_to_done() -> None:
    g = Group()
    with pytest.raises(ActionError, match="nothing_to_buy"):
        actions.release_list(g.view, "shop", "anna", NOW)
    g.apply(actions.add_article(g.view, "shop", "Milch", None, "anna", NOW, g.new_id))
    g.apply(actions.add_article(g.view, "shop", "Brot", None, "anna", NOW, g.new_id))
    with pytest.raises(ActionError, match="not_released"):
        actions.take_trip(g.view, "shop", "ben", NOW)
    g.apply(actions.release_list(g.view, "shop", "anna", NOW, "2026-11-18", ["ben"], " Bio "))
    ready = g.view.list_by_id["shop"]["ready"]
    assert ready == {"by": "anna", "at": NOW, "due": "2026-11-18", "for": ["ben"], "note": "Bio"}

    # What comes onto the list now is marked as new.
    g.apply(actions.add_article(g.view, "shop", "Eier", None, "anna", NOW + 5, g.new_id))
    assert g.item("new3")["late"] == NOW + 5 and g.item("new3")["lateBy"] == "anna"

    g.apply(actions.take_trip(g.view, "shop", "ben", NOW + 10))
    assert g.view.list_by_id["shop"]["takes"] == {"ben": {"at": NOW + 10, "r": NOW}}
    assert actions.take_trip(g.view, "shop", "ben", NOW + 11) == []
    g.apply(actions.drop_trip(g.view, "shop", "ben"))
    assert not g.view.list_by_id["shop"].get("takes")
    g.apply(actions.take_trip(g.view, "shop", "ben", NOW + 20))

    g.apply(actions.set_done(g.view, g.item("new1"), True, None, "ben", NOW + 30, TODAY))
    g.apply(actions.finish_trip(g.view, "shop", "ben", NOW + 40))
    lst = g.view.list_by_id["shop"]
    assert "ready" not in lst and lst["lastTrip"] == {"by": "ben", "at": NOW + 40, "n": 1, "left": 2}
    assert sorted(i["title"] for i in g.view.items if i["listId"] == "shop") == ["Brot", "Eier"]

    g.apply(actions.release_list(g.view, "shop", "anna", NOW + 50))
    g.apply(actions.withdraw_release(g.view, "shop"))
    assert "ready" not in g.view.list_by_id["shop"]


def test_list_without_release() -> None:
    g = Group()
    g.set("list", "shop", {"gate": False})
    g.apply(actions.add_article(g.view, "shop", "Milch", None, "anna", NOW, g.new_id))
    with pytest.raises(ActionError, match="no_release"):
        actions.release_list(g.view, "shop", "anna", NOW)
