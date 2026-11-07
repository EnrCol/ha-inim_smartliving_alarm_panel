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
