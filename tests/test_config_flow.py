"""Setup with an invitation link: waiting for the admin, declined, wrong links, the same group twice."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.orgaia.const import CONF_SEED, CONF_SPACE, DOMAIN

from .fake_service import SPACE, FakeService, fill_group


async def _start(hass: HomeAssistant, service: FakeService, link: str | None = None):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(result["flow_id"], {"link": link or service.link()})


async def test_full_setup(hass: HomeAssistant, service: FakeService) -> None:
    fill_group(service, "2026-11-17")
    service.answer = "accepted"
    hass.states.async_set("person.anna", "home", {"friendly_name": "Anna"})
    result = await _start(hass, service)
    assert result["type"] is FlowResultType.SHOW_PROGRESS
    assert result["description_placeholders"]["group"] == "Familie"
    assert result["description_placeholders"]["code"]
    await hass.async_block_till_done()
    result = await hass.config_entries.flow.async_configure(result["flow_id"])
    # Connected: one more look at who is who and at the dashboard, then it is done.
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "ready"
    fields = {str(k): k for k in result["data_schema"].schema}
    assert {"Anna", "Ben", "dashboard"} == set(fields)
    assert fields["Anna"].description == {"suggested_value": "person.anna"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"Anna": "person.anna", "dashboard": True}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Familie"
    assert result["result"].unique_id == SPACE
    assert result["data"][CONF_SPACE] == SPACE and result["data"][CONF_SEED]
    assert result["options"] == {"dashboard": True, "persons": {"anna": "person.anna"}}
    assert service.ha_name == "Home Assistant"


async def test_declined(hass: HomeAssistant, service: FakeService) -> None:
    service.answer = "rejected"
    result = await _start(hass, service)
    await hass.async_block_till_done()
    result = await hass.config_entries.flow.async_configure(result["flow_id"])
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "rejected"


async def test_not_a_link(hass: HomeAssistant, service: FakeService) -> None:
    result = await _start(hass, service, link="https://example.com/whatever")
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_link"}


async def test_needs_plus(hass: HomeAssistant, service: FakeService) -> None:
    from custom_components.orgaia.client.api import ApiError

    async def refuse(method, path, body=None):
        raise ApiError(402, "integration-needs-plan")

    service.req = refuse
    result = await _start(hass, service)
    assert result["errors"] == {"base": "needs_plus"}


async def test_same_group_twice(hass: HomeAssistant, service: FakeService) -> None:
    fill_group(service, "2026-11-17")
    service.answer = "accepted"
    for expected in (FlowResultType.CREATE_ENTRY, FlowResultType.ABORT):
        result = await _start(hass, service)
        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"])
        if result["type"] is FlowResultType.FORM:
            # No Home Assistant person here: the last step only offers the dashboard.
            assert [str(k) for k in result["data_schema"].schema] == ["dashboard"]
            result = await hass.config_entries.flow.async_configure(result["flow_id"], {"dashboard": False})
        assert result["type"] is expected
    assert result["reason"] == "already_configured"
    assert service.left


async def test_dashboard_in_sidebar(hass: HomeAssistant, service: FakeService) -> None:
    """The ready-made dashboard stands in the sidebar while its group is loaded, and only if chosen."""
    from homeassistant.components.lovelace.const import LOVELACE_DATA
    from homeassistant.setup import async_setup_component
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.orgaia.dashboard import dashboard_path, hide_dashboard, show_dashboard

    assert await async_setup_component(hass, "lovelace", {})
    hass.config.components.add("frontend")
    entry = MockConfigEntry(domain=DOMAIN, title="Familie", options={"dashboard": True})
    assert show_dashboard(hass, entry)
    path = dashboard_path(entry)
    board = hass.data[LOVELACE_DATA].dashboards[path]
    assert await board.async_load(False) == {
        "strategy": {
            "type": "custom:orgaia",
            "entry": entry.entry_id,
            "style": "tinte",
            "sections": ["today", "shopping", "week"],
        }
    }
    assert (await board.async_get_info())["mode"] == "yaml"
    assert hass.data["frontend_panels"][path].sidebar_title == "Familie"
    hide_dashboard(hass, entry)
    assert path not in hass.data[LOVELACE_DATA].dashboards and path not in hass.data["frontend_panels"]
    assert not show_dashboard(hass, MockConfigEntry(domain=DOMAIN, title="Verein"))


def test_dashboard_look_and_parts() -> None:
    """The look and the parts chosen in the settings reach the strategy; unknown ones do not, the order is fixed."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.orgaia.dashboard import dashboard_config

    entry = MockConfigEntry(
        domain=DOMAIN,
        options={"dashboard": True, "dashboard_style": "ha", "dashboard_sections": ["roster", "bogus", "today"]},
    )
    assert dashboard_config(entry)["strategy"] == {
        "type": "custom:orgaia",
        "entry": entry.entry_id,
        "style": "ha",
        "sections": ["today", "roster"],
    }
    entry = MockConfigEntry(domain=DOMAIN, options={"dashboard_style": "odd", "dashboard_sections": ["bogus"]})
    strategy = dashboard_config(entry)["strategy"]
    assert strategy["style"] == "tinte" and strategy["sections"] == ["today", "shopping", "week"]


async def test_missing_dashboard_is_a_repair(hass: HomeAssistant, service: FakeService) -> None:
    """When Home Assistant will not take the dashboard, a repair hint says so, and goes once it stands."""
    from homeassistant.components.lovelace.const import LOVELACE_DATA
    from homeassistant.helpers import issue_registry as ir
    from homeassistant.setup import async_setup_component
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.orgaia.dashboard import forget_dashboard_issue, issue_id, show_dashboard

    assert await async_setup_component(hass, "lovelace", {})
    hass.config.components.add("frontend")
    entry = MockConfigEntry(domain=DOMAIN, title="Familie", options={"dashboard": True})
    issues = ir.async_get(hass)
    # As if a new Home Assistant kept its dashboards elsewhere.
    lovelace = hass.data.pop(LOVELACE_DATA)
    assert not show_dashboard(hass, entry)
    issue = issues.async_get_issue(DOMAIN, issue_id(entry))
    assert issue and issue.translation_key == "dashboard_missing"
    assert issue.translation_placeholders == {"group": "Familie"}
    hass.data[LOVELACE_DATA] = lovelace
    assert show_dashboard(hass, entry)
    assert issues.async_get_issue(DOMAIN, issue_id(entry)) is None
    # Not wanted (any more): no hint either; a removed group takes it along.
    hass.data.pop(LOVELACE_DATA)
    assert not show_dashboard(hass, MockConfigEntry(domain=DOMAIN, title="Verein"))
    assert not show_dashboard(hass, entry) and issues.async_get_issue(DOMAIN, issue_id(entry))
    forget_dashboard_issue(hass, entry)
    assert issues.async_get_issue(DOMAIN, issue_id(entry)) is None
    hass.data[LOVELACE_DATA] = lovelace
