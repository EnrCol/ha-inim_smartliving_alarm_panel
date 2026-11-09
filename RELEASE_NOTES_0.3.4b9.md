# INIM SmartLiving Alarm — v0.3.4b9 (beta)

Unofficial prerelease, based on v0.3.4b8.

## Changes since v0.3.4b8

- **Output switches, on every model.** Relay, OC1, OC2 and every terminal programmed as an output become switches, named after the panel programming. The relay is disabled by default (it usually drives the main siren).
  - Command: write 8 bytes at `0x2007` (PIN + output index + state), result read from `0x2004`. Index 0/1/2 = relay/OC1/OC2, terminal outputs use their physical terminal.
  - State: register `0x2003` read with a longer length; the layout depends on the number of logical terminals of the model (10/20/50/100). Read in slow cycles and right after a command.
  - Terminal outputs on control panel terminals T1-T3 are not exposed: their index is the same as relay/OC1/OC2.
  - The read-only output sensors of b6-b8 (`binary_sensor.*_output_oc1`, `_oc2`, `_expansion_1_t1`) are removed: the switches carry the same state.
- **Names found by the panel itself.** Areas, zones, readers, keyboards, scenarios and output names are read at the address the panel publishes in RAM (`0x4014`-`0x4029`), with each table limited to the room before the next. Technique from [matteoraf#18](https://github.com/matteoraf/ha-inim_smartliving_alarm_panel/pull/18) (tested there on a 515). Fixed profile addresses remain as fallback.
- **Terminal tables for every model** from the memory map of the INIM installer software (505, 515, 1050, 10100; same for firmware 5.10 and 6.x). Terminal type read from the official terminal record (byte 11: 1 or 2 = output), replacing the table deduced by hand on the 10100. The 10100 terminal table is now read in full (240 terminals: control panel, 40 expansions, keypads).
- **Reconfigure** (*⋮ → Reconfigure*): change host, port, PIN or model and read the panel again without removing the integration, for installations made with older versions. It pauses the integration during the read (the panel accepts one connection at a time) and restores it on error.
- **Areas armed in partial (2) or instant (3) mode** are reported as armed instead of unknown ([matteoraf#14](https://github.com/matteoraf/ha-inim_smartliving_alarm_panel/issues/14)).
- **Scenario pre-check answer length per model** (10100: 27, 1050: 14, 515: 7 per matteoraf#18; 505 assumed like the 515).
- Home Assistant compatibility: `async_extract_entity_ids(call)` without the removed `hass` argument (upstream fix 9d00d33).
- Diagnostics include the output list and the resolved hardware model.

## Validation

- 60 automated tests (new: output state layout per model, state parsing from the reference reads, output command frame, terminal records, output list, model key, names at the panel pointer).
- Reference SmartLiving 10100 firmware 6.09:
  - output command with the owner present: OC2 off and on (index 2), panel result `00`, nothing else changed;
  - isolated Home Assistant TEST, upgrade from an entry made with b7: initial config refreshed automatically (revision 5), same 18 zone exclusion indexes, terminal 10 recognised as output from the official record, old output sensors removed, switches SIRENA INT / TAPPARELLE / SEZIONALE with the panel names and the right state;
  - TAPPARELLE switched off and on from Home Assistant, state updated within 3 s;
  - Reconfigure with the integration running: panel read again, entry reloaded with the same entities;
  - RAM pointers `0x4014`-`0x4029` read: all match the name offsets found by hand.

## Known limitations

- Only a SmartLiving 10100 firmware 6.09 is validated on hardware. On 505/515/1050 outputs and names follow the official memory map and matteoraf#18, but are not confirmed on hardware by this fork.
- Firmware older than 5.10 is not supported (names in another memory area, shorter reads).

## Rollback

Install v0.3.4b8 and restart Home Assistant; the old configuration is read again automatically.
