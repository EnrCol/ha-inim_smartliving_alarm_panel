"""Panel model profiles and profile-aware API patches.

The original integration was effectively modelled around SmartLiving 1050/1050L
limits: 50 zones, 10 areas, 10 keyboards and 20 readers. SmartLiving 10100/10100L
has a larger memory layout: 100 zones, 15 areas, 15 keyboards and 30 readers.

Names are stored as 16-byte ASCII records. SmartLiving 10100/10100L uses a
profile-specific memory map confirmed by a local memory dump, so the major name
blocks are configured explicitly instead of inferred where possible.
"""

from __future__ import annotations

import binascii
import logging
import math
import time
from typing import Any

from .inim_api import InimAlarmAPI, InimAlarmConstants

_LOGGER = logging.getLogger(__name__)

PANEL_MODEL_1050 = "smartliving_1050"
PANEL_MODEL_10100 = "smartliving_10100"
DEFAULT_PANEL_MODEL = PANEL_MODEL_1050

PANEL_MODEL_OPTIONS = {
    PANEL_MODEL_1050: "SmartLiving 1050 / 1050L compatible",
    PANEL_MODEL_10100: "SmartLiving 10100 / 10100L",
}

BYTES_PER_NAME = 16
MAX_MEMORY_READ_DATA_BYTES = 250

PANEL_PROFILES: dict[str, dict[str, int | str]] = {
    PANEL_MODEL_1050: {
        "label": "SmartLiving 1050 / 1050L compatible",
        "max_zones": 50,
        "max_areas": 10,
        "max_scenarios": 30,
        "max_keyboards": 10,
        "max_readers": 20,
        "area_names_start": 0x0000,
        "zone_names_start": 0x00A0,
        "keyboard_names_start": 0x0B40,
        # Keep the 1050-compatible scenario offset used by the original integration.
        "reader_names_start": 0x1310,
        "scenario_names_start": 0x1450,
    },
    PANEL_MODEL_10100: {
        "label": "SmartLiving 10100 / 10100L",
        "max_zones": 100,
        "max_areas": 15,
        "max_scenarios": 30,
        "max_keyboards": 15,
        "max_readers": 30,
        # Confirmed on SmartLiving 10100/10100L dump from the test panel:
        # 0x0000..0x00E0 area names, 0x00F0 first zone name.
        "area_names_start": 0x0000,
        "zone_names_start": 0x00F0,
        # 0x13B0 reader 1, 0x1590 keyboard 1, 0x2350 scenario 1.
        "reader_names_start": 0x13B0,
        "keyboard_names_start": 0x1590,
        "scenario_names_start": 0x2350,
    },
}


def get_panel_profile(panel_model: str | None) -> dict[str, int | str]:
    """Return panel profile data, falling back to the 1050-compatible profile."""
    return PANEL_PROFILES.get(panel_model or DEFAULT_PANEL_MODEL, PANEL_PROFILES[DEFAULT_PANEL_MODEL])


def configure_api_for_panel(api: InimAlarmAPI, panel_model: str | None) -> None:
    """Attach selected panel profile limits to an API instance."""
    profile = get_panel_profile(panel_model)
    api.panel_model = panel_model or DEFAULT_PANEL_MODEL
    api.panel_profile = profile
    api.system_max_zones = int(profile["max_zones"])
    api.system_max_areas = int(profile["max_areas"])
    api.system_max_scenarios = int(profile["max_scenarios"])
    api.system_max_keyboards = int(profile["max_keyboards"])
    api.system_max_readers = int(profile["max_readers"])
    _LOGGER.info(
        "Configured Inim API panel profile %s: zones=%s areas=%s scenarios=%s keyboards=%s readers=%s",
        profile["label"],
        api.system_max_zones,
        api.system_max_areas,
        api.system_max_scenarios,
        api.system_max_keyboards,
        api.system_max_readers,
    )


