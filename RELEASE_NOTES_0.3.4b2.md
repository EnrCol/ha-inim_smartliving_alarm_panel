# INIM SmartLiving Alarm — v0.3.4b2 (beta candidate, NOT published)

Based on v0.3.4b1. This document accompanies a **draft PR only**. No release or Home Assistant deployment is authorized by creating this branch.

## Candidate changes
- Show only programmed scenario names in the setup and options selectors, with their real, zero-based INIM indexes. Placeholder entries and unprogrammed slots are excluded.
- On initial SmartLiving 10100 setup, suggest actual area/zone/scenario limits derived from the panel rather than the hardware maxima (expected on the reference panel: 5 areas, 19 zones through Z032, 5 scenarios).
- No longer guess `Home` from ambiguous site-specific names such as `SOLO P.T.`. Explicit names `HOME` or `ARMED HOME` remain eligible. Present exact, uniquely recognizable standard mapping suggestions in the setup form.
- Treat a mapping key explicitly set to `None` as a manual choice, rather than silently replacing it during runtime auto-import. Existing configured nonempty mappings remain unchanged.
- An active scenario not mapped to an HA arm mode is reported as `unknown` in `alarm_control_panel` instead of falsely presenting `armed_custom_bypass`. Missing scenario reads no longer imply `disarmed`. Triggered areas retain highest priority.
- Introduce a separate read-only binary sensor `Any Area Armed` based on programmed area status. `on` means at least one area is armed, `off` requires all programmed areas to be verified disarmed, and `unknown` represents incomplete or unavailable data. No new physical command is sent.
- Avoid warning messages every 2-second polling cycle for an otherwise valid scenario missing an HA mapping; log only meaningful alarm state transitions.
- Extend automated regression tests for scenario choices, manual override preservation, missing data, unknown scenarios, triggered precedence and tri-state area status.

## Verification before publication
- GitHub Actions Python, HACS and hassfest checks must pass.
- Install only in isolated Home Assistant TEST after explicit approval. Production and the panel's programmed scenarios remain unchanged.
- Confirm original scenario names and indexes, the manual `Home -> SOLO SEMINT. (index 2)` mapping, no false disarmed states, and no recurring unmapped-scenario warnings.
- Confirm the new area-armed sensor from real areas and test unknown read behavior without issuing alarm commands.

## Still open, deliberately NOT silently claimed fixed
- The integration/Marketplace icon was still invisible on both pages with v0.3.4b1; repository PNG files passed structural validation, but the local installation assets and branding endpoint have not yet been verified. Do not publish b2 with a claim that the icon is fixed until that check has been performed.
- Excessive DEBUG logs in the TEST instance may be due to its logging configuration; only the known repeated unmapped-scenario warning is addressed here.
- PR #12 from scorbacella (active-scenario read mask), OC1/OC2, Z011 output handling, and unknown compact event action codes are excluded.
- Only SmartLiving 10100 firmware 6.09 is available for physical validation; 505/515 and 1050 hardware is not tested.

## Rollback
Before any TEST installation, record current integration options and working version. Select and reinstall v0.3.4b1 from the beta channel if regression occurs, then reload/restart only with explicit approval. Never use a rollback to send physical alarm commands.
