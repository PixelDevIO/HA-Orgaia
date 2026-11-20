"""Absences, birthdays and the hours nobody looks after a child, as entities."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_capture_events

from custom_components.orgaia.const import EVENT_ORGAIA

from .fake_service import FakeService
from .test_init import setup_group


async def test_away_birthdays_and_care_gap(hass: HomeAssistant, service: FakeService, freezer) -> None:
    hass.config.language = "de"
    entry = await setup_group(hass, service, freezer)
    # Without a timetable and a roster there is nothing to say about care.
    assert hass.states.get("binary_sensor.familie_kind_ohne_betreuung") is None
    assert hass.states.get("binary_sensor.ben_familie_weg").state == "off"
    assert hass.states.get("sensor.familie_geburtstage_und_jahrestage").state == "0"

    # Tuesday 2026-11-17, 12:00: Ben's school is over after two lessons, Anna works until 16:00.
    service.write(
        "list",
        "tt",
        {
            "name": "Stundenplan Ben",
            "type": "timetable",
            "order": 3,
            "ttFor": "ben",
            "subj.ma": {"name": "Mathe"},
            "les.2.1": "ma",
            "les.2.2": "ma",
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
    service.write(
        "item",
        "oma",
        {
            "title": "Oma Hildegard",
            "listId": "todo",
            "kind": "event",
            "occasion": "birthday",
            "year": 1951,
            "start": "2020-11-17T00:00",
            "allDay": True,
            "repeat": {"freq": "year", "interval": 1},
        },
    )
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    gap = hass.states.get("binary_sensor.familie_kind_ohne_betreuung")
    assert gap.state == "on"
    assert gap.attributes["children"] == ["Ben"]
    assert gap.attributes["until"] == "16:00"
    assert gap.attributes["today"][-1]["end"] == "16:00"

    days = hass.states.get("sensor.familie_geburtstage_und_jahrestage")
    assert days.state == "1"
    assert days.attributes["today"] == ["Oma Hildegard (75)"]
    assert days.attributes["upcoming"][0]["years"] == 75

    # Ben goes on a class trip from today: no school, nobody waits for him at home, and he reads as away.
    events = async_capture_events(hass, EVENT_ORGAIA)
    service.write("person", "ben", {"away.k1": {"from": "2026-11-17", "to": "2026-11-18", "note": "Klassenfahrt"}})
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    away = hass.states.get("binary_sensor.ben_familie_weg")
    assert away.state == "on"
    assert away.attributes["until"] == "2026-11-18"
    assert away.attributes["note"] == "Klassenfahrt"
    assert hass.states.get("binary_sensor.familie_kind_ohne_betreuung").state == "off"
    assert hass.states.get("binary_sensor.ben_familie_in_der_schule").state == "off"

    midnight = dt_util.start_of_local_day()
    got = await hass.services.async_call(
        "calendar",
        "get_events",
        {"start_date_time": midnight, "end_date_time": midnight + timedelta(days=1)},
        target={"entity_id": "calendar.ben_familie_kalender"},
        blocking=True,
        return_response=True,
    )
    assert [e["summary"] for e in got["calendar.ben_familie_kalender"]["events"]] == ["Ben weg · Klassenfahrt"]
    # An absence is no appointment somebody made.
    assert not [e for e in events if e.data["type"] == "event_created"]
