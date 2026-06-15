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
from homeassistant.util import dt as dt_util

from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .protocol import (
    CMD_POWER_CONSUMPTION,
    CMD_POWER_CONSUMPTION_DAILY,
    CMD_POWER_CONSUMPTION_HOURLY,
    CMD_TURN_OFF,
    CMD_TURN_ON,
    NOTIFY_UUID,
    POLL_DAILY,
    POLL_HOURLY,
    POLL_POWER,
    WRITE_UUID,
    FrameAssembler,
    PlugState,
    decode_daily,
    decode_hourly,
    frame_command,
    frame_payload,
    parse_power_frame,
)

_LOGGER = logging.getLogger(__name__)

# How long to wait for the notification carrying a response frame.
NOTIFY_TIMEOUT = 5.0
# History responses are larger (multiple fragments) so allow a little longer.
HISTORY_TIMEOUT = 6.0
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
        self._history_logged = False

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
        """A single connect, optional command, poll(s), then disconnect."""
        ble_device = self._get_ble_device()
        _LOGGER.debug(
            "%s: connecting (rssi=%s)", self.address, getattr(ble_device, "rssi", "?")
        )
        client = await establish_connection(
            BleakClientWithServiceCache,
            ble_device,
            self.name,
        )
        assembler = FrameAssembler()
        frames: dict[int, bytes] = {}
        frame_received = asyncio.Event()

        def _on_notify(_char, data: bytearray) -> None:
            frame = assembler.feed(bytes(data))
            if frame is not None:
                frames[frame_command(frame)] = frame
                frame_received.set()

        async def _exchange(
            packet: bytes, want_cmd: int, timeout: float
        ) -> bytes | None:
            await client.write_gatt_char(WRITE_UUID, packet, response=True)
            try:
                while want_cmd not in frames:
                    frame_received.clear()
                    await asyncio.wait_for(frame_received.wait(), timeout)
            except TimeoutError:
                return None
            return frames[want_cmd]

        try:
            await client.start_notify(NOTIFY_UUID, _on_notify)

            if pre_command is not None:
                await client.write_gatt_char(WRITE_UUID, pre_command, response=True)
                await asyncio.sleep(WRITE_SETTLE)

            # Instant power + on/off state is required.
            power_frame = await _exchange(
                POLL_POWER, CMD_POWER_CONSUMPTION, NOTIFY_TIMEOUT
            )
            if power_frame is None:
                raise UpdateFailed("No power response from plug within timeout")
            state = parse_power_frame(power_frame)
            if state is None:
                raise UpdateFailed("Could not parse power response")

            # Energy history is best-effort; failure here must not break the poll.
            await asyncio.sleep(WRITE_SETTLE)
            hourly_frame = await _exchange(
                POLL_HOURLY, CMD_POWER_CONSUMPTION_HOURLY, HISTORY_TIMEOUT
            )
            await asyncio.sleep(WRITE_SETTLE)
            daily_frame = await _exchange(
                POLL_DAILY, CMD_POWER_CONSUMPTION_DAILY, HISTORY_TIMEOUT
            )

            self._apply_history(state, hourly_frame, daily_frame)

            try:
                await client.stop_notify(NOTIFY_UUID)
            except Exception:  # noqa: BLE001 - disconnect cleans up regardless
                pass

            if not self._device_info_read:
                await self._read_device_information(client)

            _LOGGER.debug(
                "%s: poll ok -> is_on=%s power=%.3f W today=%s 24h=%s yesterday=%s",
                self.address,
                state.is_on,
                state.power_w,
                state.energy_today_kwh,
                state.energy_24h_kwh,
                state.energy_yesterday_kwh,
            )
            return state
        finally:
            await client.disconnect()

    def _apply_history(
        self, state: PlugState, hourly_frame: bytes | None, daily_frame: bytes | None
    ) -> None:
        """Decode hourly/daily energy and fold it into ``state``.

        Logged at INFO the first time so the raw bytes can be validated against
        the plug; afterwards at DEBUG to avoid log spam.
        """
        log = _LOGGER.info if not self._history_logged else _LOGGER.debug

        hourly: list[int] | None = None
        if hourly_frame is not None:
            hourly = decode_hourly(frame_payload(hourly_frame))
            log(
                "%s: hourly raw=%s decoded=%s sum=%s",
                self.address,
                hourly_frame.hex(" "),
                hourly,
                sum(hourly),
            )
        else:
            log("%s: no hourly history response", self.address)

        daily: list[int] | None = None
        if daily_frame is not None:
            daily = decode_daily(frame_payload(daily_frame))
            log(
                "%s: daily raw=%s decoded=%s sum=%s",
                self.address,
                daily_frame.hex(" "),
                daily,
                sum(daily),
            )
        else:
            log("%s: no daily history response", self.address)

        self._history_logged = True

        # Treat the values as Wh (the app's legacy plug path uses them directly).
        # This is the part to confirm from the logged raw values above.
        if hourly:
            state.energy_24h_kwh = round(sum(hourly) / 1000.0, 3)
            # Last (current_hour + 1) buckets cover local midnight .. now.
            current_hour = dt_util.now().hour
            today = hourly[-(current_hour + 1) :]
            state.energy_today_kwh = round(sum(today) / 1000.0, 3)
        if daily:
            state.energy_yesterday_kwh = round(daily[-1] / 1000.0, 3)

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
            # Some plugs return the characteristic's label ("Firmware Revision")
            # instead of a real value; only accept something version-like.
            if not value or not any(ch.isdigit() for ch in value):
                continue
            if getattr(self, attr) != value:
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
