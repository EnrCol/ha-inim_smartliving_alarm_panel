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
