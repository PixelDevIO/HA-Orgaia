"""Writing through Home Assistant's own to-do lists and calendars, and the day overview."""

from __future__ import annotations

import json
import os
from pathlib import Path

from homeassistant.components.todo import TodoListEntityFeature
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError
import pytest

from custom_components.orgaia.const import CONF_PERSONS, CONF_VOICE_PERSON, DOMAIN, VERSION
from custom_components.orgaia.protocol.actions import ActionError, repeat_of_rrule

from .fake_service import FakeService
from .test_init import setup_group

FIXTURE = Path(__file__).parent / "card" / "board.json"


async def as_ben(hass: HomeAssistant, entry, user_id: str) -> None:
    hass.states.async_set("person.benjamin", "home", {"user_id": user_id})
    hass.config_entries.async_update_entry(entry, options={CONF_PERSONS: {"ben": "person.benjamin"}})
    await hass.async_block_till_done()


async def test_todo_lists_write_as_the_user(
    hass: HomeAssistant, service: FakeService, freezer, hass_admin_user
) -> None:
    entry = await setup_group(hass, service, freezer)
    shop = "todo.familie_einkauf"
    # Not allowed by an admin: Home Assistant offers no ticking at all.
    assert hass.states.get(shop).attributes["supported_features"] == 0

    service.can_write = True
    await entry.runtime_data.async_refresh()
    await as_ben(hass, entry, "nobody")
    features = hass.states.get(shop).attributes["supported_features"]
    assert features & TodoListEntityFeature.CREATE_TODO_ITEM and features & TodoListEntityFeature.UPDATE_TODO_ITEM

    me = Context(user_id=hass_admin_user.id)
    # A user who is no person of the group may not write.
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            "todo", "add_item", {"item": "Brot"}, target={"entity_id": shop}, blocking=True, context=me
        )
    assert err.value.translation_key == "who_are_you"
    assert not service.sent()

    await as_ben(hass, entry, hass_admin_user.id)
    await hass.services.async_call(
        "todo", "add_item", {"item": "Brot, 2 Eier"}, target={"entity_id": shop}, blocking=True, context=me
    )
    await hass.services.async_call(
        "todo",
        "update_item",
        {"item": "Milch", "status": "completed"},
        target={"entity_id": shop},
        blocking=True,
        context=me,
    )
    await hass.async_block_till_done()
    sent = service.sent()
    assert {op["as"] for op in sent} == {"ben"}
    titles = {op["set"].get("title") for op in sent}
    assert {"Brot", "Eier"} <= titles
    assert any(op["e"] == "s1" and op["set"]["done"]["by"] == "ben" for op in sent)


async def test_voice_only_adds_articles(hass: HomeAssistant, service: FakeService, freezer) -> None:
    entry = await setup_group(hass, service, freezer)
    service.can_write = True
    await entry.runtime_data.async_refresh()
    shop = "todo.familie_einkauf"
    # Assist calls the list without a user: without a voice person nothing is written.
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call("todo", "add_item", {"item": "Käse"}, target={"entity_id": shop}, blocking=True)
    assert err.value.translation_key == "no_user"

    hass.config_entries.async_update_entry(entry, options={CONF_VOICE_PERSON: "anna"})
    await hass.async_block_till_done()
    await hass.services.async_call("todo", "add_item", {"item": "Käse"}, target={"entity_id": shop}, blocking=True)
    assert service.sent()[-1]["as"] == "anna" and service.sent()[-1]["set"]["title"] == "Käse"
    # Ticking off is never done by the voice person.
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            "todo", "update_item", {"item": "Milch", "status": "completed"}, target={"entity_id": shop}, blocking=True
        )
    assert err.value.translation_key == "no_user"


async def test_calendar_creates_appointments(
    hass: HomeAssistant, service: FakeService, freezer, hass_admin_user, hass_ws_client
) -> None:
    entry = await setup_group(hass, service, freezer)
    service.can_write = True
    await entry.runtime_data.async_refresh()
    await as_ben(hass, entry, hass_admin_user.id)
    me = Context(user_id=hass_admin_user.id)
    await hass.services.async_call(
        "calendar",
        "create_event",
        {
            "summary": "Zahnarzt",
            "start_date_time": "2026-11-20 09:00:00",
            "end_date_time": "2026-11-20 09:30:00",
            "location": "Praxis",
            "description": "Karte mitnehmen",
        },
        target={"entity_id": "calendar.anna_familie_calendar"},
        blocking=True,
        context=me,
    )
    op = service.sent()[-1]
    assert op["as"] == "ben"
    assert op["set"]["kind"] == "event" and op["set"]["listId"] == "todo" and op["set"]["assignees"] == ["anna"]
    assert op["set"]["start"] == "2026-11-20T09:00" and op["set"]["end"] == "2026-11-20T09:30"
    assert op["set"]["location"] == "Praxis" and op["set"]["note"] == "Karte mitnehmen"

    # From the calendar panel: no context, the signed-in connection says who it is.
    refresh = await hass.auth.async_create_refresh_token(hass_admin_user, "https://example.com/app")
    client = await hass_ws_client(hass, hass.auth.async_create_access_token(refresh))
    await client.send_json_auto_id(
        {
            "type": "calendar/event/create",
            "entity_id": "calendar.familie_calendar",
            "event": {
                "summary": "Ferien",
                "dtstart": "2026-12-21",
                "dtend": "2026-12-24",
                "rrule": "FREQ=YEARLY",
            },
        }
    )
    assert (await client.receive_json())["success"]
    op = service.sent()[-1]
    assert op["as"] == "ben" and "assignees" not in op["set"]
    assert (
        op["set"]["allDay"] is True
        and op["set"]["start"] == "2026-12-21T00:00"
        and op["set"]["end"] == "2026-12-23T00:00"
    )
    assert op["set"]["repeat"] == {"freq": "year", "interval": 1}


