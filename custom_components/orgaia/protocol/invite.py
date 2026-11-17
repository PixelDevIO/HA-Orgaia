"""Invitation codes and links, as parseCode in Orgaia's packages/protocol/src/wire.ts reads them."""

from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import parse_qsl

_WEB = re.compile(r"^https://[^/?#]+/join/?[#?](.*)$", re.S)
_APP = re.compile(r"^orgaia:///?(join|link)\?(.*)$", re.S)


@dataclass(frozen=True)
class InviteCode:
    """An invitation: the sync service, the invite id, the inviting admin's keys and a secret."""

    s: str
    i: str
    a: str
    b: str
    g: str
    x: str
    n: str | None = None

    @property
    def server(self) -> str:
        return self.s.rstrip("/")

    def as_dict(self) -> dict[str, str | int]:
        out: dict[str, str | int] = {
            "v": 1,
            "s": self.s,
            "i": self.i,
            "a": self.a,
            "b": self.b,
            "g": self.g,
            "x": self.x,
        }
        if self.n:
            out["n"] = self.n
        return out


def parse_invite(text: str) -> InviteCode | None:
    """Reads an invitation link (https://…/join#…) or code (orgaia://join?…). None for anything else."""
    clean = (text or "").strip()
    web = _WEB.match(clean)
    if web:
        what, query = "join", web.group(1)
    else:
        app = _APP.match(clean)
        if not app:
            return None
        what, query = app.group(1), app.group(2)
    if what != "join":
        return None
    q: dict[str, str] = {}
    for k, v in parse_qsl(query, keep_blank_values=True):
        q.setdefault(k, v)
    if q.get("v") != "1":
        return None
    fields = {k: q.get(k, "") for k in ("i", "a", "b", "g", "x")}
    if not all(fields.values()):
        return None
    name = q.get("n", "")[:60] or None
    return InviteCode(s=q.get("s", ""), n=name, **fields)
