"""The integration in Home Assistant: entities, calendar, repairs and leaving the group."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.orgaia.client.engine import GroupEngine
from custom_components.orgaia.const import DOMAIN
from custom_components.orgaia.diagnostics import async_get_config_entry_diagnostics
from custom_components.orgaia.protocol.invite import parse_invite

from .fake_service import SERVER, SPACE, FakeService, fill_group


async def setup_group(hass: HomeAssistant, service: FakeService) -> MockConfigEntry:
    await hass.config.async_set_time_zone("Europe/Berlin")
    fill_group(service, dt_util.now().date().isoformat())
    engine = GroupEngine(MagicMock(), GroupEngine.new_data(SERVER))
    await engine.request_join(parse_invite(service.link()), "Home Assistant")
    service.answer = "accepted"
    await engine.check_join()
    data = {k: v for k, v in engine.to_dict().items() if k in ("seed", "server", "device", "node", "space", "join")}
    entry = MockConfigEntry(domain=DOMAIN, title="Familie", unique_id=SPACE, data=data)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_entities(hass: HomeAssistant, service: FakeService) -> None:
    entry = await setup_group(hass, service)
    assert entry.state is ConfigEntryState.LOADED

    haushalt = hass.states.get("todo.familie_haushalt")
    einkauf = hass.states.get("todo.familie_einkauf")
    assert haushalt is not None and einkauf is not None
    # Keller, Steuer and today's Müll are open; the done task still shows, ticked.
    assert haushalt.state == "3"
    assert einkauf.state == "1"

    items = await hass.services.async_call(
        "todo", "get_items", {}, target={"entity_id": "todo.familie_haushalt"}, blocking=True, return_response=True
    )
    by_title = {i["summary"]: i for i in items["todo.familie_haushalt"]["items"]}
    assert by_title["Erledigt"]["status"] == "completed"
    assert "Belege suchen" in by_title["Steuer"]["description"]
    assert "☐ Kontoauszüge" in by_title["Steuer"]["description"]
    assert "Ben" in by_title["Keller aufräumen"]["description"]
    assert "Elternabend" not in by_title

    assert hass.states.get("sensor.familie_open_tasks").state == "3"
    assert hass.states.get("sensor.familie_overdue").state == "1"
    assert hass.states.get("sensor.familie_shopping_list").state == "1"
    assert hass.states.get("sensor.familie_connection").state == "ok"
    assert hass.states.get("calendar.familie_calendar") is not None

    midnight = dt_util.start_of_local_day()
    events = await hass.services.async_call(
        "calendar",
        "get_events",
        {"start_date_time": midnight, "end_date_time": midnight + timedelta(days=2)},
        target={"entity_id": "calendar.familie_calendar"},
        blocking=True,
        return_response=True,
    )
    titles = [e["summary"] for e in events["calendar.familie_calendar"]["events"]]
    assert "Elternabend" in titles
    assert titles.count("Müll raus") == 2

    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["status"] == "ok" and diag["persons"] == 2
    assert "Familie" not in str(diag)


async def test_new_list_appears_and_gone_list_goes(hass: HomeAssistant, service: FakeService) -> None:
    entry = await setup_group(hass, service)
    service.write("list", "garten", {"name": "Garten", "type": "tasks", "order": 3})
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("todo.familie_garten") is not None
    service.write("list", "garten", {"deleted": True})
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("todo.familie_garten") is None


async def test_plus_ended_shows_a_repair(hass: HomeAssistant, service: FakeService) -> None:
    entry = await setup_group(hass, service)
    service.block = (402, "integration-needs-plan")
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    issues = ir.async_get(hass)
    assert issues.async_get_issue(DOMAIN, f"needs_plus_{entry.entry_id}") is not None
    assert hass.states.get("sensor.familie_connection").state == "needs_plus"
    assert hass.states.get("sensor.familie_open_tasks").state == "unavailable"
    service.block = None
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert issues.async_get_issue(DOMAIN, f"needs_plus_{entry.entry_id}") is None
    assert hass.states.get("sensor.familie_open_tasks").state == "3"


async def test_removed_asks_for_a_new_link(hass: HomeAssistant, service: FakeService) -> None:
    entry = await setup_group(hass, service)
    service.removed = True
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)


async def test_remove_leaves_the_group(hass: HomeAssistant, service: FakeService) -> None:
    entry = await setup_group(hass, service)
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert service.left
