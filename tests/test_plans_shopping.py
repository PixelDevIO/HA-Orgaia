"""Timetables and rosters as entities, deadlines in the calendar, the release of a shopping list, and fewer reads."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_capture_events, async_fire_time_changed

from custom_components.orgaia.board import board
from custom_components.orgaia.const import DOMAIN, EVENT_ORGAIA

from .fake_service import SPACE, FakeService
from .test_init import setup_group


def entity(hass: HomeAssistant, domain: str, unique_id: str) -> str:
    """Entities are looked up by what they stand for: their names follow Home Assistant's language."""
    found = er.async_get(hass).async_get_entity_id(domain, DOMAIN, unique_id)
    assert found, unique_id
    return found


async def refresh(hass: HomeAssistant, entry) -> None:
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


async def test_timetable_and_roster(hass: HomeAssistant, service: FakeService, freezer) -> None:
    # 17 November 2026 is a Tuesday.
    entry = await setup_group(hass, service, freezer)
    service.write(
        "list",
        "tt",
        {
            "name": "Stundenplan Ben",
            "type": "timetable",
            "order": 3,
            "ttFor": "ben",
            "packTime": "19:00",
            "subj.ma": {"name": "Mathe", "room": "R12"},
            "subj.sp": {"name": "Sport", "things": ["Sportzeug"]},
            "les.2.1": "ma",
            "les.2.2": "ma",
            "les.3.1": "sp",
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
    await refresh(hass, entry)

    school = hass.states.get(entity(hass, "sensor", f"{SPACE}_ben_timetable_tt_today"))
    assert school.attributes["status"] == "school" and school.attributes["plan"] == "Stundenplan Ben"
    assert [(x["period"], x["subject"]) for x in school.attributes["lessons"]] == [(1, "Mathe"), (2, "Mathe")]
    assert school.attributes["lessons"][0]["room"] == "R12"
    assert school.attributes["start"] and school.attributes["start"] in school.state
    assert school.attributes["pack_today"] == ["Sportzeug"]
    assert school.attributes["tomorrow"]["lessons"][0]["subject"] == "Sport"

    work = hass.states.get(entity(hass, "sensor", f"{SPACE}_anna_roster_rs_today"))
    assert work.attributes["start"] == "08:00" and work.attributes["end"] == "16:00"
    assert "08:00" in work.state and len(work.attributes["next_days"]) == 7

    # 12:00: Anna is at work; whether Ben is still at school depends on the lesson times.
    at_work = entity(hass, "binary_sensor", f"{SPACE}_anna_roster_rs_now")
    at_school = entity(hass, "binary_sensor", f"{SPACE}_ben_timetable_tt_now")
    assert hass.states.get(at_work).state == "on"
    end = school.attributes["end"]
    assert hass.states.get(at_school).state == ("on" if end > "12:00" else "off")
    freezer.move_to("2026-11-17T16:30:00+01:00")
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert hass.states.get(at_work).state == "off" and hass.states.get(at_school).state == "off"

    # The timetable as a calendar of its own: one entry per lesson.
    calendar = entity(hass, "calendar", f"{SPACE}_ben_timetable_tt_lessons")
    midnight = dt_util.start_of_local_day()
    got = await hass.services.async_call(
        "calendar",
        "get_events",
        {"start_date_time": midnight, "end_date_time": midnight + timedelta(days=2)},
        target={"entity_id": calendar},
        blocking=True,
        return_response=True,
    )
    assert [e["summary"] for e in got[calendar]["events"]] == ["Mathe", "Mathe", "Sport"]
    assert got[calendar]["events"][0]["location"] == "R12"

    # Holidays: no school, and the group says so.
    holidays = entity(hass, "binary_sensor", f"{SPACE}_school_holidays")
    assert hass.states.get(holidays).state == "off"
    service.write("meta", "space", {"schoolOff.h1": {"name": "Herbstferien", "from": "2026-11-16", "to": "2026-11-20"}})
    await refresh(hass, entry)
    assert hass.states.get(holidays).state == "on"
    school = hass.states.get(entity(hass, "sensor", f"{SPACE}_ben_timetable_tt_today"))
    assert school.attributes["status"] == "holiday" and school.attributes["holiday"] == "Herbstferien"

    # The plan is deleted: its entities go.
    service.write("list", "tt", {"deleted": True})
    await refresh(hass, entry)
    assert er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{SPACE}_ben_timetable_tt_today") is None


async def test_deadlines_and_ticks_in_the_calendar(hass: HomeAssistant, service: FakeService, freezer) -> None:
    entry = await setup_group(hass, service, freezer)
    service.write("item", "d1", {"title": "Anmeldung", "listId": "todo", "dueDate": "2026-11-18", "dueTime": "18:00"})
    service.write("occ", "t4|2026-11-17", {"done": {"by": "anna", "at": 1}})
    await refresh(hass, entry)
    calendar = "calendar.familie_calendar"
    midnight = dt_util.start_of_local_day()
    got = await hass.services.async_call(
        "calendar",
        "get_events",
        {"start_date_time": midnight, "end_date_time": midnight + timedelta(days=2)},
        target={"entity_id": calendar},
        blocking=True,
        return_response=True,
    )
    titles = [e["summary"] for e in got[calendar]["events"]]
    # Due today without a time slot, and due tomorrow at 18:00: both are in the calendar now.
    assert any("Steuer" in t for t in titles) and any("Anmeldung" in t for t in titles)
    # Today's round of the chore is ticked off, tomorrow's is not.
    assert "✓ Müll raus" in titles and "Müll raus" in titles
    # The next appointment stays an appointment.
    assert hass.states.get("sensor.familie_next_appointment").attributes["title"] == "Elternabend"


async def test_released_list_in_events_and_calendar(hass: HomeAssistant, service: FakeService, freezer) -> None:
    entry = await setup_group(hass, service, freezer)
    events = async_capture_events(hass, EVENT_ORGAIA)
    shop = "todo.familie_einkauf"
    service.write("list", "shop", {"ready": {"by": "anna", "at": 1000, "due": "2026-11-18", "for": ["ben"]}})
    await refresh(hass, entry)
    assert hass.states.get(shop).attributes["shopping_state"] == "ready"
    assert hass.states.get(shop).attributes["for"] == ["Ben"]
    service.write("list", "shop", {"take.ben": {"at": 2000, "r": 1000}})
    await refresh(hass, entry)
    assert hass.states.get(shop).attributes["shopping_state"] == "going"
    midnight = dt_util.start_of_local_day()
    got = await hass.services.async_call(
        "calendar",
        "get_events",
        {"start_date_time": midnight, "end_date_time": midnight + timedelta(days=2)},
        target={"entity_id": "calendar.familie_calendar"},
        blocking=True,
        return_response=True,
    )
    assert any("Einkauf" in e["summary"] for e in got["calendar.familie_calendar"]["events"])
    service.write("item", "s1", {"deleted": True, "deletedAt": None})
    service.write("list", "shop", {"ready": None, "lastTrip": {"by": "ben", "at": 3000, "n": 1, "left": 0}})
    await refresh(hass, entry)
    kinds = [e.data["type"] for e in events if e.data["type"].startswith("shopping_")]
    assert kinds == ["shopping_released", "shopping_taken", "shopping_done"]
    assert hass.states.get(shop).attributes["shopping_state"] == "draft"


async def test_reads_less_while_the_live_connection_stands(hass: HomeAssistant, service: FakeService, freezer) -> None:
    entry = await setup_group(hass, service, freezer)
    coordinator = entry.runtime_data

    def reads() -> int:
        return sum(1 for method, path in service.calls if method == "GET" and "/ops" in path)

    # Without the live connection every look reads the group.
    before = reads()
    await coordinator.async_refresh()
    assert reads() == before + 1
    # With it, a look only moves the time of day on; the service says when there is something to fetch.
    coordinator.live = True
    before = reads()
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    assert reads() == before
    await coordinator.fetch()
    await hass.async_block_till_done()
    assert reads() == before + 1
    # After an hour it reads again, to be safe.
    freezer.tick(timedelta(minutes=61))
    await coordinator.async_refresh()
    assert reads() == before + 2


async def test_board_views(hass: HomeAssistant, service: FakeService, freezer) -> None:
    """What the card's timetable, roster and agenda views are drawn from."""
    # 17 November 2026 is a Tuesday.
    entry = await setup_group(hass, service, freezer)
    service.write(
        "list",
        "tt",
        {
            "name": "Stundenplan Ben",
            "type": "timetable",
            "order": 3,
            "ttFor": "ben",
            "subj.ma": {"name": "Mathe", "room": "R12"},
            "subj.sp": {"name": "Sport", "things": ["Sportzeug"]},
            "les.2.1": "ma",
            "les.2.2": "ma",
            "les.3.1": "sp",
        },
    )
    service.write(
        "list",
        "rs",
        {
            "name": "Schichten Anna",
            "type": "roster",
            "order": 4,
            "rsFor": "anna",
            "mode": "shifts",
            "shift.f": {"name": "Früh", "code": "F", "start": "06:00", "end": "14:00"},
            "shift.n": {"name": "Nacht", "code": "N", "start": "22:00", "end": "06:00"},
            "d.2026-11-17": "f",
            "d.2026-11-19": "n",
        },
    )
    service.write("meta", "space", {"schoolOff.h1": {"name": "Brückentag", "from": "2026-11-27", "to": "2026-11-27"}})
    await refresh(hass, entry)
    got = board(entry.runtime_data.data, "2026-11-17")

    (plan,) = got["timetables"]
    assert plan["name"] == "Stundenplan Ben" and plan["person"] == "ben" and len(plan["periods"]) >= 2
    this, following = plan["weeks"]
    assert this["start"] == "2026-11-16" and following["start"] == "2026-11-23"
    assert [d["status"] for d in this["days"]] == ["free", "school", "school", "free", "free", "free", "free"]
    tuesday = this["days"][1]
    assert [(x["period"], x["subject"], x.get("room")) for x in tuesday["lessons"]] == [
        (1, "Mathe", "R12"),
        (2, "Mathe", "R12"),
    ]
    assert tuesday["pack"] == ["Sportzeug"] and this["days"][2]["pack"] == []
    assert following["days"][4]["status"] == "holiday" and following["days"][4]["holiday"] == "Brückentag"

    (roster,) = got["rosters"]
    assert roster["person"] == "anna" and len(roster["days"]) == 28 and roster["days"][0]["date"] == "2026-11-16"
    early, night = roster["days"][1], roster["days"][3]
    assert (early["shift"], early["code"], early["spans"][0]["start"]) == ("Früh", "F", "06:00")
    assert night["spans"][0]["overnight"] is True and roster["days"][2]["status"] == "free"

    agenda = got["agenda"]
    assert [r["start"] for r in agenda] == sorted(r["start"] for r in agenda)
    kinds = {r["kind"] for r in agenda}
    assert {"school", "work", "event"} <= kinds
    school = next(r for r in agenda if r["kind"] == "school")
    assert school["persons"] == ["ben"] and school["start"].startswith("2026-11-17T")
    assert all(r["start"][:10] >= "2026-11-17" or r.get("end", "")[:10] >= "2026-11-17" for r in agenda)
