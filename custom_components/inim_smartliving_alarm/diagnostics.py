"""Diagnostics for the Inim SmartLiving integration.

Besides the usual entry data, the download contains a read-only copy of the
panel memory (configuration and names banks plus two live windows). It lets
the memory map of panel models we do not own be worked out from a file that
any user can attach to an issue.

Security: the PIN is removed from the entry data, and in the memory copy the
user / installer code tables, telephone numbers and every occurrence of the
configured PIN are overwritten before the file is built (see redact_codes).
Names (zones, areas, users) are kept: they are needed to map the memory. Reading the memory takes about 20-30 seconds and pauses polling.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_HOST, CONF_PIN, DATA_API_CLIENT, DATA_COORDINATOR, DOMAIN
from .inim_api import InimAlarmAPI

_LOGGER = logging.getLogger(__name__)

TO_REDACT = {CONF_PIN, CONF_HOST, "pin_code_str"}

# (label, bank selector b1 b2, start, length). Bank "0001" = configuration,
# "0101" = names, "0000" = live memory.
MEMORY_BLOCKS: tuple[tuple[str, str, int, int], ...] = (
    ("config", "0001", 0x0000, 0x10000),
    ("names", "0101", 0x0000, 0x4000),
    ("live_0700", "0000", 0x0700, 0x0100),
    ("live_2000", "0000", 0x2000, 0x0100),
)
CHUNK = 250
REDACTED_BYTE = 0xEE
CODE_RECORD = 6
CODE_TABLE_MIN_RECORDS = 8


def _code_record(record: bytes) -> bool:
    return all(b <= 9 or b == 0xFF for b in record) and sum(b <= 9 for b in record) >= 4


def _looks_like_codes(table: bytes) -> bool:
    """Real codes use most digits; configuration tables of small values do not."""
    digits = [b for b in table if b <= 9]
    records = [table[i : i + CODE_RECORD] for i in range(0, len(table), CODE_RECORD)]
    varied = sum(len({b for b in r if b <= 9}) >= 3 for r in records)
    return len(set(digits)) >= 7 and varied >= 0.3 * len(records)


def redact_codes(data: bytes, pin: str | None) -> tuple[bytes, list[list[int]]]:
    """Overwrite codes, phone numbers and the configured PIN; return the ranges.

    - Code tables: at least CODE_TABLE_MIN_RECORDS consecutive 6-byte records
      made only of digits (one per byte) and 0xFF padding, using most of the
      ten digits. On the reference SmartLiving 10100 the user/installer codes
      are such a table (configuration memory 0xA4C7, 104 records).
    - Runs of 8 or more ASCII digits: telephone numbers of the dialler
      (0x0022, 0x0042, ... on the reference panel) and similar identifiers.
    - The configured PIN wherever it appears (one digit per byte, ASCII, BCD).
    """
    out = bytearray(data)
    ranges: list[list[int]] = []

    def wipe(start: int, end: int) -> None:
        out[start:end] = bytes([REDACTED_BYTE]) * (end - start)
        ranges.append([start, end])

    pos = 0
    while pos + CODE_RECORD * CODE_TABLE_MIN_RECORDS <= len(out):
        count = 0
        while pos + CODE_RECORD * (count + 1) <= len(out) and _code_record(
            bytes(out[pos + CODE_RECORD * count : pos + CODE_RECORD * (count + 1)])
        ):
            count += 1
        end = pos + CODE_RECORD * count
        if count >= CODE_TABLE_MIN_RECORDS and _looks_like_codes(bytes(out[pos:end])):
            wipe(pos, end)
            pos = end
        elif count >= CODE_TABLE_MIN_RECORDS:
            pos = end
        else:
            pos += 1

    pos = 0
    while pos < len(out):
        end = pos
        while end < len(out) and 0x30 <= out[end] <= 0x39:
            end += 1
        if end - pos >= 8:
            wipe(pos, end)
        pos = max(end, pos + 1)

    if pin and pin.isdigit():
        patterns = {bytes(int(c) for c in pin), pin.encode()}
        if len(pin) % 2 == 0:
            patterns.add(bytes.fromhex(pin))
        for pattern in patterns:
            start = out.find(pattern)
            while start >= 0:
                wipe(start, start + len(pattern))
                start = out.find(pattern, start + 1)
    return bytes(out), sorted(ranges)


def _read_block(api: InimAlarmAPI, bank: str, start: int, length: int) -> tuple[bytes, list[int]]:
    """Read one memory block; unreadable chunks are returned as zeros and listed."""
    data = bytearray()
    failed: list[int] = []
    for address in range(start, start + length, CHUNK):
        size = min(CHUNK, start + length - address)
        frame = f"00{bank}{address:04x}{size:04x}"
        if not api._is_connected:
            time.sleep(2.2)  # the SmartLAN delays a connection that follows a closed one
            api.connect()
        response = api._send_command_core(
            frame + api.calculate_checksum(frame), expect_specific_response_len=size + 1
        )
        if response and len(response) >= size * 2:
            data += bytes.fromhex(response[: size * 2])
        else:
            failed.append(address)
            data += bytes(size)
            api.disconnect()
    return bytes(data), failed


def read_memory_snapshot(api: InimAlarmAPI) -> dict[str, Any]:
    """Read the diagnostic memory blocks under the API lock (blocks polling)."""
    started = time.monotonic()
    blocks: dict[str, Any] = {}
    with api._api_lock:
        try:
            if not api._is_connected and not api.connect():
                return {"error": "connection failed"}
            for label, bank, start, length in MEMORY_BLOCKS:
                data, failed = _read_block(api, bank, start, length)
                redacted: list[list[int]] = []
                if label == "config":
                    data, redacted = redact_codes(data, getattr(api, "pin_code_str", None))
                blocks[label] = {
                    "bank": bank,
                    "start": start,
                    "hex": data.hex(),
                    "unreadable_chunks": failed,
                    "redacted_ranges": redacted,
                }
        finally:
            if getattr(api, "keep_connection_open", False) and api._is_connected:
                api._last_io = time.monotonic()
            else:
                api.disconnect()
    return {"seconds": round(time.monotonic() - started, 1), "blocks": blocks}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    api: InimAlarmAPI | None = entry_data.get(DATA_API_CLIENT)
    coordinator = entry_data.get(DATA_COORDINATOR)
    initial = entry.data.get("initial_panel_config") or {}

    memory: dict[str, Any]
    if api is None:
        memory = {"error": "integration not loaded"}
    else:
        try:
            memory = await hass.async_add_executor_job(read_memory_snapshot, api)
        except Exception as err:  # diagnostics must not fail because of the panel
            _LOGGER.warning("Memory snapshot for diagnostics failed: %s", err)
            memory = {"error": str(err)}

    return {
        "entry": {
            "data": async_redact_data(
                {k: v for k, v in entry.data.items() if k != "initial_panel_config"},
                TO_REDACT,
            ),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "panel": {
            "system_info": initial.get("system_info"),
            "panel_model": getattr(api, "panel_model", None),
            "zone_command_indexes": initial.get("zone_command_indexes"),
            "outputs": initial.get("outputs"),
            "hardware": getattr(api, "panel_hardware_key", None),
        },
        "live_data": coordinator.data if coordinator else None,
        "memory": memory,
    }
