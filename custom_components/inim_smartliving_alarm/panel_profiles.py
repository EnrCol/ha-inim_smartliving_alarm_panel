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

# Setup only: resolved to a concrete model from the type the panel reports.
PANEL_MODEL_AUTO = "auto"
PANEL_MODEL_SETUP_OPTIONS = {
    PANEL_MODEL_AUTO: "Automatic (detected from the panel)",
    **PANEL_MODEL_OPTIONS,
}


def detect_panel_model(system_type: str | None) -> str | None:
    """Map the system type reported by the panel to a profile.

    The panel answers the system info request with e.g. "6.09 10100" (reference
    10100) or "6.07 01050" (example in the original integration). 515 and 505
    use the 1050-compatible profile. Unknown types return None.
    """
    digits = "".join(ch for ch in str(system_type or "") if ch.isdigit()).lstrip("0")
    if digits.startswith("10100"):
        return PANEL_MODEL_10100
    if digits in ("1050", "515", "505"):
        return PANEL_MODEL_1050
    return None


def read_panel_system_info(api: InimAlarmAPI) -> dict[str, Any] | None:
    """Connect, read only the system info (type and firmware), disconnect."""
    with api._api_lock:
        if not api.connect():
            return None
        try:
            return api.get_system_info()
        finally:
            api.disconnect()

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
        # Names of relay, OC1, OC2 (names bank).
        "output_names_start": 0x26A0,
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
    configure_api_hardware(api, None)
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


# Per-model facts from the memory map of the INIM installer software, identical
# for firmware 5.10 and 6.x (verified on a SmartLiving 10100 firmware 6.09):
# - logical_terminals: number of logical terminals (sizes the output state layout);
# - terminal_table: configuration memory, one byte per physical terminal, value =
#   logical terminal (= zone - 1), 0xFF free. The position is the physical index
#   used by the zone exclusion and output commands;
# - physical_terminals: length of that table (control panel, expansions, keypads);
# - terminal_records: configuration memory, 12 bytes per logical terminal; byte 11
#   is the terminal type (1 or 2 = output);
# - precheck_response_len: answer length of the scenario activation pre-check
#   (10100: 27, 1050: 14 as originally implemented, 515: 7 per matteoraf#18;
#   505 assumed like the 515, not verified).
PANEL_HARDWARE: dict[str, dict[str, int]] = {
    "505": {"precheck_response_len": 7, "logical_terminals": 10, "terminal_table": 0x3DE0, "physical_terminals": 40, "terminal_records": 0x2971},
    "515": {"precheck_response_len": 7, "logical_terminals": 20, "terminal_table": 0x4595, "physical_terminals": 70, "terminal_records": 0x306F},
    "1050": {"precheck_response_len": 14, "logical_terminals": 50, "terminal_table": 0x78FD, "physical_terminals": 130, "terminal_records": 0x57D4},
    "10100": {"precheck_response_len": 27, "logical_terminals": 100, "terminal_table": 0xCF75, "physical_terminals": 240, "terminal_records": 0x90CD},
}
TERMINAL_RECORD_SIZE = 12
TERMINAL_RECORD_TYPE_OFFSET = 11
TERMINAL_OUTPUT_TYPES = (1, 2)
# Relay, OC1, OC2: present on every SmartLiving model. The output command uses
# index 0, 1, 2 for them (OC2 = 2 verified on a SmartLiving 10100).
FIXED_OUTPUT_DEFAULT_NAMES = ("Relay", "OC1", "OC2")


def hardware_key(system_type: str | None, panel_model: str | None = None) -> str:
    """Return the PANEL_HARDWARE key for the type the panel reports.

    Falls back to the selected profile when the type is unknown.
    """
    digits = "".join(ch for ch in str(system_type or "") if ch.isdigit()).lstrip("0")
    for key in ("10100", "1050", "515", "505"):
        if digits == key:
            return key
    return "10100" if panel_model == PANEL_MODEL_10100 else "1050"


