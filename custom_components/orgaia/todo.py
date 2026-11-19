"""To-do lists: one per task and shopping list of the group, and one per person with everything assigned to them.

A standard to-do card cannot ask who ticks off. So they tick off and add only for a Home Assistant
user who is assigned to a person of the group (Configure › People), once an admin allowed writing in
the app. A voice assistant knows no user: it may put articles on a shopping list in the name of the
person chosen for it under Configure › Settings, and do nothing else. Everybody else uses the Orgaia
card, which asks who it is.
"""

from __future__ import annotations

import time
from typing import Any

from homeassistant.components.todo import TodoItem, TodoItemStatus, TodoListEntity, TodoListEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import OrgaiaConfigEntry, OrgaiaCoordinator
from .entity import completed_days, list_shown, person_entity, person_ids_for, space_key, track_dynamic
from .protocol import actions
from .protocol.actions import ActionError
from .protocol.shopping import AISLE_NAMES, parse_articles, trip_of
from .summary import TodoEntry, todo_entries, todo_lists
from .util import from_ms, to_date, to_datetime, today
from .writing import Writer, fail


async def async_setup_entry(
    hass: HomeAssistant, entry: OrgaiaConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    # Rosters were shown as (empty) to-do lists before 0.3; their entities go.
    prefix = f"{space_key(entry)}_list_"
    lists = {prefix + lst["id"] for lst in todo_lists(coordinator.data) if list_shown(entry, lst["id"])}
    registry = er.async_get(hass)
    for reg in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg.domain == "todo" and reg.unique_id.startswith(prefix) and reg.unique_id not in lists:
            registry.async_remove(reg.entity_id)
    track_dynamic(
        hass,
        entry,
        lambda view: [lst["id"] for lst in todo_lists(view) if list_shown(entry, lst["id"])],
        lambda list_id: [OrgaiaTodoList(coordinator, list_id)],
        async_add_entities,
        "todo",
    )
    track_dynamic(
        hass,
        entry,
        person_ids_for(entry),
        lambda person_id: [OrgaiaPersonTodo(coordinator, person_id)],
        async_add_entities,
        "todo",
    )


MISSED_LABEL = {"de": "nicht bekommen", "en": "not got"}


def _description(
    e: TodoEntry, with_persons: bool = True, list_name: str | None = None, language: str | None = None
) -> str | None:
    lang = (language or "de").split("-")[0].lower()
    parts = []
    if list_name:
        parts.append("📋 " + list_name)
    if with_persons and e.persons:
        parts.append("👤 " + ", ".join(e.persons))
    if e.late:
        # Came onto the list after it was released, as the app's mark "new".
        parts.append("🆕")
    if e.missed_by is not None:
        who = f" ({e.missed_by})" if e.missed_by else ""
        parts.append(f"✗ {MISSED_LABEL.get(lang, MISSED_LABEL['en'])}{who}")
    if e.aisle:
        parts.append("🏷 " + AISLE_NAMES.get(lang, AISLE_NAMES["en"])[e.aisle])
    if e.note:
        parts.append(e.note)
    if e.subtasks:
        parts.append("\n".join(("☑ " if done else "☐ ") + title for title, done in e.subtasks))
    return "\n\n".join(parts) or None


def _item(e: TodoEntry, description: str | None) -> TodoItem:
    return TodoItem(
        summary=f"{e.title} ({e.qty})" if e.qty else e.title,
        uid=e.uid,
        status=TodoItemStatus.COMPLETED if e.done else TodoItemStatus.NEEDS_ACTION,
        due=(to_datetime(e.due) if len(e.due) > 10 else to_date(e.due)) if e.due else None,
        description=description,
        completed=from_ms(e.done_at) if e.done else None,
    )


class _Writable(Writer, TodoListEntity):
    """Ticks off and adds in the name of the person the Home Assistant user is."""

    list_id: str | None = None

    @property
    def supported_features(self) -> TodoListEntityFeature:
        if not self.coordinator.engine.can_write:
            return TodoListEntityFeature(0)
        return self._features()

    def _features(self) -> TodoListEntityFeature:
        return TodoListEntityFeature.UPDATE_TODO_ITEM

    def _entries(self) -> list[TodoEntry]:
        raise NotImplementedError

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Ticking off or opening again; everything else is changed in the app."""
        entry = next((e for e in self._entries() if e.uid == item.uid), None)
        if entry is None:
            raise fail("no_item", item=item.uid or "")
        wanted = item.status == TodoItemStatus.COMPLETED
        shown = f"{entry.title} ({entry.qty})" if entry.qty else entry.title
        if item.summary not in (None, shown) and wanted == entry.done:
            raise fail("change_in_app")
        if wanted == entry.done:
            return
        person = self._person()
        view = self.coordinator.data
        try:
            changes = actions.set_done(
                view, view.item_by_id[entry.item_id], wanted, entry.occ_date, person, int(time.time() * 1000), today()
            )
        except ActionError as err:
            raise fail(err.reason) from err
        await self._write(changes, person)


class OrgaiaTodoList(_Writable):
    _attr_translation_key = "list"
    # Names and notes stay out of the recorder's database.
    _unrecorded_attributes = frozenset({"released_by", "for", "note", "shopper", "shopper_entity"})

    def __init__(self, coordinator: OrgaiaCoordinator, list_id: str) -> None:
        super().__init__(coordinator, f"list_{list_id}")
        self.list_id = list_id

    def _features(self) -> TodoListEntityFeature:
        lst = self.coordinator.data.list_by_id.get(self.list_id or "") or {}
        if lst.get("type") in ("tasks", "shopping"):
            return TodoListEntityFeature.UPDATE_TODO_ITEM | TodoListEntityFeature.CREATE_TODO_ITEM
        # A timetable's packing tasks are ticked off, never added.
        return TodoListEntityFeature.UPDATE_TODO_ITEM

    def _entries(self) -> list[TodoEntry]:
        return todo_entries(
            self.coordinator.data, today(), completed_days(self.coordinator.config_entry), list_id=self.list_id
        )

    async def async_create_todo_item(self, item: TodoItem) -> None:
        view = self.coordinator.data
        lst = view.list_by_id.get(self.list_id or "")
        if not lst:
            raise fail("no_list", list=self.list_id or "")
        shopping = lst["type"] == "shopping"
        person = self._person(adding_article=shopping)
        now = int(time.time() * 1000)
        try:
            if shopping:
                many = parse_articles(item.summary or "")
                changes = actions.add_articles(view, lst["id"], many, person, now, self.coordinator.engine.new_id)
            else:
                due = item.due.isoformat()[:10] if item.due else None
                changes = actions.add_task(
                    view, lst["id"], item.summary or "", person, now, self.coordinator.engine.new_id, due
                )
        except ActionError as err:
            raise fail(err.reason) from err
        await self._write(changes, person)

    @property
    def name(self) -> str | None:
        lst = self.coordinator.data.list_by_id.get(self.list_id)
        return lst["name"] if lst else None

    @property
    def icon(self) -> str:
        lst = self.coordinator.data.list_by_id.get(self.list_id) or {}
        return "mdi:cart-outline" if lst.get("type") == "shopping" else "mdi:format-list-checks"

    @property
    def available(self) -> bool:
        return super().available and self.list_id in self.coordinator.data.list_by_id

    @property
    def todo_items(self) -> list[TodoItem]:
        entries = self._entries()
        language = self.hass.config.language if self.hass else None
        return [_item(e, _description(e, language=language)) for e in entries]

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """For a shopping list: whether it is still being written, released, or somebody is shopping."""
        view = self.coordinator.data
        lst = view.list_by_id.get(self.list_id)
        if not lst or lst["type"] != "shopping":
            return None
        trip = trip_of(view, lst)
        ready = trip.ready or {}
        released = from_ms(ready.get("at"))
        entry = self.coordinator.config_entry

        def name(pid: str | None) -> str | None:
            return (view.person_by_id.get(pid) or {}).get("name") if pid else None

        return {
            "list_id": self.list_id,
            "list_type": "shopping",
            "shopping_state": trip.state,
            "open": trip.open,
            "bought": trip.bought,
            "released_by": name(ready.get("by")),
            "released_at": released.isoformat() if released else None,
            "due": ready.get("due"),
            "for": view.names(ready.get("for") or []),
            "note": ready.get("note"),
            "shopper": name(trip.shopper),
            "shopper_entity": person_entity(entry, trip.shopper) if trip.shopper else None,
            "not_got": sum(
                1 for i in view.items if i["listId"] == self.list_id and not i.get("done") and i.get("missed")
            ),
            "fixed_purchases": [x["name"] for x in lst.get("sets") or []],
        }


class OrgaiaPersonTodo(_Writable):
    """Everything assigned to one person, from all task lists of the group."""

    _attr_translation_key = "person_tasks"
    _attr_icon = "mdi:account-check-outline"

    def __init__(self, coordinator: OrgaiaCoordinator, person_id: str) -> None:
        super().__init__(coordinator, "tasks", person_id)

    def _entries(self) -> list[TodoEntry]:
        return todo_entries(
            self.coordinator.data, today(), completed_days(self.coordinator.config_entry), person=self.person_id
        )

    @property
    def todo_items(self) -> list[TodoItem]:
        view = self.coordinator.data
        entries = self._entries()
        return [
            _item(e, _description(e, with_persons=False, list_name=(view.list_by_id.get(e.list_id) or {}).get("name")))
            for e in entries
        ]
