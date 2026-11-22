"""The ready-made dashboard: today, the shopping and the week of a group, one tap away in the sidebar.

Home Assistant keeps its dashboards in a registry of its own that an integration cannot add to, so this
one is served the way a YAML dashboard is: a fixed configuration that only names the strategy
(`custom:orgaia`, part of the card file). It cannot be edited; whoever wants to arrange things
differently builds a dashboard of their own with the Orgaia card. All of it is a convenience: when
Home Assistant changes underneath, the integration goes on without the dashboard.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.json import json_bytes, json_fragment

from .const import CONF_DASHBOARD

_LOGGER = logging.getLogger(__name__)

ICON = "mdi:calendar-check"


def dashboard_path(entry: ConfigEntry) -> str:
    """Where the dashboard of this group lives. A dashboard's address needs a hyphen."""
    return f"orgaia-{entry.entry_id[:8].lower()}"


def dashboard_config(entry: ConfigEntry) -> dict[str, Any]:
    return {"strategy": {"type": "custom:orgaia", "entry": entry.entry_id}}


@callback
def show_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Puts the group's dashboard into the sidebar, if that was chosen. Says whether it stands."""
    if not entry.options.get(CONF_DASHBOARD):
        return False
    try:
        from homeassistant.components import frontend  # noqa: PLC0415
        from homeassistant.components.lovelace.const import LOVELACE_DATA  # noqa: PLC0415
        from homeassistant.components.lovelace.dashboard import LovelaceConfig  # noqa: PLC0415

        lovelace = hass.data.get(LOVELACE_DATA)
        if lovelace is None or "frontend" not in hass.config.components:
            return False
        path = dashboard_path(entry)
        config = dashboard_config(entry)

        class OrgaiaDashboard(LovelaceConfig):
            """A dashboard that is the same for good: only the strategy decides what it shows."""

            @property
            def mode(self) -> str:
                return "yaml"

            async def async_get_info(self) -> dict[str, Any]:
                return {"mode": "yaml", "views": 1}

            async def async_load(self, force: bool) -> dict[str, Any]:
                return config

            async def async_json(self, force: bool) -> json_fragment:
                return json_fragment(json_bytes(config))

        lovelace.dashboards[path] = OrgaiaDashboard(
            hass, path, {"mode": "yaml", "title": entry.title, "icon": ICON, "show_in_sidebar": True, "require_admin": False}
        )
        frontend.async_register_built_in_panel(
            hass,
            "lovelace",
            sidebar_title=entry.title or "Orgaia",
            sidebar_icon=ICON,
            frontend_url_path=path,
            config={"mode": "yaml"},
            require_admin=False,
            update=True,
        )
    except Exception:  # noqa: BLE001 - the dashboard is a convenience; the integration works without it
        _LOGGER.warning("Could not put the Orgaia dashboard into the sidebar", exc_info=True)
        return False
    return True


@callback
def hide_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Takes the group's dashboard out of the sidebar again."""
    try:
        from homeassistant.components import frontend  # noqa: PLC0415
        from homeassistant.components.lovelace.const import LOVELACE_DATA  # noqa: PLC0415

        path = dashboard_path(entry)
        lovelace = hass.data.get(LOVELACE_DATA)
        if lovelace is None or path not in lovelace.dashboards:
            return
        lovelace.dashboards.pop(path, None)
        frontend.async_remove_panel(hass, path, warn_if_unknown=False)
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Could not take the Orgaia dashboard out of the sidebar", exc_info=True)
