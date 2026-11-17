"""Each task and shopping list of the group as a to-do list. Read only for now: changes are made in the app."""

from __future__ import annotations

from homeassistant.components.todo import TodoItem, TodoItemStatus, TodoListEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import COMPLETED_DAYS, DOMAIN
from .coordinator import OrgaiaConfigEntry, OrgaiaCoordinator
from .entity import OrgaiaEntity
from .summary import TodoEntry, todo_entries, todo_lists
from .util import from_ms, to_date, to_datetime, today


async def async_setup_entry(
    hass: HomeAssistant, entry: OrgaiaConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    known: dict[str, OrgaiaTodoList] = {}

    @callback
    def _sync_lists() -> None:
        current = {lst["id"] for lst in todo_lists(coordinator.data)}
        new = [OrgaiaTodoList(coordinator, list_id) for list_id in current if list_id not in known]
        for entity in new:
            known[entity.list_id] = entity
        if new:
            async_add_entities(new)
        registry = er.async_get(hass)
        for list_id in [i for i in known if i not in current]:
            entity = known.pop(list_id)
            if entity_id := registry.async_get_entity_id("todo", DOMAIN, entity.unique_id or ""):
                registry.async_remove(entity_id)

    _sync_lists()
    entry.async_on_unload(coordinator.async_add_listener(_sync_lists))


def _description(e: TodoEntry) -> str | None:
    parts = []
    if e.persons:
        parts.append("👤 " + ", ".join(e.persons))
    if e.note:
        parts.append(e.note)
    if e.subtasks:
        parts.append("\n".join(("☑ " if done else "☐ ") + title for title, done in e.subtasks))
    return "\n\n".join(parts) or None


class OrgaiaTodoList(OrgaiaEntity, TodoListEntity):
    _attr_translation_key = "list"

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
        entries = todo_entries(self.coordinator.data, self.list_id, today(), COMPLETED_DAYS)
        return [
            TodoItem(
                summary=e.title,
                uid=e.uid,
                status=TodoItemStatus.COMPLETED if e.done else TodoItemStatus.NEEDS_ACTION,
                due=(to_datetime(e.due) if len(e.due) > 10 else to_date(e.due)) if e.due else None,
                description=_description(e),
                completed=from_ms(e.done_at) if e.done else None,
            )
            for e in entries
        ]