def test_rrule() -> None:
    assert repeat_of_rrule("FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,TH;UNTIL=20270101T000000Z", "2026-11-19") == {
        "freq": "week",
        "interval": 2,
        "until": "2027-01-01",
        "days": [1, 4],
    }
    # The weekday the series starts on needs no list of its own.
    assert repeat_of_rrule("FREQ=WEEKLY;BYDAY=TH", "2026-11-19") == {"freq": "week", "interval": 1}
    for bad in ("FREQ=HOURLY", "FREQ=DAILY;COUNT=3", "FREQ=MONTHLY;BYDAY=1MO"):
        with pytest.raises(ActionError):
            repeat_of_rrule(bad, "2026-11-19")


async def test_day_overview(hass: HomeAssistant, service: FakeService, freezer) -> None:
    await setup_group(hass, service, freezer)
    today = hass.states.get("sensor.familie_today")
    assert today is not None
    got = await hass.services.async_call(DOMAIN, "get_agenda", {"days": 2}, blocking=True, return_response=True)
    (group,) = got["groups"]
    first = group["days"][0]
    assert [a["title"] for a in first["appointments"]] == ["Elternabend"]
    assert "Steuer" in [d["title"] for d in first["due"]]
    assert first["speech"].startswith("Today: 23:00 Elternabend")
    assert len(group["days"]) == 2
    assert hass.states.get("binary_sensor.familie_may_tick_off_and_add").state == "off"


async def test_card_gets_aisles_sets_drives_and_days(
    hass: HomeAssistant, service: FakeService, freezer, hass_ws_client, hass_admin_user
) -> None:
    """What the card's shopping, agenda and today views need, and the card knows its own version."""
    entry = await setup_group(hass, service, freezer)
    day = hass.states.get("sensor.familie_connection").last_updated.astimezone().date().isoformat()
    service.write("item", "s2", {"title": "Brot", "listId": "shop", "aisle": "bakery", "qty": "2", "order": 2})
    service.write("item", "s3", {"title": "Gouda", "listId": "shop", "missed": {"by": "ben", "at": 1}, "order": 3})
    service.write(
        "list", "shop", {"set.w": {"name": "Wocheneinkauf", "items": [{"title": "Milch"}, {"title": "Eier"}]}}
    )
    service.write(
        "item",
        "e2",
        {"title": "Training", "listId": "todo", "kind": "event", "start": f"{day}T22:00", "needTo": True, "order": 6},
    )
    service.write("item", "e2", {"assignees": ["ben"], "driveTo": None})
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    refresh = await hass.auth.async_create_refresh_token(hass_admin_user, "https://example.com/app")
    client = await hass_ws_client(hass, hass.auth.async_create_access_token(refresh))
    await client.send_json_auto_id({"type": "orgaia/board/subscribe"})
    assert (await client.receive_json())["success"]
    got = (await client.receive_json())["event"]

    assert got["version"] == VERSION
    card = (Path(__file__).parents[1] / "custom_components/orgaia/www/orgaia-card.js").read_text()
    assert f"const CARD_VERSION = '{VERSION}';" in card
    shop = next(lst for lst in got["lists"] if lst["id"] == "shop")
    entries = {e["title"]: e for e in shop["entries"]}
    assert entries["Brot"]["aisle"] == "bakery" and entries["Brot"]["step"] is True
    assert entries["Gouda"]["missed"] == "ben" and entries["Milch"]["aisle"] == "dairy"
    assert shop["sets"] == [{"id": "w", "name": "Wocheneinkauf", "count": 2}]
    assert [k for k, _ in got["aisles"]][:2] == ["produce", "bakery"]
    # The server speaks English here; the card still gets the German names for a German user.
    assert got["aisle_names"]["de"]["bakery"] == "Brot & Backwaren" and got["aisle_names"]["en"]["bakery"] == "Bakery"
    training = next(r for r in got["agenda"] if r["title"] == "Training")
    assert training["drive"] == {"item": "e2", "date": day, "to": None}
    today, tomorrow = got["days"]
    assert today["date"] == day and [a["title"] for a in today["appointments"]] == ["Training", "Elternabend"]
    assert today["appointments"][0]["drive_missing"] == ["to"]
    assert today["speech"].startswith("Today:") and tomorrow["speech"].startswith("Tomorrow:")

    # The card's browser test draws every view from this.
    if os.environ.get("UPDATE_CARD_FIXTURE"):
        FIXTURE.write_text(json.dumps(got, ensure_ascii=False, indent=1) + "\n")
    assert FIXTURE.exists()
