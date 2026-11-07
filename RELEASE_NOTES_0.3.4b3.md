# INIM SmartLiving Alarm — v0.3.4b3 (beta)

Based on v0.3.4b2. Unofficial beta. INIM protocol commands, panel programming and physical command payloads are unchanged; only how and how often existing read commands are sent changes.

## Changes
- **One TCP connection per polling cycle.** Live status and compact events are now read over the same connection. On the reference SmartLiving 10100 the SmartLAN interface delays a new connection by about 2 seconds when it follows a just-closed one (measured 2025-2084 ms, while each read command takes about 60 ms), so the previous two-connection cycle took 2.8-3.9 s.
- **Kept-alive connection for fast polling.** With a fast interval of 10 s or less the connection stays open between cycles. Any error closes it and the cycle reconnects once, so a desynchronised stream never carries over. The panel closes idle connections after 15-30 s; the connection is closed on unload.
- **Fast and slow reads.** New option `Slow polling interval` (setup and options, 1-300 s, default 10 s):
  - every fast cycle: zones (doors/windows), areas (armed/alarm) and active scenario — 3 commands, about 0.2 s;
  - every slow cycle: also zone exclusions, zone alarm memory and the event log. Between slow cycles the last values are kept.
  - After a command sent from Home Assistant the next read is always a full one.
- **Minimum fast interval lowered from 2 s to 1 s.** No pause between polling read commands (60 back-to-back cycles at 1 s ran without errors).
- **Quieter logs.** Per-cycle DEBUG lines from the coordinator and the alarm panel entity were removed; Home Assistant's own `Finished fetching … in X seconds` line remains and is useful to measure cycle time.
- **Security: the stored PIN is no longer returned by the options form.** Previously it was pre-filled as a suggested value and visible to anyone opening the options (UI or API). Leave the field empty to keep the current PIN.

## Validation
- Isolated Home Assistant TEST, SmartLiving 10100 firmware 6.09, fast 1 s / slow 5 s: 63/63 cycles successful, mean period 0.997 s (max 1.2 s), light cycles 0.16-0.19 s; about 3.6 commands/s instead of 6. Exclusion switches and alarm-memory sensors kept their values between slow cycles.
- `Home -> SOLO SEMINT. (index 2)` read back as `armed_home`.
- 22 automated tests (5 new for single connection, keep-alive, reconnection, light cycle and slow-read scheduling).
- The INIM mobile app (cloud) kept working while Home Assistant held the local connection.
- Physical commands from Home Assistant with the kept-alive connection, each confirmed by the panel and read back from it:
  - `alarm_arm_home` with the scenario already active: pre-check allowed, acknowledged in 0.21 s;
  - zone 5 excluded and re-included: acknowledged in < 0.2 s, read back as excluded/enabled; panel log shows `Zone Excluded` / `End of Zone Excluded` for zone index 4;
  - `alarm_disarm` then `alarm_arm_home`: `disarmed` with all areas off and `Any Area Armed` off, then back to `armed_home` with only area 2 armed.
  - No warning or error in the log. After a command the state appears in Home Assistant after about 3.5 s, because the command closes the connection and the panel delays the next one by about 2 s.

## Known limitations
- **The SmartLAN accepts a single TCP client.** While the connection is kept open (fast interval ≤ 10 s) other local clients, such as installer programming software, cannot connect. Disable the integration or raise the fast interval above 10 s before a local programming session.
- Long-running behaviour at 1 s (24-48 h) is still being observed on the reference panel.
- Only SmartLiving 10100 firmware 6.09 is available for physical validation; 505/515 and 1050/1050L hardware is not tested.
- PR #12 (active-scenario read mask), OC1/OC2, Z011 command index and unknown compact event action codes are still excluded. Observed but not yet decoded: `0x08` + `0x88` on scenario activation from Home Assistant, `0xC1` about 2 s after each command.

## Rollback
Reinstall v0.3.4b2 from the beta channel. Existing options remain valid; `slow_polling_interval` is ignored by older versions.
