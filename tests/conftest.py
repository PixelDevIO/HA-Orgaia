"""Fixtures for the Orgaia tests: a fake sync service instead of the real one."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from .fake_service import FakeService


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading custom_components/orgaia."""
    return


@pytest.fixture(autouse=True)
def all_entities():
    """The tests look at every entity, also those a new group starts without."""
    with patch("homeassistant.helpers.entity.Entity.entity_registry_enabled_default", new=True):
        yield


@pytest.fixture
def service():
    svc = FakeService()

    async def req(api, method, path, body=None):
        return await svc.req(method, path, body)

    with (
        patch("custom_components.orgaia.client.api.Api.req", new=req),
        patch("custom_components.orgaia.coordinator.OrgaiaCoordinator.run_live", new=AsyncMock()),
        patch("custom_components.orgaia.config_flow.JOIN_POLL_SECONDS", 0.01),
    ):
        yield svc
