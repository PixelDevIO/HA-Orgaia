"""Services to change a group from Home Assistant: tick off, add, release a shopping list and take it over.

Every one of them needs a person of the group: who ticked off must be known, in the app too. They
only work once an admin of the group allowed this Home Assistant to write, in the app under
Manage › Home Assistant. The Orgaia card uses the same services.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import time
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er
import voluptuous as vol

from .board import loaded_entries
from .client.engine import WriteError
from .const import COMPLETED_DAYS, CONF_PERSONS, DOMAIN
from .coordinator import OrgaiaConfigEntry, OrgaiaCoordinator
from .entity import space_key
from .protocol import actions
from .protocol.actions import ActionError, Change
from .protocol.view import SpaceView
from .summary import todo_entries
from .util import today

ATTR_ENTRY = "config_entry_id"
ATTR_PERSON = "person"
ATTR_LIST = "list"
ATTR_ITEM = "item"
ATTR_DONE = "done"
ATTR_TITLE = "title"
ATTR_QUANTITY = "quantity"
ATTR_DUE = "due_date"
ATTR_FOR = "for"
ATTR_NOTE = "note"
ATTR_ASSIGNEES = "assignees"

_BASE = {vol.Optional(ATTR_ENTRY): cv.string, vol.Required(ATTR_PERSON): cv.string}
_LIST = {**_BASE, vol.Required(ATTR_LIST): cv.string}
_DATE = vol.All(cv.date, lambda d: d.isoformat())
_PERSONS = vol.All(cv.ensure_list, [cv.string])

Handler = Callable[[OrgaiaCoordinator, ServiceCall, str], list[Change]]


def _fail(key: str, **placeholders: str) -> ServiceValidationError:
    return ServiceValidationError(translation_domain=DOMAIN, translation_key=key, translation_placeholders=placeholders)


def _entry(hass: HomeAssistant, call: ServiceCall) -> OrgaiaConfigEntry:
    entries = loaded_entries(hass)
    wanted = call.data.get(ATTR_ENTRY)
    if wanted:
        entry = next((e for e in entries if e.entry_id == wanted), None)
        if entry is None:
            raise _fail("no_group")
        return entry
    if len(entries) == 1:
        return entries[0]
    raise _fail("which_group" if entries else "no_group")


def person_id(entry: OrgaiaConfigEntry, view: SpaceView, who: str) -> str:
    """A person of the group from their id, a Home Assistant person assigned in the options, or their name."""
    active = view.active_persons()
    who = who.strip()
    if any(p["id"] == who for p in active):
        return who
    if who.startswith("person."):
        for pid, entity_id in (entry.options.get(CONF_PERSONS) or {}).items():
            if entity_id == who and any(p["id"] == pid for p in active):
                return pid
    named = [p["id"] for p in active if p["name"].strip().casefold() == who.casefold()]
    if len(named) == 1:
        return named[0]
    raise _fail("no_person", person=who)


def list_id(hass: HomeAssistant, entry: OrgaiaConfigEntry, view: SpaceView, which: str) -> str:
    """A list of the group from its id, its to-do entity, or its name."""
    which = which.strip()
    if which in view.list_by_id:
        return which
    if which.startswith("todo."):
        reg = er.async_get(hass).async_get(which)
        prefix = f"{space_key(entry)}_list_"
        if reg and reg.platform == DOMAIN and reg.unique_id.startswith(prefix):
            found = reg.unique_id[len(prefix) :]
            if found in view.list_by_id:
                return found
    named = [lst["id"] for lst in view.lists if lst["name"].strip().casefold() == which.casefold()]
    if len(named) == 1:
        return named[0]
    raise _fail("no_list", list=which)


def _now() -> int:
    return int(time.time() * 1000)


def _set_done(coordinator: OrgaiaCoordinator, call: ServiceCall, person: str) -> list[Change]:
    view = coordinator.data
    wanted: str = call.data[ATTR_ITEM].strip()
    which = call.data.get(ATTR_LIST)
    only = list_id(coordinator.hass, coordinator.config_entry, view, which) if which else None
    # What the to-do lists show: a one-off task, or the day of a repeating one that is due now.
    entries = todo_entries(view, today(), COMPLETED_DAYS, list_id=only)
    entry = next((e for e in entries if e.uid == wanted), None)
    if entry is None:
        titled = [e for e in entries if e.title.strip().casefold() == wanted.casefold()]
        entry = titled[0] if len(titled) == 1 else None
    if entry is None:
        raise _fail("no_item", item=wanted)
    item = view.item_by_id[entry.item_id]
    return actions.set_done(view, item, call.data[ATTR_DONE], entry.occ_date, person, _now(), today())


def _add_article(coordinator: OrgaiaCoordinator, call: ServiceCall, person: str) -> list[Change]:
    view = coordinator.data
    lst = list_id(coordinator.hass, coordinator.config_entry, view, call.data[ATTR_LIST])
    return actions.add_article(
        view, lst, call.data[ATTR_TITLE], call.data.get(ATTR_QUANTITY), person, _now(), coordinator.engine.new_id
    )


def _add_task(coordinator: OrgaiaCoordinator, call: ServiceCall, person: str) -> list[Change]:
    view = coordinator.data
    entry = coordinator.config_entry
    lst = list_id(coordinator.hass, entry, view, call.data[ATTR_LIST])
    who = [person_id(entry, view, p) for p in call.data.get(ATTR_ASSIGNEES) or []]
    return actions.add_task(
        view, lst, call.data[ATTR_TITLE], person, _now(), coordinator.engine.new_id, call.data.get(ATTR_DUE), who
    )


def _release(coordinator: OrgaiaCoordinator, call: ServiceCall, person: str) -> list[Change]:
    view = coordinator.data
    entry = coordinator.config_entry
    lst = list_id(coordinator.hass, entry, view, call.data[ATTR_LIST])
    who = [person_id(entry, view, p) for p in call.data.get(ATTR_FOR) or []]
    return actions.release_list(view, lst, person, _now(), call.data.get(ATTR_DUE), who, call.data.get(ATTR_NOTE))


def _on_list(fn: Callable[..., list[Change]], with_person: bool = True, with_now: bool = False) -> Handler:
    def handle(coordinator: OrgaiaCoordinator, call: ServiceCall, person: str) -> list[Change]:
        view = coordinator.data
        lst = list_id(coordinator.hass, coordinator.config_entry, view, call.data[ATTR_LIST])
        args: list[Any] = [view, lst]
        if with_person:
            args.append(person)
        if with_now:
            args.append(_now())
        return fn(*args)

    return handle


SERVICES: dict[str, tuple[dict[Any, Any], Handler]] = {
    "set_done": (
        {
            **_BASE,
            vol.Required(ATTR_ITEM): cv.string,
            vol.Optional(ATTR_LIST): cv.string,
            vol.Optional(ATTR_DONE, default=True): cv.boolean,
        },
        _set_done,
    ),
    "add_article": (
        {**_LIST, vol.Required(ATTR_TITLE): cv.string, vol.Optional(ATTR_QUANTITY): cv.string},
        _add_article,
    ),
    "add_task": (
        {
            **_LIST,
            vol.Required(ATTR_TITLE): cv.string,
            vol.Optional(ATTR_DUE): _DATE,
            vol.Optional(ATTR_ASSIGNEES): _PERSONS,
        },
        _add_task,
    ),
    "release_shopping_list": (
        {**_LIST, vol.Optional(ATTR_DUE): _DATE, vol.Optional(ATTR_FOR): _PERSONS, vol.Optional(ATTR_NOTE): cv.string},
        _release,
    ),
    "withdraw_shopping_list": (_LIST, _on_list(actions.withdraw_release, with_person=False)),
    "take_shopping": (_LIST, _on_list(actions.take_trip, with_now=True)),
    "drop_shopping": (_LIST, _on_list(actions.drop_trip)),
    "finish_shopping": (_LIST, _on_list(actions.finish_trip, with_now=True)),
}


def _service(hass: HomeAssistant, handler: Handler) -> Callable[[ServiceCall], Awaitable[None]]:
    async def run(call: ServiceCall) -> None:
        entry = _entry(hass, call)
        coordinator = entry.runtime_data
        person = person_id(entry, coordinator.data, call.data[ATTR_PERSON])
        try:
            changes = handler(coordinator, call, person)
        except ActionError as err:
            raise _fail(err.reason) from err
        try:
            await coordinator.write(changes, person)
        except WriteError as err:
            if err.reason == "read_only":
                raise _fail("read_only", group=entry.title) from err
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key=f"write_{err.reason}",
                translation_placeholders={"group": entry.title},
            ) from err

    return run


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    for name, (schema, handler) in SERVICES.items():
        hass.services.async_register(DOMAIN, name, _service(hass, handler), schema=vol.Schema(schema))
