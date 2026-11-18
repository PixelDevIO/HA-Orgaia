"""A wall display stays filled when the service is gone, and shows timetables and rosters as the app does."""

from __future__ import annotations

from datetime import timedelta
import socket
from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_capture_events, async_fire_time_changed

from custom_components.orgaia.const import EVENT_ORGAIA

from .fake_service import FakeService
from .test_init import NOON, setup_group


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


async def test_saves_only_changes(hass: HomeAssistant, service: FakeService, freezer) -> None:
    """The group file is written when the group changed, not on every look at the service."""
    entry = await setup_group(hass, service, freezer)
    coordinator = entry.runtime_data
    with patch.object(coordinator.store, "async_delay_save") as save:
        await coordinator.async_refresh()
        await coordinator.async_refresh()
        assert save.call_count == 0
        service.write("item", "n1", {"title": "Neu", "listId": "todo"})
        await coordinator.async_refresh()
        await coordinator.async_refresh()
        assert save.call_count == 1


ICS = "\r\n".join(
    [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "BEGIN:VEVENT",
        "UID:wander",
        "SUMMARY:Wandertag",
        "DTSTART;TZID=Europe/Berlin:{day}T080000",
        "DTEND;TZID=Europe/Berlin:{day}T130000",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
)


def resolves_to(ip: str):
    """Answer every name lookup with one address, so the tests do not depend on the network they run in."""

    async def lookup(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

    return lookup


async def test_subscribed_calendar(hass: HomeAssistant, service: FakeService, freezer, aioclient_mock) -> None:
    """A school calendar the family subscribed to shows in the calendars of the people it is for."""
    # The group is written at the time the test plays at: changes from a day ahead would not be taken.
    await hass.config.async_set_time_zone("Europe/Berlin")
    freezer.move_to(NOON)
    today = dt_util.now().date()
    day = (today + timedelta(days=2)).strftime("%Y%m%d")
    aioclient_mock.get("https://schule.example/kal.ics", text=ICS.format(day=day))
    service.write(
        "list",
        "feed1",
        {"name": "Schule", "type": "feed", "url": "webcal://schule.example/kal.ics", "feedFor": ["ben"], "order": 9},
    )
    events = async_capture_events(hass, EVENT_ORGAIA)
    with patch.object(hass.loop, "getaddrinfo", resolves_to("93.184.215.14")):
        entry = await setup_group(hass, service, freezer)
        await hass.async_block_till_done()
    when = (today + timedelta(days=2)).isoformat()
    got = await hass.services.async_call(
        "calendar",
        "get_events",
        {"start_date_time": f"{when}T00:00:00", "end_date_time": f"{when}T23:59:00"},
        target={"entity_id": ["calendar.ben_familie_calendar", "calendar.anna_familie_calendar"]},
        blocking=True,
        return_response=True,
    )
    assert [e["summary"] for e in got["calendar.ben_familie_calendar"]["events"]] == ["Wandertag"]
    assert got["calendar.anna_familie_calendar"]["events"] == []
    assert got["calendar.ben_familie_calendar"]["events"][0]["start"].startswith(f"{when}T08:00:00")
    # Nobody "made" it: no event for it, and it is fetched only once within a few hours.
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert not [e for e in events if e.data.get("title") == "Wandertag"]
    assert aioclient_mock.call_count == 1


async def test_calendar_in_home_network(hass: HomeAssistant, service: FakeService, freezer, aioclient_mock) -> None:
    """A calendar address whose name points into the home network is not fetched."""
    # The group is written at the time the test plays at: changes from a day ahead would not be taken.
    await hass.config.async_set_time_zone("Europe/Berlin")
    freezer.move_to(NOON)
    aioclient_mock.get("https://schule.example/kal.ics", text="")
    service.write(
        "list",
        "feed1",
        {"name": "Schule", "type": "feed", "url": "webcal://schule.example/kal.ics", "feedFor": ["ben"], "order": 9},
    )
    with patch.object(hass.loop, "getaddrinfo", resolves_to("192.168.178.1")):
        await setup_group(hass, service, freezer)
        await hass.async_block_till_done()
    assert aioclient_mock.call_count == 0
