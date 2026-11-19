"""Releasing a shopping list, as Orgaia's packages/core/src/shopping-read.ts and shopping-trip.ts.

A shopping list of a group is written by everybody until somebody says it is complete. Only then is
it something to do: whoever is out anyway takes it over, and ends the trip when done.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

TAKE_PREFIX = "take."
TRIP_PREFIX = "trip~"

_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

# off: no release for this list. draft: still being written. ready: released, nobody goes yet.
# going: somebody took it over.
STATE_OFF = "off"
STATE_DRAFT = "draft"
STATE_READY = "ready"
STATE_GOING = "going"


def _num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x == x and x not in (float("inf"), -float("inf"))


def read_trip(raw: dict[str, Any]) -> dict[str, Any]:
    """The release of a shopping list from its fields. Another member could send anything, so all is checked."""
    out: dict[str, Any] = {}
    if raw.get("gate") is False:
        out["gate"] = False
    r = raw.get("ready")
    if isinstance(r, dict) and isinstance(r.get("by"), str) and _num(r.get("at")):
        ready: dict[str, Any] = {"by": r["by"], "at": r["at"]}
        if isinstance(r.get("due"), str) and _DATE.fullmatch(r["due"]):
            ready["due"] = r["due"]
        who = [p for p in r["for"] if isinstance(p, str)] if isinstance(r.get("for"), list) else []
        if who:
            ready["for"] = who
        if isinstance(r.get("note"), str) and r["note"].strip():
            ready["note"] = r["note"].strip()[:200]
        out["ready"] = ready
        # Only answers to this very release count.
        takes = {
            k[len(TAKE_PREFIX) :]: {"at": v["at"], "r": v["r"]}
            for k, v in raw.items()
            if k.startswith(TAKE_PREFIX) and isinstance(v, dict) and _num(v.get("at")) and v.get("r") == r["at"]
        }
        if takes:
            out["takes"] = takes
    last = raw.get("lastTrip")
    if isinstance(last, dict) and isinstance(last.get("by"), str) and _num(last.get("at")):
        out["lastTrip"] = {
            "by": last["by"],
            "at": last["at"],
            "n": int(last["n"]) if _num(last.get("n")) else 0,
            "left": int(last["left"]) if _num(last.get("left")) else 0,
        }
        if _num(last.get("missed")) and last["missed"] > 0:
            out["lastTrip"]["missed"] = last["missed"]
        if isinstance(last.get("from"), str):
            out["lastTrip"]["from"] = last["from"]
    return out


@dataclass(frozen=True)
class Trip:
    state: str
    open: int
    bought: int
    ready: dict[str, Any] | None = None
    # Person id of who shops, and since when.
    shopper: str | None = None
    since: float | None = None


def has_gate(view: Any, lst: dict[str, Any]) -> bool:
    """Whether a list can be released at all."""
    return view.kind == "group" and lst["type"] == "shopping" and lst.get("gate") is not False


def shopper_of(view: Any, lst: dict[str, Any]) -> tuple[str, float] | None:
    """Who took the list over: the first to say so; two at the same moment are settled by their ids."""
    best: tuple[str, float] | None = None
    for pid, take in (lst.get("takes") or {}).items():
        p = view.person_by_id.get(pid)
        if not p or p["removed"]:
            continue
        if best is None or take["at"] < best[1] or (take["at"] == best[1] and pid < best[0]):
            best = (pid, take["at"])
    return best


def trip_of(view: Any, lst: dict[str, Any]) -> Trip:
    items = [i for i in view.items if i["listId"] == lst["id"]]
    n_open = sum(1 for i in items if not i.get("done"))
    bought = len(items) - n_open
    if not has_gate(view, lst):
        return Trip(STATE_OFF, n_open, bought)
    ready = lst.get("ready")
    if not ready:
        return Trip(STATE_DRAFT, n_open, bought)
    shopper = shopper_of(view, lst)
    if shopper:
        return Trip(STATE_GOING, n_open, bought, ready, shopper[0], shopper[1])
    return Trip(STATE_READY, n_open, bought, ready)


def trip_overdue(trip: Trip, today: str) -> bool:
    """Past its day without anybody having bought it."""
    due = (trip.ready or {}).get("due")
    return trip.state in (STATE_READY, STATE_GOING) and bool(due) and due < today


def is_late(item: dict[str, Any], trip: Trip) -> bool:
    """An article that came onto the list after it was released."""
    late = item.get("late")
    return bool(trip.ready) and not item.get("done") and _num(late) and late >= trip.ready["at"]


# --- Aisles, articles not got, several articles at once, fixed purchases ------------------------
# As Orgaia's packages/core/src/shopping-extra.ts.

AISLES = [
    "produce",
    "bakery",
    "dairy",
    "meat",
    "frozen",
    "pantry",
    "drinks",
    "sweets",
    "drugstore",
    "household",
    "other",
]

AISLE_NAMES = {
    "de": {
        "produce": "Obst & Gemüse",
        "bakery": "Brot & Backwaren",
        "dairy": "Milch, Käse & Eier",
        "meat": "Fleisch, Wurst & Fisch",
        "frozen": "Tiefkühl",
        "pantry": "Vorrat",
        "drinks": "Getränke",
        "sweets": "Süßes & Knabbern",
        "drugstore": "Drogerie",
        "household": "Haushalt",
        "other": "Sonstiges",
    },
    "en": {
        "produce": "Fruit & veg",
        "bakery": "Bakery",
        "dairy": "Dairy & eggs",
        "meat": "Meat & fish",
        "frozen": "Frozen",
        "pantry": "Pantry",
        "drinks": "Drinks",
        "sweets": "Sweets & snacks",
        "drugstore": "Toiletries",
        "household": "Household",
        "other": "Other",
    },
}

# A first guess from the word itself, before anybody sorted the article by hand. German and English.
_GUESS: list[tuple[str, list[str]]] = [
    ("produce", ["apfel", "äpfel", "banane", "birne", "tomate", "gurke", "salat", "kartoffel", "zwiebel", "knoblauch", "paprika", "karotte", "möhre", "zitrone", "orange", "trauben", "beeren", "erdbeer", "pilz", "champignon", "zucchini", "brokkoli", "spinat", "kräuter", "petersilie", "avocado", "obst", "gemüse", "apple", "banana", "tomato", "potato", "onion", "lemon", "fruit", "vegetable"]),  # noqa: E501
    ("bakery", ["brot", "brötchen", "toast", "semmel", "baguette", "croissant", "kuchen", "brezel", "bread", "roll"]),
    ("dairy", ["milch", "käse", "joghurt", "butter", "sahne", "quark", "ei", "eier", "margarine", "schmand", "frischkäse", "mozzarella", "milk", "cheese", "yoghurt", "yogurt", "cream", "egg"]),  # noqa: E501
    ("meat", ["fleisch", "hack", "wurst", "schinken", "salami", "hähnchen", "huhn", "pute", "steak", "fisch", "lachs", "thunfisch", "aufschnitt", "speck", "meat", "chicken", "ham", "fish", "bacon"]),  # noqa: E501
    ("frozen", ["tk", "tiefkühl", "eis", "pizza", "pommes", "frozen", "ice cream"]),
    ("pantry", ["nudeln", "pasta", "spaghetti", "reis", "mehl", "zucker", "salz", "öl", "essig", "müsli", "haferflocken", "cornflakes", "konserve", "dose", "tomatenmark", "passierte", "linsen", "bohnen", "kaffee", "tee", "honig", "marmelade", "nutella", "gewürz", "pfeffer", "brühe", "rice", "flour", "sugar", "coffee", "tea", "oil"]),  # noqa: E501
    ("drinks", ["wasser", "saft", "cola", "limo", "bier", "wein", "sprudel", "schorle", "water", "juice", "beer", "wine"]),
    ("sweets", ["schokolade", "chips", "kekse", "gummibärchen", "süßigkeiten", "snack", "riegel", "chocolate", "cookies", "candy"]),  # noqa: E501
    ("drugstore", ["zahnpasta", "zahnbürste", "shampoo", "duschgel", "seife", "deo", "creme", "windeln", "tampons", "binden", "rasierer", "pflaster", "toothpaste", "soap", "diapers"]),  # noqa: E501
    ("household", ["spülmittel", "waschmittel", "klopapier", "toilettenpapier", "küchenrolle", "müllbeutel", "schwamm", "putzmittel", "alufolie", "frischhaltefolie", "batterien", "tabs", "weichspüler", "detergent", "toilet paper", "bin bags"]),  # noqa: E501
]

_WORDS = re.compile(r"[^a-zäöüß]+")


def guess_aisle(title: str) -> str:
    whole = title.lower()
    words = [w for w in _WORDS.split(whole) if w]
    for aisle, keys in _GUESS:
        # German puts the kind last: "Vollkornbrot" is bread, "Hafermilch" is milk.
        for k in keys:
            if any(w == k or (len(k) >= 4 and w.endswith(k)) for w in words) or (len(k) > 4 and k in whole):
                return aisle
    return "other"


def aisle_memory(items: list[dict[str, Any]]) -> dict[str, str]:
    """How each article was sorted last time, by its title, from all articles the group ever had."""
    best: dict[str, tuple[float, str]] = {}
    for i in items:
        aisle, title = i.get("aisle"), i.get("title")
        if aisle not in AISLES or not isinstance(title, str):
            continue
        key = title.strip().lower()
        at = i.get("createdAt") if _num(i.get("createdAt")) else 0
        if key not in best or at > best[key][0]:
            best[key] = (at, aisle)
    return {k: v[1] for k, v in best.items()}


def aisle_of(memory: dict[str, str], item: dict[str, Any]) -> str:
    """As sorted by hand, else as the same article was sorted last time, else a guess from the word."""
    if item.get("aisle") in AISLES:
        return item["aisle"]
    title = item.get("title") or ""
    return memory.get(title.strip().lower()) or guess_aisle(title)


def by_aisle(memory: dict[str, str], items: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """Articles in the order of the aisles; inside an aisle as they were added."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for i in items:
        groups.setdefault(aisle_of(memory, i), []).append(i)
    return [(a, groups[a]) for a in AISLES if a in groups]


