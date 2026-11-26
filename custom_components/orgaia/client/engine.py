"""Keeps one group in sync as a member of the kind ``integration``, as packages/core/src/engine.ts does for the app.

Home Assistant is never an admin of a group, so everything only admins do (letting people in, new
group keys, snapshots) is left out. It reads; once an admin allowed it in the app it also writes,
always in the name of a person of the group who said at Home Assistant who they are.

The engine does not depend on Home Assistant: it reads and
writes its state through ``to_dict``/``from_dict`` and reports changes through a callback.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
import secrets
from typing import Any
from urllib.parse import quote

import aiohttp

from ..protocol.b64 import from_b64, to_b64
from ..protocol.crypto import (
    CryptoError,
    Identity,
    open_record,
    open_sealed,
    seal_for,
    seal_record,
    verify_box_key,
)
from ..protocol.invite import InviteCode
from ..protocol.model import MAX_DRIFT_MS, Clock, State, apply_op, empty_state, hlc_wall, merge_state, now_ms
from ..protocol.view import SpaceView, build_view
from .api import Api, ApiError, space_path

_LOGGER = logging.getLogger(__name__)

# Why a group cannot be read right now, as far as Home Assistant can tell.
STATUS_OK = "ok"
STATUS_NEEDS_PLUS = "needs_plus"
STATUS_UPDATE = "update_required"
STATUS_REMOVED = "removed"
STATUS_OFFLINE = "offline"
# The group was deleted and waits a week in the trash: shown as it was, nothing can be changed.
STATUS_DELETED = "deleted"


# How long reading waits at a change whose group key has not reached this Home Assistant.
KEY_WAIT_MS = 3 * 24 * 60 * 60 * 1000


class JoinError(Exception):
    """Joining did not work: the invitation is wrong, used up, or the group cannot take a service."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class WriteError(Exception):
    """A change could not be made: ``read_only``, ``offline``, ``needs_plus``, ``removed``, ``full``,
    ``group_deleted`` or ``unknown``."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# One kind of entity, its id and the fields to set.
Change = tuple[str, str, dict[str, Any]]
# The service takes at most 200 changes at once; the app sends 100.
WRITE_BATCH = 100


def _random_id(n: int) -> str:
    return to_b64(secrets.token_bytes(n))


class GroupEngine:
    """One group, read (and, when allowed, written) with Home Assistant's own key."""

    def __init__(self, session: aiohttp.ClientSession, data: dict[str, Any], now: Callable[[], int] = now_ms) -> None:
        self.identity = Identity.from_seed(from_b64(data["seed"]))
        self.server: str = data["server"].rstrip("/")
        self.device_id: str = data.get("device") or _random_id(16)
        self.node: str = data.get("node") or _random_id(6).replace("-", "x").replace("_", "x")[:8].ljust(8, "0")
        self.space_id: str | None = data.get("space")
        self.join: dict[str, Any] | None = data.get("join")
        self.epoch: int = int(data.get("epoch", 0))
        self.keys: dict[int, str] = {int(k): v for k, v in (data.get("keys") or {}).items()}
        self.cursor: int = int(data.get("cursor", 0))
        # Id of the change at ``cursor``: the service tells by it when its history no longer goes on from there.
        self.cursor_id: str | None = data.get("cursorId")
        self.members: list[dict[str, Any]] = data.get("members") or []
        self.plan: dict[str, Any] | None = data.get("plan")
        # Set while the group is in the trash: ``at``, ``purgeAt`` (ms) and who deleted it.
        self.deleted: dict[str, Any] | None = data.get("deleted")
        self.state: State = data.get("state") or empty_state()
        self.status: str = data.get("status") or STATUS_OK
        # When the group was last read from the service (ms since 1970).
        self.synced_at: int | None = data.get("syncedAt")
        # When Home Assistant last stopped with this group, in ms; set only on a clean stop.
        self.stopped_at: int | None = data.get("stoppedAt")
        # Since when changes wait that need a group key this Home Assistant has not got; reading stops there.
        self.key_wait: int | None = data.get("keyWait")
        self._snapshot_read = False
        self.api = Api(session, self.server, self.identity, self.device_id)
        # The service's time when this machine's clock is far off: a clock a day behind would
        # otherwise make every change of the others look like it came from the future.
        self._now = lambda: now() + self.api.clock_offset
        self.clock = Clock(self.node, self._now)
        for table in self.state.values():
            for doc in table.values():
                for cell in doc.values():
                    self.clock.observe(cell[0])
        self._listeners: list[Callable[[], None]] = []
        self._version = 0
        self._view: tuple[int, SpaceView] | None = None
        self._sync_lock = asyncio.Lock()

    # --- Persistence -------------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": to_b64(self.identity.seed),
            "server": self.server,
            "device": self.device_id,
            "node": self.node,
            "space": self.space_id,
            "join": self.join,
            "epoch": self.epoch,
            "keys": {str(k): v for k, v in self.keys.items()},
            "cursor": self.cursor,
            "cursorId": self.cursor_id,
            "members": self.members,
            "plan": self.plan,
            "deleted": self.deleted,
            "state": self.state,
            "status": self.status,
            "syncedAt": self.synced_at,
            "stoppedAt": self.stopped_at,
            "keyWait": self.key_wait,
        }

    @staticmethod
    def new_data(server: str) -> dict[str, Any]:
        """Data for a fresh identity on a service."""
        return {"seed": to_b64(Identity.create().seed), "server": server.rstrip("/")}

    # --- Observation -------------------------------------------------------------------------

    def subscribe(self, fn: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(fn)
        return lambda: self._listeners.remove(fn) if fn in self._listeners else None

    def _changed(self) -> None:
        self._version += 1
        for fn in list(self._listeners):
            fn()

    @property
    def version(self) -> int:
        """Goes up with every change of the group."""
        return self._version

    def view(self) -> SpaceView:
        if self._view is None or self._view[0] != self._version:
            self._view = (self._version, build_view(self.space_id or "", "group", self.state))
        return self._view[1]

    # --- Writing ------------------------------------------------------------------------------

    @property
    def can_write(self) -> bool:
        """Whether an admin allowed this Home Assistant to write, as far as it was told."""
        return any(m.get("signPub") == self.identity.sign_pub and m.get("write") is True for m in self.members)

    def new_id(self) -> str:
        """An id for a new entry."""
        return _random_id(9)

    async def write(self, changes: list[Change], as_person: str) -> None:
        """Makes changes in the name of a person of the group.

        Nothing is kept for later: the changes reach the service now, or the call fails and the group
        stays as it was. So Home Assistant never shows a tick the others do not see.
        """
        if not changes:
            return
        if not self.space_id:
            raise WriteError("removed")
        if self.deleted:
            raise WriteError("group_deleted")
        try:
            if not self.can_write or not self.keys.get(self.epoch):
                # Allowed a moment ago, perhaps: ask before saying no.
                if not await self.refresh_space():
                    raise WriteError("removed")
                if not self.can_write:
                    raise WriteError("read_only")
            ops = [
                {
                    "id": _random_id(12),
                    "ts": self.clock.tick(),
                    "by": self.identity.sign_pub,
                    "k": kind,
                    "e": eid,
                    "set": fields,
                    "as": as_person,
                }
                for kind, eid, fields in changes
            ]
            for at in range(0, len(ops), WRITE_BATCH):
                batch = ops[at : at + WRITE_BATCH]
                await self._post(batch)
                for op in batch:
                    apply_op(self.state, op)
                self._changed()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise WriteError("offline") from err
        except ApiError as err:
            # From reading the group again on the way: the service is busy or away, or wants a newer version.
            if err.code == "update-required":
                self.status = STATUS_UPDATE
                raise WriteError("update_required") from err
            if err.code == "group-deleted":
                await self.refresh_space()
                raise WriteError("group_deleted") from err
            raise WriteError("offline" if err.status >= 500 or err.status == 429 else "unknown") from err

    async def _post(self, ops: list[dict[str, Any]]) -> None:
        path = space_path(self.space_id or "") + "/ops"
        for attempt in range(2):
            key = self.keys.get(self.epoch)
            if not key:
                raise WriteError("unknown")
            body = {
                "ops": [
                    {
                        "id": op["id"],
                        "rec": seal_record(self.space_id or "", self.epoch, from_b64(key), self.identity, op),
                    }
                    for op in ops
                ]
            }
            try:
                await self.api.req("POST", path, body)
                return
            except ApiError as err:
                if err.code == "stale-epoch" and attempt == 0 and await self.refresh_space():
                    # The group got a new key meanwhile: seal again with that one.
                    continue
                if err.code == "integration-read-only":
                    await self.refresh_space()
                    raise WriteError("read_only") from err
                if err.code == "update-required":
                    self.status = STATUS_UPDATE
                    raise WriteError("update_required") from err
                if err.status == 402:
                    raise WriteError("needs_plus") from err
                if err.status in (403, 404):
                    if not await self.refresh_space():
                        self._changed()
                    raise WriteError("removed") from err
                if err.code == "stale-epoch":
                    # Still another key than the service expects (after it was restored from a backup):
                    # nothing is full, it just cannot be written right now.
                    raise WriteError("offline") from err
                if err.status in (409, 413):
                    raise WriteError("full") from err
                if err.status >= 500 or err.status == 429:
                    raise WriteError("offline") from err
                raise WriteError("unknown") from err

    # --- Joining ------------------------------------------------------------------------------

    async def request_join(self, code: InviteCode, name: str) -> None:
        """Asks to join with an invitation for a service. An admin confirms it in the app."""
        if not verify_box_key(code.a, code.b, code.g):
            raise JoinError("invalid_link")
        profile = {"name": name[:60], "boxPub": self.identity.box_pub, "x": code.x}
        body = {"profile": seal_for(code.b, self.identity, "join:" + code.i, profile), "kind": "integration"}
        try:
            await self.api.req("POST", f"/v1/invites/{code.i}/join", body)
        except ApiError as err:
            raise JoinError(_join_reason(err)) from err
        self.join = {"invite": code.i, "admin": code.a}

    async def check_join(self) -> str:
        """Whether the admin answered: ``pending``, ``accepted``, ``rejected`` or ``expired``."""
        if self.space_id:
            return "accepted"
        if not self.join:
            return "expired"
        try:
            res = await self.api.req("GET", f"/v1/invites/{self.join['invite']}/status")
        except ApiError as err:
            if err.status in (404, 410):
                return "expired"
            raise
        state = res.get("state")
        if state == "accepted" and isinstance(res.get("spaceId"), str):
            self.space_id = res["spaceId"]
            await self.refresh_space()
            return "accepted" if self.keys else "pending"
        return state if state in ("pending", "rejected", "expired") else "pending"

    async def withdraw_join(self) -> None:
        """Takes a join request back that nobody answered, so the invitation can be used again and
        nobody accepts a Home Assistant that is no longer waiting. Services that do not know this yet say 404."""
        if self.space_id or not self.join:
            return
        try:
            await self.api.req("DELETE", f"/v1/invites/{self.join['invite']}/join")
        except (ApiError, aiohttp.ClientError, TimeoutError):
            return
        self.join = None

    async def leave(self) -> None:
        """Leaves the group, for when the integration is removed from Home Assistant."""
        if self.space_id:
            await self.api.req("POST", space_path(self.space_id) + "/leave")

    # --- Syncing ------------------------------------------------------------------------------

    def _adopt_envelope(self, info: dict[str, Any]) -> bool:
        """Takes the group keys, but only from an envelope an admin of the group sealed."""
        envelope = info.get("envelope")
        if not isinstance(envelope, str):
            return False
        try:
            payload, sender = open_sealed(envelope, self.identity, "envelope:" + info["id"])
        except CryptoError:
            return False
        admins = {m.get("signPub") for m in info.get("members") or [] if m.get("role") == "admin"}
        persons = self.state.get("person") or {}
        # The admin who invited is taken at their word only until the group itself is known.
        expected = not persons and bool(self.join) and self.join.get("admin") == sender
        if sender not in admins and not expected:
            return False
        # Once the group is known, keys are only taken from somebody on its own, encrypted list of
        # persons. What the service calls an admin is not enough: whoever runs it could add one.
        # Cells are [timestamp, value] pairs.
        pubs = {
            cell[1]
            for doc in persons.values()
            if isinstance(cell := doc.get("pub"), list)
            and len(cell) > 1
            and not (doc.get("removed") or [None, None])[1]
        }
        if persons and not expected and sender not in pubs:
            return False
        keys = payload.get("keys") if isinstance(payload, dict) else None
        if not isinstance(keys, dict):
            return False
        for epoch, key in keys.items():
            try:
                number = int(epoch)
            except (TypeError, ValueError):
                continue
            if isinstance(key, str) and 0 <= number < 2**31:
                self.keys[number] = key
        if self.keys:
            self.epoch = max(self.keys)
        return True

    async def refresh_space(self) -> bool:
        """Reads members, plan and keys. Returns False when Home Assistant is no longer in the group."""
        # With groups in the trash: such a group is still there for a week and may come back.
        infos = await self.api.req("GET", "/v1/spaces?deleted=1")
        info = next((s for s in infos or [] if s.get("id") == self.space_id), None)
        if info is None:
            self.status = STATUS_REMOVED
            self.deleted = None
            return False
        self.members = info.get("members") or []
        self.plan = info.get("plan")
        deleted = info.get("deleted")
        self.deleted = deleted if isinstance(deleted, dict) else None
        if self.deleted:
            self.status = STATUS_DELETED
        elif self.status == STATUS_DELETED:
            self.status = STATUS_OK
        self._adopt_envelope(info)
        return True

    def _known_author(self, sign_pub: str) -> bool:
        return sign_pub == self.identity.sign_pub or any(m.get("signPub") == sign_pub for m in self.members)

    def _apply_remote(self, rec: dict[str, Any]) -> bool:
        key = self.keys.get(rec.get("e")) if isinstance(rec, dict) else None
        if not key or not self._known_author(rec.get("a", "")):
            return False
        try:
            op = open_record(self.space_id or "", from_b64(key), rec)
        except CryptoError:
            return False
        if not isinstance(op, dict) or op.get("by") != rec.get("a") or not isinstance(op.get("ts"), str):
            return False
        # A device with a clock far ahead would otherwise win every later edit of these fields.
        if not 0 <= hlc_wall(op["ts"]) <= self._now() + MAX_DRIFT_MS:
            return False
        self.clock.observe(op["ts"])
        return apply_op(self.state, op)

    async def _load_snapshot(self) -> bool:
        """Merges the snapshot. ``_snapshot_read`` says afterwards whether it could be read at all."""
        self._snapshot_read = False
        path = space_path(self.space_id or "")
        snap = await self.api.req("GET", path + "/snapshot")
        if not isinstance(snap, dict):
            return False
        rec = snap.get("rec") or {}
        if not self.keys.get(rec.get("e")) or not self._known_author(rec.get("a", "")):
            await self.refresh_space()
        key = self.keys.get(rec.get("e"))
        if not key or not self._known_author(rec.get("a", "")):
            return False
        try:
            other = open_record(self.space_id or "", from_b64(key), rec)
        except CryptoError:
            return False
        # A device with a clock far ahead must not win through the snapshot what its single changes are refused.
        latest = self._now() + MAX_DRIFT_MS
        if isinstance(other, dict):
            for table in other.values():
                for doc in table.values() if isinstance(table, dict) else []:
                    if not isinstance(doc, dict):
                        continue
                    for field in [
                        f
                        for f, cell in doc.items()
                        if isinstance(cell, dict) and isinstance(cell.get("ts"), str) and hlc_wall(cell["ts"]) > latest
                    ]:
                        del doc[field]
        changed = merge_state(self.state, other) if isinstance(other, dict) else False
        self._snapshot_read = True
        upto = int(snap.get("uptoSeq") or 0)
        if upto > self.cursor:
            self.cursor_id = None
        self.cursor = max(self.cursor, upto)
        return changed

    async def sync(self) -> bool:
        """Fetches what changed. Returns True when the group looks different afterwards."""
        async with self._sync_lock:
            try:
                changed = await self._sync()
            except ApiError as err:
                if err.code == "integration-needs-plan":
                    self.status = STATUS_NEEDS_PLUS
                elif err.code == "update-required":
                    self.status = STATUS_UPDATE
                elif err.status in (403, 404):
                    # Removed from the group, or the group is gone.
                    if not await self.refresh_space():
                        self.status = STATUS_REMOVED
                        self._changed()
                        return True
                raise
            except (aiohttp.ClientError, TimeoutError):
                self.status = STATUS_OFFLINE
                raise
            if self.status == STATUS_REMOVED and not await self.refresh_space():
                # Found out while reading: Home Assistant is no longer in the group.
                self._changed()
                return True
            self.status = STATUS_DELETED if self.deleted else STATUS_OK
            self.synced_at = self._now()
            if changed:
                self._changed()
            return changed

    async def _sync(self) -> bool:
        if not self.space_id:
            raise JoinError("not_joined")
        if not self.keys:
            await self.refresh_space()
        path = space_path(self.space_id) + "/ops"
        changed = False
        asked_for_keys = False
        first_pull = self.cursor == 0
        tried_snapshot = False
        reset = False
        for _ in range(1000):
            at = f"&at={quote(self.cursor_id, safe='')}" if self.cursor_id else ""
            res = await self.api.req("GET", f"{path}?after={self.cursor}{at}")
            if res.get("reset"):
                # The service was restored from a backup: its history no longer goes on from what was read.
                # Read it from the start again; what is here stays, the newest value of each field wins.
                if reset:
                    break
                reset = True
                self.cursor = 0
                self.cursor_id = None
                first_pull = True
                tried_snapshot = False
                changed = True
                continue
            # A new member of a group with a long history starts from the snapshot.
            if first_pull and self.cursor == 0 and res.get("more") and not tried_snapshot:
                tried_snapshot = True
                changed = await self._load_snapshot() or changed
                if self.cursor > 0:
                    continue
            floor = int(res.get("floor") or 0)
            if floor > self.cursor:
                changed = await self._load_snapshot() or changed
                if not self._snapshot_read:
                    # What lies before can only be read from the snapshot. Its key may still be on the way:
                    # reading waits here for a few days instead of passing all of it for good.
                    if self.key_wait is None:
                        self.key_wait = self._now()
                    if self._now() - self.key_wait < KEY_WAIT_MS:
                        break
                elif self.key_wait is not None:
                    self.key_wait = None
                self.cursor = max(self.cursor, floor)
                self.cursor_id = None
                continue
            missing = False
            waiting = False
            for row in res.get("ops") or []:
                rec = row.get("rec") or {}
                epoch = rec.get("e")
                keyless = isinstance(epoch, int) and epoch > self.epoch and epoch not in self.keys
                # Written with a key or by a member Home Assistant does not know yet: read the group again first.
                if not asked_for_keys and (keyless or not self._known_author(rec.get("a", ""))):
                    missing = True
                    break
                # Still no key after asking: its envelope is not there yet. Reading waits at this change for a
                # few days instead of passing it for good; after that it is given up, as before.
                if keyless:
                    if self.key_wait is None:
                        self.key_wait = self._now()
                    if self._now() - self.key_wait < KEY_WAIT_MS:
                        waiting = True
                        break
                elif self.key_wait is not None and epoch in self.keys:
                    self.key_wait = None
                if self._apply_remote(rec):
                    changed = True
                self.cursor = int(row.get("seq") or self.cursor)
                self.cursor_id = row.get("id") or None
            if missing:
                asked_for_keys = True
                if not await self.refresh_space():
                    return True
                continue
            if waiting or not res.get("more"):
                break
        return changed

    async def on_event(self, event: dict[str, Any]) -> bool:
        """Handles a message from the live connection. Returns True when a sync is due."""
        if event.get("spaceId") != self.space_id:
            return False
        if event.get("t") == "ops":
            head = event.get("head")
            return not (isinstance(head, int) and head <= self.cursor)
        if event.get("t") in ("members", "joined"):
            if not await self.refresh_space():
                self._changed()
                return False
            return True
        return False


def _join_reason(err: ApiError) -> str:
    if err.code == "integration-needs-plan":
        return "needs_plus"
    if err.code == "too-many-integrations":
        return "too_many"
    if err.code in ("invite-invalid", "not-found") or err.status in (404, 410):
        return "invite_invalid"
    if err.code == "already-member":
        return "already_member"
    if err.code == "update-required":
        return "update_required"
    return "unknown"
