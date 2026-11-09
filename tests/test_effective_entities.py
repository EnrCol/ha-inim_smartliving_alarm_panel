"""Tests for automatic SmartLiving entity detection."""

from custom_components.inim_smartliving_alarm.config_flow import _build_scenario_choices
from custom_components.inim_smartliving_alarm.const import (
    CONF_LIMIT_AREAS,
    CONF_LIMIT_SCENARIOS,
    CONF_LIMIT_ZONES,
    CONF_SCENARIO_ARM_AWAY,
    CONF_SCENARIO_ARM_HOME,
    CONF_SCENARIO_ARM_NIGHT,
    CONF_SCENARIO_DISARM,
)
from custom_components.inim_smartliving_alarm.effective_entities import (
    build_automatic_options,
    resolve_any_area_armed,
    resolve_ha_alarm_state,
    effective_indexes,
    infer_scenario_mappings,
    is_effective_name,
    normalize_panel_name,
)


def test_effective_name_filters_only_empty_and_numbered_placeholders() -> None:
    assert not is_effective_name("", "zone")
    assert not is_effective_name("ZONE 015", "zone")
    assert not is_effective_name("AREA 006", "area")
    assert not is_effective_name("SCENARIO 030", "scenario")

    assert is_effective_name("SENSORI ESTERNI", "area")
    assert is_effective_name("PORTONE INGRESSO", "zone")
    assert is_effective_name("SOLO P.T.", "scenario")


def test_normalize_panel_name_handles_punctuation_and_accents() -> None:
    assert normalize_panel_name("  Solo P.T. ") == "SOLO P T"
    assert normalize_panel_name("Vacànza") == "VACANZA"


def test_effective_indexes_keep_real_slots_with_gaps() -> None:
    names = ["PORTA", "", "ZONE 003", "FINESTRA"]
    assert effective_indexes(names, "zone") == [0, 3]


def test_infer_scenario_mappings_for_common_italian_names() -> None:
    names = [
        "DISINSERITO",
        "SOLO P.T.",
        "SOLO SEMINT.",
        "TOTALE",
        "NOTTE",
        "SCENARIO 006",
    ]

    assert infer_scenario_mappings(names) == {
        CONF_SCENARIO_DISARM: 0,
        CONF_SCENARIO_ARM_AWAY: 3,
        CONF_SCENARIO_ARM_NIGHT: 4,
    }


def test_duplicate_alias_is_not_inferred() -> None:
    names = ["TOTALE", "TOTALE"]
    assert CONF_SCENARIO_ARM_AWAY not in infer_scenario_mappings(names)


def test_build_automatic_options_replaces_stale_limits_and_preserves_manual_mapping() -> None:
    initial_config = {
        "areas": {
            "names": [
                "PERIMETRALE P.T.",
                "PERIM. SEMI",
                "VOL. P.T.",
                "VOL. SEMINT.",
                "SENSORI ESTERNI",
                "AREA 006",
            ]
        },
        "zones": {
            "zone_names": [
                *[f"ZONA REALE {index}" for index in range(1, 15)],
                *["" for _ in range(13)],
                "FIN TAVERNA 1",
                "FIN TAVERNA 2",
                "FIN TAVERNA 3",
                "FIN LAVANDERIA",
                "FIN BAGNO SEMI",
            ]
        },
        "scenarios": {
            "names": [
                "DISINSERITO",
                "SOLO P.T.",
                "SOLO SEMINT.",
                "TOTALE",
                "NOTTE",
                "SCENARIO 006",
            ]
        },
    }
    current_options = {
        CONF_LIMIT_AREAS: 8,
        CONF_LIMIT_ZONES: 34,
        CONF_LIMIT_SCENARIOS: 12,
        CONF_SCENARIO_ARM_HOME: 2,
        CONF_SCENARIO_ARM_AWAY: None,
    }

    updated, summary = build_automatic_options(initial_config, current_options)

    assert updated[CONF_LIMIT_AREAS] == 5
    assert updated[CONF_LIMIT_ZONES] == 32
    assert updated[CONF_LIMIT_SCENARIOS] == 5
    assert updated[CONF_SCENARIO_ARM_HOME] == 2
    assert updated[CONF_SCENARIO_ARM_AWAY] is None
    assert updated[CONF_SCENARIO_DISARM] == 0
    assert updated[CONF_SCENARIO_ARM_NIGHT] == 4
    assert summary["effective_areas"] == 5
    assert summary["effective_zones"] == 19
    assert summary["effective_scenarios"] == 5


