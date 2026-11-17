"""A wall display stays filled when the service is gone, and shows timetables and rosters as the app does."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_capture_events, async_fire_time_changed

from custom_components.orgaia.const import EVENT_ORGAIA

from .fake_service import FakeService
from .test_init import setup_group


async def test_outage_keeps_the_last_state(hass: HomeAssistant, service: FakeService, freezer) -> None:
    entry = await setup_group(hass, service, freezer)
    service.down = True
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.familie_connection").state == "offline"
    assert hass.states.get("sensor.familie_open_tasks").state == "3"
    assert hass.states.get("todo.familie_haushalt").state == "3"
    assert hass.states.get("calendar.familie_calendar").state != "unavailable"
    last = hass.states.get("sensor.familie_connection").attributes.get("last_sync")
    assert last is not None

    # Back again: the status says so, and changes made meanwhile arrive.
    service.down = False
    service.write("item", "t9", {"title": "Neu", "listId": "todo", "order": 9})
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.familie_connection").state == "ok"
    assert hass.states.get("sensor.familie_open_tasks").state == "4"


async def test_start_without_network(hass: HomeAssistant, service: FakeService, freezer) -> None:
    entry = await setup_group(hass, service, freezer)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    service.down = True
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.familie_connection").state == "offline"
    assert hass.states.get("sensor.familie_open_tasks").state == "3"


async def test_timetable_and_roster(hass: HomeAssistant, service: FakeService, freezer) -> None:
    # Titles come in Home Assistant's language, as the app shows them in the person's.
    hass.config.language = "de"
    entry = await setup_group(hass, service, freezer)
    events = async_capture_events(hass, EVENT_ORGAIA)
    # Tuesday 2026-11-17: Ben has sport on Wednesday, so "Sportzeug" is packed today at 19:00.
    service.write(
        "list",
        "tt",
        {
            "name": "Stundenplan Ben",
            "type": "timetable",
            "order": 3,
            "ttFor": "ben",
            "packTime": "19:00",
            "subj.sp": {"name": "Sport", "things": ["Sportzeug"]},
            "les.3.1": "sp",
            "les.3.2": "sp",
        },
    )
    service.write(
        "list",
        "rs",
        {
            "name": "Arbeit Anna",
            "type": "roster",
            "order": 4,
            "rsFor": "anna",
            "wk.2": [{"start": "08:00", "end": "16:00"}],
        },
    )
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    # The timetable is a to-do list with its packing task; the roster is no to-do list.
    items = await hass.services.async_call(
        "todo",
        "get_items",
        {},
        target={"entity_id": "todo.familie_stundenplan_ben"},
        blocking=True,
        return_response=True,
    )
    titles = [i["summary"] for i in items["todo.familie_stundenplan_ben"]["items"]]
    assert titles == ["Sportzeug einpacken"]
    assert hass.states.get("todo.familie_arbeit_anna") is None
    assert "Sportzeug einpacken" in hass.states.get("sensor.familie_heute_fallig").attributes["titles"]
    ben = await hass.services.async_call(
        "todo", "get_items", {}, target={"entity_id": "todo.ben_familie_aufgaben"}, blocking=True, return_response=True
    )
    assert "Sportzeug einpacken" in [i["summary"] for i in ben["todo.ben_familie_aufgaben"]["items"]]

    # School on Wednesday and work today in the calendars of the people.
    midnight = dt_util.start_of_local_day()
    got = await hass.services.async_call(
        "calendar",
        "get_events",
        {"start_date_time": midnight, "end_date_time": midnight + timedelta(days=2)},
        target={"entity_id": ["calendar.ben_familie_kalender", "calendar.anna_familie_kalender"]},
        blocking=True,
        return_response=True,
    )
    assert [e["summary"] for e in got["calendar.ben_familie_kalender"]["events"]] == ["Schule"]
    assert "Arbeit" in [e["summary"] for e in got["calendar.anna_familie_kalender"]["events"]]

    # Worked out, not made by anybody: no "created" events.
    assert not [e for e in events if e.data["type"] in ("task_created", "event_created")]

    # Past 19:00 the packing task is late, once.
    freezer.move_to("2026-11-17T19:05:00+01:00")
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    late = [e for e in events if e.data["type"] == "task_overdue"]
    assert [e.data["title"] for e in late].count("Sportzeug einpacken") == 1
