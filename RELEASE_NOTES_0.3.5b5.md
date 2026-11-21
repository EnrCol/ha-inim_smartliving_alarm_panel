# INIM SmartLiving Alarm — v0.3.5b5 (beta)

Unofficial prerelease, based on v0.3.5b4.

## Changes since v0.3.5b4

- **INIM alarm panel card redrawn in the style of the Home Assistant alarm panel dialog**: header with the alarm icon and name (tap opens the entity), active scenario in large type with the state and "x minutes ago" underneath, and a vertical column of pill buttons, one per scenario, the active one filled with the Home Assistant alarm colour (armed green, disarmed grey, alarm red and blinking). Light and dark themes follow the Home Assistant variables.
- The active scenario cannot be pressed again; a second tap still confirms the others.
- New option `show_time` (default on).

## Validation

- Rendered in a headless browser with light and dark themes.

## Rollback

Install v0.3.5b4 and restart Home Assistant (clear the browser cache to load the previous card).
