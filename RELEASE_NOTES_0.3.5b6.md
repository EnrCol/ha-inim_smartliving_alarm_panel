# INIM SmartLiving Alarm — v0.3.5b6 (beta)

Unofficial prerelease, based on v0.3.5b5.

## Changes since v0.3.5b5

- **Compact mode for the INIM alarm panel card** (`compact: true`, also in the visual editor): the card takes one row like a tile (alarm icon, name, active scenario and state) and a tap opens the full panel in a dialog, like the Home Assistant more-info dialog: a bottom sheet on phones, a centred window on wider screens. It closes with the X, a tap outside or Esc.
- The full card is a little smaller (headline and buttons).

## Validation

- Rendered in a headless browser: compact row and open dialog at phone width.

## Rollback

Install v0.3.5b5 and restart Home Assistant (clear the browser cache to load the previous card).
