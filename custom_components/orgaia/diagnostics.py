"""Diagnostics for bug reports. Holds no content of the group and no keys: only counts and states."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from homeassistant.core import HomeAssistant

from .const import VERSION
from .coordinator import OrgaiaConfigEntry


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: OrgaiaConfigEntry) -> dict[str, Any]:
    coordinator = entry.runtime_data
    engine = coordinator.engine
    view = engine.view()
    return {
        "version": VERSION,
        "server": urlparse(engine.server).hostname,
        "status": engine.status,
        "last_update_success": coordinator.last_update_success,
        "epoch": engine.epoch,
        "known_epochs": sorted(engine.keys),
        "cursor": engine.cursor,
        "plan": engine.plan,
        "members": {
            "total": len(engine.members),
            "admins": sum(1 for m in engine.members if m.get("role") == "admin"),
            "integrations": sum(1 for m in engine.members if m.get("kind") == "integration"),
        },
        "persons": len(view.active_persons()),
        "lists": {t: sum(1 for lst in view.lists if lst["type"] == t) for t in ("tasks", "shopping", "feed")},
        "items": {
            "tasks": sum(1 for i in view.items if i["kind"] == "task"),
            "events": sum(1 for i in view.items if i["kind"] == "event"),
            "repeating": sum(1 for i in view.items if i.get("repeat")),
        },
        "exceptions": len(view.occs),
    }