def test_unambiguous_mappings_fill_only_absent_keys() -> None:
    config = {
        "areas": {"names": ["PERIMETRALE P.T."]},
        "zones": {"zone_names": ["FINESTRA"]},
        "scenarios": {"names": ["DISINSERITO", "SOLO P.T.", "TOTALE", "NOTTE"]},
    }
    options, _ = build_automatic_options(config, {})
    assert CONF_SCENARIO_ARM_HOME not in options
    assert options[CONF_SCENARIO_DISARM] == 0
    assert options[CONF_SCENARIO_ARM_AWAY] == 2
    assert options[CONF_SCENARIO_ARM_NIGHT] == 3

    disabled, _ = build_automatic_options(config, {CONF_SCENARIO_ARM_AWAY: None})
    assert disabled[CONF_SCENARIO_ARM_AWAY] is None


def test_ha_state_does_not_guess_unmapped_or_missing_scenarios() -> None:
    mappings = {
        CONF_SCENARIO_DISARM: 0,
        CONF_SCENARIO_ARM_HOME: 2,
        CONF_SCENARIO_ARM_AWAY: 3,
        CONF_SCENARIO_ARM_NIGHT: 4,
    }
    assert resolve_ha_alarm_state(0, mappings, []) == "disarmed"
    assert resolve_ha_alarm_state(2, mappings, []) == "armed_home"
    assert resolve_ha_alarm_state(3, mappings, []) == "armed_away"
    assert resolve_ha_alarm_state(4, mappings, []) == "armed_night"
    assert resolve_ha_alarm_state(1, mappings, []) is None
    assert resolve_ha_alarm_state(None, mappings, []) is None
    assert resolve_ha_alarm_state(-1, mappings, []) is None
    assert resolve_ha_alarm_state(0, mappings, [2]) == "triggered"
    assert resolve_ha_alarm_state(1, mappings, [2]) == "triggered"
    assert resolve_ha_alarm_state(0, {}, []) is None
    assert resolve_ha_alarm_state(None, {}, [1]) == "triggered"


def test_any_area_armed_is_tri_state_and_ignores_unprogrammed_areas() -> None:
    names = ["PERIMETRALE P.T.", "PERIM. SEMI", "AREA 003"]
    assert resolve_any_area_armed(
        {1: "disarmed", 2: "armed", 3: "unknown"}, names
    ) is True
    assert resolve_any_area_armed(
        {1: "disarmed", 2: "disarmed", 3: "armed"}, names
    ) is False
    assert resolve_any_area_armed({1: "disarmed"}, names) is None
    assert resolve_any_area_armed({1: "unknown", 2: "disarmed"}, names) is None
    assert resolve_any_area_armed(None, names) is None
    assert resolve_any_area_armed({1: "disarmed"}, ["AREA 001"]) is None
    assert resolve_any_area_armed(
        {1: "disarmed", 2: "armed"}, names, limit=1
    ) is False


def test_scenario_selector_preserves_real_indexes_but_omits_placeholders() -> None:
    initial_config = {
        "scenarios": {"names": [
            "DISINSERITO", "SCENARIO 002", "SOLO SEMINT.",
            "", "NOTTE", "SCENARIO 006",
        ]}
    }
    choices = _build_scenario_choices(initial_config)
    assert choices == {
        "none": "None (Do Not Assign)",
        "0": "0: DISINSERITO",
        "2": "2: SOLO SEMINT.",
        "4": "4: NOTTE",
    }


# --- Active-scenario read: area bitmask (PR #12 by scorbacella) ---
from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402

