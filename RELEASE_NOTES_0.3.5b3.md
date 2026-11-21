# INIM SmartLiving Alarm — v0.3.5b3 (beta)

Unofficial prerelease, based on v0.3.5b2.

## Changes since v0.3.5b2

- **Unmapped scenario shown as *Armed custom bypass*** when at least one area is armed ([#29](https://github.com/EnrCol/ha-inim_smartliving_alarm_panel/issues/29)). The alarm panel is *unknown* only when the area states are missing; a scenario mapped to a mode keeps that mode.
- **Scenario programming read at the address of each model** (INIM installer software map, `eep_prg_scenari`): 505 `0x3B0A`, 515 `0x42BF`, 1050 `0x73D8` (unchanged), 10100 `0xC81F` with 10-byte records (thanks to claustro, [#28](https://github.com/EnrCol/ha-inim_smartliving_alarm_panel/issues/28)). Until now every model read the 1050 address, so on the 10100 the per-area actions of the scenarios (attribute `area_actions_details` of the scenario buttons) were wrong.
- Initial configuration revision 5 → 6: the panel programming is read again automatically on the first start.

## Validation

- Automated tests (64), including the custom bypass fallback.

## Rollback

Install v0.3.5b2 and restart Home Assistant.
