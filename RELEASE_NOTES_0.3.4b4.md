# INIM SmartLiving Alarm — v0.3.4b4 (beta)

Unofficial prerelease, based on v0.3.4b3 with the active-scenario read-mask fix from merged PR #16. No new physical-control commands, panel programming changes, or command optimizations are introduced in this release.

## Changes since v0.3.4b3

- **Active-scenario read mask derived from the number of areas**, instead of the fixed `0x007F` (areas 1–7). This avoids misidentifying scenarios that differ only in area 8 or above.
- The mask covers `max(7, configured area limit)`, capped at the maximum for the panel profile. For up to seven configured areas, the transmitted read command is unchanged. A profile with 10 configured areas uses `0x03FF`, and a profile with 15 areas uses `0x7FFF`.
- The command checksum is generated from the calculated mask. PR #16 adds regression tests for the mask, checksum, captured example commands and limit rule.
- Keep the v0.3.4b3 changes: one persistent TCP connection when fast polling is ≤10 s; fast status reads for zones, areas and scenario; configurable slower reads for exclusions, alarm memory and compact events; fast interval can be set to 1 s.
- Manifest, Marketplace release notes and README updated to v0.3.4b4.

## Verification and limits

- The mask variants were checked by read-only commands against the reference SmartLiving 10100 (firmware 6.09). With area 2 armed, masks `0x007F`, `0x001F`, `0x0002`, `0x7FFF` returned scenario 2; mask `0x0001` returned scenario 0. These observations and the automated tests are documented in PR #16.
- No hardware validation has been performed on 505/515, 1050/1050L or panels with more than seven programmed areas. They remain unverified even though the mask logic has tests.
- The integration remains a beta, not a substitute for the certified alarm panel.
- The SmartLAN accepts a single local TCP client. With fast polling ≤10 s, Home Assistant may prevent a second local programming client from connecting; temporarily disable this integration before installer access.
- Previously observed: after a Home Assistant command the panel state may take approximately 3.5 s to appear because the command closes the TCP connection. Reducing this delay has **not** been implemented.
- The command index for zone Z011, outputs OC1/OC2 and undecoded compact event action codes are not addressed by this release.
- For long-term testing, collect timestamps, successful/failed polls, reconnections, max latency, and entity availability; a healthy short sample does not prove a 24–48 hour soak.

## Deployment and rollback

- Install `v0.3.4b4` using Home Assistant Marketplace (beta versions enabled), preserving existing config entry and scenario mappings.
- Activate the new code with a Home Assistant restart, after a valid configuration check and with explicit permission for the restart.
- The reference SmartLiving 10100 should continue reporting the same active scenario when five areas are configured; the read command is unchanged at that limit.
- Rollback: install `v0.3.4b3` and restart Home Assistant. The configuration options remain compatible.
