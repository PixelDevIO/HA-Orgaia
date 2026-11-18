"""The connection to the service: the live channel, a wrong clock, and news that arrive late."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import time
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import async_capture_events

from custom_components.orgaia.client.api import Api
from custom_components.orgaia.client.engine import STATUS_REMOVED, GroupEngine
from custom_components.orgaia.const import EVENT_ORGAIA
from custom_components.orgaia.coordinator import OrgaiaCoordinator
from custom_components.orgaia.protocol import PROTOCOL_VERSION
from custom_components.orgaia.protocol.crypto import Identity
from custom_components.orgaia.protocol.model import now_ms

from .fake_service import SERVER, FakeService, fill_group
from .test_engine import joined
from .test_init import setup_group

# The tests' fixture replaces the live connection; this is the real one.
RUN_LIVE = OrgaiaCoordinator.run_live
DAY = 24 * 3600 * 1000


async def test_token_is_not_part_of_the_address() -> None:
    ws = MagicMock(send_json=AsyncMock())
    session = MagicMock(ws_connect=AsyncMock(return_value=ws))
    api = Api(session, SERVER, Identity.create(), "device")
    with patch.object(Api, "auth_token", new=AsyncMock(return_value="s3cret")):
        assert await api.ws_connect() is ws
    url = session.ws_connect.call_args.args[0]
    assert url.endswith("/v1/ws") and "s3cret" not in url
    ws.send_json.assert_awaited_once_with({"t": "auth", "token": "s3cret"})


async def test_signs_in_with_the_current_protocol_and_learns_the_time() -> None:
    api = Api(MagicMock(), SERVER, Identity.create(), "device")
    sent: list[dict] = []

    async def raw(method, path, body=None, token=None):
        sent.append(body)
        if path.endswith("/challenge"):
            return {"nonce": "n", "now": time.time() * 1000 + 2 * DAY}
        return {"token": "t", "expiresAt": time.time() * 1000 + DAY}

    with patch.object(Api, "_raw", new=AsyncMock(side_effect=raw)):
        await api.auth_token()
        assert sent[1]["protocol"] == PROTOCOL_VERSION == 2
        assert abs(api.clock_offset - 2 * DAY) < 5000

    # A clock that is only a little off is left alone.
    async def close(method, path, body=None, token=None):
        if path.endswith("/challenge"):
            return {"nonce": "n", "now": time.time() * 1000 + 60_000}
        return {"token": "t", "expiresAt": time.time() * 1000 + DAY}

    with patch.object(Api, "_raw", new=AsyncMock(side_effect=close)):
        await api.auth_token(force=True)
        assert api.clock_offset == 0


async def test_reads_changes_although_the_clock_is_days_behind(service: FakeService) -> None:
    fill_group(service, "2026-11-17")
    engine = await joined(service)
    behind = GroupEngine(MagicMock(), engine.to_dict(), now=lambda: now_ms() - 3 * DAY)
    # Without the service's time everything the others wrote looks like it came from the future.
    await behind.sync()
    assert behind.view().name != "Familie"
    behind = GroupEngine(MagicMock(), engine.to_dict(), now=lambda: now_ms() - 3 * DAY)
    behind.api.clock_offset = 3 * DAY
    await behind.sync()
    assert behind.view().name == "Familie"


async def test_removed_while_reading_stays_removed(service: FakeService) -> None:
    engine = await joined(service)
    await engine.sync()
    # The group is gone for Home Assistant, and it notices while reading a change it cannot place.
    service.answer = "rejected"
    service.write("item", "x", {"title": "Fremd"}, author=Identity.create())
    await engine.sync()
    assert engine.status == STATUS_REMOVED


async def test_live_connection_survives_the_unexpected(hass: HomeAssistant, service: FakeService, freezer) -> None:
    entry = await setup_group(hass, service, freezer)
    coordinator = entry.runtime_data
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    connect = AsyncMock(side_effect=[ValueError("odd"), KeyError("odder"), asyncio.CancelledError()])
    with (
        patch.object(coordinator.engine.api, "ws_connect", new=connect),
        patch("custom_components.orgaia.coordinator.asyncio.sleep", new=sleep),
        patch("custom_components.orgaia.coordinator.spread", new=lambda delay: delay),
        pytest.raises(asyncio.CancelledError),
    ):
        await RUN_LIVE(coordinator)
    assert connect.await_count == 3
    assert waits == [1.0, 2.0]


async def test_connection_closed_at_once_waits_longer_each_time(
    hass: HomeAssistant, service: FakeService, freezer
) -> None:
    entry = await setup_group(hass, service, freezer)
    coordinator = entry.runtime_data
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    class Closed:
        """A connection the service ends right away, as when there are too many."""

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    connect = AsyncMock(side_effect=[Closed(), Closed(), Closed(), asyncio.CancelledError()])
    with (
        patch.object(coordinator.engine.api, "ws_connect", new=connect),
        patch("custom_components.orgaia.coordinator.asyncio.sleep", new=sleep),
        patch("custom_components.orgaia.coordinator.spread", new=lambda delay: delay),
        pytest.raises(asyncio.CancelledError),
    ):
        await RUN_LIVE(coordinator)
    assert waits == [1.0, 2.0, 4.0]


async def test_news_after_a_long_outage_are_late(hass: HomeAssistant, service: FakeService, freezer) -> None:
    entry = await setup_group(hass, service, freezer)
    coordinator = entry.runtime_data
    events = async_capture_events(hass, EVENT_ORGAIA)

    async def outage(change: str) -> None:
        service.down = True
        await coordinator.async_refresh()
        freezer.tick(timedelta(minutes=1))
        service.down = False
        service.write("item", change, {"title": change, "listId": "todo", "order": 9})
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    # A short hiccup: what changed meanwhile is news as usual.
    await outage("Kurz")
    with patch("custom_components.orgaia.coordinator.LATE_AFTER", -1.0):
        await outage("Lang")
    # Afterwards everything is on time again.
    service.write("item", "Danach", {"title": "Danach", "listId": "todo", "order": 10})
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    created = [(e.data["title"], e.data.get("late", False)) for e in events if e.data["type"] == "task_created"]
    assert created == [("Kurz", False), ("Lang", True), ("Danach", False)]
