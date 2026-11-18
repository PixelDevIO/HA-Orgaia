"""What the Orgaia card shows: the group's lists with their entries, and who can say "that was me".

The card gets this over Home Assistant's websocket connection, again whenever the group changes.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
import voluptuous as vol

from .const import COMPLETED_DAYS, CONF_PERSONS, DOMAIN
from .coordinator import OrgaiaConfigEntry, OrgaiaCoordinator
from .protocol.shopping import trip_of, trip_overdue
from .protocol.view import SpaceView, occ_id
from .summary import TodoEntry, todo_entries, todo_lists
from .util import today


def _own_ticks(view: SpaceView, e: TodoEntry) -> list[str] | None:
    """For "each for themselves": who ticked off their part already."""
    item = view.item_by_id.get(e.item_id) or {}
    if item.get("mode") != "each":
        return None
    marks = (view.occs.get(occ_id(e.item_id, e.occ_date)) or {} if e.occ_date else item).get("doneBy") or {}
    return [p for p in e.assignees if isinstance(marks.get(p), dict)]


def _entry(view: SpaceView, e: TodoEntry, day: str) -> dict[str, Any]:
    out: dict[str, Any] = {"uid": e.uid, "title": e.title, "done": e.done}
    if e.due:
        out["due"] = e.due
        out["overdue"] = not e.done and e.due[:10] < day
    if e.assignees:
        out["assignees"] = e.assignees
    if e.qty:
        out["qty"] = e.qty
    if e.late:
        out["late"] = True
    if e.note:
        out["note"] = e.note
    if e.done and e.done_by in view.person_by_id:
        out["done_by"] = e.done_by
    ticks = _own_ticks(view, e)
    if ticks is not None:
        out["each"] = ticks
    return out


def board(view: SpaceView, day: str) -> dict[str, Any]:
    """People and lists of a group, as plain data. Free of Home Assistant, so it is easy to test."""
    lists = []
    for lst in todo_lists(view):
        entries = todo_entries(view, day, COMPLETED_DAYS, list_id=lst["id"])
        row: dict[str, Any] = {
            "id": lst["id"],
            "name": lst["name"],
            "type": lst["type"],
            "entries": [_entry(view, e, day) for e in entries],
        }
        if lst["type"] == "shopping":
            trip = trip_of(view, lst)
            ready = trip.ready or {}
            row["trip"] = {
                "state": trip.state,
                "open": trip.open,
                "bought": trip.bought,
                **({"by": ready["by"]} if ready.get("by") in view.person_by_id else {}),
                **({"due": ready["due"]} if ready.get("due") else {}),
                **({"for": ready["for"]} if ready.get("for") else {}),
                **({"note": ready["note"]} if ready.get("note") else {}),
                **({"shopper": trip.shopper} if trip.shopper else {}),
                **({"overdue": True} if trip_overdue(trip, day) else {}),
            }
        lists.append(row)
    persons = [{"id": p["id"], "name": p["name"], "color": p["color"]} for p in view.active_persons()]
    return {"persons": persons, "lists": lists}


def _me(hass: HomeAssistant, entry: OrgaiaConfigEntry, user_id: str | None) -> str | None:
    """The person of the group the signed-in Home Assistant user is, if the options say so."""
    if not user_id:
        return None
    mine = {s.entity_id for s in hass.states.async_all("person") if s.attributes.get("user_id") == user_id}
    for person_id, entity_id in (entry.options.get(CONF_PERSONS) or {}).items():
        if entity_id in mine:
            return person_id
    return None


def _payload(hass: HomeAssistant, entry: OrgaiaConfigEntry, user_id: str | None) -> dict[str, Any]:
    coordinator: OrgaiaCoordinator = entry.runtime_data
    view = coordinator.data
    me = _me(hass, entry, user_id)
    return {
        "entry_id": entry.entry_id,
        "title": entry.title,
        "status": coordinator.status,
        "can_write": coordinator.engine.can_write,
        "me": me if me in view.person_by_id and not view.person_by_id[me]["removed"] else None,
        "today": today(),
        **board(view, today()),
    }


GROUPS = f"{DOMAIN}_groups"


def loaded_entries(hass: HomeAssistant) -> list[OrgaiaConfigEntry]:
    """The groups that are set up right now, in the order they were connected."""
    return list((hass.data.get(GROUPS) or {}).values())


@callback
def group_loaded(hass: HomeAssistant, entry: OrgaiaConfigEntry, loaded: bool) -> None:
    """Keeps track of the groups that can be shown and written to, and tells the open cards."""
    groups: dict[str, OrgaiaConfigEntry] = hass.data.setdefault(GROUPS, {})
    if loaded:
        groups[entry.entry_id] = entry
    else:
        groups.pop(entry.entry_id, None)
    notify_boards(hass)


BOARDS = f"{DOMAIN}_boards"


@websocket_api.websocket_command({vol.Required("type"): "orgaia/board/subscribe", vol.Optional("entry_id"): str})
@callback
def ws_board(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Sends a group's board now and after every change. Without ``entry_id`` the first group is taken."""
    wanted = msg.get("entry_id")
    user_id = connection.user.id if connection.user else None

    @callback
    def send() -> None:
        entries = loaded_entries(hass)
        entry = next((e for e in entries if not wanted or e.entry_id == wanted), None)
        # A group that is being loaded again is back in a moment: the card keeps what it shows.
        data = _payload(hass, entry, user_id) if entry else {"entry_id": wanted, "status": "not_loaded"}
        connection.send_message(websocket_api.event_message(msg["id"], data))

    boards: set[Any] = hass.data.setdefault(BOARDS, set())
    boards.add(send)
    connection.subscriptions[msg["id"]] = lambda: boards.discard(send)
    connection.send_result(msg["id"])
    send()


@callback
def notify_boards(hass: HomeAssistant) -> None:
    """A group changed, came or went: every open card hears about it."""
    for send in list(hass.data.get(BOARDS) or ()):
        send()


@callback
def async_setup_board(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_board)
