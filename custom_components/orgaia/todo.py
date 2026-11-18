"""To-do lists: one per task and shopping list of the group, and one per person with everything assigned to them.

They show only: a standard to-do card cannot ask who ticks off. That is what the Orgaia card and the
actions in services.py are for.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.todo import TodoItem, TodoItemStatus, TodoListEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import COMPLETED_DAYS
from .coordinator import OrgaiaConfigEntry, OrgaiaCoordinator
from .entity import OrgaiaEntity, active_person_ids, person_entity, space_key, track_dynamic
from .protocol.shopping import trip_of
from .summary import TodoEntry, todo_entries, todo_lists
from .util import from_ms, to_date, to_datetime, today


async def async_setup_entry(
    hass: HomeAssistant, entry: OrgaiaConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    # Rosters were shown as (empty) to-do lists before 0.3; their entities go.
    prefix = f"{space_key(entry)}_list_"
    lists = {prefix + lst["id"] for lst in todo_lists(coordinator.data)}
    registry = er.async_get(hass)
    for reg in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg.domain == "todo" and reg.unique_id.startswith(prefix) and reg.unique_id not in lists:
            registry.async_remove(reg.entity_id)
    track_dynamic(
        hass,
        entry,
        lambda view: [lst["id"] for lst in todo_lists(view)],
        lambda list_id: [OrgaiaTodoList(coordinator, list_id)],
        async_add_entities,
        "todo",
    )
    track_dynamic(
        hass,
        entry,
        active_person_ids,
        lambda person_id: [OrgaiaPersonTodo(coordinator, person_id)],
        async_add_entities,
        "todo",
    )


def _description(e: TodoEntry, with_persons: bool = True, list_name: str | None = None) -> str | None:
    parts = []
    if list_name:
        parts.append("📋 " + list_name)
    if with_persons and e.persons:
        parts.append("👤 " + ", ".join(e.persons))
    if e.late:
        # Came onto the list after it was released, as the app's mark "new".
        parts.append("🆕")
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


class OrgaiaTodoList(OrgaiaEntity, TodoListEntity):
    _attr_translation_key = "list"
    # Names and notes stay out of the recorder's database.
    _unrecorded_attributes = frozenset({"released_by", "for", "note", "shopper", "shopper_entity"})

    def __init__(self, coordinator: OrgaiaCoordinator, list_id: str) -> None:
        super().__init__(coordinator, f"list_{list_id}")
        self.list_id = list_id

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
        entries = todo_entries(self.coordinator.data, today(), COMPLETED_DAYS, list_id=self.list_id)
        return [_item(e, _description(e)) for e in entries]

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
        }


class OrgaiaPersonTodo(OrgaiaEntity, TodoListEntity):
    """Everything assigned to one person, from all task lists of the group."""

    _attr_translation_key = "person_tasks"
    _attr_icon = "mdi:account-check-outline"

    def __init__(self, coordinator: OrgaiaCoordinator, person_id: str) -> None:
        super().__init__(coordinator, "tasks", person_id)

    @property
    def todo_items(self) -> list[TodoItem]:
        view = self.coordinator.data
        entries = todo_entries(view, today(), COMPLETED_DAYS, person=self.person_id)
        return [
            _item(e, _description(e, with_persons=False, list_name=(view.list_by_id.get(e.list_id) or {}).get("name")))
            for e in entries
        ]
