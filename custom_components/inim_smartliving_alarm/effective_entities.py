"""Helpers for detecting effective panel entities and scenario mappings."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Any

from .const import (
    CONF_LIMIT_AREAS,
    CONF_LIMIT_SCENARIOS,
    CONF_LIMIT_ZONES,
    CONF_SCENARIO_ARM_AWAY,
    CONF_SCENARIO_ARM_HOME,
    CONF_SCENARIO_ARM_NIGHT,
    CONF_SCENARIO_ARM_VACATION,
    CONF_SCENARIO_DISARM,
    KEY_INIT_AREA_NAMES,
    KEY_INIT_AREAS,
    KEY_INIT_SCENARIO_NAMES,
    KEY_INIT_SCENARIOS,
    KEY_INIT_ZONE_NAMES,
    KEY_INIT_ZONES,
)

_PLACEHOLDER_PATTERNS = {
    "zone": re.compile(r"^(?:ZONE|ZONA)\s*0*\d+$", re.IGNORECASE),
    "area": re.compile(r"^AREA\s*0*\d+$", re.IGNORECASE),
    "scenario": re.compile(r"^SCENARIO\s*0*\d+$", re.IGNORECASE),
}

_SCENARIO_ALIASES = {
    CONF_SCENARIO_DISARM: {
        "DISINSERITO",
        "DISARMATO",
        "DISARMO",
        "DISARMED",
    },
    CONF_SCENARIO_ARM_AWAY: {
        "TOTALE",
        "INSERIMENTO TOTALE",
        "ARMED AWAY",
        "AWAY",
    },
    CONF_SCENARIO_ARM_HOME: {
        # Only explicit Home labels are unambiguous. "SOLO P.T." is
        # installation-specific and must be chosen by the user.
        "ARMED HOME",
        "HOME",
    },
    CONF_SCENARIO_ARM_NIGHT: {
        "NOTTE",
        "NIGHT",
        "ARMED NIGHT",
    },
    CONF_SCENARIO_ARM_VACATION: {
        "VACANZA",
        "VACATION",
        "ARMED VACATION",
    },
}


def normalize_panel_name(name: str | None) -> str:
    """Return a stable uppercase representation for comparisons."""
    if not name:
        return ""

    normalized = unicodedata.normalize("NFKD", str(name))
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = re.sub(r"[^A-Za-z0-9]+", " ", normalized.upper())
    return " ".join(normalized.split())


def is_effective_name(name: str | None, entity_kind: str) -> bool:
    """Return True for a programmed name, excluding empty/default placeholders."""
    stripped = (name or "").strip()
    if not stripped:
        return False

    pattern = _PLACEHOLDER_PATTERNS.get(entity_kind)
    if pattern is None:
        raise ValueError(f"Unsupported entity kind: {entity_kind}")

    return pattern.fullmatch(stripped) is None


def effective_indexes(
    names: Iterable[str | None], entity_kind: str, limit: int | None = None
) -> list[int]:
    """Return zero-based indexes whose names are effective and within the limit."""
    names_list = list(names)
    upper_bound = len(names_list) if limit is None else min(len(names_list), limit)
    return [
        index
        for index in range(upper_bound)
        if is_effective_name(names_list[index], entity_kind)
    ]


def infer_scenario_mappings(scenario_names: Iterable[str | None]) -> dict[str, int]:
    """Infer safe Home Assistant scenario mappings from exact known aliases.

    Only unambiguous exact normalized-name matches are returned. Unknown or
    duplicate aliases are intentionally left unmapped for manual selection.
    Site-specific partial scenarios (e.g. SOLO P.T.) are never guessed as Home.
    """
    matches: dict[str, list[int]] = {key: [] for key in _SCENARIO_ALIASES}

    for index, raw_name in enumerate(scenario_names):
        if not is_effective_name(raw_name, "scenario"):
            continue

        normalized_name = normalize_panel_name(raw_name)
        for mapping_key, aliases in _SCENARIO_ALIASES.items():
            if normalized_name in aliases:
                matches[mapping_key].append(index)

    return {
        mapping_key: indexes[0]
        for mapping_key, indexes in matches.items()
        if len(indexes) == 1
    }


def _last_effective_limit(names: Iterable[str | None], entity_kind: str) -> int | None:
    """Return the smallest contiguous import limit covering all effective indexes."""
    indexes = effective_indexes(names, entity_kind)
    return indexes[-1] + 1 if indexes else None


def build_automatic_options(
    initial_panel_config: dict[str, Any], current_options: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build automatic limits and safe scenario mappings from panel data.

    Import limits are recalculated from the last programmed slot. Existing
    scenario mappings (including explicit None) remain manual overrides;
    only absent mapping keys are filled from unambiguous exact-name matches.
    """
    area_names = initial_panel_config.get(KEY_INIT_AREAS, {}).get(
        KEY_INIT_AREA_NAMES, []
    )
    zone_names = initial_panel_config.get(KEY_INIT_ZONES, {}).get(
        KEY_INIT_ZONE_NAMES, []
    )
    scenario_names = initial_panel_config.get(KEY_INIT_SCENARIOS, {}).get(
        KEY_INIT_SCENARIO_NAMES, []
    )

    area_indexes = effective_indexes(area_names, "area")
    zone_indexes = effective_indexes(zone_names, "zone")
    scenario_indexes = effective_indexes(scenario_names, "scenario")

    detected_limits = {
        CONF_LIMIT_AREAS: _last_effective_limit(area_names, "area"),
        CONF_LIMIT_ZONES: _last_effective_limit(zone_names, "zone"),
        CONF_LIMIT_SCENARIOS: _last_effective_limit(scenario_names, "scenario"),
    }

    updated_options = dict(current_options)
    for option_key, detected_value in detected_limits.items():
        if detected_value is not None:
            updated_options[option_key] = detected_value

    inferred_mappings = infer_scenario_mappings(scenario_names)
    applied_mappings: dict[str, int] = {}
    for mapping_key, scenario_index in inferred_mappings.items():
        if mapping_key not in updated_options:
            # A key explicitly saved as None means the user selected "none".
            # Never override that choice at runtime.
            updated_options[mapping_key] = scenario_index
            applied_mappings[mapping_key] = scenario_index

    summary = {
        "effective_areas": len(area_indexes),
        "effective_zones": len(zone_indexes),
        "effective_scenarios": len(scenario_indexes),
        "detected_limits": {
            key: value for key, value in detected_limits.items() if value is not None
        },
        "applied_scenario_mappings": applied_mappings,
    }
    return updated_options, summary



