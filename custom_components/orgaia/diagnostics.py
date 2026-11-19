"""Diagnostics for bug reports. Holds no content of the group and no keys: only counts and states."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from homeassistant.core import HomeAssistant

from .const import CARD_URL, CONF_LISTS, CONF_PERSON_DEVICES, CONF_PERSONS, CONF_VOICE_PERSON, VERSION
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
        "can_write": engine.can_write,
        "write_refused": coordinator.write_refused,
        "live": {
            "connected": coordinator.live,
            "since": coordinator.live_since,
            "reconnects": coordinator.live_reconnects,
            "last_error": coordinator.live_error,
        },
        "last_sync": engine.synced_at,
        "feeds": coordinator.feeds.status(),
        "plans": {
            "timetables": sum(1 for lst in view.lists if lst["type"] == "timetable"),
            "rosters": sum(1 for lst in view.lists if lst["type"] == "roster"),
        },
        "options": {
            "persons_assigned": len(entry.options.get(CONF_PERSONS) or {}),
            "voice_person": bool(entry.options.get(CONF_VOICE_PERSON)),
            "lists_chosen": len(entry.options.get(CONF_LISTS) or []),
            "person_devices": entry.options.get(CONF_PERSON_DEVICES, True),
        },
        "card_resource": _card_listed(hass),
    }


def _card_listed(hass: HomeAssistant) -> bool | None:
    """Whether the card is among the dashboard resources; None where they are written in YAML."""
    lovelace = hass.data.get("lovelace")
    resources = getattr(lovelace, "resources", None)
    if resources is None or getattr(lovelace, "resource_mode", None) != "storage" or not resources.loaded:
        return None
    return any(str(r.get("url", "")).split("?")[0] == CARD_URL for r in resources.async_items())
