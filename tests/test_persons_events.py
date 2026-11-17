"""Phase 2: entities per person, the mapping to Home Assistant persons, events and device triggers."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.device_automation import DeviceAutomationType
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    async_capture_events,
    async_fire_time_changed,
    async_get_device_automations,
)

from custom_components.orgaia.const import DOMAIN, EVENT_ORGAIA
from custom_components.orgaia.events import EVENT_TYPES
from custom_components.orgaia.protocol.model import now_ms

from .fake_service import SPACE, FakeService
from .test_init import setup_group


async def refresh(hass: HomeAssistant, entry) -> None:
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


async def test_person_entities(hass: HomeAssistant, service: FakeService, freezer) -> None:
    entry = await setup_group(hass, service, freezer)
    assert hass.states.get("sensor.ben_familie_open_tasks").state == "1"
    assert hass.states.get("sensor.ben_familie_overdue").state == "1"
    assert hass.states.get("sensor.ben_familie_next_task").state == "Keller aufräumen"
    assert hass.states.get("sensor.anna_familie_open_tasks").state == "0"
    assert hass.states.get("todo.ben_familie_tasks").state == "1"
    assert hass.states.get("calendar.anna_familie_calendar") is not None
    assert hass.states.get("sensor.ben_familie_shopping_list") is None

    items = await hass.services.async_call(
        "todo", "get_items", {}, target={"entity_id": "todo.ben_familie_tasks"}, blocking=True, return_response=True
    )
    (only,) = items["todo.ben_familie_tasks"]["items"]
    assert only["summary"] == "Keller aufräumen"
    assert "Haushalt" in only["description"]

    # Ben leaves the group: his device and entities go.
    service.write("person", "ben", {"removed": True})
    await refresh(hass, entry)
    assert hass.states.get("sensor.ben_familie_open_tasks") is None
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert not any((DOMAIN, f"{SPACE}_ben") in d.identifiers for d in devices)


async def test_person_mapping(hass: HomeAssistant, service: FakeService, freezer) -> None:
    hass.states.async_set("person.anna", "home", {"friendly_name": "Anna"})
    entry = await setup_group(hass, service, freezer)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"
    fields = {str(k): k for k in result["data_schema"].schema}
    assert set(fields) == {"Anna", "Ben"}
    assert fields["Anna"].description == {"suggested_value": "person.anna"}
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"Anna": "person.anna"})
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.options["persons"] == {"anna": "person.anna"}
    assert hass.states.get("sensor.anna_familie_open_tasks").attributes["person_entity"] == "person.anna"


async def test_events(hass: HomeAssistant, service: FakeService, freezer) -> None:
    hass.states.async_set("person.anna", "home", {"friendly_name": "Anna"})
    entry = await setup_group(hass, service, freezer)
    hass.config_entries.async_update_entry(entry, options={"persons": {"anna": "person.anna"}})
    await hass.async_block_till_done()
    entry = hass.config_entries.async_get_entry(entry.entry_id)
    events = async_capture_events(hass, EVENT_ORGAIA)
    await refresh(hass, entry)
    assert events == []  # what was there at the start fires nothing

    today = dt_util.now().date().isoformat()
    service.write("item", "n1", {"title": "Fenster putzen", "listId": "todo", "assignees": ["ben"]})
    service.write("item", "t1", {"done": {"at": now_ms(), "by": "anna"}})
    service.write("item", "t2", {"assignees": ["anna"]})
    service.write("item", "e2", {"title": "Arzt", "listId": "todo", "kind": "event", "start": f"{today}T15:00"})
    service.write("item", "e1", {"location": "Turnhalle"})
    await refresh(hass, entry)
    by_type = {e.data["type"]: e.data for e in events}
    assert by_type["task_created"]["title"] == "Fenster putzen"
    assert by_type["task_created"]["assignees"] == ["Ben"]
    assert by_type["task_completed"]["title"] == "Keller aufräumen"
    assert by_type["task_completed"]["completed_by"] == "Anna"
    assert by_type["task_completed"]["completed_by_entity"] == "person.anna"
    assert by_type["task_assigned"]["assigned_entities"] == ["person.anna"]
    assert by_type["event_created"]["title"] == "Arzt"
    assert by_type["event_changed"]["location"] == "Turnhalle"
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, SPACE)})
    assert all(e.data["device_id"] == device.id for e in events)

    # Time passes: the chore is late at 19:01, the appointment starts at 23:00.
    events.clear()
    freezer.move_to(dt_util.now().replace(hour=19, minute=1))
    async_fire_time_changed(hass, dt_util.now() + timedelta(seconds=1))
    await hass.async_block_till_done()
    assert [(e.data["type"], e.data["title"]) for e in events] == [("task_overdue", "Müll raus")]
    assert hass.states.get("sensor.familie_overdue").state == "1"  # Keller is done, Müll raus is late
    events.clear()
    freezer.move_to(dt_util.now().replace(hour=23, minute=0, second=30))
    async_fire_time_changed(hass, dt_util.now() + timedelta(seconds=1))
    await hass.async_block_till_done()
    assert [(e.data["type"], e.data["title"]) for e in events] == [("event_starting", "Elternabend")]


async def test_device_triggers(hass: HomeAssistant, service: FakeService, freezer) -> None:
    entry = await setup_group(hass, service, freezer)
    registry = dr.async_get(hass)
    group = registry.async_get_device(identifiers={(DOMAIN, SPACE)})
    person = registry.async_get_device(identifiers={(DOMAIN, f"{SPACE}_anna")})
    triggers = await async_get_device_automations(hass, DeviceAutomationType.TRIGGER, group.id)
    assert {t["type"] for t in triggers if t["domain"] == DOMAIN} == set(EVENT_TYPES)
    person_triggers = await async_get_device_automations(hass, DeviceAutomationType.TRIGGER, person.id)
    assert [t for t in person_triggers if t["domain"] == DOMAIN] == []

    fired = async_capture_events(hass, "orgaia_test_done")
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "trigger": {"platform": "device", "domain": DOMAIN, "device_id": group.id, "type": "task_completed"},
                "action": {"event": "orgaia_test_done", "event_data": {"title": "{{ trigger.event.data.title }}"}},
            }
        },
    )
    service.write("item", "t2", {"done": {"at": now_ms(), "by": "anna"}})
    await refresh(hass, entry)
    assert [e.data["title"] for e in fired] == ["Steuer"]


async def test_task_that_comes_back(hass: HomeAssistant, service: FakeService, freezer) -> None:
    """Done with a task that comes back: it stays open with a new due date, yet it was completed."""
    entry = await setup_group(hass, service, freezer)
    service.write(
        "item",
        "r1",
        {
            "title": "Rasen mähen",
            "listId": "todo",
            "assignees": ["ben"],
            "rotation": ["ben", "anna"],
            "dueDate": "2000-01-01",
            "again": {"freq": "week", "interval": 2},
        },
    )
    await refresh(hass, entry)
    events = async_capture_events(hass, EVENT_ORGAIA)

    # What the app writes when Ben ticks it off: open again, due later, Anna's turn, lastDone set.
    done = {"at": now_ms(), "by": "ben"}
    service.write("item", "r1", {"done": None, "lastDone": done, "dueDate": "2000-01-15", "assignees": ["anna"]})
    await refresh(hass, entry)
    by_type = {e.data["type"]: e.data for e in events}
    assert by_type["task_completed"]["title"] == "Rasen mähen"
    assert by_type["task_completed"]["completed_by"] == "Ben"
    assert by_type["task_completed"]["assignees"] == ["Ben"]  # the round that was finished
    assert by_type["task_assigned"]["assigned"] == ["Anna"]
    assert "task_reopened" not in by_type

    # Taken back with "Rückgängig": lastDone goes back to what it was.
    events.clear()
    service.write("item", "r1", {"lastDone": None, "dueDate": "2000-01-01", "assignees": ["ben"]})
    await refresh(hass, entry)
    assert [e.data["type"] for e in events if e.data["type"] != "task_assigned"] == ["task_reopened"]

    # Nothing changed: nothing fires.
    events.clear()
    await refresh(hass, entry)
    assert events == []


async def test_drives_in_calendar(hass: HomeAssistant, service: FakeService, freezer) -> None:
    """An appointment that needs a drive says in the calendar who drives, or that nobody does yet."""
    hass.config.language = "de"
    entry = await setup_group(hass, service, freezer)
    service.write("item", "e1", {"needTo": True, "needFrom": True, "driveTo": "ben"})
    await refresh(hass, entry)
    today = dt_util.now().date().isoformat()
    events = await hass.services.async_call(
        "calendar",
        "get_events",
        {"start_date_time": f"{today}T00:00:00", "end_date_time": f"{today}T23:59:00"},
        target={"entity_id": "calendar.familie_kalender"},
        blocking=True,
        return_response=True,
    )
    (abend,) = [e for e in events["calendar.familie_kalender"]["events"] if e["summary"] == "Elternabend"]
    assert "🚗 Hinfahrt: Ben · Rückfahrt: noch offen" in abend["description"]
