"""Switch entities for the AwoX Smart Plug."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.const import CONF_NAME, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AwoxPlugConfigEntry
from .const import DEFAULT_NAME
from .entity import AwoxPlugEntity

SERVICE_FACTORY_RESET = "factory_reset"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AwoxPlugConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the plug switches and the factory-reset action."""
    coordinator = entry.runtime_data
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)
    async_add_entities(
        [
            AwoxPlugSwitch(coordinator, name),
            AwoxPlugLedSwitch(coordinator, name),
        ]
    )

    # Destructive action guarded by a required confirm flag, so it can never
    # fire from an accidental press.
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_FACTORY_RESET,
        {vol.Required("confirm"): cv.boolean},
        "async_factory_reset",
    )


class _AwoxBaseSwitch(AwoxPlugEntity, SwitchEntity):
    """Shared switch base so both switches support the factory-reset action."""

    async def async_factory_reset(self, confirm: bool) -> None:
        if not confirm:
            raise ServiceValidationError(
                "Factory reset was not confirmed. This erases the plug's stored "
                "energy history; pass confirm: true to proceed."
            )
        await self.coordinator.async_factory_reset()


class AwoxPlugSwitch(_AwoxBaseSwitch):
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


class AwoxPlugLedSwitch(_AwoxBaseSwitch):
    """The plug's status-light (LED) indicator."""

    _attr_translation_key = "led"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, name: str) -> None:
        super().__init__(coordinator, name)
        self._attr_unique_id = f"{coordinator.address}_led"

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.led_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_led(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_led(False)
