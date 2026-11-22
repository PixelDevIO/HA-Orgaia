"""Services to change a group from Home Assistant: tick off, add, release a shopping list and take it over.

Every one of them needs a person of the group: who ticked off must be known, in the app too. They
only work once an admin of the group allowed this Home Assistant to write, in the app under
Group › Home Assistant. The Orgaia card uses the same services.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import time
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback
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
from .protocol.recur import add_days
from .protocol.shopping import AISLES, parse_articles, step_qty
from .protocol.view import SpaceView
from .report import day_report, speech
from .summary import Drive, TodoEntry, drives_between, todo_entries
from .util import local_now, minute_of_day, today

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
ATTR_MISSED = "missed"
ATTR_STEP = "step"
ATTR_AISLE = "aisle"
ATTR_SET = "set"
ATTR_WHICH = "which"
ATTR_DATE = "date"
ATTR_DAYS = "days"

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


def find_entry(coordinator: OrgaiaCoordinator, wanted: str, which: str | None) -> TodoEntry:
    """A line of a to-do list by the id the list gives it, or by its title (with or without the quantity)."""
    view = coordinator.data
    wanted = wanted.strip()
    only = list_id(coordinator.hass, coordinator.config_entry, view, which) if which else None
    # What the to-do lists show: a one-off task, or the day of a repeating one that is due now.
    entries = todo_entries(view, today(), COMPLETED_DAYS, list_id=only)
    entry = next((e for e in entries if e.uid == wanted or e.item_id == wanted), None)
    if entry is None:
        key = wanted.casefold()
        titled = [
            e
            for e in entries
            if e.title.strip().casefold() == key or (e.qty and f"{e.title} ({e.qty})".casefold() == key)
        ]
        # An open one before one that is ticked off already.
        titled.sort(key=lambda e: e.done)
        entry = titled[0] if len(titled) == 1 or (titled and not titled[0].done and titled[1].done) else None
    if entry is None:
        raise _fail("no_item", item=wanted)
    return entry


def _set_done(coordinator: OrgaiaCoordinator, call: ServiceCall, person: str) -> list[Change]:
    view = coordinator.data
    entry = find_entry(coordinator, call.data[ATTR_ITEM], call.data.get(ATTR_LIST))
    item = view.item_by_id[entry.item_id]
    return actions.set_done(view, item, call.data[ATTR_DONE], entry.occ_date, person, _now(), today())


def _add_article(coordinator: OrgaiaCoordinator, call: ServiceCall, person: str) -> list[Change]:
    view = coordinator.data
    lst = list_id(coordinator.hass, coordinator.config_entry, view, call.data[ATTR_LIST])
    title: str = call.data[ATTR_TITLE]
    qty = call.data.get(ATTR_QUANTITY)
    # "Milch, 2 Brot, 500 g Kaffee" puts three articles on the list, as typing it in the app does.
    many = parse_articles(title) if not qty else []
    if len(many) > 1 or (many and many[0].get("qty")):
        return actions.add_articles(view, lst, many, person, _now(), coordinator.engine.new_id)
    return actions.add_article(view, lst, title, qty, person, _now(), coordinator.engine.new_id)


def _article(coordinator: OrgaiaCoordinator, call: ServiceCall) -> dict[str, Any]:
    entry = find_entry(coordinator, call.data[ATTR_ITEM], call.data.get(ATTR_LIST))
    return coordinator.data.item_by_id[entry.item_id]


def _set_missed(coordinator: OrgaiaCoordinator, call: ServiceCall, person: str) -> list[Change]:
    return actions.set_missed(coordinator.data, _article(coordinator, call), call.data[ATTR_MISSED], person, _now())


def _set_quantity(coordinator: OrgaiaCoordinator, call: ServiceCall, person: str) -> list[Change]:
    item = _article(coordinator, call)
    qty = call.data.get(ATTR_QUANTITY)
    step = call.data.get(ATTR_STEP)
    if step:
        qty = step_qty(item.get("qty"), step)
    return actions.set_quantity(coordinator.data, item, qty)


def _set_aisle(coordinator: OrgaiaCoordinator, call: ServiceCall, person: str) -> list[Change]:
    return actions.set_aisle(coordinator.data, _article(coordinator, call), call.data.get(ATTR_AISLE))


def _add_set(coordinator: OrgaiaCoordinator, call: ServiceCall, person: str) -> list[Change]:
    view = coordinator.data
    lst = list_id(coordinator.hass, coordinator.config_entry, view, call.data[ATTR_LIST])
    return actions.apply_shop_set(view, lst, call.data[ATTR_SET], person, _now(), coordinator.engine.new_id)


def find_drive(coordinator: OrgaiaCoordinator, wanted: str, day: str | None) -> Drive:
    """An appointment that needs a drive, by its id or title, on a day (or the next time it happens)."""
    view = coordinator.data
    first = day or today()
    last = day or add_days(first, 30)
    key = wanted.strip().casefold()
    for d in drives_between(view, first, last):
        if d.occ.item["id"] == wanted.strip() or d.occ.item["title"].strip().casefold() == key:
            return d
    raise _fail("no_drive_found", item=wanted)


def _drive(take: bool) -> Handler:
    def handle(coordinator: OrgaiaCoordinator, call: ServiceCall, person: str) -> list[Change]:
        d = find_drive(coordinator, call.data[ATTR_ITEM], call.data.get(ATTR_DATE))
        which = call.data[ATTR_WHICH]
        sides = [w for w, need in (("to", d.need_to), ("from", d.need_from)) if need and which in (w, "both")]
        if not sides:
            raise _fail("no_drive")
        item = coordinator.data.item_by_id.get(d.occ.item["id"]) or d.occ.item
        out: list[Change] = []
        for side in sides:
            current = d.driver_to if side == "to" else d.driver_from
            if not take and current != person:
                continue
            out.extend(actions.set_driver(coordinator.data, item, side, person if take else None, d.occ.occ_date))
        return out

    return handle


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
    "set_not_got": (
        {
            **_BASE,
            vol.Required(ATTR_ITEM): cv.string,
            vol.Optional(ATTR_LIST): cv.string,
            vol.Optional(ATTR_MISSED, default=True): cv.boolean,
        },
        _set_missed,
    ),
    "set_quantity": (
        {
            **_BASE,
            vol.Required(ATTR_ITEM): cv.string,
            vol.Optional(ATTR_LIST): cv.string,
            vol.Exclusive(ATTR_QUANTITY, "amount"): cv.string,
            vol.Exclusive(ATTR_STEP, "amount"): vol.All(vol.Coerce(int), vol.Range(min=-99, max=99)),
        },
        _set_quantity,
    ),
    "set_aisle": (
        {
            **_BASE,
            vol.Required(ATTR_ITEM): cv.string,
            vol.Optional(ATTR_LIST): cv.string,
            vol.Optional(ATTR_AISLE): vol.Any(None, vol.In(AISLES)),
        },
        _set_aisle,
    ),
    "add_fixed_purchase": ({**_LIST, vol.Required(ATTR_SET): cv.string}, _add_set),
    "take_drive": (
        {
            **_BASE,
            vol.Required(ATTR_ITEM): cv.string,
            vol.Optional(ATTR_DATE): _DATE,
            vol.Optional(ATTR_WHICH, default="both"): vol.In(["to", "from", "both"]),
        },
        _drive(True),
    ),
    "drop_drive": (
        {
            **_BASE,
            vol.Required(ATTR_ITEM): cv.string,
            vol.Optional(ATTR_DATE): _DATE,
            vol.Optional(ATTR_WHICH, default="both"): vol.In(["to", "from", "both"]),
        },
        _drive(False),
    ),
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


async def _get_agenda(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """What happens on a day (today unless ``date``), for every group or one; optionally of one person.

    Reads only, so it needs no person and no permission to write.
    """
    wanted = call.data.get(ATTR_ENTRY)
    entries = [e for e in loaded_entries(hass) if not wanted or e.entry_id == wanted]
    if not entries:
        raise _fail("no_group")
    first = call.data.get(ATTR_DATE) or today()
    now = local_now()
    groups = []
    for entry in entries:
        view = entry.runtime_data.data
        who = call.data.get(ATTR_PERSON)
        person = person_id(entry, view, who) if who else None
        days = []
        for n in range(call.data[ATTR_DAYS]):
            report = day_report(view, add_days(first, n), today(), minute_of_day(now), person)
            report["speech"] = speech(report, hass.config.language, today())
            days.append(report)
        groups.append({"group": view.name or entry.title, "config_entry_id": entry.entry_id, "days": days})
    return {"groups": groups, "speech": " ".join(d["speech"] for g in groups for d in g["days"])}


GET_AGENDA_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY): cv.string,
        vol.Optional(ATTR_PERSON): cv.string,
        vol.Optional(ATTR_DATE): _DATE,
        vol.Optional(ATTR_DAYS, default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=14)),
    }
)


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    for name, (schema, handler) in SERVICES.items():
        hass.services.async_register(DOMAIN, name, _service(hass, handler), schema=vol.Schema(schema))

    async def get_agenda(call: ServiceCall) -> ServiceResponse:
        return await _get_agenda(hass, call)

    hass.services.async_register(
        DOMAIN, "get_agenda", get_agenda, schema=GET_AGENDA_SCHEMA, supports_response=SupportsResponse.ONLY
    )
