"""Regression tests for quiet normal INIM polling and actionable errors."""

import logging

from custom_components.inim_smartliving_alarm import inim_api
from custom_components.inim_smartliving_alarm.inim_api import InimAlarmAPI


class FakeSocket:
    """No physical panel access: simulate a successful TCP exchange."""

    def settimeout(self, timeout):
        self.timeout = timeout

    def connect(self, endpoint):
        self.endpoint = endpoint

    def sendall(self, packet):
        self.last_packet = packet

    def recv(self, length):
        return bytes.fromhex("0202")

    def close(self):
        pass


def test_normal_tcp_exchange_does_not_log_each_frame(monkeypatch, caplog):
    fake = FakeSocket()
    monkeypatch.setattr(inim_api.socket, "socket", lambda *a, **kw: fake)
    api = InimAlarmAPI("127.0.0.1", 5004, "1234")

    with caplog.at_level(logging.DEBUG, logger=inim_api.logger.name):
        assert api.connect() is True
        # Include a PIN-like payload: raw commands must never appear in logs.
        assert api._send_raw_command("000000010000aaaa01020304ffff") is True
        assert api._read_raw_response() == "0202"
        api.disconnect()

    records = [r for r in caplog.records if r.name == inim_api.logger.name]
    assert records == []


def test_normal_live_poll_is_quiet_at_debug(monkeypatch, caplog):
    api = InimAlarmAPI("127.0.0.1", 5004, "1234")
    monkeypatch.setattr(api, "connect", lambda: True)
    monkeypatch.setattr(api, "disconnect", lambda: None)
    monkeypatch.setattr(inim_api.time, "sleep", lambda _: None)
    monkeypatch.setattr(api, "get_areas_status", lambda: {"area_statuses": {1: "armed"}})
    monkeypatch.setattr(api, "get_zones_status", lambda: {"zone_statuses": {}})
    monkeypatch.setattr(api, "get_zones_excluded_status", lambda: {"zone_excluded_statuses": {}})
    monkeypatch.setattr(api, "get_zones_triggered_status", lambda: {"zone_triggered_statuses": {}})
    monkeypatch.setattr(api, "get_active_scenario", lambda: {"active_scenario_number": 2})

    with caplog.at_level(logging.DEBUG, logger=inim_api.logger.name):
        result = api.get_live_status_snapshot()

    assert result["active_scenario"]["active_scenario_number"] == 2
    assert result["errors"] == []
    assert not [r for r in caplog.records if r.name == inim_api.logger.name]


def test_no_new_compact_events_do_not_spam_even_debug(monkeypatch, caplog):
    api = InimAlarmAPI("127.0.0.1", 5004, "1234")
    # Exercise real pointer parsing, but stub TCP I/O: "0200" -> X=0x0002.
    monkeypatch.setattr(api, "_send_command_core", lambda *a, **kw: "0200")

    # x_next = 2 => most recent compact index = 0x920D.
    with caplog.at_level(logging.DEBUG, logger=inim_api.logger.name):
        result = api.get_compact_events(last_processed_compact_event_index_val=0x920D)

    assert result["events"] == []
    assert result["latest_event_index_val"] == 0x920D
    assert not [r for r in caplog.records if r.name == inim_api.logger.name]


def test_new_compact_event_still_emits_useful_log(monkeypatch, caplog):
    api = InimAlarmAPI("127.0.0.1", 5004, "1234")
    monkeypatch.setattr(api, "_get_raw_next_event_pointer", lambda: "0002")
    monkeypatch.setattr(api, "_fetch_one_compact_event", lambda *a: {"event": "example"})
    monkeypatch.setattr(inim_api.time, "sleep", lambda _: None)

    with caplog.at_level(logging.DEBUG, logger=inim_api.logger.name):
        result = api.get_compact_events(last_processed_compact_event_index_val=0x9204)

    assert len(result["events"]) == 1
    assert any("Retrieved 1 compact events" in r.getMessage() for r in caplog.records)
    assert not [
        r for r in caplog.records
        if r.name == inim_api.logger.name and r.levelno == logging.DEBUG
    ]


