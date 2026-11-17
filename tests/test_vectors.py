"""The Python protocol against the test vectors made by Orgaia's TypeScript code (packages/core/test/ha-vectors.ts)."""

from __future__ import annotations

import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from custom_components.orgaia.protocol.agenda import current_occurrence, deadlines, is_overdue, open_counts
from custom_components.orgaia.protocol.b64 import from_b64
from custom_components.orgaia.protocol.crypto import (
    CryptoError,
    Identity,
    fingerprint,
    open_record,
    open_sealed,
    private_space,
    seal_for,
    seal_record,
    to_json,
    verify,
    verify_box_key,
)
from custom_components.orgaia.protocol.ics import parse_ics
from custom_components.orgaia.protocol.invite import parse_invite
from custom_components.orgaia.protocol.model import apply_op, empty_state, merge_state, to_app_state
from custom_components.orgaia.protocol.plans import PlanLabels, is_plan_item, with_plan_items
from custom_components.orgaia.protocol.recur import occurrence_dates, rotation_assignee
from custom_components.orgaia.protocol.view import build_view, occ_id

VECTORS = json.loads((Path(__file__).parent / "vectors" / "ha-v1.json").read_text())


def test_protocol_version_matches() -> None:
    from custom_components.orgaia.protocol import PROTOCOL_VERSION

    assert VECTORS["protocol"] == PROTOCOL_VERSION


@pytest.mark.parametrize("case", VECTORS["identities"])
def test_identity(case: dict) -> None:
    seed = from_b64(case["seed"])
    me = Identity.from_seed(seed)
    assert me.sign_pub == case["signPub"]
    assert me.box_pub == case["boxPub"]
    assert me.box_sig == case["boxSig"]
    assert verify_box_key(me.sign_pub, me.box_pub, me.box_sig)
    assert fingerprint(me.sign_pub) == case["fingerprint"]
    sid, key = private_space(seed)
    assert sid == case["privateSpaceId"]
    assert key == from_b64(case["privateSpaceKey"])


@pytest.mark.parametrize("case", VECTORS["records"])
def test_records(case: dict) -> None:
    key = from_b64(case["key"])
    author = Identity.from_seed(from_b64(case["authorSeed"]))
    sealed = case["sealed"]
    assert to_json(case["payload"]) == case["json"]
    # What TypeScript sealed, Python opens.
    assert open_record(case["spaceId"], key, sealed) == case["payload"]
    # Python seals the same bytes with the same nonce.
    assert seal_record(case["spaceId"], case["epoch"], key, author, case["payload"], from_b64(sealed["n"])) == sealed
    # Tampering is noticed.
    with pytest.raises(CryptoError):
        open_record(case["spaceId"] + "x", key, sealed)
    with pytest.raises(CryptoError):
        open_record(case["spaceId"], bytes(32), sealed)


@pytest.mark.parametrize("case", VECTORS["sealed"])
def test_sealed(case: dict) -> None:
    sender = Identity.from_seed(from_b64(case["senderSeed"]))
    recipient = Identity.from_seed(from_b64(case["recipientSeed"]))
    payload, by = open_sealed(case["sealed"], recipient, case["context"])
    assert payload == case["payload"]
    assert by == sender.sign_pub
    again = seal_for(
        recipient.box_pub,
        sender,
        case["context"],
        case["payload"],
        from_b64(case["ephSecret"]),
        from_b64(case["nonce"]),
    )
    assert again == case["sealed"]
    with pytest.raises(CryptoError):
        open_sealed(case["sealed"], recipient, case["context"] + "x")
    with pytest.raises(CryptoError):
        open_sealed(case["sealed"], sender, case["context"])


def test_auth_signature() -> None:
    auth = VECTORS["auth"]
    me = Identity.from_seed(from_b64(auth["seed"]))
    assert me.sign(auth["message"].encode()) == auth["sig"]
    assert verify(auth["sig"], auth["message"].encode(), me.sign_pub)


@pytest.mark.parametrize("case", VECTORS["invites"])
def test_invites(case: dict) -> None:
    parsed = parse_invite(case["text"])
    if case["parsed"] is None:
        assert parsed is None
    else:
        assert parsed is not None
        assert parsed.as_dict() == case["parsed"]


