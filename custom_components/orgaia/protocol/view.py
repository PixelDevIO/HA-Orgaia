"""A typed picture of one group, built from its raw state, as Orgaia's packages/core/src/view.ts does.

Only what Home Assistant shows is built: people, lists, entries (with "everyone", teams and the
defaults of a project list resolved), subtasks and the exceptions of repeating entries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import plan_read as plans
from .model import State, plain

RSVP_PREFIX = "rsvp."
DONE_PREFIX = "done."
VOTE_PREFIX = "vote."
COMMENT_PREFIX = "c."
_PREFIXES = (RSVP_PREFIX, DONE_PREFIX, VOTE_PREFIX, COMMENT_PREFIX)

# Order of punctuation in the root collation JavaScript's localeCompare uses; ids only hold these.
_PUNCT = {"_": 0, "-": 1}


def locale_key(text: str) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Sorts ids and names like JavaScript's localeCompare: letters by their base first, lower case before upper."""
    primary: list[int] = []
    tertiary: list[int] = []
    for ch in text:
        if ch in _PUNCT:
            primary.append(_PUNCT[ch])
            tertiary.append(0)
        elif ch.isdigit():
            primary.append(100 + ord(ch))
            tertiary.append(0)
        elif ch.isalpha():
            primary.append(1000 + ord(ch.lower()))
            tertiary.append(1 if ch.isupper() else 0)
        else:
            primary.append(10 + ord(ch) % 80)
            tertiary.append(0)
    return tuple(primary), tuple(tertiary)


def _strings(x: Any) -> list[str] | None:
    return [v for v in x if isinstance(v, str)] if isinstance(x, list) else None


def _num(x: Any) -> float:
    if isinstance(x, bool):
        return float(x)
    if isinstance(x, (int, float)):
        return float(x)
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _per_person(fields: dict[str, Any], prefix: str) -> dict[str, Any] | None:
    out: dict[str, Any] | None = None
    for k, v in fields.items():
        if not k.startswith(prefix) or v is None:
            continue
        out = out or {}
        out[k[len(prefix) :]] = v
    return out


def _split_personal(raw: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in raw.items() if not k.startswith(_PREFIXES)}
    for name, prefix in (("rsvps", RSVP_PREFIX), ("doneBy", DONE_PREFIX), ("votes", VOTE_PREFIX)):
        found = _per_person(raw, prefix)
        if found:
            out[name] = found
    return out


def _latest(marks: list[dict[str, Any]]) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    for m in marks:
        if best is None or _num(m.get("at")) > _num(best.get("at")):
            best = m
    return best


def each_done(assignees: list[str], done_by: dict[str, Any] | None) -> dict[str, Any] | None:
    """ "Each for themselves" is done once every assignee ticked it off."""
    if not assignees:
        return None
    marks = [done_by[p] for p in assignees if done_by and isinstance(done_by.get(p), dict)]
    return _latest(marks) if len(marks) == len(assignees) else None


@dataclass
class SpaceView:
    space_id: str
    kind: str
    meta: dict[str, Any]
    persons: list[dict[str, Any]]
    lists: list[dict[str, Any]]
    items: list[dict[str, Any]]
    subs_by_item: dict[str, list[dict[str, Any]]]
    occs: dict[str, dict[str, Any]]
    person_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    list_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    item_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def name(self) -> str:
        name = self.meta.get("name")
        return name if isinstance(name, str) and name else ""

    def active_persons(self) -> list[dict[str, Any]]:
        return [p for p in self.persons if not p["removed"]]

    def names(self, ids: list[str]) -> list[str]:
        return [self.person_by_id[p]["name"] for p in ids if p in self.person_by_id]


def occ_id(item_id: str, d: str) -> str:
    return f"{item_id}|{d}"


def _list_type(t: Any) -> str:
    return t if t in ("shopping", "feed", "timetable", "roster") else "tasks"


