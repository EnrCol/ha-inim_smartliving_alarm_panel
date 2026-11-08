# INIM SmartLiving Alarm — v0.3.4b6 (beta)

Unofficial prerelease, based on v0.3.4b5. No new command is sent to the panel: only one extra memory read.

## Changes since v0.3.4b5

- **Output state sensors (SmartLiving 10100 / 10100L only, read-only).** Three new binary sensors, on = output active:
  - `Output OC1`: bit 0x20 of live memory 0x0750;
  - `Output OC2`: bit 0x40 of live memory 0x0750;
  - `Output Expansion 1 T1`: bit 0x04 of live memory 0x0745. This is terminal T1 of expansion 1 when it is programmed as an output (on the reference panel it drives a sectional door lock while the alarm is armed).
  - Read with one 32-byte memory read (`0x0740`, about 60 ms) during slow polling cycles. Between slow cycles the last value is kept. Other panel models read nothing new.
  - The outputs cannot be switched from Home Assistant: the activation command is not known yet.

## How the positions were found

On the reference SmartLiving 10100 firmware 6.09, the whole live memory (0x0000-0xFFFF) was read before and after switching each output from the INIM app. For each output, the only consistent change was that bit, and it returned to its original value when the output was switched back. Checked also with the NOTTE scenario, which switches OC1 off, OC2 on and activates expansion 1 T1.

## Validation

- 48 automated tests (3 new: parsing of the reference captures, read only during full cycles on 10100, no read on other profiles).
- Isolated Home Assistant TEST with the reference panel: disarmed panel read as OC1 on, OC2 off, expansion 1 T1 off; OC2 switched on from the INIM app read as on within the slow interval, then off again. No warning or error in the log.

## Known limitations

- Bit positions are confirmed only on SmartLiving 10100 firmware 6.09. Other firmware may use a different memory layout.
- The OC1/OC2 polarity is the panel's own "active" state; how it maps to the physical relay depends on the installation.
- The SmartLAN accepts a single TCP client; long-running behaviour at 1 s is still being observed; zone Z011 is not excludable on the reference panel because its terminal is an output.

## Rollback

Install v0.3.4b5 and restart Home Assistant. The three output entities become unavailable and can be removed.
