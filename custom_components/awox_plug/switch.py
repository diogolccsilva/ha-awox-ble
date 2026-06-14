"""Switch entity for the AwoX Smart Plug."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AwoxPlugConfigEntry
from .const import DEFAULT_NAME
from .entity import AwoxPlugEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AwoxPlugConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the plug switch."""
    coordinator = entry.runtime_data
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)
    async_add_entities([AwoxPlugSwitch(coordinator, name)])


class AwoxPlugSwitch(AwoxPlugEntity, SwitchEntity):
    """The plug's on/off relay."""

    _attr_device_class = SwitchDeviceClass.OUTLET
    _attr_name = None  # primary feature -> use the device name

    def __init__(self, coordinator, name: str) -> None:
        super().__init__(coordinator, name)
        self._attr_unique_id = f"{coordinator.address}_switch"

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_power(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_power(False)