@pytest.mark.parametrize("case", VECTORS["views"])
def test_view(case: dict) -> None:
    state = empty_state()
    for op in case["ops"]:
        apply_op(state, op)
    assert to_app_state(state) == case["state"]
    # Any order of the same changes gives the same state.
    reversed_state = empty_state()
    for op in reversed(case["ops"]):
        apply_op(reversed_state, op)
    assert reversed_state == state

    view = build_view("gVectors", "group", state)
    today, minute = case["today"], case["minute"]
    expect = case["expect"]
    assert [
        {
            "id": p["id"],
            "name": p["name"],
            "removed": p["removed"],
            "child": p["child"],
            "role": p["role"],
            "teams": p["teams"],
        }
        for p in view.persons
    ] == expect["persons"]
    assert [{"id": lst["id"], "name": lst["name"], "type": lst["type"]} for lst in view.lists] == expect["lists"]
    got = []
    for i in view.items:
        occurrences = []
        if i.get("repeat"):
            for d in occurrence_dates(i, "2026-11-01", "2026-12-31"):
                occ = view.occs.get(occ_id(i["id"], d)) or {}
                turn = rotation_assignee(i, d)
                occurrences.append(
                    {
                        "date": d,
                        "done": bool(occ.get("done")),
                        "skip": bool(occ.get("skip")),
                        "title": occ.get("title"),
                        "start": occ.get("start"),
                        "end": occ.get("end"),
                        "assignees": occ["assignees"] if "assignees" in occ else ([turn] if turn else i["assignees"]),
                    }
                )
        got.append(
            {
                "id": i["id"],
                "listId": i["listId"],
                "kind": i["kind"],
                "title": i["title"],
                "note": i.get("note"),
                "assignees": i["assignees"],
                "done": bool(i["done"]),
                "doneBy": i["done"]["by"] if i["done"] else None,
                "dueDate": i.get("dueDate"),
                "dueTime": i.get("dueTime"),
                "start": i.get("start"),
                "end": i.get("end"),
                "allDay": bool(i.get("allDay")),
                "repeats": bool(i.get("repeat")),
                "overdue": is_overdue(i, today, minute),
                "current": current_occurrence(view, i, today),
                "occurrences": occurrences,
            }
        )
    for mine, theirs in zip(got, expect["items"], strict=True):
        assert mine == theirs, mine["id"]
    assert dict(sorted(open_counts(view, today).items())) == expect["openCounts"]


def test_deadlines() -> None:
    """Deadlines of tasks, repeating ones without a time slot included."""
    case = VECTORS["deadlines"]
    state = empty_state()
    for op in VECTORS["views"][0]["ops"]:
        apply_op(state, op)
    view = build_view("gVectors", "group", state)
    got = [
        {
            "itemId": d.item["id"],
            "title": d.item["title"],
            "date": d.date,
            "time": d.time,
            "occDate": d.occ_date,
            "done": d.done,
            "assignees": d.item.get("assignees") or [],
        }
        for d in deadlines(view, case["from"], case["to"])
    ]
    assert got == case["expect"]


@pytest.mark.parametrize("case", VECTORS["plans"])
def test_plans(case: dict) -> None:
    """Packing tasks, school days and working time come out exactly as in the app."""
    state = empty_state()
    merge_state(state, case["state"])
    view = build_view("gPlans", "group", state)
    assert [{"id": lst["id"], "type": lst["type"]} for lst in view.lists] == case["lists"]
    labels = PlanLabels(case["labels"]["pack"], case["labels"]["school"], case["labels"]["work"])
    full = with_plan_items(view, labels, case["today"])
    derived = [{k: v for k, v in i.items() if k != "done"} for i in full.items if is_plan_item(i)]
    for mine, theirs in zip(derived, case["items"], strict=True):
        assert mine == theirs, theirs["id"]
    assert sorted(oid for oid, o in full.occs.items() if o.get("skip")) == case["skips"]


def test_feeds() -> None:
    """Subscribed calendars: the same file gives the same entries as in the app, in the same zone."""
    case = VECTORS["feeds"]
    zone = ZoneInfo(case["zone"])
    for c in case["cases"]:
        got = [e.to_json() for e in parse_ics(c["text"], c["from"], c["to"], zone)]
        assert got == c["expect"]
