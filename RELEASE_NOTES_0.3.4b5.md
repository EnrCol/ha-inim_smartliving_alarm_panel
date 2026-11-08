# INIM SmartLiving Alarm — v0.3.4b5 (beta)

Unofficial prerelease, based on v0.3.4b4. INIM protocol commands, panel programming and command payloads are unchanged; only how commands use the TCP connection changes.

## Changes since v0.3.4b4

- **Faster state after a command.** With a fast polling interval of 10 s or less, commands sent from Home Assistant (arm/disarm areas, scenarios, zone exclusion, area alarm reset) reuse the connection kept open by polling and leave it open when they succeed. Previously every command closed the connection and the SmartLAN delayed the next read by about 2 s, so the new state appeared after about 3.5 s; it now appears after about 1 s.
  - A kept connection idle for more than 12 s is reopened before a command, so a command is never written to a socket the panel has already dropped.
  - Any failed command closes the connection. A scenario activation refused by the panel (for example an open zone) is a valid exchange and keeps it.
  - With a fast interval above 10 s nothing changes: each command opens and closes its own connection.
- **Compact event `0x1E` decoded as "End of Scenario Activated"**, with the scenario that ended (it is logged together with `0x9E` when a new scenario replaces the previous one).

## Validation

- 45 automated tests (6 new: command reuses the kept connection, failed command closes it, idle connection reopened, behaviour without keep-alive unchanged, refused scenario keeps the connection, `0x1E` decoding from a real frame).
- Reference SmartLiving 10100 firmware 6.09, fast 1 s / slow 5 s, production installation:
  - zone 5 excluded: panel log `Zone Excluded` at 16:25:00, state read back in Home Assistant at 16:25:01.2;
  - zone 5 re-included: panel log `End of Zone Excluded` and Home Assistant state both at 16:25:31;
  - no warning or error in the log, polling kept its 1 s cadence.
- Arm/disarm and scenario commands use the same connection path but were not repeated on hardware for this release.

## Known limitations

- **The SmartLAN accepts a single TCP client.** With fast polling ≤10 s other local clients, such as installer programming software, cannot connect. Disable the integration or raise the fast interval above 10 s before a local programming session.
- Long-running behaviour at 1 s (24-48 h) is still being observed.
- Only SmartLiving 10100 firmware 6.09 is available for physical validation; 505/515 and 1050/1050L hardware is not tested.
- Zone Z011 command index, outputs OC1/OC2 and other compact event codes (`0x07`/`0x87`, `0x1F`/`0x9F`, `0x08`/`0x88`, `0xC1`) are still undecoded.

## Rollback

Install v0.3.4b4 and restart Home Assistant. Options remain compatible.
