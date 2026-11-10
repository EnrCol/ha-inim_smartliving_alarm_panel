"""Scenario select for the Inim SmartLiving integration.

One entity whose options are the scenarios programmed on the panel, with
their real names. The current option is the active scenario; choosing an
option activates it. The attributes carry what a dashboard card needs to
draw an alarm panel with every scenario (see www/inim-alarm-panel.js):
the scenario list, the armed / disarmed / triggered state of the areas and
the open zones.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_LIMIT_AREAS,
    CONF_LIMIT_SCENARIOS,
    CONF_LIMIT_ZONES,
    CONF_PANEL_NAME,
    DATA_API_CLIENT,
    DATA_COORDINATOR,
    DATA_INITIAL_PANEL_CONFIG,
    DEFAULT_LIMIT_SCENARIOS,
    DEFAULT_PANEL_NAME,
    DOMAIN,
    KEY_INIT_AREA_NAMES,
    KEY_INIT_AREAS,
    KEY_INIT_SCENARIO_ACTIVATION_AREA_ACTIONS,
    KEY_INIT_SCENARIO_ACTIVATION_INDEX,
    KEY_INIT_SCENARIO_ACTIVATIONS,
    KEY_INIT_SCENARIO_NAMES,
    KEY_INIT_SCENARIOS,
    KEY_INIT_SYSTEM_INFO,
    KEY_INIT_SYSTEM_INFO_TYPE,
    KEY_INIT_SYSTEM_INFO_VERSION,
    KEY_INIT_ZONE_NAMES,
    KEY_INIT_ZONES,
    KEY_LIVE_ACTIVE_SCENARIO,
    KEY_LIVE_ACTIVE_SCENARIO_NUMBER,
    KEY_LIVE_AREA_STATUSES_MAP,
    KEY_LIVE_AREAS_STATUS,
    KEY_LIVE_TRIGGERED_AREAS_LIST,
    KEY_LIVE_ZONE_STATUSES_MAP,
    KEY_LIVE_ZONES_STATUS,
)
from .effective_entities import effective_indexes
from .inim_api import InimAlarmAPI
from .utils import async_handle_scenario_activation_failure

_LOGGER = logging.getLogger(__name__)


def scenario_kind(activation: dict[str, Any] | None) -> str:
    """Return "disarm" when a scenario only disarms areas, otherwise "arm"."""
    actions = set(
        ((activation or {}).get(KEY_INIT_SCENARIO_ACTIVATION_AREA_ACTIONS) or {}).values()
    )
    return "disarm" if "disarm" in actions and "arm" not in actions else "arm"


def _by_number(mapping: dict[Any, Any] | None, number: int) -> Any:
    """Look up a 1-based number in a dict keyed by int or str."""
    if not mapping:
        return None
    return mapping.get(number, mapping.get(str(number)))


def panel_summary(
    data: dict[str, Any] | None,
    area_names: list[str | None],
    zone_names: list[str | None],
    limit_areas: int | None,
    limit_zones: int | None,
) -> dict[str, Any]:
    """Alarm state, armed areas and open zones from one coordinator snapshot.

    alarm_state: "triggered" if an area is in alarm, "armed" if at least one
    programmed area is armed, "disarmed" only when every programmed area is
    known to be disarmed, otherwise "unknown".
    """
    data = data or {}
    area_data = data.get(KEY_LIVE_AREAS_STATUS) or {}
    statuses = area_data.get(KEY_LIVE_AREA_STATUSES_MAP) or {}
    triggered = area_data.get(KEY_LIVE_TRIGGERED_AREAS_LIST) or []

    armed_areas: list[str] = []
    known = True
    for index in effective_indexes(area_names, "area", limit_areas):
        status = _by_number(statuses, index + 1)
        if not isinstance(status, str):
            known = False
        elif status.lower() == "armed":
            armed_areas.append((area_names[index] or "").strip())

    if any(triggered):
        state = "triggered"
    elif armed_areas:
        state = "armed"
    elif known and statuses:
        state = "disarmed"
    else:
        state = "unknown"

    zone_statuses = (data.get(KEY_LIVE_ZONES_STATUS) or {}).get(KEY_LIVE_ZONE_STATUSES_MAP) or {}
    upper = len(zone_names) if limit_zones is None else min(len(zone_names), limit_zones)
    open_zones = [
        (zone_names[i] or "").strip()
        for i in range(upper)
        if (zone_names[i] or "").strip()
        and _by_number(zone_statuses, i + 1) == "alarmed"
    ]
    return {"alarm_state": state, "armed_areas": armed_areas, "open_zones": open_zones}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the scenario select."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    initial = entry.data.get(DATA_INITIAL_PANEL_CONFIG, {})
    names = (initial.get(KEY_INIT_SCENARIOS) or {}).get(KEY_INIT_SCENARIO_NAMES) or []
    limit = entry.options.get(
        CONF_LIMIT_SCENARIOS, entry.data.get(CONF_LIMIT_SCENARIOS, DEFAULT_LIMIT_SCENARIOS)
    )
    activations = initial.get(KEY_INIT_SCENARIO_ACTIVATIONS) or []
    scenarios = []
    for index in effective_indexes(names, "scenario", limit):
        activation = next(
            (a for a in activations if a.get(KEY_INIT_SCENARIO_ACTIVATION_INDEX) == index),
            None,
        )
        scenarios.append(
            {"index": index, "name": names[index].strip(), "kind": scenario_kind(activation)}
        )
    if not scenarios:
        _LOGGER.info("No programmed scenarios: scenario select not created")
        return
    async_add_entities(
        [
            InimScenarioSelect(
                entry_data[DATA_COORDINATOR],
                entry_data[DATA_API_CLIENT],
                entry,
                initial,
                scenarios,
            )
        ]
    )


class InimScenarioSelect(CoordinatorEntity, SelectEntity):
    """Active scenario of the panel; selecting an option activates it."""

    _attr_icon = "mdi:shield-home"

    def __init__(
        self,
        coordinator,
        api_client: InimAlarmAPI,
        entry: ConfigEntry,
        initial: dict[str, Any],
        scenarios: list[dict[str, Any]],
    ) -> None:
        super().__init__(coordinator)
        self.api_client = api_client
        self.config_entry = entry
        self._initial = initial
        self._scenarios = scenarios
        self._by_name = {s["name"]: s for s in scenarios}
        self._panel_name = entry.data.get(CONF_PANEL_NAME, DEFAULT_PANEL_NAME)
        self._system_info = initial.get(KEY_INIT_SYSTEM_INFO) or {}
        self._area_names = (initial.get(KEY_INIT_AREAS) or {}).get(KEY_INIT_AREA_NAMES) or []
        self._zone_names = (initial.get(KEY_INIT_ZONES) or {}).get(KEY_INIT_ZONE_NAMES) or []
        self._attr_name = f"{self._panel_name} Scenario"
        self._attr_unique_id = f"{entry.entry_id}_scenario_select"
        self._attr_options = [s["name"] for s in scenarios]

    @property
    def suggested_object_id(self) -> str | None:
        return f"{self._panel_name}_scenario"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.config_entry.entry_id)},
            name=self._panel_name,
            manufacturer="Inim Electronics",
            model=self._system_info.get(KEY_INIT_SYSTEM_INFO_TYPE, "SmartLiving"),
            sw_version=self._system_info.get(KEY_INIT_SYSTEM_INFO_VERSION, "Unknown"),
        )

    def _active_index(self) -> int | None:
        scenario = (self.coordinator.data or {}).get(KEY_LIVE_ACTIVE_SCENARIO) or {}
        index = scenario.get(KEY_LIVE_ACTIVE_SCENARIO_NUMBER)
        return index if isinstance(index, int) and index >= 0 else None

    @property
    def current_option(self) -> str | None:
        index = self._active_index()
        return next((s["name"] for s in self._scenarios if s["index"] == index), None)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        options = self.config_entry.options
        summary = panel_summary(
            self.coordinator.data,
            self._area_names,
            self._zone_names,
            options.get(CONF_LIMIT_AREAS),
            options.get(CONF_LIMIT_ZONES),
        )
        return {
            "scenarios": self._scenarios,
            "active_scenario_index": self._active_index(),
            **summary,
        }

    async def async_select_option(self, option: str) -> None:
        scenario = self._by_name.get(option)
        if scenario is None:
            raise ValueError(f"Unknown scenario {option!r}")
        index = scenario["index"]
        action = f"activate scenario '{option}' (index {index})"
        _LOGGER.info("%s: %s", self.entity_id, action)
        success = await self.hass.async_add_executor_job(
            self.api_client.execute_activate_scenario, index
        )
        if success:
            await self.coordinator.async_request_refresh()
            return
        await async_handle_scenario_activation_failure(
            self.hass,
            self.coordinator,
            self._initial,
            self.unique_id,
            self.name or "Scenario",
            index,
            action,
            is_disarm_scenario=scenario["kind"] == "disarm",
        )
