"""Unit tests for the reverse-engineered Revogi protocol.

These validate against the exact byte sequences emitted by the official AwoX
Smart Control app (verified by decompilation), so a regression here means the
plug would stop responding.
"""

import protocol


def _frame(state: int, milliwatts: int, reserved: int = 0) -> bytes:
    """Build a command-4 response frame the way the plug would."""
    data = bytes([state, reserved]) + milliwatts.to_bytes(4, "big")
    body = bytes([protocol.CMD_POWER_CONSUMPTION, 0]) + data
    checksum = 0  # parser does not verify the checksum on responses
    return (
        bytes([protocol.PACKET_START, len(data) + 3])
        + body
        + bytes([checksum])
        + b"\xff\xff"
    )


def test_build_packet_matches_app_bytes():
    # These hex strings come straight from the decompiled app.
    assert protocol.POLL_POWER.hex() == "0f050400000005ffff"
    assert protocol.CMD_TURN_ON.hex() == "0f06030001000005ffff"
    assert protocol.CMD_TURN_OFF.hex() == "0f06030000000004ffff"


def test_history_request_packets():
    # Hourly: cmd 0x0A, checksum (10+1)=0x0b; Daily: cmd 0x0B, checksum (11+1)=0x0c.
    assert protocol.POLL_HOURLY.hex() == "0f050a0000000bffff"
    assert protocol.POLL_DAILY.hex() == "0f050b0000000cffff"


def test_build_set_time_matches_app_layout():
    from datetime import datetime

    # 2026-06-15 09:30:45  (year 2026 = 0x07EA -> hi=0x07, lo=0xEA)
    pkt = protocol.build_set_time(datetime(2026, 6, 15, 9, 30, 45))
    # data = sec,min,hour,day,month,year_hi,year_lo,0,0,0,0
    data = bytes([45, 30, 9, 15, 6, 0x07, 0xEA, 0, 0, 0, 0])
    checksum = (protocol.CMD_SET_TIME + 1 + sum(data)) & 0xFF
    expected = (
        bytes([0x0F, len(data) + 3, protocol.CMD_SET_TIME, 0x00])
        + data
        + bytes([checksum])
        + b"\xff\xff"
    )
    assert pkt == expected
    assert pkt.hex() == "0f0e01002d1e090f0607ea000000005cffff"


def test_checksum_formula():
    # cmd=3, data={1,0,0} -> checksum = (3 + 1 + 1) & 0xFF = 5
    pkt = protocol.build_packet(0x03, b"\x01\x00\x00")
    assert pkt[0] == 0x0F
    assert pkt[1] == len(b"\x01\x00\x00") + 3
    assert pkt[2] == 0x03
    assert pkt[-3] == 0x05
    assert pkt[-2:] == b"\xff\xff"


def test_parse_power_on():
    state = protocol.ResponseAssembler().feed(_frame(state=1, milliwatts=1161))
    assert state is not None
    assert state.is_on is True
    assert state.power_w == 1.161


def test_parse_power_off_zero_watts():
    state = protocol.ResponseAssembler().feed(_frame(state=0, milliwatts=0))
    assert state is not None
    assert state.is_on is False
    assert state.power_w == 0.0


def test_parse_high_power():
    # 3500.5 W -> 3_500_500 mW
    state = protocol.ResponseAssembler().feed(_frame(state=1, milliwatts=3_500_500))
    assert state.power_w == 3500.5


def test_fragmented_reassembly():
    frame = _frame(state=1, milliwatts=1161)
    assembler = protocol.ResponseAssembler()
    result = None
    for i in range(0, len(frame), 7):  # 7-byte chunks, like BLE notifications
        result = assembler.feed(frame[i : i + 7])
    assert result is not None
    assert result.power_w == 1.161


def test_ignores_frame_with_wrong_start_byte():
    assert protocol.ResponseAssembler().feed(b"\x99\x05\x04\x00") is None


def test_ignores_non_power_command():
    # A well-formed frame for a different command (e.g. LED state, cmd 16).
    data = b"\x01\x00"
    body = bytes([0x10, 0]) + data
    frame = bytes([0x0F, len(data) + 3]) + body + b"\x00\xff\xff"
    assert protocol.ResponseAssembler().feed(frame) is None


def test_partial_frame_returns_none_until_complete():
    frame = _frame(state=1, milliwatts=500)
    assembler = protocol.ResponseAssembler()
    # Feed everything except the last byte.
    assert assembler.feed(frame[:-1]) is None
    # Final byte completes it.
    assert assembler.feed(frame[-1:]) is not None


def _history_frame(command: int, data: bytes) -> bytes:
    body = bytes([command, 0]) + data
    return bytes([protocol.PACKET_START, len(data) + 3]) + body + b"\x00\xff\xff"


def test_frame_assembler_returns_command_and_payload():
    data = bytes([0x00, 0x32, 0x00, 0x10])  # two 16-bit values: 50, 16
    frame = _history_frame(protocol.CMD_POWER_CONSUMPTION_HOURLY, data)
    out = protocol.FrameAssembler().feed(frame)
    assert out is not None
    assert protocol.frame_command(out) == protocol.CMD_POWER_CONSUMPTION_HOURLY
    assert protocol.frame_payload(out) == data


def test_decode_hourly_big_endian_shorts():
    data = bytes([0x00, 0x32, 0x00, 0x10, 0x01, 0x00])  # 50, 16, 256
    assert protocol.decode_hourly(data) == [50, 16, 256]


def test_decode_daily_big_endian_ints():
    data = (1000).to_bytes(4, "big") + (65540).to_bytes(4, "big")
    assert protocol.decode_daily(data) == [1000, 65540]


def test_decode_history_ignores_trailing_odd_bytes():
    # Two whole shorts plus a stray byte -> the stray byte is dropped.
    assert protocol.decode_hourly(bytes([0x00, 0x05, 0x00, 0x07, 0x99])) == [5, 7]