def _memory_read_command(self: InimAlarmAPI, address: int, length: int) -> str:
    """Build a SmartLiving memory read command."""
    command_without_checksum = f"000101{address:04x}{length:04x}"
    return command_without_checksum + self.calculate_checksum(command_without_checksum)


def _read_memory_block(self: InimAlarmAPI, address: int, length: int) -> str | None:
    """Read one memory block and return checksum-stripped data hex."""
    command = _memory_read_command(self, address, length)
    return self._send_command_core(command, expect_specific_response_len=length + 1)


def _read_memory_range(self: InimAlarmAPI, start_address: int, total_length: int) -> str | None:
    """Read a memory range in chunks supported by the panel response length."""
    data_parts: list[str] = []
    remaining = total_length
    address = start_address

    while remaining > 0:
        chunk_len = min(remaining, MAX_MEMORY_READ_DATA_BYTES)
        part = _read_memory_block(self, address, chunk_len)
        if part is None:
            _LOGGER.error(
                "Failed to read memory block at 0x%04X length 0x%04X",
                address,
                chunk_len,
            )
            return None
        data_parts.append(part)
        address += chunk_len
        remaining -= chunk_len

    return "".join(data_parts)


def _decode_fixed_names(data_hex: str, count: int) -> list[str]:
    """Decode 16-byte ASCII names from a hex memory block."""
    raw = binascii.unhexlify(data_hex[: count * BYTES_PER_NAME * 2])
    names: list[str] = []
    for index in range(count):
        chunk = raw[index * BYTES_PER_NAME : (index + 1) * BYTES_PER_NAME]
        names.append(chunk.decode("ascii", errors="ignore").strip())
    return names


def _read_profile_names(
    self: InimAlarmAPI,
    start_key: str,
    count_attr: str,
    default_count: int,
    raw_key: str = "raw_hex",
    names_key: str = "names",
) -> dict[str, Any] | None:
    """Read a profile-based fixed-name block."""
    profile = getattr(self, "panel_profile", get_panel_profile(None))
    start = int(profile[start_key])
    count = int(getattr(self, count_attr, default_count))
    length = count * BYTES_PER_NAME

    data_hex = _read_memory_range(self, start, length)
    if data_hex is None:
        return None
    try:
        return {raw_key: data_hex, names_key: _decode_fixed_names(data_hex, count)}
    except Exception as err:
        _LOGGER.error("Error parsing profile names for %s: %s", start_key, err)
        return {raw_key: data_hex, "error": str(err)}


def _profile_get_areas(self: InimAlarmAPI) -> dict[str, Any] | None:
    """Read area names using the selected panel profile area count."""
    return _read_profile_names(
        self,
        start_key="area_names_start",
        count_attr="system_max_areas",
        default_count=InimAlarmConstants.DEFAULT_SYSTEM_MAX_AREAS,
    )


def _profile_get_zones(self: InimAlarmAPI) -> dict[str, Any] | None:
    """Read zone names using the selected profile zone-name offset."""
    return _read_profile_names(
        self,
        start_key="zone_names_start",
        count_attr="system_max_zones",
        default_count=InimAlarmConstants.DEFAULT_SYSTEM_MAX_ZONES,
        raw_key="raw_hex_full",
        names_key="zone_names",
    )


def _profile_get_keyboard_names(self: InimAlarmAPI) -> dict[str, Any] | None:
    """Read keyboard names using the selected profile keyboard count."""
    return _read_profile_names(
        self,
        start_key="keyboard_names_start",
        count_attr="system_max_keyboards",
        default_count=10,
    )


def _profile_get_reader_names(self: InimAlarmAPI) -> dict[str, Any] | None:
    """Read reader names using the selected profile reader count."""
    return _read_profile_names(
        self,
        start_key="reader_names_start",
        count_attr="system_max_readers",
        default_count=20,
    )