def resolve_ha_alarm_state(
    active_scenario_index: int | None,
    scenario_mappings: dict[str, int | None],
    triggered_areas: Iterable[int] | None = None,
) -> str | None:
    """Resolve only verified states; None makes alarm_control_panel unknown.

    Never infer "disarmed" from missing data and never use "custom_bypass"
    for an unrecognized scenario. Physical alarm trigger takes precedence.
    """
    if triggered_areas and any(triggered_areas):
        return "triggered"
    if active_scenario_index is None or active_scenario_index < 0:
        return None

    states_by_mapping = (
        (CONF_SCENARIO_DISARM, "disarmed"),
        (CONF_SCENARIO_ARM_HOME, "armed_home"),
        (CONF_SCENARIO_ARM_AWAY, "armed_away"),
        (CONF_SCENARIO_ARM_NIGHT, "armed_night"),
        (CONF_SCENARIO_ARM_VACATION, "armed_vacation"),
    )
    for mapping_key, state in states_by_mapping:
        mapped_index = scenario_mappings.get(mapping_key)
        if mapped_index is not None and active_scenario_index == mapped_index:
            return state
    return None


def resolve_any_area_armed(
    area_statuses: dict[int, str] | None,
    programmed_area_names: Iterable[str | None],
    limit: int | None = None,
) -> bool | None:
    """Read-only tri-state: True if armed, False only if ALL known disarmed.

    Unknown or missing area status must never be presented as disarmed.
    Only programmed areas within the import limit count.
    """
    areas = effective_indexes(programmed_area_names, "area", limit)
    if not areas or not area_statuses:
        return None
    values = [area_statuses.get(index + 1) for index in areas]
    if any(isinstance(value, str) and value.lower() == "armed" for value in values):
        return True
    if all(isinstance(value, str) and value.lower() == "disarmed" for value in values):
        return False
    return None