def test_connection_error_remains_visible(monkeypatch, caplog):
    class FailedSocket(FakeSocket):
        def connect(self, endpoint):
            raise OSError("test connection failure")

    monkeypatch.setattr(inim_api.socket, "socket", lambda *a, **kw: FailedSocket())
    api = InimAlarmAPI("127.0.0.1", 5004, "1234")

    with caplog.at_level(logging.INFO, logger=inim_api.logger.name):
        assert api.connect() is False

    assert any(
        r.levelno >= logging.ERROR and "Connection failed" in r.getMessage()
        for r in caplog.records
    )


def test_poll_cycle_uses_one_connection(monkeypatch, caplog):
    """Status and events must share a single TCP connection per cycle."""
    api = InimAlarmAPI("127.0.0.1", 5004, "1234")
    calls = {"connect": 0, "disconnect": 0}

    def fake_connect():
        calls["connect"] += 1
        return True

    monkeypatch.setattr(api, "connect", fake_connect)
    monkeypatch.setattr(api, "disconnect", lambda: calls.__setitem__("disconnect", calls["disconnect"] + 1))
    monkeypatch.setattr(inim_api.time, "sleep", lambda _: None)
    monkeypatch.setattr(api, "get_areas_status", lambda: {"area_statuses": {}})
    monkeypatch.setattr(api, "get_zones_status", lambda: {"zone_statuses": {}})
    monkeypatch.setattr(api, "get_zones_excluded_status", lambda: {"zone_excluded_statuses": {}})
    monkeypatch.setattr(api, "get_zones_triggered_status", lambda: {"zone_triggered_statuses": {}})
    monkeypatch.setattr(api, "get_active_scenario", lambda: {"active_scenario_number": 0})
    monkeypatch.setattr(api, "_send_command_core", lambda *a, **kw: "0200")

    with caplog.at_level(logging.DEBUG, logger=inim_api.logger.name):
        result = api.execute_poll_cycle(last_processed_compact_event_index_val=0x920D)

    assert calls == {"connect": 1, "disconnect": 1}
    assert result["errors"] == []
    assert result["events_result"] == {"events": [], "latest_event_index_val": 0x920D}
    assert not [r for r in caplog.records if r.name == inim_api.logger.name]


def test_poll_cycle_connection_failure(monkeypatch):
    api = InimAlarmAPI("127.0.0.1", 5004, "1234")
    monkeypatch.setattr(api, "connect", lambda: False)
    result = api.execute_poll_cycle(count=5)
    assert result["error"] == "Connection failure"
    assert result["events_result"]["events"] == []


def _stub_status(monkeypatch, api, fail_first=0):
    state = {"fails": fail_first}

    def areas():
        if state["fails"]:
            state["fails"] -= 1
            return None
        return {"area_statuses": {}}

    monkeypatch.setattr(inim_api.time, "sleep", lambda _: None)
    monkeypatch.setattr(api, "get_areas_status", areas)
    monkeypatch.setattr(api, "get_zones_status", lambda: {"zone_statuses": {}})
    monkeypatch.setattr(api, "get_zones_excluded_status", lambda: {"zone_excluded_statuses": {}})
    monkeypatch.setattr(api, "get_zones_triggered_status", lambda: {"zone_triggered_statuses": {}})
    monkeypatch.setattr(api, "get_active_scenario", lambda: {"active_scenario_number": 0})
    monkeypatch.setattr(api, "_send_command_core", lambda *a, **kw: "0200")


def _count_sockets(monkeypatch):
    opened = []

    def factory(*a, **kw):
        opened.append(FakeSocket())
        return opened[-1]

    monkeypatch.setattr(inim_api.socket, "socket", factory)
    return opened


def test_keep_alive_reuses_connection(monkeypatch):
    opened = _count_sockets(monkeypatch)
    api = InimAlarmAPI("127.0.0.1", 5004, "1234")
    _stub_status(monkeypatch, api)
    for _ in range(3):
        result = api.execute_poll_cycle(last_processed_compact_event_index_val=0x920D, keep_alive=True)
        assert result["errors"] == []
    assert len(opened) == 1
    assert api._is_connected
    api.close()
    assert not api._is_connected


def test_keep_alive_reconnects_once_on_stale_connection(monkeypatch):
    opened = _count_sockets(monkeypatch)
    api = InimAlarmAPI("127.0.0.1", 5004, "1234")
    _stub_status(monkeypatch, api)
    api.execute_poll_cycle(last_processed_compact_event_index_val=0x920D, keep_alive=True)
    _stub_status(monkeypatch, api, fail_first=1)  # kept socket now broken
    result = api.execute_poll_cycle(last_processed_compact_event_index_val=0x920D, keep_alive=True)
    assert result["errors"] == []
    assert len(opened) == 2


