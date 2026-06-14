"""Bluetooth polling coordinator for the AwoX Smart Plug."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from bleak.backends.device import BLEDevice
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .protocol import (
    CMD_TURN_OFF,
    CMD_TURN_ON,
    NOTIFY_UUID,
    POLL_POWER,
    WRITE_UUID,
    PlugState,
    ResponseAssembler,
)

_LOGGER = logging.getLogger(__name__)

# How long to wait for the notification carrying the command-4 response.
NOTIFY_TIMEOUT = 5.0
# The app waits 200ms after a write before expecting the device to settle.
WRITE_SETTLE = 0.2


class AwoxPlugCoordinator(DataUpdateCoordinator[PlugState]):
    """Serializes all BLE access to the plug and polls it on an interval."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, address: str) -> None:
        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{address}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.address = address
        self._entry = entry
        # One BLE operation at a time so our own writes/polls never collide.
        self._lock = asyncio.Lock()

    async def _async_update_data(self) -> PlugState:
        return await self._run()

    async def async_set_power(self, turn_on: bool) -> None:
        """Toggle the plug and immediately refresh state from the same session."""
        _LOGGER.debug("%s: setting power %s", self.address, "ON" if turn_on else "OFF")
        state = await self._run(pre_command=CMD_TURN_ON if turn_on else CMD_TURN_OFF)
        self.async_set_updated_data(state)

    def _get_ble_device(self) -> BLEDevice:
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if ble_device is None:
            raise UpdateFailed(
                f"Plug {self.address} not found by any Bluetooth adapter "
                "(out of range, powered off, or not advertising)"
            )
        return ble_device

    async def _run(self, pre_command: bytes | None = None) -> PlugState:
        """Connect, optionally send a command, poll telemetry, then disconnect."""
        async with self._lock:
            ble_device = self._get_ble_device()
            _LOGGER.debug(
                "%s: connecting (rssi=%s)",
                self.address,
                getattr(ble_device, "rssi", "?"),
            )
            client = await establish_connection(
                BleakClientWithServiceCache,
                ble_device,
                self.name,
            )
            assembler = ResponseAssembler()
            result: dict[str, PlugState] = {}
            done = asyncio.Event()

            def _on_notify(_char, data: bytearray) -> None:
                state = assembler.feed(bytes(data))
                if state is not None:
                    result["state"] = state
                    done.set()

            try:
                await client.start_notify(NOTIFY_UUID, _on_notify)

                if pre_command is not None:
                    await client.write_gatt_char(WRITE_UUID, pre_command, response=True)
                    await asyncio.sleep(WRITE_SETTLE)

                await client.write_gatt_char(WRITE_UUID, POLL_POWER, response=True)

                try:
                    await asyncio.wait_for(done.wait(), timeout=NOTIFY_TIMEOUT)
                except TimeoutError as err:
                    raise UpdateFailed(
                        "No telemetry response from plug within timeout"
                    ) from err

                try:
                    await client.stop_notify(NOTIFY_UUID)
                except Exception:  # noqa: BLE001 - disconnect cleans up regardless
                    pass

                state = result["state"]
                _LOGGER.debug(
                    "%s: poll ok -> is_on=%s power=%.3f W",
                    self.address,
                    state.is_on,
                    state.power_w,
                )
                return state
            except UpdateFailed:
                raise
            except Exception as err:  # noqa: BLE001
                raise UpdateFailed(f"Error communicating with plug: {err}") from err
            finally:
                await client.disconnect()
