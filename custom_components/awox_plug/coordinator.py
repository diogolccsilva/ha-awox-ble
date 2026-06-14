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
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
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
# Retry transient BLE failures (adapter contention, device briefly asleep, etc.).
ATTEMPTS = 3
RETRY_DELAY = 1.5

# Standard BLE Device Information Service characteristics (optional on the plug).
FIRMWARE_REV_UUID = "00002a26-0000-1000-8000-00805f9b34fb"
HARDWARE_REV_UUID = "00002a27-0000-1000-8000-00805f9b34fb"


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
        self.firmware_version: str | None = None
        self.hardware_version: str | None = None
        self._device_info_read = False

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
        """Connect/poll with retries; all BLE access is serialized by the lock."""
        async with self._lock:
            last_error: UpdateFailed | None = None
            for attempt in range(1, ATTEMPTS + 1):
                try:
                    return await self._run_once(pre_command)
                except UpdateFailed as err:
                    last_error = err
                except Exception as err:  # noqa: BLE001
                    last_error = UpdateFailed(f"Error communicating with plug: {err}")
                if attempt < ATTEMPTS:
                    _LOGGER.debug(
                        "%s: attempt %s/%s failed (%s); retrying",
                        self.address,
                        attempt,
                        ATTEMPTS,
                        last_error,
                    )
                    await asyncio.sleep(RETRY_DELAY)
            assert last_error is not None
            raise last_error

    async def _run_once(self, pre_command: bytes | None) -> PlugState:
        """A single connect, optional command, poll, then disconnect."""
        ble_device = self._get_ble_device()
        _LOGGER.debug(
            "%s: connecting (rssi=%s)", self.address, getattr(ble_device, "rssi", "?")
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

            if not self._device_info_read:
                await self._read_device_information(client)

            state = result["state"]
            _LOGGER.debug(
                "%s: poll ok -> is_on=%s power=%.3f W",
                self.address,
                state.is_on,
                state.power_w,
            )
            return state
        finally:
            await client.disconnect()

    async def _read_device_information(
        self, client: BleakClientWithServiceCache
    ) -> None:
        """Best-effort read of the standard BLE Device Information Service.

        These characteristics are optional; if the plug doesn't expose them we
        simply leave the versions unset rather than showing incorrect data.
        """
        self._device_info_read = True
        changed = False
        for uuid, attr in (
            (FIRMWARE_REV_UUID, "firmware_version"),
            (HARDWARE_REV_UUID, "hardware_version"),
        ):
            try:
                raw = await client.read_gatt_char(uuid)
            except Exception:  # noqa: BLE001 - characteristic is optional
                continue
            value = raw.decode("utf-8", "replace").strip("\x00 ").strip()
            if value and getattr(self, attr) != value:
                setattr(self, attr, value)
                changed = True
        if changed:
            self._update_device_registry()

    def _update_device_registry(self) -> None:
        """Push firmware/hardware versions to an already-registered device."""
        dev_reg = dr.async_get(self.hass)
        device = dev_reg.async_get_device(identifiers={(DOMAIN, self.address)})
        if device is not None:
            dev_reg.async_update_device(
                device.id,
                sw_version=self.firmware_version,
                hw_version=self.hardware_version,
            )
