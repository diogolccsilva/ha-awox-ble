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
        address = coordinator.address
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            connections={(CONNECTION_BLUETOOTH, address)},
            name=name,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )
