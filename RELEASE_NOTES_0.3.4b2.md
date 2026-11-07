# INIM SmartLiving Alarm — v0.3.4b2 (beta)

Based on v0.3.4b1. Unofficial beta; no change to INIM protocol commands or panel programming.

## Changes
- Show only programmed scenario names in the setup and options selectors, with their real, zero-based INIM indexes. Placeholder entries and unprogrammed slots are excluded.
- On initial SmartLiving 10100 setup, suggest actual area/zone/scenario limits derived from the panel rather than the hardware maxima (expected on the reference panel: 5 areas, 19 zones through Z032, 5 scenarios).
- No longer guess `Home` from ambiguous site-specific names such as `SOLO P.T.`. Explicit names `HOME` or `ARMED HOME` remain eligible. Present exact, uniquely recognizable standard mapping suggestions in the setup form.
- Treat a mapping key explicitly set to `None` as a manual choice, rather than silently replacing it during runtime auto-import. Existing configured nonempty mappings remain unchanged.
- An active scenario not mapped to an HA arm mode is reported as `unknown` in `alarm_control_panel` instead of falsely presenting `armed_custom_bypass`. Missing scenario reads no longer imply `disarmed`. Triggered areas retain highest priority.
- Introduce a separate read-only binary sensor `Any Area Armed` based on programmed area status. `on` means at least one area is armed, `off` requires all programmed areas to be verified disarmed, and `unknown` represents incomplete or unavailable data. No new physical command is sent.
- Avoid warning messages every 2-second polling cycle for an otherwise valid scenario missing an HA mapping; log only meaningful alarm state transitions.
- Reduce API log amplification during normal 2-second polling: omit routine TCP connect/disconnect messages and raw HEX frames (which could disclose payload/PIN), and log compact event batches only when nonempty. Communication errors and real actions remain logged.
- Extend automated regression tests for scenario choices, manual override preservation, missing data, unknown scenarios, triggered precedence, tri-state area status, quiet polling and retained connection failures.

## Validation
- Clean installation on isolated Home Assistant TEST (SmartLiving 10100 firmware 6.09) confirmed 5 programmed areas, 19 zones, 5 scenarios, 18 writable zone switches (Z011 excluded), and no unavailable entities.
- `Home -> SOLO SEMINT. (index 2)` read back as `armed_home`; temporarily removing only the Home mapping produced `unknown` (not `disarmed`) while the independent area sensor stayed `on`; original mapping restored.
- Final logging fix `9af1190a` installed and loaded after restarting the isolated TEST. Repeated compact-event pointer/no-change DEBUG messages were absent across subsequent polling cycles; the only `inim_api` messages observed were two one-time INFO lines for the initial 50-event history load. No INIM warning or error appeared.
- CI for `9af1190a`: 15 Python tests passed; HACS and hassfest successful. Production and the panel's programmed scenarios remain unchanged.

## Known limitations
- Integration and Marketplace icons are visible in the HA TEST interface after clean setup; no PNG replacement was needed. This is a TEST observation, not proof of every HACS frontend/installation.
- Logging was validated on the reference TEST instance; other hardware models and installations have not been evaluated for log volume.
- PR #12 from scorbacella (active-scenario read mask), OC1/OC2, Z011 output handling, and unknown compact event action codes are excluded.
- Only SmartLiving 10100 firmware 6.09 is available for physical validation; 505/515 and 1050 hardware is not tested.

## Rollback
Before any TEST installation, record current integration options and working version. Select and reinstall v0.3.4b1 from the beta channel if regression occurs, then reload/restart only with explicit approval. Never use a rollback to send physical alarm commands.
