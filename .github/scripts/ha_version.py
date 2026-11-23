"""Which pytest-homeassistant-custom-component to test with: for the newest Home Assistant, its beta, or a given one.

Each release of that package pins exactly one Home Assistant version and the Python it needs. Prints lines for
$GITHUB_OUTPUT: `phcc`, `homeassistant`, `python`, and `skip=true` when there is nothing to test (no beta out).

    python ha_version.py stable
    python ha_version.py beta
    python ha_version.py minimum 2025.6.0
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request

PACKAGE = "https://pypi.org/pypi/pytest-homeassistant-custom-component"


def get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def pinned(version: str) -> tuple[str, str]:
    """The Home Assistant version a release pins, and the Python it needs (as "3.14")."""
    info = get(f"{PACKAGE}/{version}/json")["info"]
    pins = [r for r in info.get("requires_dist") or [] if r.startswith("homeassistant==")]
    ha = pins[0].split("==")[1].split(";")[0].strip() if pins else "0.0.0"  # the oldest releases pin nothing
    python = re.search(r"3\.\d+", info.get("requires_python") or "")
    return ha, python.group(0) if python else "3.13"


def order(ha: str) -> tuple[int, ...]:
    """2026.11.0b3 before 2026.11.0, which comes before 2026.11.1."""
    m = re.match(r"(\d+)\.(\d+)\.(\d+)(?:b(\d+))?", ha)
    if not m:
        return (0,)
    year, month, patch, beta = m.groups()
    return (int(year), int(month), int(patch), int(beta) if beta is not None else 10**6)


def is_beta(ha: str) -> bool:
    return bool(re.search(r"(b|dev|rc)\d*$", ha))


def releases() -> list[str]:
    """All releases, newest first."""
    files = get(f"{PACKAGE}/json")["releases"]
    usable = [v for v, f in files.items() if f and not all(x.get("yanked") for x in f)]
    return sorted(usable, key=lambda v: max(x["upload_time"] for x in files[v]), reverse=True)


def main(track: str, wanted: str | None = None) -> None:
    versions = releases()
    found: tuple[str, str, str] | None = None
    if track in ("stable", "beta"):
        for v in versions[:60]:
            ha, python = pinned(v)
            if is_beta(ha) == (track == "beta"):
                found = (v, ha, python)
                break
            if track == "beta":
                break  # the newest release is a stable one: no beta out right now
    elif track == "minimum" and wanted:
        # Oldest first; the releases follow Home Assistant in order, so halve the range instead of asking for each.
        old = versions[::-1]
        lo, hi = 0, len(old) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if order(pinned(old[mid])[0]) < order(wanted):
                lo = mid + 1
            else:
                hi = mid
        ha, python = pinned(old[lo])
        found = (old[lo], ha, python)
    else:
        raise SystemExit(__doc__)
    if not found:
        print("skip=true")
        return
    v, ha, python = found
    print(f"phcc={v}\nhomeassistant={ha}\npython={python}\nskip=false")


if __name__ == "__main__":
    main(*sys.argv[1:3])
