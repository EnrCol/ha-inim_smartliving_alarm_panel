# INIM SmartLiving Alarm — v0.3.5b7 (beta)

Unofficial prerelease, based on v0.3.5b6.

## Changes since v0.3.5b6

- **The INIM alarm panel dialog can be opened from any card** with `tap_action: {action: fire-dom-event, inim_alarm_panel: {entity: select.<panel>_scenario}}` (tile, button, Mushroom…). An existing card keeps its look and opens the panel with every scenario instead of the standard alarm dialog. The options are the same as the card's (`name`, `names`, `icons`, `hide`, `confirm`, `show_zones`, `show_time`).

## Validation

- Headless browser: a `fire-dom-event` from another element opens the dialog with the scenario list and the open zones.

## Rollback

Install v0.3.5b6 and restart Home Assistant.