def build_view(space_id: str, kind: str, state: State) -> SpaceView:
    meta_doc = state.get("meta", {}).get("space")
    meta: dict[str, Any] = plain(meta_doc) if meta_doc else {}
    raw_teams = meta.get("teams")
    teams = (
        [
            t
            for t in raw_teams
            if isinstance(t, dict)
            and isinstance(t.get("id"), str)
            and isinstance(t.get("name"), str)
            and not t.get("deleted")
        ]
        if isinstance(raw_teams, list)
        else []
    )
    if "teams" in meta:
        meta["teams"] = teams
    if meta.get("schoolOff"):
        meta["schoolOff"] = plans.read_school_off(meta["schoolOff"])

    persons: list[dict[str, Any]] = []
    for pid, doc in state.get("person", {}).items():
        p = plain(doc)
        if not isinstance(p.get("name"), str):
            continue
        person = {
            "id": pid,
            "name": p["name"],
            "color": int(_num(p.get("color"))),
            "pub": p.get("pub") or None,
            "role": "admin" if p.get("role") == "admin" else "member",
            "child": p.get("child") is True,
            "removed": bool(p.get("removed")),
            "order": _num(p.get("order")),
            "teams": _strings(p.get("teams")) or [],
        }
        persons.append(person)
    persons.sort(key=lambda p: (p["order"], locale_key(p["id"])))

    lists: list[dict[str, Any]] = []
    for lid, doc in state.get("list", {}).items():
        raw = plain(doc)
        if not isinstance(raw.get("name"), str) or raw.get("deleted"):
            continue
        ltype = _list_type(raw.get("type"))
        lst: dict[str, Any] = {
            "id": lid,
            "name": raw["name"],
            "color": int(_num(raw.get("color"))),
            "type": ltype,
            "order": _num(raw.get("order")),
        }
        if ltype == "tasks":
            if isinstance(raw.get("from"), str) and raw["from"]:
                lst["from"] = raw["from"]
            if isinstance(raw.get("dueDate"), str) and raw["dueDate"]:
                lst["dueDate"] = raw["dueDate"]
            if _strings(raw.get("assignees")):
                lst["assignees"] = _strings(raw.get("assignees"))
            if isinstance(raw.get("note"), str) and raw["note"]:
                lst["note"] = raw["note"]
            if raw.get("inbox") is True and kind == "private":
                lst["inbox"] = True
        elif ltype == "feed":
            lst["url"] = raw["url"] if isinstance(raw.get("url"), str) else ""
            lst["feedFor"] = raw["feedFor"] if isinstance(raw.get("feedFor"), list) else []
        elif ltype == "timetable":
            lst["timetable"] = plans.read_timetable(raw)
        elif ltype == "roster":
            lst["roster"] = plans.read_roster(raw)
        lists.append(lst)
    lists.sort(key=lambda lst: (lst["order"], locale_key(lst["id"])))
    list_by_id = {lst["id"]: lst for lst in lists}

    gone = {p["id"] for p in persons if p["removed"]}
    for lst in lists:
        if lst.get("feedFor") and any(p in gone for p in lst["feedFor"]):
            lst["feedFor"] = [p for p in lst["feedFor"] if p not in gone]

    def live(x: dict[str, Any]) -> dict[str, Any]:
        if not gone:
            return x
        out = dict(x)
        if isinstance(out.get("assignees"), list) and any(i in gone for i in out["assignees"]):
            out["assignees"] = [i for i in out["assignees"] if i not in gone]
        if isinstance(out.get("rotation"), list) and any(i in gone for i in out["rotation"]):
            out["rotation"] = [i for i in out["rotation"] if i not in gone]
        if out.get("driveTo") in gone:
            out["driveTo"] = None
        if out.get("driveFrom") in gone:
            out["driveFrom"] = None
        return out

    active = [p for p in persons if not p["removed"]]
    team_ids = {t["id"] for t in teams}

    def resolve(own: list[str], everyone: Any, for_teams: Any) -> list[str]:
        if kind == "private":
            return own
        if everyone:
            return [p["id"] for p in active]
        from_teams = [p["id"] for t in (_strings(for_teams) or []) if t in team_ids for p in active if t in p["teams"]]
        if not from_teams:
            return own
        return list(dict.fromkeys([*own, *from_teams]))

    items: list[dict[str, Any]] = []
    for iid, doc in state.get("item", {}).items():
        raw = plain(doc)
        i = live(_split_personal(raw))
        if not isinstance(i.get("title"), str) or not isinstance(i.get("listId"), str) or i.get("deleted"):
            continue
        lst = list_by_id.get(i["listId"])
        if lst is None:
            continue
        item = {**i, "id": iid, "kind": "event" if i.get("kind") == "event" else "task"}
        if not isinstance(item.get("assignees"), list):
            item["assignees"] = []
        else:
            item["assignees"] = [a for a in item["assignees"] if isinstance(a, str)]
        if item.get("mode") and item["mode"] not in ("any", "each", "together"):
            item["mode"] = None
        if not isinstance(item.get("repeat"), dict):
            item["repeat"] = None
        if item["kind"] == "task" and lst["type"] == "tasks":
            inherited: list[str] = []
            if (
                not item.get("from")
                and not item.get("dueDate")
                and not item.get("start")
                and not item.get("repeat")
                and (lst.get("from") or lst.get("dueDate"))
            ):
                if lst.get("from"):
                    item["from"] = lst["from"]
                    inherited.append("from")
                if lst.get("dueDate"):
                    item["dueDate"] = lst["dueDate"]
                    inherited.append("dueDate")
            if (
                not item["assignees"]
                and not item.get("everyone")
                and not _strings(item.get("teams"))
                and lst.get("assignees")
                and not _strings(item.get("rotation"))
            ):
                item["assignees"] = [p for p in lst["assignees"] if p not in gone]
                inherited.append("assignees")
            if inherited:
                item["fromList"] = inherited
        item["ownAssignees"] = [] if "assignees" in item.get("fromList", []) else list(item["assignees"])
        who = resolve(item["assignees"], item.get("everyone"), item.get("teams"))
        seats = item.get("seats")
        if isinstance(seats, (int, float)) and not isinstance(seats, bool) and seats > 0:
            yes = [
                (p, r)
                for p, r in (item.get("rsvps") or {}).items()
                if isinstance(r, dict) and r.get("a") == "yes" and p not in gone
            ]
            yes.sort(key=lambda pr: _num(pr[1].get("at")))
            who = [p for p, _ in yes[: int(seats)]]
        item["assignees"] = who
        if item.get("mode") == "each" and not item.get("repeat"):
            item["done"] = each_done(who, item.get("doneBy"))
        if not isinstance(item.get("done"), dict):
            item["done"] = None
        items.append(item)
    items.sort(key=lambda i: (_num(i.get("order")), _num(i.get("createdAt")), locale_key(i["id"])))
    item_by_id = {i["id"]: i for i in items}
    for item in items:
        bundle = _strings(item.get("bundle"))
        if item["done"] or not bundle:
            continue
        parts = [item_by_id[b] for b in bundle if b in item_by_id]
        if parts and all(p["done"] for p in parts):
            item["done"] = _latest([p["done"] for p in parts])

    subs_by_item: dict[str, list[dict[str, Any]]] = {}
    for sid, doc in state.get("sub", {}).items():
        s = plain(doc)
        if not isinstance(s.get("title"), str) or not isinstance(s.get("itemId"), str) or s.get("deleted"):
            continue
        subs_by_item.setdefault(s["itemId"], []).append(
            {
                "id": sid,
                "itemId": s["itemId"],
                "title": s["title"],
                "done": bool(s.get("done")),
                "order": _num(s.get("order")),
            }
        )
    for arr in subs_by_item.values():
        arr.sort(key=lambda s: (s["order"], locale_key(s["id"])))

    occs: dict[str, dict[str, Any]] = {}
    for oid, doc in state.get("occ", {}).items():
        o = live(_split_personal(plain(doc)))
        if isinstance(o.get("assignees"), list) and not o["assignees"]:
            del o["assignees"]
        sep = oid.rfind("|")
        if sep < 0:
            continue
        occ = {**o, "id": oid, "itemId": oid[:sep], "date": oid[sep + 1 :]}
        parent = item_by_id.get(occ["itemId"])
        if parent and parent.get("mode") == "each":
            occ["done"] = each_done(occ.get("assignees") or parent.get("assignees") or [], occ.get("doneBy"))
        occs[oid] = occ

    return SpaceView(
        space_id=space_id,
        kind=kind,
        meta=meta,
        persons=persons,
        lists=lists,
        items=items,
        subs_by_item=subs_by_item,
        occs=occs,
        person_by_id={p["id"]: p for p in persons},
        list_by_id=list_by_id,
        item_by_id=item_by_id,
    )