from custom_components.inim_smartliving_alarm import _configure_active_scenario_mask  # noqa: E402
from custom_components.inim_smartliving_alarm.inim_api import InimAlarmAPI  # noqa: E402


@pytest.mark.parametrize(
    ("areas", "command"),
    [
        (7, "0000001ffb7f019a"),  # historical fixed command
        (5, "0000001ffb1f013a"),  # official app on SmartLiving 515
        (10, "0003001ffbff011d"),  # official app on SmartLiving 1050
        (15, "007f001ffbff0199"),  # verified on SmartLiving 10100
        (1, "0000001ffb01011c"),  # verified on 10100: area 1 only
    ],
)
def test_command_mask_and_checksum(areas, command):
    assert InimAlarmAPI.build_active_scenario_command(areas) == command


def test_legacy_command_when_not_configured(monkeypatch):
    api = InimAlarmAPI("127.0.0.1", 5004, "1234")
    sent = []
    monkeypatch.setattr(api, "_send_command_core", lambda cmd, **kw: sent.append(cmd) or "02")
    assert api.get_active_scenario()["active_scenario_number"] == 2
    assert sent == ["0000001ffb7f019a"]


def test_configured_mask_is_sent(monkeypatch):
    api = InimAlarmAPI("127.0.0.1", 5004, "1234")
    api.active_scenario_area_count = 15
    sent = []
    monkeypatch.setattr(api, "_send_command_core", lambda cmd, **kw: sent.append(cmd) or "00")
    api.get_active_scenario()
    assert sent == ["007f001ffbff0199"]


@pytest.mark.parametrize(
    ("limit_areas", "max_areas", "expected"),
    [
        (5, 15, 7),  # reference 10100 with 5 areas: unchanged (0x007F)
        (5, 10, 7),  # 515 under the 1050 profile: unchanged
        (3, 10, 7),  # low import limit never hides legacy areas
        (10, 10, 10),  # 1050 with 10 areas: like the official app
        (15, 15, 15),  # 10100 with 15 areas
        (12, 10, 10),  # never beyond the panel profile
        (None, 15, 10),  # missing option: integration default (10)
        ("x", 15, 7),  # invalid value: legacy
    ],
)
def test_area_count_rule(limit_areas, max_areas, expected):
    api = SimpleNamespace(system_max_areas=max_areas, active_scenario_area_count=None)
    options = {} if limit_areas is None else {"limit_areas": limit_areas}
    entry = SimpleNamespace(options=options, data={})
    _configure_active_scenario_mask(api, entry)
    assert api.active_scenario_area_count == expected


# Terminal tables read from the reference SmartLiving 10100 (firmware 6.09).
REFERENCE_TERMINAL_TABLE = bytes.fromhex(
    "000102030405060708090a" + "ff" * 24 + "0b0c0d" + "ffff" + "1b1c1d1e1f" + "ff" * 85
)


def test_terminal_table_reproduces_field_confirmed_indexes():
    from custom_components.inim_smartliving_alarm.panel_profiles import build_zone_command_indexes
    from custom_components.inim_smartliving_alarm.switch import SMARTLIVING_10100_ZONE_COMMAND_INDEX_MAP

    assert len(REFERENCE_TERMINAL_TABLE) == 130
    types = bytes([0] * 10 + [1] + [0] * 89)  # logical terminal 10 = output
    indexes, outputs = build_zone_command_indexes(REFERENCE_TERMINAL_TABLE, types)
    assert indexes == SMARTLIVING_10100_ZONE_COMMAND_INDEX_MAP
    assert outputs == {11: 10}  # expansion 1 T1 programmed as an output


def test_terminal_table_without_type_table_keeps_every_assigned_terminal():
    from custom_components.inim_smartliving_alarm.panel_profiles import build_zone_command_indexes

    indexes, outputs = build_zone_command_indexes(REFERENCE_TERMINAL_TABLE)
    assert indexes[11] == 10
    assert outputs == {}
    assert len(indexes) == 19