def missed_of(item: dict[str, Any]) -> dict[str, Any] | None:
    """Who did not get an article while out shopping, and when."""
    m = item.get("missed")
    if isinstance(m, dict) and isinstance(m.get("by"), str) and _num(m.get("at")):
        return {"by": m["by"], "at": m["at"]}
    return None


_UNITS = ["x", "stück", "stk", "st", "g", "gr", "kg", "l", "ml", "pck", "pkg", "packung", "packungen", "dose", "dosen", "flasche", "flaschen", "glas", "gläser", "bund", "becher", "tüte", "tüten", "kiste", "kisten", "rolle", "rollen", "pcs", "pack", "can", "cans", "bottle", "bottles"]  # noqa: E501
_LEAD = re.compile(r"^(\d+(?:[.,]\d+)?)\s*(" + "|".join(_UNITS) + r")?\.?\s+(.+)$", re.IGNORECASE)


def parse_articles(text: str) -> list[dict[str, str]]:
    """ "Milch, 2 Brot, 500 g Kaffee": one or more articles, an amount in front taken as the quantity."""
    out = []
    for part in (p.strip() for p in re.split(r"[,;\n]+", text)):
        if not part:
            continue
        m = _LEAD.match(part)
        if not m:
            out.append({"title": part})
            continue
        n, unit, rest = m.group(1), m.group(2), m.group(3)
        out.append({"title": rest.strip(), "qty": f"{n} {unit}" if unit and unit.lower() != "x" else n})
    return out