def test_errors_close_kept_connection(monkeypatch):
    _count_sockets(monkeypatch)
    api = InimAlarmAPI("127.0.0.1", 5004, "1234")
    _stub_status(monkeypatch, api, fail_first=1)  # fresh connection, no retry
    result = api.execute_poll_cycle(last_processed_compact_event_index_val=0x920D, keep_alive=True)
    assert result["errors"]
    assert not api._is_connected


def test_light_cycle_reads_only_fast_status(monkeypatch):
    """Light cycle: zones, areas, scenario only; no exclusions, memory or events."""
    _count_sockets(monkeypatch)
    api = InimAlarmAPI("127.0.0.1", 5004, "1234")
    _stub_status(monkeypatch, api)
    called = []
    for name in ("get_zones_excluded_status", "get_zones_triggered_status"):
        monkeypatch.setattr(api, name, lambda n=name: called.append(n))
    monkeypatch.setattr(api, "_send_command_core", lambda *a, **kw: called.append("events") or "0200")

    result = api.execute_poll_cycle(last_processed_compact_event_index_val=0x920D, keep_alive=True, full=False)

    assert called == []
    assert result["errors"] == []
    assert result["events_result"] is None
    assert result["zones_status"] == {"zone_statuses": {}}
    assert api._is_connected  # healthy light cycle keeps the connection


def test_full_read_scheduling(monkeypatch):
    from custom_components.inim_smartliving_alarm import coordinator as coord

    c = coord.InimDataUpdateCoordinator.__new__(coord.InimDataUpdateCoordinator)
    c._slow_interval = 5
    c._force_full_read = False
    now = [1000.0]
    monkeypatch.setattr(coord.time, "monotonic", lambda: now[0])

    c._last_full_read = None
    assert c._full_read_due()  # first cycle is always full
    c._last_full_read = 1000.0
    now[0] = 1001.0
    assert not c._full_read_due()
    now[0] = 1004.6
    assert c._full_read_due()  # 5 s slow interval with jitter margin
    now[0] = 1001.0
    c._force_full_read = True  # set by async_request_refresh after a command
    assert c._full_read_due()


def _poll_then(monkeypatch, keep, command_ok=True):
    opened = _count_sockets(monkeypatch)
    api = InimAlarmAPI("127.0.0.1", 5004, "1234")
    api.keep_connection_open = keep
    _stub_status(monkeypatch, api)
    monkeypatch.setattr(api, "set_zone_excluded_status", lambda *a: command_ok)
    api.execute_poll_cycle(last_processed_compact_event_index_val=0x920D, keep_alive=keep)
    return api, opened


def test_command_reuses_kept_connection_and_leaves_it_open(monkeypatch):
    api, opened = _poll_then(monkeypatch, keep=True)
    assert api.execute_set_zone_excluded_status(4, True) is True
    assert api._is_connected
    api.execute_poll_cycle(last_processed_compact_event_index_val=0x920D, keep_alive=True)
    assert len(opened) == 1


def test_failed_command_closes_kept_connection(monkeypatch):
    api, opened = _poll_then(monkeypatch, keep=True, command_ok=False)
    assert api.execute_set_zone_excluded_status(4, True) is False
    assert not api._is_connected


def test_idle_kept_connection_is_reopened_before_command(monkeypatch):
    api, opened = _poll_then(monkeypatch, keep=True)
    api._last_io -= api.KEPT_CONNECTION_MAX_IDLE + 1
    assert api.execute_set_zone_excluded_status(4, True) is True
    assert len(opened) == 2


def test_command_closes_connection_without_keep_alive(monkeypatch):
    api, opened = _poll_then(monkeypatch, keep=False)
    assert not api._is_connected
    assert api.execute_set_zone_excluded_status(4, True) is True
    assert not api._is_connected


def test_refused_scenario_keeps_connection(monkeypatch):
    api, opened = _poll_then(monkeypatch, keep=True)
    monkeypatch.setattr(api, "check_scenario_activation_allowed", lambda **kw: False)
    assert api.execute_activate_scenario(1) is False
    assert api._is_connected
    monkeypatch.setattr(api, "check_scenario_activation_allowed", lambda **kw: None)
    assert api.execute_activate_scenario(1) is False
    assert not api._is_connected


