# INIM SmartLiving Alarm — v0.3.5b2 (beta)

Unofficial prerelease, based on v0.3.5b1.

## Changes since v0.3.5b1

- The card marks as "disarm" the scenario mapped to Disarm in the options (or, without a mapping, the one named DISINSERITO / DISARMED). The per-area actions read from the panel are not reliable on every model: on the reference 10100 they marked TOTALE as a disarm scenario.
- The scenario select uses the device name, so new installations get `select.<panel>_scenario` instead of a doubled panel name. Existing entity IDs are kept by Home Assistant.

## Validation

- Automated tests (63).
- v0.3.5b1 in production on the reference SmartLiving 10100: select options = the 5 programmed scenarios, state = active scenario, alarm state, armed areas and open zones correct; no errors.

## Rollback

Install v0.3.5b1 or v0.3.4 and restart Home Assistant.
