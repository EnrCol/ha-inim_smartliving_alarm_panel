"""Tests for automatic SmartLiving entity detection."""

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
        CONF_SCENARIO_ARM_HOME: 1,
        CONF_SCENARIO_ARM_AWAY: 3,
        CONF_SCENARIO_ARM_NIGHT: 4,
    }


def test_duplicate_alias_is_not_inferred() -> None:
    names = ["TOTALE", "TOTALE"]
    assert CONF_SCENARIO_ARM_AWAY not in infer_scenario_mappings(names)


def test_build_automatic_options_detects_limits_and_preserves_manual_mapping() -> None:
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
        CONF_SCENARIO_ARM_HOME: 2,
        CONF_SCENARIO_ARM_AWAY: None,
    }

    updated, summary = build_automatic_options(initial_config, current_options)

    assert updated[CONF_LIMIT_AREAS] == 5
    assert updated[CONF_LIMIT_ZONES] == 32
    assert updated[CONF_LIMIT_SCENARIOS] == 5
    assert updated[CONF_SCENARIO_ARM_HOME] == 2
    assert updated[CONF_SCENARIO_ARM_AWAY] == 3
    assert updated[CONF_SCENARIO_DISARM] == 0
    assert updated[CONF_SCENARIO_ARM_NIGHT] == 4
    assert summary["effective_areas"] == 5
    assert summary["effective_zones"] == 19
    assert summary["effective_scenarios"] == 5
