# INIM SmartLiving Alarm — v0.3.4b7 (beta)

Unofficial prerelease, based on v0.3.4b6. No new command is sent to the panel: only two configuration memory reads at setup.

## Changes since v0.3.4b6

- **SmartLiving 10100 / 10100L: zone exclusion indexes read from the panel.** The exclusion command uses the terminal a zone is wired to, not the zone number. Until now the integration used a map written by hand for the reference installation, so on another 10100 a switch could exclude the wrong zone. At setup it now reads:
  - the terminal → zone table (configuration memory `0xCF75`, 130 bytes; position = command index, value = zone − 1, `0xFF` = free);
  - the terminal type table (`0x9252`, 12-byte records): terminals whose type byte is `0x04` (output) get no exclusion switch.
  - If the terminal table cannot be read, the built-in map is used and a warning is logged. If only the type table fails, no terminal is filtered.
- **Automatic refresh.** The initial configuration revision goes from 3 to 4, so existing installations read the tables again on the first start after the update, without reconfiguring.

## Validation

- 52 automated tests (4 new: the reference tables rebuild exactly the 18 field-confirmed indexes and skip the output terminal; behaviour without the type table; config-memory read commands and chunking; no read on the 1050 profile).
- Isolated Home Assistant TEST with the reference SmartLiving 10100 firmware 6.09: on start the stored configuration was refreshed (revision 3 → 4); the panel tables gave exactly the 18 indexes of the built-in map, zone 11 (expansion 1 T1, programmed as an output) was skipped, and 18 exclusion switches were created. No warning or error.

## Known limitations

- The meaning of type byte `0x04` comes from a single terminal on the reference panel, so it is used only to hide a switch, never to create one.
- Memory positions are confirmed only on SmartLiving 10100 firmware 6.09. The 1050/1050L and 505/515 profiles are unchanged and untested on hardware.
- The SmartLAN accepts a single TCP client; long-running behaviour at 1 s is still being observed; outputs are read-only.

## Rollback

Install v0.3.4b6 and restart Home Assistant. The stored configuration keeps the extra data, which older versions ignore.
