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
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"link": link or service.link(), "name": "Smart Home"}
    )


async def test_full_setup(hass: HomeAssistant, service: FakeService) -> None:
    fill_group(service, "2026-11-17")
    service.answer = "accepted"
    result = await _start(hass, service)
    assert result["type"] is FlowResultType.SHOW_PROGRESS
    assert result["description_placeholders"]["group"] == "Familie"
    assert result["description_placeholders"]["code"]
    await hass.async_block_till_done()
    result = await hass.config_entries.flow.async_configure(result["flow_id"])
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Familie"
    assert result["result"].unique_id == SPACE
    assert result["data"][CONF_SPACE] == SPACE and result["data"][CONF_SEED]
    assert service.ha_name == "Smart Home"


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
        assert result["type"] is expected
    assert result["reason"] == "already_configured"
    assert service.left
