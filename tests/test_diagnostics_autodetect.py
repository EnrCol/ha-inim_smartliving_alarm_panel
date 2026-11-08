"""Tests for model auto-detection and the diagnostics memory snapshot."""

import threading

from custom_components.inim_smartliving_alarm.diagnostics import (
    MEMORY_BLOCKS,
    REDACTED_BYTE,
    read_memory_snapshot,
    redact_codes,
)
from custom_components.inim_smartliving_alarm.panel_profiles import (
    PANEL_MODEL_1050,
    PANEL_MODEL_10100,
    detect_panel_model,
)


def test_detect_panel_model_from_reported_type():
    assert detect_panel_model("10100") == PANEL_MODEL_10100  # reference panel "6.09 10100"
    assert detect_panel_model("10100L") == PANEL_MODEL_10100
    assert detect_panel_model("01050") == PANEL_MODEL_1050  # original integration example
    assert detect_panel_model("1050") == PANEL_MODEL_1050
    assert detect_panel_model("515") == PANEL_MODEL_1050
    assert detect_panel_model("505") == PANEL_MODEL_1050
    assert detect_panel_model("Unknown") is None
    assert detect_panel_model(None) is None


def _code_table(records):
    # Same layout as the reference 10100 (0xA4C7): 6 bytes per code, one digit
    # per byte, 0xFF padding for 4-digit codes. Values here are fake.
    table = b""
    for i in range(records):
        table += bytes([(i + k) % 10 for k in range(4)]) + b"\xff\xff"
    return table


def test_redact_codes_overwrites_code_tables_and_pin():
    pin = "135792"
    blob = b"\x41" * 50 + _code_table(104) + b"\x20" * 30 + bytes(int(c) for c in pin) + b"\x20" * 10
    redacted, ranges = redact_codes(blob, pin)
    assert len(redacted) == len(blob)
    assert redacted[50 : 50 + 624] == bytes([REDACTED_BYTE]) * 624
    pin_at = 50 + 624 + 30
    assert redacted[pin_at : pin_at + 6] == bytes([REDACTED_BYTE]) * 6
    assert redacted[:50] == blob[:50]  # names and other data untouched
    assert [50, 674] in ranges


def test_redact_codes_keeps_short_digit_runs():
    # A few small numeric fields (timers, counters) are not a code table.
    blob = bytes([1, 2, 3, 4, 0xFF, 0xFF] * 3) + b"\x80" * 20
    redacted, ranges = redact_codes(blob, None)
    assert redacted == blob
    assert ranges == []


class FakeApi:
    def __init__(self):
        self._api_lock = threading.Lock()
        self._is_connected = True
        self.keep_connection_open = True
        self._last_io = 0.0
        self.pin_code_str = "135792"
        self.frames = []

    def connect(self):
        self._is_connected = True
        return True

    def disconnect(self):
        self._is_connected = False

    def calculate_checksum(self, frame):
        return "00"

    def _send_command_core(self, cmd, expect_specific_response_len):
        self.frames.append(cmd)
        length = int(cmd[10:14], 16)
        assert expect_specific_response_len == length + 1
        return "11" * length + "00"


def test_memory_snapshot_reads_all_blocks_and_keeps_connection():
    api = FakeApi()
    result = read_memory_snapshot(api)
    blocks = result["blocks"]
    assert set(blocks) == {label for label, *_ in MEMORY_BLOCKS}
    assert len(bytes.fromhex(blocks["config"]["hex"])) == 0x10000
    assert len(bytes.fromhex(blocks["names"]["hex"])) == 0x4000
    assert all(f[:6] in ("000001", "000101", "000000") for f in api.frames)
    assert api._is_connected  # kept connection left open for polling
    assert not api._api_lock.locked()


def test_redact_phone_numbers_and_keep_small_value_tables():
    phone = b"0123456789"  # fake dialler number stored as ASCII
    config_table = bytes([0, 1, 0, 1, 0xFF, 0xFF] * 40)  # small values, not codes
    blob = b"\x00" * 34 + phone + b"\x00" * 20 + config_table
    redacted, ranges = redact_codes(blob, None)
    assert redacted[34:44] == bytes([REDACTED_BYTE]) * 10
    assert redacted[64:] == config_table
    assert ranges == [[34, 44]]
