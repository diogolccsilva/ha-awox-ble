"""Sensor entities for the AwoX Smart Plug."""

from __future__ import annotations

import time

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import CONF_NAME, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AwoxPlugConfigEntry
from .const import DEFAULT_NAME
from .entity import AwoxPlugEntity

# If the plug is unreachable for longer than this, don't integrate across the
# gap (we have no idea what the load did meanwhile) -- just restart from the
# next live reading.
MAX_INTEGRATION_GAP = 3600.0


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
            AwoxPlugEnergySensor(coordinator, name),
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


class AwoxPlugEnergySensor(AwoxPlugEntity, RestoreSensor):
    """Energy total derived by integrating the live power reading.

    This is a trapezoidal Riemann sum over the polled power values (the same
    method as Home Assistant's Integration helper). It is an approximation
    limited by the polling interval; a device-measured energy figure can be
    added later. The running total is restored across restarts and feeds the
    Energy Dashboard.
    """

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_translation_key = "energy"
    _attr_suggested_display_precision = 3

    def __init__(self, coordinator, name: str) -> None:
        super().__init__(coordinator, name)
        self._attr_unique_id = f"{coordinator.address}_energy"
        self._energy_kwh: float = 0.0
        self._last_power: float | None = None
        self._last_time: float | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        if last is not None and last.native_value is not None:
            try:
                self._energy_kwh = float(last.native_value)
            except (TypeError, ValueError):
                self._energy_kwh = 0.0
        # Start integrating from the next live reading.
        self._last_power = None
        self._last_time = None

    @property
    def native_value(self) -> float:
        return round(self._energy_kwh, 6)

    @callback
    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        if data is None or not self.coordinator.last_update_success:
            # Unknown gap; drop the baseline so we don't integrate over it.
            self._last_power = None
            self._last_time = None
            super()._handle_coordinator_update()
            return

        now = time.monotonic()
        power = data.power_w
        if self._last_power is not None and self._last_time is not None:
            dt = now - self._last_time
            if 0.0 < dt < MAX_INTEGRATION_GAP:
                avg_power_w = (self._last_power + power) / 2.0
                # W * s -> kWh
                self._energy_kwh += avg_power_w * dt / 3_600_000.0
        self._last_power = power
        self._last_time = now
        super()._handle_coordinator_update()
