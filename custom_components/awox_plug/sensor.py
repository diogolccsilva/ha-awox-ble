"""Sensor entities for the AwoX Smart Plug.

All energy figures are read directly from the plug's own measured history, so
there are no derived/approximate values.
"""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import CONF_NAME, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import AwoxPlugConfigEntry
from .const import DEFAULT_NAME
from .entity import AwoxPlugEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AwoxPlugConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the power and energy sensors."""
    coordinator = entry.runtime_data
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)
    async_add_entities(
        [
            AwoxPlugPowerSensor(coordinator, name),
            # "Energy today" resets daily and feeds the Energy Dashboard via
            # state_class TOTAL + a midnight last_reset. The other two are
            # informational (no state_class).
            AwoxPlugEnergyHistorySensor(
                coordinator,
                name,
                "energy_today",
                "energy_today_kwh",
                state_class=SensorStateClass.TOTAL,
                daily_reset=True,
            ),
            AwoxPlugEnergyHistorySensor(
                coordinator, name, "energy_24h", "energy_24h_kwh"
            ),
            AwoxPlugEnergyHistorySensor(
                coordinator, name, "energy_yesterday", "energy_yesterday_kwh"
            ),
        ]
    )


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


class AwoxPlugEnergyHistorySensor(AwoxPlugEntity, SensorEntity):
    """Energy figure read directly from the plug's own stored history."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 3

    def __init__(
        self,
        coordinator,
        name: str,
        key: str,
        value_attr: str,
        state_class: SensorStateClass | None = None,
        daily_reset: bool = False,
    ) -> None:
        super().__init__(coordinator, name)
        self._attr_unique_id = f"{coordinator.address}_{key}"
        self._attr_translation_key = key
        self._attr_state_class = state_class
        self._value_attr = value_attr
        self._daily_reset = daily_reset

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return getattr(self.coordinator.data, self._value_attr)

    @property
    def last_reset(self) -> datetime | None:
        # For a daily-resetting TOTAL, the accumulation period starts at local
        # midnight; this lets the Energy Dashboard bucket it per day.
        if self._daily_reset:
            return dt_util.start_of_local_day()
        return None
