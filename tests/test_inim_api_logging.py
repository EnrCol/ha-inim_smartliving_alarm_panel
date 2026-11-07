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


def test_no_new_compact_events_do_not_spam_info(monkeypatch, caplog):
    api = InimAlarmAPI("127.0.0.1", 5004, "1234")
    monkeypatch.setattr(api, "_get_raw_next_event_pointer", lambda: "0002")

    # x_next = 2 => most recent compact index = 0x920D.
    with caplog.at_level(logging.INFO, logger=inim_api.logger.name):
        result = api.get_compact_events(last_processed_compact_event_index_val=0x920D)

    assert result["events"] == []
    assert result["latest_event_index_val"] == 0x920D
    assert not [r for r in caplog.records if r.name == inim_api.logger.name]


def test_new_compact_event_still_emits_useful_log(monkeypatch, caplog):
    api = InimAlarmAPI("127.0.0.1", 5004, "1234")
    monkeypatch.setattr(api, "_get_raw_next_event_pointer", lambda: "0002")
    monkeypatch.setattr(api, "_fetch_one_compact_event", lambda *a: {"event": "example"})
    monkeypatch.setattr(inim_api.time, "sleep", lambda _: None)

    with caplog.at_level(logging.INFO, logger=inim_api.logger.name):
        result = api.get_compact_events(last_processed_compact_event_index_val=0x9204)

    assert len(result["events"]) == 1
    assert any("Retrieved 1 compact events" in r.getMessage() for r in caplog.records)


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
