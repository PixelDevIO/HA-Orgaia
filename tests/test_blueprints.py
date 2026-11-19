"""The automation blueprints are valid and become working automations."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.automation.config import AUTOMATION_BLUEPRINT_SCHEMA, async_validate_config_item
from homeassistant.components.blueprint import models
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import load_yaml
import pytest

FOLDER = Path(__file__).parents[1] / "blueprints" / "automation" / "orgaia"
FILES = sorted(FOLDER.glob("*.yaml"))


def test_there_are_blueprints() -> None:
    assert len(FILES) >= 6


@pytest.mark.parametrize("path", FILES, ids=[p.stem for p in FILES])
async def test_blueprint_is_valid(hass: HomeAssistant, path: Path) -> None:
    assert await async_setup_component(hass, "automation", {})
    blueprint = models.Blueprint(load_yaml(path), expected_domain="automation", schema=AUTOMATION_BLUEPRINT_SCHEMA)
    assert blueprint.metadata["source_url"].endswith(f"blueprints/automation/orgaia/{path.name}")
    inputs = {}
    for key, spec in blueprint.inputs.items():
        if spec and "default" in spec:
            continue
        inputs[key] = {
            "person": "person.anna",
            "notify_device": "abc123",
            "calendar": "calendar.familie_calendar",
        }[key]
    config = models.BlueprintInputs(blueprint, {"use_blueprint": {"path": path.name, "input": inputs}})
    substituted = config.async_substitute()
    # The companion app cannot be loaded in tests: its notify action is checked as a plain notify call.
    substituted["actions"] = [
        {"action": "notify.notify", "data": {k: v for k, v in a.items() if k in ("title", "message", "data")}}
        if a.get("domain") == "mobile_app"
        else a
        for a in substituted["actions"]
    ]
    assert any(a.get("action") == "notify.notify" for a in substituted["actions"])
    checked = await async_validate_config_item(hass, "test", {"id": "t", **substituted})
    assert checked is not None and checked.validation_error is None, checked.validation_error
