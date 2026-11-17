"""The shared data model, as in Orgaia's packages/protocol/src/model.ts and hlc.ts.

A space is a set of entities per kind; every entity is a bag of fields. Changes travel as ops that
set fields, and for every field the write with the latest timestamp wins.
"""

from __future__ import annotations

import time
from typing import Any

KINDS = ("meta", "person", "list", "item", "sub", "occ", "tpl", "inv")
UNSAFE_KEYS = frozenset({"__proto__", "constructor", "prototype"})

# Cells are [timestamp, value] pairs: compact in storage and cheap to copy.
State = dict[str, dict[str, dict[str, list[Any]]]]


def empty_state() -> State:
    return {k: {} for k in KINDS}


def apply_op(state: State, op: dict[str, Any]) -> bool:
    """Applies an op in place. Returns True when it changed anything."""
    kind, eid, fields, ts = op.get("k"), op.get("e"), op.get("set"), op.get("ts")
    if (
        kind not in KINDS
        or not isinstance(eid, str)
        or eid in UNSAFE_KEYS
        or not isinstance(fields, dict)
        or not isinstance(ts, str)
    ):
        return False
    doc = state.setdefault(kind, {}).setdefault(eid, {})
    changed = False
    for field, value in fields.items():
        if field in UNSAFE_KEYS:
            continue
        cell = doc.get(field)
        if cell is None or ts > cell[0]:
            doc[field] = [ts, value]
            changed = True
    return changed


def merge_state(into: State, other: dict[str, Any]) -> bool:
    """Merges a state as the app stores it ({kind: {id: {field: {ts, v}}}}); the later write wins."""
    changed = False
    for kind in KINDS:
        table = other.get(kind) or {}
        if not isinstance(table, dict):
            continue
        for eid, doc in table.items():
            if eid in UNSAFE_KEYS or not isinstance(doc, dict):
                continue
            target = into.setdefault(kind, {}).setdefault(eid, {})
            for field, cell in doc.items():
                if field in UNSAFE_KEYS or not isinstance(cell, dict) or not isinstance(cell.get("ts"), str):
                    continue
                mine = target.get(field)
                if mine is None or cell["ts"] > mine[0]:
                    target[field] = [cell["ts"], cell.get("v")]
                    changed = True
    return changed


def plain(doc: dict[str, list[Any]]) -> dict[str, Any]:
    return {field: cell[1] for field, cell in doc.items()}


def to_app_state(state: State) -> dict[str, Any]:
    """The state in the app's form, {kind: {id: {field: {ts, v}}}}."""
    return {
        k: {e: {f: {"ts": c[0], "v": c[1]} for f, c in doc.items()} for e, doc in table.items()}
        for k, table in state.items()
    }


# --- Hybrid logical clock --------------------------------------------------------------------

MAX_DRIFT_MS = 24 * 60 * 60 * 1000
_MAX_COUNTER = 36**3 - 1
_DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"


def _base36(n: int, width: int) -> str:
    out = ""
    while n:
        n, r = divmod(n, 36)
        out = _DIGITS[r] + out
    return (out or "0").rjust(width, "0")


def hlc_wall(ts: str) -> int:
    try:
        return int(ts[:9], 36)
    except (TypeError, ValueError):
        return -1


def _hlc_counter(ts: str) -> int:
    try:
        return int(ts[9:12], 36)
    except (TypeError, ValueError):
        return 0


def now_ms() -> int:
    return int(time.time() * 1000)


class Clock:
    """Timestamps that sort as strings and always move forward: 9 chars wall clock, 3 chars counter, node id."""

    def __init__(self, node: str, now=now_ms) -> None:
        self.node = node
        self._now = now
        self._wall = 0
        self._counter = 0

    def tick(self) -> str:
        phys = self._now()
        if phys > self._wall:
            self._wall = phys
            self._counter = 0
        elif self._counter >= _MAX_COUNTER:
            self._wall += 1
            self._counter = 0
        else:
            self._counter += 1
        return _base36(self._wall, 9) + _base36(self._counter, 3) + self.node

    def observe(self, ts: str) -> None:
        wall = hlc_wall(ts)
        if wall < 0 or wall > self._now() + MAX_DRIFT_MS:
            return
        counter = _hlc_counter(ts)
        if wall > self._wall:
            self._wall = wall
            self._counter = counter
        elif wall == self._wall and counter > self._counter:
            self._counter = counter