def configure_api_hardware(api: InimAlarmAPI, system_info: dict[str, Any] | None) -> None:
    """Attach the hardware facts of the reported panel type to the API."""
    key = hardware_key((system_info or {}).get("type"), getattr(api, "panel_model", None))
    api.panel_hardware_key = key
    api.panel_hardware = PANEL_HARDWARE[key]
    api.logical_terminals = PANEL_HARDWARE[key]["logical_terminals"]


def build_zone_command_indexes(
    terminal_table: bytes, terminal_types: bytes | None = None
) -> tuple[dict[int, int], dict[int, int]]:
    """Map zone number (1-based) -> physical terminal index.

    ``terminal_table`` has one byte per physical terminal: the position is the
    index used by the zone exclusion command 0x2009 and by the output command
    0x2007, the value is zone - 1 (0xFF = free). Terminals are numbered:
    central T1-T10 = 0-9, then expansion n terminal t = 10 + 5 (n - 1) + (t - 1).
    Verified on a SmartLiving 10100 firmware 6.09: the table reproduces all 18
    field-confirmed exclusion indexes.

    ``terminal_types`` has one type byte per logical terminal (zone - 1).
    Terminals programmed as outputs are returned in the second mapping instead.
    """
    indexes: dict[int, int] = {}
    outputs: dict[int, int] = {}
    for command_index, value in enumerate(terminal_table):
        if value == 0xFF:
            continue
        zone = value + 1
        if terminal_types is not None and value < len(terminal_types):
            if terminal_types[value] in TERMINAL_OUTPUT_TYPES:
                outputs.setdefault(zone, command_index)
                continue
        indexes.setdefault(zone, command_index)
    return indexes, outputs


def build_output_list(
    logical_terminals: int,
    fixed_names: list[str] | None,
    output_terminals: dict[int, int],
    zone_names: list[str],
) -> list[dict[str, Any]]:
    """Describe the outputs that can be switched.

    ``bit`` is the position in the output state bits (see
    InimAlarmAPI.get_outputs_status), ``index`` the output command index.
    Terminal outputs at physical index 0-2 would share the command index of a
    fixed output, so they are left out.
    """
    outputs: list[dict[str, Any]] = []
    for j, default in enumerate(FIXED_OUTPUT_DEFAULT_NAMES):
        name = (fixed_names[j] if fixed_names and j < len(fixed_names) else "") or default
        outputs.append({"key": f"fixed_{j}", "index": j, "bit": logical_terminals + j, "name": name})
    for zone, index in sorted(output_terminals.items()):
        if index < len(FIXED_OUTPUT_DEFAULT_NAMES) or zone > logical_terminals:
            _LOGGER.warning("Output terminal of zone %s (index %s) not exposed: ambiguous index", zone, index)
            continue
        name = (zone_names[zone - 1] if zone - 1 < len(zone_names) else "") or f"Terminal {zone}"
        outputs.append({"key": f"terminal_{zone - 1}", "index": index, "bit": zone - 1, "name": name})
    return outputs


def _read_config_memory_range(self: InimAlarmAPI, start_address: int, total_length: int) -> str | None:
    """Read configuration memory (bank 00 01) in panel-sized chunks."""
    parts: list[str] = []
    address = start_address
    remaining = total_length
    while remaining > 0:
        chunk = min(remaining, MAX_MEMORY_READ_DATA_BYTES)
        frame = f"000001{address:04x}{chunk:04x}"
        data = self._send_command_core(
            frame + self.calculate_checksum(frame), expect_specific_response_len=chunk + 1
        )
        if not data or len(data) < chunk * 2:
            _LOGGER.error("Failed to read config memory at 0x%04X length 0x%04X", address, chunk)
            return None
        parts.append(data[: chunk * 2])
        address += chunk
        remaining -= chunk
    return "".join(parts)


