"""Power sensor entity for the AwoX Smart Plug."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import CONF_NAME, UnitOfPower
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
    """Set up the power sensor."""
    coordinator = entry.runtime_data
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)
    async_add_entities([AwoxPlugPowerSensor(coordinator, name)])


class AwoxPlugPowerSensor(AwoxPlugEntity, SensorEntity):
    """Live power draw reported by the plug."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "power"

    def __init__(self, coordinator, name: str) -> None:
        super().__init__(coordinator, name)
        self._attr_unique_id = f"{coordinator.address}_power"

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.power_w
