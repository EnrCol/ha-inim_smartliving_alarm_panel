# INIM SmartLiving Alarm — v0.3.4b8 (beta)

Unofficial prerelease, based on v0.3.4b7. Polling and commands are unchanged.

## Changes since v0.3.4b7

- **Panel model detected automatically at setup.** The model field now defaults to `Automatic (detected from the panel)`: the integration reads the system type the panel reports and stores the matching profile (`10100` → SmartLiving 10100 / 10100L; `1050`, `515`, `505` → 1050-compatible). Unknown types use the 1050-compatible profile and log a warning. Existing entries keep their profile; if it does not match the type the panel reports, a warning is logged at startup.
- **Diagnostics with a read-only copy of the panel memory.** *Download diagnostics* now contains, besides the entry settings (PIN and host removed) and the live state, a copy of the configuration bank (64 KB), the names bank (16 KB) and two live windows. It is meant to work out the memory map of panel models we do not own.
  - Before the file is built the code tables (6-byte records of digits using most of 0-9), runs of 8 or more ASCII digits (dialler telephone numbers) and every occurrence of the configured PIN are overwritten with `0xEE`; the overwritten ranges are listed in the file.
  - Names are kept. The README asks users to check the file before attaching it to a public issue.
  - Reading takes about 40 s and pauses polling; the kept connection is left open afterwards.
- README: setup with automatic model and a "Helping support other panels" section.

## Validation

- 57 automated tests (8 new: model detection from reported types, code / telephone / PIN redaction, small-value configuration tables left intact, memory snapshot reading every block and leaving the kept connection open).
- Isolated Home Assistant TEST with the reference SmartLiving 10100 firmware 6.09:
  - diagnostics downloaded through the API in 40 s, 179 KB, every block read with no unreadable chunk;
  - redacted: user/installer code table (0xA4C6, 618 bytes), three telephone numbers, one 9-digit identifier; the configured PIN does not appear anywhere in the file; the terminal table and zone configuration are intact;
  - polling resumed right after the download (cycles 0.17-0.43 s), no warning or error.
- The automatic model choice is covered by tests with the type reported by the reference panel (`10100`); a new setup through the UI was not repeated on hardware.

## Known limitations

- Redaction is heuristic: it was checked on the 10100 memory only. Names (zones, areas, users) are not removed.
- Only SmartLiving 10100 firmware 6.09 is validated on hardware; 1050/1050L and 505/515 use the original profile and are untested.

## Rollback

Install v0.3.4b7 and restart Home Assistant. Entries created with the automatic model store a concrete profile and stay compatible.