def _profile_get_zone_command_indexes(self: InimAlarmAPI) -> dict[str, Any] | None:
    """Read the terminal tables: zone exclusion indexes and output terminals."""
    hardware = getattr(self, "panel_hardware", None)
    if not hardware:
        return None
    table_hex = _read_config_memory_range(
        self, hardware["terminal_table"], hardware["physical_terminals"]
    )
    if table_hex is None:
        return None
    types: bytes | None = None
    records_hex = _read_config_memory_range(
        self,
        hardware["terminal_records"],
        hardware["logical_terminals"] * TERMINAL_RECORD_SIZE,
    )
    if records_hex is None:
        _LOGGER.warning("Terminal records not read; output terminals are not recognised")
    else:
        records = bytes.fromhex(records_hex)
        types = records[TERMINAL_RECORD_TYPE_OFFSET::TERMINAL_RECORD_SIZE]
    indexes, outputs = build_zone_command_indexes(bytes.fromhex(table_hex), types)
    _LOGGER.info(
        "Terminal table read from the panel: zone exclusion indexes %s, output terminals %s",
        indexes,
        outputs,
    )
    # String keys: the config entry is stored as JSON.
    return {
        "zone_command_indexes": {str(zone): index for zone, index in indexes.items()},
        "output_zones": sorted(outputs),
        "output_terminals": {str(zone): index for zone, index in outputs.items()},
        "terminal_table_hex": table_hex,
    }


def _profile_get_output_names(self: InimAlarmAPI) -> list[str] | None:
    """Read the names of the fixed outputs (relay, OC1, OC2) when known."""
    self.fixed_output_count = len(FIXED_OUTPUT_DEFAULT_NAMES)
    result = _read_profile_names(
        self, "output_names_start", "fixed_output_count", len(FIXED_OUTPUT_DEFAULT_NAMES)
    )
    return (result or {}).get("names")


# RAM addresses where the panel publishes, as 16-bit little endian pointers,
# the names-bank address of each table of names (found by JackMagna in
# matteoraf#18 for areas, zones and scenarios; on the reference SmartLiving
# 10100 every pointer matches the address found by hand, plus readers,
# keyboards and fixed outputs). The address of a table depends on model and
# firmware, so reading the pointer makes the names work on any panel.
NAME_POINTER_BLOCK = (0x4014, 0x16)
NAME_POINTERS = {
    "area_names_start": 0x4014,
    "zone_names_start": 0x4016,
    "reader_names_start": 0x401A,
    "keyboard_names_start": 0x401C,
    "scenario_names_start": 0x4024,
    "output_names_start": 0x4028,
}


