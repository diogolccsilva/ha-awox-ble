"""The AwoX Smart Plug (Revogi) integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_ADDRESS
from .coordinator import AwoxPlugCoordinator

PLATFORMS: list[Platform] = [Platform.SWITCH, Platform.SENSOR]

type AwoxPlugConfigEntry = ConfigEntry[AwoxPlugCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: AwoxPlugConfigEntry) -> bool:
    """Set up AwoX Smart Plug from a config entry."""
    address: str = entry.data[CONF_ADDRESS]
    coordinator = AwoxPlugCoordinator(hass, entry, address)

    # Fail setup (and retry later) if the plug can't be reached right now.
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AwoxPlugConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: AwoxPlugConfigEntry) -> None:
    """Reload when options (e.g. scan interval) change."""
    await hass.config_entries.async_reload(entry.entry_id)
