"""A small stand-in for Orgaia's sync service with one group, written by an admin with real encryption."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import aiohttp

from custom_components.orgaia.client.api import ApiError
from custom_components.orgaia.protocol.b64 import to_b64
from custom_components.orgaia.protocol.crypto import Identity, open_sealed, random_bytes, seal_for, seal_record
from custom_components.orgaia.protocol.model import Clock, now_ms

SERVER = "https://orgaia.test"
SPACE = "space-familie"
INVITE = "inv-1"


class FakeService:
    def __init__(self) -> None:
        self.admin = Identity.create()
        self.key = random_bytes(32)
        self.epoch = 1
        self.clock = Clock("admin000", now_ms)
        self.rows: list[dict[str, Any]] = []
        self.ha_sign: str | None = None
        self.ha_box: str | None = None
        self.ha_name: str | None = None
        self.answer = "pending"  # what the admin decided: pending, accepted, rejected
        self.removed = False
        self.left = False
        self.block: tuple[int, str] | None = None
        # The service or the internet is gone: every call fails as a connection error does.
        self.down = False
        self.calls: list[tuple[str, str]] = []

    # --- What the admin does in the app ---------------------------------------------------------

    def link(self, name: str = "Familie") -> str:
        q = {
            "v": "1",
            "s": SERVER,
            "i": INVITE,
            "a": self.admin.sign_pub,
            "b": self.admin.box_pub,
            "g": self.admin.box_sig,
            "x": "secret",
            "n": name,
        }
        return f"{SERVER}/join#{urlencode(q)}"

    def write(
        self, kind: str, eid: str, fields: dict[str, Any], author: Identity | None = None, ts: str | None = None
    ) -> None:
        author = author or self.admin
        op = {
            "id": to_b64(random_bytes(9)),
            "ts": ts or self.clock.tick(),
            "by": author.sign_pub,
            "k": kind,
            "e": eid,
            "set": fields,
        }
        self.rows.append({"seq": len(self.rows) + 1, "rec": seal_record(SPACE, self.epoch, self.key, author, op)})

    # --- The service ---------------------------------------------------------------------------

    def _members(self) -> list[dict[str, Any]]:
        out = [{"signPub": self.admin.sign_pub, "boxPub": self.admin.box_pub, "role": "admin", "kind": "person"}]
        if self.ha_sign and self.answer == "accepted":
            out.append({"signPub": self.ha_sign, "boxPub": self.ha_box, "role": "member", "kind": "integration"})
        return out

    async def req(self, method: str, path: str, body: Any = None) -> Any:
        self.calls.append((method, path))
        if self.down:
            raise aiohttp.ClientConnectionError("down")
        url = urlparse(path)
        if method == "POST" and url.path == f"/v1/invites/{INVITE}/join":
            assert body["kind"] == "integration"
            profile, sender = open_sealed(body["profile"], self.admin, "join:" + INVITE)
            self.ha_sign, self.ha_box, self.ha_name = sender, profile["boxPub"], profile["name"]
            return {"ok": True}
        if method == "GET" and url.path == f"/v1/invites/{INVITE}/status":
            return {"state": self.answer, **({"spaceId": SPACE} if self.answer == "accepted" else {})}
        if method == "GET" and url.path == "/v1/spaces":
            if self.removed or self.answer != "accepted":
                return []
            envelope = seal_for(
                self.ha_box, self.admin, "envelope:" + SPACE, {"keys": {str(self.epoch): to_b64(self.key)}}
            )
            return [{"id": SPACE, "members": self._members(), "plan": {"tier": "plus"}, "envelope": envelope}]
        if method == "GET" and url.path == f"/v1/spaces/{SPACE}/ops":
            if self.removed:
                raise ApiError(403, "not-member")
            if self.block:
                raise ApiError(*self.block)
            after = int(parse_qs(url.query).get("after", ["0"])[0])
            return {"ops": [r for r in self.rows if r["seq"] > after], "more": False, "floor": 0}
        if method == "POST" and url.path == f"/v1/spaces/{SPACE}/leave":
            self.left = True
            return {"ok": True}
        raise ApiError(404, "not-found")


def fill_group(svc: FakeService, today: str) -> None:
    """A family with a task list, a shopping list, a repeating chore and an appointment."""
    svc.write("meta", "space", {"name": "Familie"})
    svc.write("person", "anna", {"name": "Anna", "pub": svc.admin.sign_pub, "role": "admin", "order": 1})
    svc.write("person", "ben", {"name": "Ben", "order": 2})
    svc.write("list", "todo", {"name": "Haushalt", "type": "tasks", "order": 1})
    svc.write("list", "shop", {"name": "Einkauf", "type": "shopping", "order": 2})
    svc.write(
        "item",
        "t1",
        {"title": "Keller aufräumen", "listId": "todo", "assignees": ["ben"], "dueDate": "2000-01-01", "order": 1},
    )
    svc.write(
        "item", "t2", {"title": "Steuer", "listId": "todo", "dueDate": today, "note": "Belege suchen", "order": 2}
    )
    svc.write("item", "t3", {"title": "Erledigt", "listId": "todo", "done": {"at": now_ms(), "by": "anna"}, "order": 3})
    svc.write(
        "item",
        "t4",
        {"title": "Müll raus", "listId": "todo", "start": f"{today}T19:00", "repeat": {"freq": "day"}, "order": 4},
    )
    svc.write("item", "s1", {"title": "Milch", "listId": "shop", "order": 1})
    svc.write(
        "item",
        "e1",
        {
            "title": "Elternabend",
            "listId": "todo",
            "kind": "event",
            "start": f"{today}T23:00",
            "end": f"{today}T23:30",
            "location": "Schule",
            "order": 5,
        },
    )
    svc.write("sub", "t2a", {"title": "Kontoauszüge", "itemId": "t2", "order": 1})
