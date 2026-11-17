"""One device per group; every entity of the group belongs to it."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME, VERSION
from .coordinator import OrgaiaCoordinator


class OrgaiaEntity(CoordinatorEntity[OrgaiaCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: OrgaiaCoordinator, key: str) -> None:
        super().__init__(coordinator)
        space = coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        self._attr_unique_id = f"{space}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, space)},
            name=coordinator.config_entry.title,
            manufacturer=NAME,
            model="Gruppe",
            sw_version=VERSION,
            entry_type=DeviceEntryType.SERVICE,
        )
