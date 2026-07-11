"""Helpers for detecting effective panel entities and scenario mappings."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from .const import (
    CONF_SCENARIO_ARM_AWAY,
    CONF_SCENARIO_ARM_HOME,
    CONF_SCENARIO_ARM_NIGHT,
    CONF_SCENARIO_ARM_VACATION,
    CONF_SCENARIO_DISARM,
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
        "SOLO P T",
        "SOLO PT",
        "PARZIALE P T",
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
