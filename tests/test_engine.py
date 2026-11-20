"""The sync engine against the fake service: joining, reading, and what it refuses."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.orgaia.client.api import ApiError
from custom_components.orgaia.client.engine import STATUS_NEEDS_PLUS, STATUS_OK, STATUS_REMOVED, GroupEngine, JoinError
from custom_components.orgaia.protocol.crypto import Identity
from custom_components.orgaia.protocol.invite import parse_invite
from custom_components.orgaia.protocol.model import Clock, now_ms

from .fake_service import SERVER, SPACE, FakeService, fill_group


async def joined(service: FakeService) -> GroupEngine:
    engine = GroupEngine(MagicMock(), GroupEngine.new_data(SERVER))
    await engine.request_join(parse_invite(service.link()), "Home Assistant")
    assert await engine.check_join() == "pending"
    service.answer = "accepted"
    assert await engine.check_join() == "accepted"
    return engine


async def test_join_and_read(service: FakeService) -> None:
    fill_group(service, "2026-11-17")
    engine = await joined(service)
    assert service.ha_name == "Home Assistant"
    assert engine.space_id == SPACE and engine.keys
    assert await engine.sync() is True
    view = engine.view()
    assert view.name == "Familie"
    assert [p["name"] for p in view.persons] == ["Anna", "Ben"]
    assert {lst["id"] for lst in view.lists} == {"todo", "shop"}
    assert engine.status == STATUS_OK
    # Nothing new: nothing changes.
    assert await engine.sync() is False
    service.write("item", "s2", {"title": "Brot", "listId": "shop"})
    assert await engine.sync() is True
    assert "s2" in engine.view().item_by_id


async def test_state_survives_a_restart(service: FakeService) -> None:
    fill_group(service, "2026-11-17")
    engine = await joined(service)
    await engine.sync()
    again = GroupEngine(MagicMock(), engine.to_dict())
    assert again.view().name == "Familie"
    assert again.cursor == engine.cursor


async def test_rejects_wrong_invite(service: FakeService) -> None:
    engine = GroupEngine(MagicMock(), GroupEngine.new_data(SERVER))
    code = parse_invite(service.link())
    forged = code.__class__(**{**code.__dict__, "g": Identity.create().box_sig})
    with pytest.raises(JoinError, match="invalid_link"):
        await engine.request_join(forged, "HA")


async def test_ignores_strangers_and_far_future_clocks(service: FakeService) -> None:
    engine = await joined(service)
    service.write("meta", "space", {"name": "Familie"})
    service.write("item", "x", {"title": "Fremd"}, author=Identity.create())
    future = Clock("evil0000", lambda: now_ms() + 10 * 24 * 3600 * 1000).tick()
    service.write("meta", "space", {"name": "Gekapert"}, ts=future)
    await engine.sync()
    assert engine.view().name == "Familie"
    assert "x" not in engine.state["item"]


async def test_plus_ended_and_removed(service: FakeService) -> None:
    engine = await joined(service)
    service.block = (402, "integration-needs-plan")
    with pytest.raises(ApiError):
        await engine.sync()
    assert engine.status == STATUS_NEEDS_PLUS
    service.block = None
    await engine.sync()
    assert engine.status == STATUS_OK
    service.removed = True
    assert await engine.sync() is True
    assert engine.status == STATUS_REMOVED


async def test_live_events(service: FakeService) -> None:
    engine = await joined(service)
    await engine.sync()
    assert await engine.on_event({"t": "ops", "spaceId": "other", "head": 99}) is False
    assert await engine.on_event({"t": "ops", "spaceId": SPACE, "head": engine.cursor}) is False
    assert await engine.on_event({"t": "ops", "spaceId": SPACE, "head": engine.cursor + 1}) is True
    assert await engine.on_event({"t": "members", "spaceId": SPACE}) is True


async def test_reads_again_after_a_restore(service: FakeService) -> None:
    fill_group(service, "2026-11-17")
    engine = await joined(service)
    await engine.sync()
    kept = len(service.rows)
    service.write("item", "lost", {"title": "Nach dem Backup", "listId": "shop"})
    await engine.sync()
    assert engine.cursor_id
    # The service is restored from a backup taken before the last change, then someone writes something new.
    service.rows = service.rows[:kept]
    service.write("item", "s9", {"title": "Nach dem Restore", "listId": "shop"})
    assert await engine.sync() is True
    assert "s9" in engine.view().item_by_id
    # What Home Assistant read before stays; an app device sends it back to the service.
    assert "lost" in engine.view().item_by_id
    assert engine.cursor == len(service.rows)
    # And it goes on normally afterwards.
    service.write("item", "s10", {"title": "Danach", "listId": "shop"})
    assert await engine.sync() is True
    assert "s10" in engine.view().item_by_id


async def test_waits_for_a_group_key_it_has_not_got(service: FakeService) -> None:
    """A change written with a newer group key is not passed for good while its key is on the way."""
    from custom_components.orgaia.protocol.b64 import to_b64
    from custom_components.orgaia.protocol.crypto import random_bytes, seal_record

    fill_group(service, "2026-11-17")
    engine = await joined(service)
    await engine.sync()
    before = engine.cursor
    new_key = random_bytes(32)
    op = {
        "id": to_b64(random_bytes(9)),
        "ts": service.clock.tick(),
        "by": service.admin.sign_pub,
        "k": "item",
        "e": "s9",
        "set": {"title": "Butter", "listId": "shop"},
    }
    service.rows.append({"seq": len(service.rows) + 1, "rec": seal_record(SPACE, 2, new_key, service.admin, op)})
    # The envelope with the new key has not arrived: reading stops in front of the change.
    await engine.sync()
    assert engine.cursor == before and engine.key_wait is not None
    assert "s9" not in engine.view().item_by_id
    # It survives a restart, and the change is read once the key is there.
    again = GroupEngine(MagicMock(), engine.to_dict())
    service.epoch, service.key = 2, new_key
    assert await again.sync() is True
    assert "s9" in again.view().item_by_id and again.key_wait is None