def _profile_get_scenarios(self: InimAlarmAPI) -> dict[str, Any] | None:
    """Read scenario names from the selected profile scenario-name offset."""
    return _read_profile_names(
        self,
        start_key="scenario_names_start",
        count_attr="system_max_scenarios",
        default_count=InimAlarmConstants.DEFAULT_SYSTEM_MAX_SCENARIOS,
    )


def _profile_get_areas_status(self: InimAlarmAPI) -> dict[str, Any] | None:
    """Parse live area status for 10-area and 15-area panels."""
    spec = InimAlarmConstants.COMMAND_SPECS["GET_AREAS_STATUS"]
    response_data_hex = self._send_command_core(
        spec["cmd_full"], expect_specific_response_len=spec["resp_len"]
    )
    if not response_data_hex:
        return None

    max_areas = int(getattr(self, "system_max_areas", InimAlarmConstants.DEFAULT_SYSTEM_MAX_AREAS))
    status_bytes_count = min(math.ceil(max_areas / 2), InimAlarmConstants.MAX_AREAS_PAYLOAD // 2)
    area_status_hex = response_data_hex[: status_bytes_count * 2]

    statuses: dict[int, str] = {}
    for byte_idx in range(status_bytes_count):
        byte_val_hex = area_status_hex[byte_idx * 2 : byte_idx * 2 + 2]
        area_in_msn = (byte_idx + 1) * 2
        area_in_lsn = (byte_idx + 1) * 2 - 1
        status_char_msn = byte_val_hex[0]
        status_char_lsn = byte_val_hex[1]

        if area_in_lsn <= max_areas:
            statuses[area_in_lsn] = (
                "armed" if status_char_lsn == InimAlarmConstants.AREA_STATUS_ARMED
                else "disarmed" if status_char_lsn == InimAlarmConstants.AREA_STATUS_DISARMED
                else "unknown"
            )
        if area_in_msn <= max_areas:
            statuses[area_in_msn] = (
                "armed" if status_char_msn == InimAlarmConstants.AREA_STATUS_ARMED
                else "disarmed" if status_char_msn == InimAlarmConstants.AREA_STATUS_DISARMED
                else "unknown"
            )

    triggered_areas: list[int] = []
    if len(response_data_hex) >= 22:
        triggered_byte_val = int(response_data_hex[20:22], 16)
        for area_index in range(min(max_areas, 8)):
            if (triggered_byte_val >> area_index) & 1:
                triggered_areas.append(area_index + 1)

    return {
        "raw_hex": response_data_hex,
        "area_statuses": statuses,
        "triggered_areas": triggered_areas,
    }


def _profile_get_scenario_activations(self: InimAlarmAPI):
    """Parse scenario activations using the selected profile area count."""
    spec = InimAlarmConstants.COMMAND_SPECS.get("GET_SCENARIO_ACTIVATIONS")
    if not spec:
        _LOGGER.error("Command spec for GET_SCENARIO_ACTIVATIONS not found.")
        return None

    response_data_hex = self._send_command_core(
        spec["cmd_full"], expect_specific_response_len=spec["resp_len"]
    )
    if not response_data_hex:
        _LOGGER.error("No response or error when fetching scenario activations.")
        return None

    bytes_per_scenario_activation = 8
    scenario_count = int(getattr(self, "system_max_scenarios", InimAlarmConstants.DEFAULT_SYSTEM_MAX_SCENARIOS))
    max_areas = int(getattr(self, "system_max_areas", 10))
    area_bytes_to_parse = min(math.ceil(max_areas / 2), bytes_per_scenario_activation)
    action_map = {
        InimAlarmConstants.AREA_ACTION_ARM: "arm",
        InimAlarmConstants.AREA_ACTION_DISARM: "disarm",
        InimAlarmConstants.AREA_ACTION_KEEP_STATUS: "keep",
    }

    all_scenario_details = []
    for scenario_index in range(scenario_count):
        offset = scenario_index * bytes_per_scenario_activation * 2
        scenario_activation_hex = response_data_hex[offset : offset + (bytes_per_scenario_activation * 2)]
        if len(scenario_activation_hex) != bytes_per_scenario_activation * 2:
            all_scenario_details.append(
                {
                    "scenario_index": scenario_index,
                    "raw_hex": scenario_activation_hex,
                    "error": "Insufficient data for this scenario block",
                }
            )
            continue

        area_action_hex_part = scenario_activation_hex[: area_bytes_to_parse * 2]
        unknown_part_hex = scenario_activation_hex[area_bytes_to_parse * 2 :]
        parsed_area_actions: dict[int, str] = {}

        for byte_idx in range(area_bytes_to_parse):
            byte_val_hex = area_action_hex_part[byte_idx * 2 : byte_idx * 2 + 2]
            area_num_in_msn_slot = (byte_idx + 1) * 2
            area_num_in_lsn_slot = (byte_idx + 1) * 2 - 1
            action_char_for_msn_slot = byte_val_hex[0]
            action_char_for_lsn_slot = byte_val_hex[1]

            if area_num_in_lsn_slot <= max_areas:
                parsed_area_actions[area_num_in_lsn_slot] = action_map.get(action_char_for_lsn_slot, "unknown")
            if area_num_in_msn_slot <= max_areas:
                parsed_area_actions[area_num_in_msn_slot] = action_map.get(action_char_for_msn_slot, "unknown")

        all_scenario_details.append(
            {
                "scenario_index": scenario_index,
                "raw_activation_hex": scenario_activation_hex,
                "area_actions": parsed_area_actions,
                "unknown_trailing_bytes_hex": unknown_part_hex,
            }
        )

    return all_scenario_details


def _profile_get_initial_panel_configuration(self: InimAlarmAPI):
    """Fetch initial configuration, including profile-aware reader names."""
    with self._api_lock:
        _LOGGER.debug("Lock acquired for profile get_initial_panel_configuration")
        if not self.connect():
            _LOGGER.error("Failed to connect for initial config.")
            return None
        cfg: dict[str, Any] = {"errors": []}
        try:
            methods_to_call = [
                ("system_info", self.get_system_info),
                ("areas", self.get_areas),
                ("zones", self.get_zones),
                ("zones_config", self.get_zones_config),
                ("scenarios", self.get_scenarios),
                ("scenario_activations", self.get_scenario_activations),
                ("keyboard_names", self.get_keyboard_names),
                ("reader_names", self.get_reader_names),
            ]
            for key, method in methods_to_call:
                _LOGGER.debug("Fetching %s...", key)
                cfg[key] = method()
                if cfg[key] is None:
                    cfg["errors"].append(f"Failed {key}.")
                time.sleep(0.1)
        except Exception as err:
            _LOGGER.error("Exception during initial config fetch: %s", err)
            cfg["errors"].append(f"Overall exc: {str(err)}")
        finally:
            self.disconnect()

        if cfg["errors"]:
            _LOGGER.warning("Initial config retrieval completed with errors: %s", cfg["errors"])
        else:
            _LOGGER.info("Initial panel configuration retrieval completed successfully.")
        return cfg


def apply_panel_profile_api_patches() -> None:
    """Apply profile-aware API methods.

    This keeps backwards compatibility because the default profile is 1050-compatible.
    """
    InimAlarmAPI.get_areas = _profile_get_areas
    InimAlarmAPI.get_zones = _profile_get_zones
    InimAlarmAPI.get_keyboard_names = _profile_get_keyboard_names
    InimAlarmAPI.get_reader_names = _profile_get_reader_names
    InimAlarmAPI.get_scenarios = _profile_get_scenarios
    InimAlarmAPI.get_areas_status = _profile_get_areas_status
    InimAlarmAPI.get_scenario_activations = _profile_get_scenario_activations
    InimAlarmAPI.get_initial_panel_configuration = _profile_get_initial_panel_configuration