def test_end_of_scenario_event_is_decoded(monkeypatch):
    api = InimAlarmAPI("127.0.0.1", 5004, "1234")
    # Real frame from a SmartLiving 10100: scenario 3 ended on disarm.
    monkeypatch.setattr(api, "_send_command_core", lambda *a, **kw: "4d508332010003001e")
    event = api._fetch_one_compact_event("00", "01")
    assert event["action_description"] == "End of Scenario Activated"
    assert event["scenario_number_0_indexed"] == 3


# Live block at 0x0740 captured from the reference SmartLiving 10100 with the
# panel disarmed: SIRENA INT (OC1) active, TAPPARELLE (OC2) and expansion 1 T1 off.
def _register_2003(active_bits, logical_terminals=100):
    """Output state register 0x2003 as read on the reference 10100 (len 0x40)."""
    base, length = InimAlarmAPI.output_state_layout(logical_terminals)
    data = bytearray(0x40)
    for k in active_bits:
        data[base + k // 8] |= 1 << (k % 8)
    return data.hex()


def test_output_state_layout_per_model():
    layout = InimAlarmAPI.output_state_layout
    assert layout(100) == (39, 52)  # 10100: verified (OC2 = byte 51 bit 6)
    assert layout(50) == (20, 27)
    assert layout(20) == (9, 12)
    assert layout(10) == (5, 7)


def test_outputs_status_parsing_follows_reference_reads():
    # 09/11 test on the reference 10100: register 0x2003 byte 40 = 0x04
    # (expansion 1 T1, logical terminal 10), byte 51 = 0x60 (OC1 + OC2).
    data = bytearray(0x40)
    data[40], data[51] = 0x04, 0x60
    assert InimAlarmAPI.parse_outputs_status(data.hex(), 100)["active_bits"] == [10, 101, 102]
    data[51] = 0x20  # OC2 switched off with the output command
    assert InimAlarmAPI.parse_outputs_status(data.hex(), 100)["active_bits"] == [10, 101]


def test_outputs_read_only_on_full_cycle(monkeypatch):
    from custom_components.inim_smartliving_alarm.panel_profiles import (
        PANEL_MODEL_1050,
        configure_api_for_panel,
        configure_api_hardware,
    )

    _count_sockets(monkeypatch)
    api = InimAlarmAPI("127.0.0.1", 5004, "1234")
    configure_api_for_panel(api, PANEL_MODEL_1050)
    configure_api_hardware(api, {"type": "00515"})
    _stub_status(monkeypatch, api)
    commands = []

    def send(cmd, **kw):
        commands.append(cmd)
        if cmd.startswith("0000002003000c"):
            assert kw["expect_specific_response_len"] == 13
            return _register_2003([3, 21], logical_terminals=20)[:24] + "00"
        return "0200"

    monkeypatch.setattr(api, "_send_command_core", send)
    light = api.execute_poll_cycle(last_processed_compact_event_index_val=0x920D, keep_alive=True, full=False)
    assert light["outputs_status"] is None
    full = api.execute_poll_cycle(last_processed_compact_event_index_val=0x920D, keep_alive=True)
    assert full["errors"] == []
    assert full["outputs_status"]["active_bits"] == [3, 21]  # terminal 3, OC1


def test_set_output_frame_and_result(monkeypatch):
    api = InimAlarmAPI("127.0.0.1", 5004, "1234")
    sent = []
    monkeypatch.setattr(api, "_send_raw_command", sent.append)
    payload = "01020304ffff" + "0200"
    monkeypatch.setattr(api, "_read_raw_response", lambda buffer_size: api.calculate_checksum(payload))
    monkeypatch.setattr(api, "_check_last_command_execution_status", lambda: {"status": "success"})
    assert api.set_output(2, 0) is True
    head = "0100002007" + "0008"
    assert sent == [head + api.calculate_checksum(head) + payload]


def _reference_terminal_records():
    """Terminal records (12 bytes per logical terminal) of the reference 10100."""
    records = [bytes.fromhex("10385b7db402121212000000")] * 9
    records.append(bytes.fromhex("10385b7db402000000000000"))
    records.append(bytes.fromhex("10385b7db401000000000001"))  # T1 of expansion 1: output
    records += [bytes.fromhex("10385b7db401000000000000")] * 89
    return b"".join(records)


def test_zone_command_indexes_read_from_config_memory(monkeypatch):
    from custom_components.inim_smartliving_alarm import panel_profiles as pp
    from test_effective_entities import REFERENCE_TERMINAL_TABLE

    api = InimAlarmAPI("127.0.0.1", 5004, "1234")
    pp.configure_api_for_panel(api, pp.PANEL_MODEL_10100)
    table = REFERENCE_TERMINAL_TABLE + b"\xff" * (240 - len(REFERENCE_TERMINAL_TABLE))
    memory = {0xCF75: table, 0x90CD: _reference_terminal_records()}
    frames = []

    def send(cmd, expect_specific_response_len):
        frames.append(cmd)
        assert cmd[:6] == "000001"  # configuration bank
        address, length = int(cmd[6:10], 16), int(cmd[10:14], 16)
        assert expect_specific_response_len == length + 1
        for base, blob in memory.items():
            if base <= address < base + len(blob):
                return blob[address - base : address - base + length].hex()
        return None

    monkeypatch.setattr(api, "_send_command_core", send)
    result = pp._profile_get_zone_command_indexes(api)

    assert "11" not in result["zone_command_indexes"]
    assert result["zone_command_indexes"]["12"] == 35
    assert result["output_zones"] == [11]
    assert result["output_terminals"] == {"11": 10}
    assert frames[0].startswith("000001cf7500f0")  # 240 physical terminals


def test_output_list_fixed_and_terminal_outputs():
    from custom_components.inim_smartliving_alarm.panel_profiles import build_output_list

    names = [""] * 11
    names[10] = "SEZIONALE"
    outputs = build_output_list(100, ["RELE'", "SIRENA INT", "TAPPARELLE"], {11: 10, 2: 1}, names)
    assert outputs == [
        {"key": "fixed_0", "index": 0, "bit": 100, "name": "RELE'"},
        {"key": "fixed_1", "index": 1, "bit": 101, "name": "SIRENA INT"},
        {"key": "fixed_2", "index": 2, "bit": 102, "name": "TAPPARELLE"},
        {"key": "terminal_10", "index": 10, "bit": 10, "name": "SEZIONALE"},
    ]  # zone 2 on physical index 1 left out: same index as OC1
    assert build_output_list(50, None, {}, [])[1]["name"] == "OC1"


def test_hardware_key_from_reported_type():
    from custom_components.inim_smartliving_alarm.panel_profiles import hardware_key

    assert hardware_key("10100") == "10100"
    assert hardware_key("01050") == "1050"
    assert hardware_key("00515") == "515"
    assert hardware_key("00505") == "505"
    assert hardware_key(None, "smartliving_10100") == "10100"
    assert hardware_key("Unknown") == "1050"


def test_names_read_at_panel_pointer_and_capped_by_next_table(monkeypatch):
    from custom_components.inim_smartliving_alarm import panel_profiles as pp

    api = InimAlarmAPI("127.0.0.1", 5004, "1234")
    pp.configure_api_for_panel(api, pp.PANEL_MODEL_1050)
    # Pointer block as read on the reference 10100 (RAM 0x4014-0x4029).
    block = bytes.fromhex("0000f000700db013901580160019602250233025a026")
    names_bank = {0x0000: b"".join(n.ljust(16).encode() for n in ["CASA", "GARAGE"] + ["X"] * 13)}
    reads = []

    def send(cmd, expect_specific_response_len):
        reads.append(cmd[:14])
        if cmd.startswith("0000004014"):
            return block.hex() + "00"
        address, length = int(cmd[6:10], 16), int(cmd[10:14], 16)
        assert cmd.startswith("000101")
        blob = names_bank[0x0000]
        return blob[address : address + length].hex()

    monkeypatch.setattr(api, "_send_command_core", send)
    api.name_pointers = pp._read_name_pointers(api)
    assert api.name_pointers["tables"]["zone_names_start"] == 0x00F0
    assert api.name_pointers["tables"]["output_names_start"] == 0x26A0
    result = pp._profile_get_areas(api)
    assert result["names"][:2] == ["CASA", "GARAGE"]
    assert len(result["names"]) == 10  # 1050 profile: 10 areas (room before zones: 15)


# --- diagnostics and model auto-detection ---
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
