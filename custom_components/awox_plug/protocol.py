"""Revogi BLE protocol helpers for AwoX smart plugs.

Reverse-engineered from the AwoX Smart Control app
(com.awox.core.impl.RevogiSmartPlugController.Protocol).

Packet layout (both directions):
    [0x0f][len][cmd][0x00][data...][checksum][0xff][0xff]
where:
    len      = len(data) + 3
    checksum = (cmd + 1 + sum(data)) & 0xFF
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# GATT service / characteristics
SERVICE_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000fff3-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000fff4-0000-1000-8000-00805f9b34fb"

PACKET_START = 0x0F

CMD_SET_TIME = 0x01
CMD_POWER_STATE = 0x03
CMD_POWER_CONSUMPTION = 0x04
CMD_POWER_CONSUMPTION_HOURLY = 0x0A
CMD_POWER_CONSUMPTION_DAILY = 0x0B
# Command 0x0F sets the LED (data starts 0x01) OR factory-resets (data 00 00 00).
CMD_LED_SET = 0x0F
CMD_LED_GET = 0x10


def build_packet(command: int, data: bytes) -> bytes:
    """Assemble a protocol packet (mirrors Protocol.getValue())."""
    packet = bytearray()
    packet.append(PACKET_START)
    packet.append((len(data) + 3) & 0xFF)
    packet.append(command & 0xFF)
    packet.append(0x00)
    packet.extend(data)
    checksum = (command + 1 + sum(data)) & 0xFF
    packet.append(checksum)
    packet.extend(b"\xff\xff")
    return bytes(packet)


# Instant consumption poll  -> 0f 05 04 00 00 00 05 ff ff (returns state + power)
POLL_POWER = build_packet(CMD_POWER_CONSUMPTION, b"\x00\x00")
# Hourly energy history      -> 0f 05 0a 00 00 00 0b ff ff (rolling ~24h, Wh/hour)
POLL_HOURLY = build_packet(CMD_POWER_CONSUMPTION_HOURLY, b"\x00\x00")
# Daily energy history       -> 0f 05 0b 00 00 00 0c ff ff (rolling ~30d, Wh/day)
POLL_DAILY = build_packet(CMD_POWER_CONSUMPTION_DAILY, b"\x00\x00")
# Power state writes         -> 0f 06 03 00 01 00 00 05 ff ff / ...00 00 04 ff ff
CMD_TURN_ON = build_packet(CMD_POWER_STATE, b"\x01\x00\x00")
CMD_TURN_OFF = build_packet(CMD_POWER_STATE, b"\x00\x00\x00")
# LED status-light control (cmd 0x0F, data = 01 <state> 00) and readback (0x10).
LED_ON = build_packet(CMD_LED_SET, b"\x01\x01\x00")
LED_OFF = build_packet(CMD_LED_SET, b"\x01\x00\x00")
POLL_LED = build_packet(CMD_LED_GET, b"\x00\x00")
# Factory reset (cmd 0x0F, data = 00 00 00). Erases the plug's stored history.
FACTORY_RESET = build_packet(CMD_LED_SET, b"\x00\x00\x00")


def build_set_time(now: datetime) -> bytes:
    """Set the plug's internal RTC (command 0x01) from a local datetime.

    Data layout (mirrors the app): sec, min, hour, day, month, year_hi,
    year_lo, then four reserved zero bytes.
    """
    data = bytes(
        [
            now.second & 0xFF,
            now.minute & 0xFF,
            now.hour & 0xFF,
            now.day & 0xFF,
            now.month & 0xFF,
            (now.year >> 8) & 0xFF,
            now.year & 0xFF,
            0,
            0,
            0,
            0,
        ]
    )
    return build_packet(CMD_SET_TIME, data)


@dataclass(slots=True)
class PlugState:
    """Decoded plug telemetry.

    ``is_on``/``power_w`` come from the command-4 response. The energy fields
    are derived from the hourly/daily history (command 0x0A / 0x0B) and may be
    ``None`` if that history wasn't read this cycle.
    """

    is_on: bool
    power_w: float
    energy_today_kwh: float | None = None
    energy_24h_kwh: float | None = None
    energy_yesterday_kwh: float | None = None
    led_on: bool | None = None


class FrameAssembler:
    """Reassembles fragmented notifications into complete protocol frames."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, data: bytes) -> bytes | None:
        """Add a notification chunk; return a full frame once one completes."""
        self._buffer.extend(data)
        if len(self._buffer) < 2 or self._buffer[0] != PACKET_START:
            self._buffer.clear()
            return None
        # byte[1] is len(data)+3; the full frame adds 4 bytes of overhead.
        expected_total = self._buffer[1] + 4
        if len(self._buffer) < expected_total:
            return None
        frame = bytes(self._buffer[:expected_total])
        del self._buffer[:expected_total]
        return frame


def frame_command(frame: bytes) -> int:
    """The command byte of a complete frame."""
    return frame[2]


def frame_payload(frame: bytes) -> bytes:
    """The data section (4-byte header + 3-byte trailer stripped)."""
    return frame[4:-3]


def parse_power_frame(frame: bytes) -> PlugState | None:
    """Decode a command-4 (instant power + on/off) frame."""
    if len(frame) < 7 or frame[2] != CMD_POWER_CONSUMPTION:
        return None
    payload = frame_payload(frame)
    if len(payload) < 6:
        return None
    is_on = payload[0] != 0
    # 4-byte big-endian milliwatts at payload[2:6]; the app divides by 1000 -> W.
    milliwatts = int.from_bytes(payload[2:6], byteorder="big", signed=False)
    return PlugState(is_on=is_on, power_w=milliwatts / 1000.0)


def decode_hourly(payload: bytes) -> list[int]:
    """Command-0x0A payload -> list of 16-bit big-endian values (Wh per hour).

    Chronological order; the last value is the current (partial) hour.
    """
    return [
        int.from_bytes(payload[i : i + 2], "big", signed=False)
        for i in range(0, len(payload) - 1, 2)
    ]


def decode_daily(payload: bytes) -> list[int]:
    """Command-0x0B payload -> list of 32-bit big-endian values (Wh per day).

    Chronological order; the last value is the most recent completed day.
    """
    return [
        int.from_bytes(payload[i : i + 4], "big", signed=False)
        for i in range(0, len(payload) - 3, 4)
    ]


def decode_led(payload: bytes) -> bool | None:
    """Command-0x10 payload -> LED on/off (payload[0] == 1)."""
    if not payload:
        return None
    return payload[0] == 1


class ResponseAssembler:
    """Convenience wrapper that yields a PlugState from command-4 frames."""

    def __init__(self) -> None:
        self._frames = FrameAssembler()

    def feed(self, data: bytes) -> PlugState | None:
        frame = self._frames.feed(data)
        if frame is None:
            return None
        return parse_power_frame(frame)
