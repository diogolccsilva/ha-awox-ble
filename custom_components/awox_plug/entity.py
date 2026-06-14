"""Shared base entity for the AwoX Smart Plug integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import AwoxPlugCoordinator


class AwoxPlugEntity(CoordinatorEntity[AwoxPlugCoordinator]):
    """Base entity that ties everything to a single HA device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AwoxPlugCoordinator, name: str) -> None:
        super().__init__(coordinator)
        self._device_name = name

    @property
    def device_info(self) -> DeviceInfo:
        """Built dynamically so firmware/hardware appear once read from the plug."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.address)},
            connections={(CONNECTION_BLUETOOTH, self.coordinator.address)},
            name=self._device_name,
            manufacturer=MANUFACTURER,
            model=MODEL,
            sw_version=self.coordinator.firmware_version,
            hw_version=self.coordinator.hardware_version,
        )
