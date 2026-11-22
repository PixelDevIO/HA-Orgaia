"""Writing from Home Assistant: only when an admin allowed it, and always in a person's name."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.setup import async_setup_component
import pytest

from custom_components.orgaia.client.api import ApiError
from custom_components.orgaia.client.engine import WriteError
from custom_components.orgaia.const import CARD_URL, CONF_PERSONS, DOMAIN, VERSION

from .fake_service import FakeService, fill_group
from .test_engine import joined
from .test_init import setup_group


async def test_engine_writes_only_when_allowed(service: FakeService) -> None:
    fill_group(service, "2026-11-17")
    engine = await joined(service)
    await engine.sync()
    before = len(service.rows)
    mark = {"by": "ben", "at": 1, "via": "ha"}
    with pytest.raises(WriteError, match="read_only"):
        await engine.write([("item", "t2", {"done": mark})], "ben")
    assert len(service.rows) == before and not engine.view().item_by_id["t2"]["done"]

    # The admin allows it in the app: the next try asks again and goes through.
    service.can_write = True
    assert not engine.can_write
    await engine.write([("item", "t2", {"done": mark})], "ben")
    assert engine.can_write
    assert engine.view().item_by_id["t2"]["done"] == mark
    (op,) = service.sent()
    assert op["as"] == "ben" and op["by"] == engine.identity.sign_pub and op["set"] == {"done": mark}
    # Reading its own change back changes nothing.
    assert await engine.sync() is False

    # Taken back: refused, and nothing is kept for later.
    service.can_write = False
    with pytest.raises(WriteError, match="read_only"):
        await engine.write([("item", "t2", {"done": None})], "ben")
    assert not engine.can_write and engine.view().item_by_id["t2"]["done"] == mark


async def test_engine_write_failures(service: FakeService) -> None:
    fill_group(service, "2026-11-17")
    engine = await joined(service)
    await engine.sync()
    service.can_write = True
    # A new group key meanwhile: sealed once more, then it goes through.
    service.stale = True
    await engine.write([("item", "t2", {"note": "a"})], "ben")
    assert len(service.sent()) == 1
    service.down = True
    with pytest.raises(WriteError, match="offline"):
        await engine.write([("item", "t2", {"note": "b"})], "ben")
    assert engine.view().item_by_id["t2"]["note"] == "a"
    service.down = False
    # The service still wants another key (after it was restored): that is "not now", not "full".
    service.stale = "always"
    with pytest.raises(WriteError, match="offline"):
        await engine.write([("item", "t2", {"note": "b"})], "ben")
    service.stale = False
    # Reading the group again on the way fails: also "not now" instead of an error nobody translates.
    service.can_write = False
    service.block = None
    real = service.req

    async def busy(method, path, body=None):
        if path == "/v1/spaces":
            raise ApiError(503, "busy")
        return await real(method, path, body)

    service.req = busy
    with pytest.raises(WriteError, match="offline"):
        await engine.write([("item", "t2", {"note": "b"})], "ben")
    service.req = real
    service.can_write = True
    await engine.refresh_space()
    service.down = False
    service.block = (402, "group-over-limit")
    with pytest.raises(WriteError, match="needs_plus"):
        await engine.write([("item", "t2", {"note": "b"})], "ben")
    service.block = None
    # More than the service takes at once goes in several parts.
    await engine.write([("item", f"n{i}", {"title": str(i), "listId": "todo"}) for i in range(150)], "ben")
    assert len(service.sent()) == 151


async def call(hass: HomeAssistant, name: str, **data) -> None:
    await hass.services.async_call(DOMAIN, name, data, blocking=True)


async def items(hass: HomeAssistant, entity_id: str) -> dict[str, dict]:
    got = await hass.services.async_call(
        "todo", "get_items", {}, target={"entity_id": entity_id}, blocking=True, return_response=True
    )
    return {i["summary"]: i for i in got[entity_id]["items"]}


async def test_services_need_permission_and_a_person(hass: HomeAssistant, service: FakeService, freezer) -> None:
    entry = await setup_group(hass, service, freezer)
    with pytest.raises(ServiceValidationError) as err:
        await call(hass, "set_done", person="Ben", item="Steuer")
    assert err.value.translation_key == "read_only"
    assert not service.sent()

    service.can_write = True
    with pytest.raises(ServiceValidationError) as err:
        await call(hass, "set_done", person="Oma", item="Steuer")
    assert err.value.translation_key == "no_person"
    with pytest.raises(ServiceValidationError) as err:
        await call(hass, "set_done", person="Ben", item="Gibt es nicht")
    assert err.value.translation_key == "no_item"
    with pytest.raises(ServiceValidationError) as err:
        await call(hass, "add_article", person="Ben", list="Haushalt", title="Milch")
    assert err.value.translation_key == "not_shopping"
    assert not service.sent()

    # By title and name, as an automation would say it.
    await call(hass, "set_done", person="Ben", item="Steuer")
    await hass.async_block_till_done()
    (op,) = service.sent()
    assert op["as"] == "ben" and op["k"] == "item" and op["e"] == "t2"
    assert op["set"]["done"]["by"] == "ben" and op["set"]["done"]["via"] == "ha"
    assert (await items(hass, "todo.familie_haushalt"))["Steuer"]["status"] == "completed"
    assert hass.states.get("sensor.familie_open_tasks").state == "2"

    # A repeating task: today's occurrence, by the id the to-do list gives.
    today = hass.states.get("sensor.familie_connection").last_updated.astimezone().date().isoformat()
    await call(hass, "set_done", person="anna", item=f"t4|{today}", list="todo.familie_haushalt")
    assert service.sent()[-1]["k"] == "occ" and service.sent()[-1]["e"] == f"t4|{today}"

    # The Home Assistant person assigned in the options counts as the person of the group.
    hass.states.async_set("person.benjamin", "home", {"user_id": "u1"})
    hass.config_entries.async_update_entry(entry, options={CONF_PERSONS: {"ben": "person.benjamin"}})
    await hass.async_block_till_done()
    await call(hass, "set_done", person="person.benjamin", item="Steuer", done=False)
    assert service.sent()[-1]["set"] == {"done": None} and service.sent()[-1]["as"] == "ben"

    service.down = True
    with pytest.raises(HomeAssistantError) as err:
        await call(hass, "set_done", person="Ben", item="Steuer")
    assert err.value.translation_key == "write_offline"


async def test_shopping_from_the_kitchen(hass: HomeAssistant, service: FakeService, freezer) -> None:
    await setup_group(hass, service, freezer)
    service.can_write = True
    shop = "todo.familie_einkauf"
    await call(hass, "add_article", person="Ben", list=shop, title="Brot", quantity="2")
    await hass.async_block_till_done()
    assert set(await items(hass, shop)) == {"Milch", "Brot (2)"}
    assert hass.states.get(shop).attributes["shopping_state"] == "draft"

    await call(hass, "release_shopping_list", person="Anna", list="Einkauf", due_date="2026-11-18", note="Bio")
    await hass.async_block_till_done()
    attrs = hass.states.get(shop).attributes
    assert attrs["shopping_state"] == "ready" and attrs["released_by"] == "Anna" and attrs["due"] == "2026-11-18"
    assert hass.states.get("sensor.familie_shopping_waiting").state == "1"

    await call(hass, "add_article", person="Anna", list="shop", title="Eier")
    await call(hass, "take_shopping", person="Ben", list=shop)
    await hass.async_block_till_done()
    assert hass.states.get(shop).attributes["shopper"] == "Ben"
    assert "🆕" in (await items(hass, shop))["Eier"]["description"]

    await call(hass, "set_done", person="Ben", item="Milch", list=shop)
    await call(hass, "finish_shopping", person="Ben", list=shop)
    await hass.async_block_till_done()
    assert set(await items(hass, shop)) == {"Brot (2)", "Eier"}
    assert hass.states.get(shop).attributes["shopping_state"] == "draft"
    assert {op["as"] for op in service.sent()} == {"anna", "ben"}


async def test_board_for_the_card(
    hass: HomeAssistant, service: FakeService, freezer, hass_ws_client, hass_admin_user
) -> None:
    entry = await setup_group(hass, service, freezer)
    # Signed in at the time the test plays at.
    refresh = await hass.auth.async_create_refresh_token(hass_admin_user, "https://example.com/app")
    client = await hass_ws_client(hass, hass.auth.async_create_access_token(refresh))
    await client.send_json_auto_id({"type": "orgaia/board/subscribe"})
    assert (await client.receive_json())["success"]
    board = (await client.receive_json())["event"]
    assert board["entry_id"] == entry.entry_id and board["title"] == "Familie"
    assert board["can_write"] is False and board["me"] is None
    assert [p["name"] for p in board["persons"]] == ["Anna", "Ben"]
    lists = {lst["name"]: lst for lst in board["lists"]}
    assert lists["Einkauf"]["type"] == "shopping" and lists["Einkauf"]["trip"]["state"] == "draft"
    keller = next(e for e in lists["Haushalt"]["entries"] if e["title"] == "Keller aufräumen")
    assert keller["assignees"] == ["ben"] and keller["overdue"] is True and keller["done"] is False

    # Allowed in the app, and a tick at the display: the card hears about both.
    service.can_write = True
    await call(hass, "set_done", person="Ben", item="t1")
    board = (await client.receive_json())["event"]
    keller = next(e for lst in board["lists"] for e in lst["entries"] if e["uid"] == "t1")
    assert board["can_write"] is True and keller["done"] is True and keller["done_by"] == "ben"

    # The signed-in user is Ben, the options say. The group loads again for that; the same card goes on.
    hass.states.async_set("person.benjamin", "home", {"user_id": hass_admin_user.id})
    hass.config_entries.async_update_entry(entry, options={CONF_PERSONS: {"ben": "person.benjamin"}})
    await hass.async_block_till_done()
    # While it loads the card is told so (and keeps what it shows); then it gets the group again.
    seen = []
    while not seen or seen[-1] == "not_loaded":
        board = (await client.receive_json())["event"]
        seen.append(board["status"])
    assert seen == ["not_loaded", "ok"]
    assert board["title"] == "Familie" and board["me"] == "ben"
    assert board["title"] == "Familie" and board["me"] == "ben"


async def test_card_is_a_dashboard_resource(hass: HomeAssistant, service: FakeService, freezer) -> None:
    """The card picker finds the card: it is listed once, under the address of this version."""
    assert await async_setup_component(hass, "lovelace", {})
    resources = hass.data["lovelace"].resources
    await resources.async_load()
    resources.loaded = True
    # Left over from an older version, and once more by hand.
    await resources.async_create_item({"res_type": "module", "url": f"{CARD_URL}?v=0.6.0"})
    await resources.async_create_item({"res_type": "module", "url": CARD_URL})
    await resources.async_create_item({"res_type": "module", "url": "/local/other-card.js"})
    await setup_group(hass, service, freezer)
    urls = sorted(r["url"] for r in resources.async_items())
    assert urls == ["/local/other-card.js", f"{CARD_URL}?v={VERSION}"]
