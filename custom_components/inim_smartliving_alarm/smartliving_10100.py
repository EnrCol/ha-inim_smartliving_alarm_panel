"""SmartLiving 10100 protocol compatibility fixes.

On SmartLiving 10100 panels the scenario activation pre-check command returns
27 bytes total: 26 data bytes plus 1 checksum byte.

The original integration expected 14 bytes total. That left 13 zero bytes in
the TCP socket buffer after a successful pre-check. The following scenario
activation command then read one of those leftover zero bytes instead of the
real activation ACK checksum, causing false checksum failures such as
"Received HEX: 00".

Observed locally on 2026-07-07:
- pre-check command: 0000001ff98x0d..
- response: 26 zero data bytes + checksum 00
- after reading only 14 bytes, 13 bytes remained queued in the socket

This module keeps the pre-check enabled and fixes the expected response length
and parser. It replaces the earlier temporary bypass that simply returned True.
"""

from __future__ import annotations

import logging

from .inim_api import InimAlarmAPI, InimAlarmConstants

_LOGGER = logging.getLogger(__name__)


SMARTLIVING_10100_PRECHECK_RESPONSE_LEN = 27


def _check_scenario_activation_allowed_10100(
    self: InimAlarmAPI, scenario_number_0_indexed: int
) -> bool:
    """Check scenario activation using the SmartLiving 10100 response length.

    A valid positive response is made only of zero data bytes. The data length
    is intentionally not hardcoded in the parser, so future panels that return
    a different all-zero data length can still be handled safely as long as the
    command response length is read completely.
    """
    spec_info = InimAlarmConstants.COMMAND_SPECS.get(
        "CHECK_SCENARIO_ACTIVATION_ALLOWED_INFO"
    )
    if not spec_info:
        _LOGGER.error(
            "Command spec for CHECK_SCENARIO_ACTIVATION_ALLOWED_INFO not found."
        )
        return False

    if not (
        0
        <= scenario_number_0_indexed
        < InimAlarmConstants.DEFAULT_SYSTEM_MAX_SCENARIOS
    ):
        _LOGGER.error(
            "Invalid scenario number: %s. Must be 0-%s.",
            scenario_number_0_indexed,
            InimAlarmConstants.DEFAULT_SYSTEM_MAX_SCENARIOS - 1,
        )
        return False

    scenario_command_byte_val = 0x80 + scenario_number_0_indexed
    scenario_command_byte_hex = format(scenario_command_byte_val, "02x")

    seven_byte_cmd_hex = (
        spec_info["cmd_prefix"]
        + scenario_command_byte_hex
        + spec_info["cmd_suffix"]
    )
    cmd_checksum = self.calculate_checksum(seven_byte_cmd_hex)
    eight_byte_cmd_with_checksum = seven_byte_cmd_hex + cmd_checksum

    response_data_hex = self._send_command_core(
        eight_byte_cmd_with_checksum,
        expect_specific_response_len=spec_info["resp_len"],
    )

    if response_data_hex is None:
        _LOGGER.error(
            "No response or error for check_scenario_activation_allowed for scenario %s.",
            scenario_number_0_indexed,
        )
        return False

    if response_data_hex and all(ch == "0" for ch in response_data_hex):
        _LOGGER.info(
            "Scenario %s activation is allowed. Pre-check response length: %s bytes.",
            scenario_number_0_indexed,
            len(response_data_hex) // 2,
        )
        return True

    _LOGGER.info(
        "Scenario %s activation is NOT allowed. Response data: %s",
        scenario_number_0_indexed,
        response_data_hex,
    )
    return False


def apply_smartliving_10100_precheck_fix() -> None:
    """Apply the SmartLiving 10100 pre-check fix at integration startup."""
    spec_info = InimAlarmConstants.COMMAND_SPECS.get(
        "CHECK_SCENARIO_ACTIVATION_ALLOWED_INFO"
    )
    if spec_info is None:
        _LOGGER.error(
            "Cannot apply SmartLiving 10100 pre-check fix: command spec missing."
        )
        return

    spec_info["resp_len"] = SMARTLIVING_10100_PRECHECK_RESPONSE_LEN
    InimAlarmAPI.check_scenario_activation_allowed = (
        _check_scenario_activation_allowed_10100
    )

    _LOGGER.info(
        "Applied SmartLiving 10100 scenario pre-check fix: expected response length %s bytes.",
        SMARTLIVING_10100_PRECHECK_RESPONSE_LEN,
    )