def _read_name_pointers(self: InimAlarmAPI) -> dict[str, Any]:
    """Read the name table pointers from RAM; empty dict if unreadable."""
    start, length = NAME_POINTER_BLOCK
    frame = f"000000{start:04x}{length:04x}"
    data = self._send_command_core(
        frame + self.calculate_checksum(frame), expect_specific_response_len=length + 1
    )
    if not data or len(data) < length * 2:
        _LOGGER.warning("Name table pointers not read; using the profile addresses")
        return {}
    raw = bytes.fromhex(data[: length * 2])
    values = [int.from_bytes(raw[i : i + 2], "little") for i in range(0, length, 2)]
    pointers = {
        key: values[(address - start) // 2]
        for key, address in NAME_POINTERS.items()
        if values[(address - start) // 2] not in (0x0000, 0xFFFF) or key == "area_names_start"
    }
    # Every pointer of the block bounds the table before it.
    return {"tables": pointers, "all": sorted(set(values))}


def _names_look_valid(names: list[str]) -> bool:
    """At least 80% of the non-empty names must be printable text."""
    filled = [name for name in names if name]
    if not filled:
        return True
    printable = sum(all(32 <= ord(ch) < 127 for ch in name) for name in filled)
    return printable >= 0.8 * len(filled)


def _decode_fixed_names(data_hex: str, count: int) -> list[str]:
    """Decode 16-byte ASCII names from a hex memory block."""
    raw = binascii.unhexlify(data_hex[: count * BYTES_PER_NAME * 2])
    names: list[str] = []
    for index in range(count):
        chunk = raw[index * BYTES_PER_NAME : (index + 1) * BYTES_PER_NAME]
        names.append(chunk.decode("ascii", errors="ignore").strip())
    return names


def _read_names_at(self: InimAlarmAPI, start: int, count: int) -> list[str] | None:
    data_hex = _read_memory_range(self, start, count * BYTES_PER_NAME)
    return _decode_fixed_names(data_hex, count) if data_hex else None


def _read_profile_names(
    self: InimAlarmAPI,
    start_key: str,
    count_attr: str,
    default_count: int,
    raw_key: str = "raw_hex",
    names_key: str = "names",
) -> dict[str, Any] | None:
    """Read a fixed-name block: at the panel's own pointer, else at the profile address.

    With the pointer, the count is limited to the room before the next table,
    so entries of the following table are not taken as names.
    """
    profile = getattr(self, "panel_profile", None) or get_panel_profile(None)
    count = int(getattr(self, count_attr, default_count))
    pointers = getattr(self, "name_pointers", None) or {}
    pointer = (pointers.get("tables") or {}).get(start_key)
    if pointer is not None:
        following = [value for value in pointers.get("all", []) if value > pointer]
        pointer_count = count
        if following:
            pointer_count = max(0, min(count, (following[0] - pointer) // BYTES_PER_NAME))
        if pointer_count:
            names = _read_names_at(self, pointer, pointer_count)
            if names is not None and _names_look_valid(names):
                return {raw_key: None, names_key: names, "address": pointer}
            _LOGGER.warning(
                "Names at the panel pointer 0x%04X for %s not usable; using the profile address",
                pointer,
                start_key,
            )
    start = profile.get(start_key)
    if start is None:
        return None
    try:
        data_hex = _read_memory_range(self, int(start), count * BYTES_PER_NAME)
        if data_hex is None:
            return None
        return {raw_key: data_hex, names_key: _decode_fixed_names(data_hex, count), "address": int(start)}
    except Exception as err:
        _LOGGER.error("Error parsing profile names for %s: %s", start_key, err)
        return None


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
                "armed" if status_char_lsn in InimAlarmConstants.AREA_ARMED_STATUSES
                else "disarmed" if status_char_lsn == InimAlarmConstants.AREA_STATUS_DISARMED
                else "unknown"
            )
        if area_in_msn <= max_areas:
            statuses[area_in_msn] = (
                "armed" if status_char_msn in InimAlarmConstants.AREA_ARMED_STATUSES
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
            methods_to_call.append(("zone_command_indexes", self.get_zone_command_indexes))
            methods_to_call.append(("output_names", self.get_output_names))
            for key, method in methods_to_call:
                _LOGGER.debug("Fetching %s...", key)
                cfg[key] = method()
                if cfg[key] is None:
                    cfg["errors"].append(f"Failed {key}.")
                if key == "system_info":
                    configure_api_hardware(self, cfg[key])
                    self.name_pointers = _read_name_pointers(self)
                    cfg["name_pointers"] = self.name_pointers
                time.sleep(0.1)
            terminals = (cfg.get("zone_command_indexes") or {}).get("output_terminals") or {}
            cfg["outputs"] = build_output_list(
                self.logical_terminals,
                cfg.get("output_names"),
                {int(zone): int(index) for zone, index in terminals.items()},
                (cfg.get("zones") or {}).get("zone_names") or [],
            )
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
    InimAlarmAPI.get_zone_command_indexes = _profile_get_zone_command_indexes
    InimAlarmAPI.get_output_names = _profile_get_output_names
    InimAlarmAPI.get_scenario_activations = _profile_get_scenario_activations
    InimAlarmAPI.get_initial_panel_configuration = _profile_get_initial_panel_configuration
