# INIM SmartLiving Alarm — v0.3.5b1 (beta)

Unofficial prerelease, based on v0.3.4. Requires Home Assistant 2025.10 or later.

## Changes since v0.3.4

- **INIM alarm panel card** (`custom:inim-alarm-panel`), served and registered by the integration itself: an alarm panel in the style of the Home Assistant one with one button per programmed scenario and its real name, alarm state (disarmed / armed / alarm), active scenario and open zones. A scenario is activated with a second tap to confirm. Scenarios can be hidden, renamed or given an icon from the card configuration.
- **Scenario select** `select.<panel>_scenario`: options = programmed scenarios, state = active scenario, selecting an option activates it. Its attributes (scenario list, alarm state, armed areas, open zones) feed the card.
- **Sixth alarm mode**: a scenario can be mapped to *Arm custom bypass* in the options, so up to six scenarios (disarm + five arm modes) are available in the standard alarm panel.

## Validation

- Automated tests (63), including the custom bypass mapping and the select summary (alarm state, armed areas, open zones).

## Rollback

Install v0.3.4 and restart Home Assistant.
