# INIM SmartLiving Alarm — v0.3.4b10 (beta)

Unofficial prerelease, based on v0.3.4b9. Polling, commands and entities are unchanged.

## Changes since v0.3.4b9

- Diagnostics also contain the live window `0x4000`-`0x403F` (system info string and the pointers to the tables of names) and the output state register `0x2003`, plus the name pointers read at setup. They let names and outputs of panels we do not own be checked from the diagnostics file alone.

## Validation

- Automated tests (diagnostics snapshot reads every block, kept connection left open).
- Isolated Home Assistant TEST with the reference SmartLiving 10100 firmware 6.09: diagnostics downloaded in 40 s, every block read with no unreadable chunk; the new window holds "6.09 10100" and the pointers (zones 0x00F0, outputs 0x26A0), the register 0x2003 the live output state (OC1, OC2, sectional door on).

## Rollback

Install v0.3.4b9 and restart Home Assistant.