_COUNT = re.compile(
    r"^(\d+)(\s*(?:x|stück|stk|st|pck|pkg|packung(?:en)?|dosen?|flaschen?|glas|gläser|bund|becher|tüten?|kisten?|rollen?)\.?)?$",
    re.IGNORECASE,
)


def can_step(qty: str | None) -> bool:
    """Whether + and − can change a quantity ("2", "3 Pck"), not "500 g". An empty one counts as 1."""
    return not (qty or "").strip() or _COUNT.match(qty.strip()) is not None


def step_qty(qty: str | None, delta: int) -> str | None:
    """One more or one less, never below 1. None for 1 without a unit."""
    m = _COUNT.match((qty or "").strip() or "1")
    if not m:
        return qty
    n = max(1, int(m.group(1)) + delta)
    unit = m.group(2) or ""
    return None if n == 1 and not unit else f"{n}{unit}"


SHOP_SET_PREFIX = "set."


def shop_sets(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """The fixed purchases of a shopping list, such as "Wocheneinkauf", stored on the list's fields."""
    out = []
    for k, v in raw.items():
        if not k.startswith(SHOP_SET_PREFIX) or not isinstance(v, dict):
            continue
        if not isinstance(v.get("name"), str) or not isinstance(v.get("items"), list):
            continue
        items = [
            {"title": x["title"][:80], **({"qty": x["qty"][:30]} if isinstance(x.get("qty"), str) and x["qty"] else {})}
            for x in v["items"]
            if isinstance(x, dict) and isinstance(x.get("title"), str)
        ][:100]
        out.append({"id": k[len(SHOP_SET_PREFIX) :], "name": v["name"][:60], "items": items})
    return sorted(out, key=lambda x: x["name"].lower())
