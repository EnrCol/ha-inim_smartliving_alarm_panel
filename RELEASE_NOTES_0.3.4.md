# INIM SmartLiving Alarm — v0.3.4

First stable release since v0.3.2. It collects the betas v0.3.4b1-b10. **Requires Home Assistant 2025.10 or later.**

## Compatibility

- SmartLiving 10100 / 10100L, firmware 6.09: verified on a real installation, every feature.
- SmartLiving 1050 / 1050L, firmware 6.07: verified on a real installation (automatic setup, names, areas, zones, scenarios, live states, outputs list).
- SmartLiving 515 / 505: expected to work from the official memory map, not tested.

## Highlights since v0.3.2

- **Automatic setup on every model.** The panel model, the names (from the pointers the panel publishes), the terminal table and the outputs are read from the panel. Placeholder areas, zones and scenarios are not created, and scenarios with unambiguous names are mapped to the alarm modes.
- **Output switches** for relay, OC1, OC2 and terminals programmed as outputs, with live state. The relay is disabled by default.
- **Zone exclusion on the 10100** uses the terminal table read from the panel; outputs are not offered as zones.
- **Faster and lighter polling.** One connection per cycle, kept open with a fast interval of 10 s or less; fast cycles for zones, areas and scenario, slow cycles for exclusions, alarm memory, outputs and events; the state is read about one second after a command.
- **Reconfigure** (*⋮ → Reconfigure*) to read the panel again, or change host, port, PIN or model, without removing the integration.
- **Alarm states**: an active scenario not mapped to an alarm mode is `unknown` instead of a wrong state; areas armed in partial or instant mode are armed; new *Any area armed* sensor.
- **Security**: the stored PIN is never shown in the options; raw frames, which could contain the PIN, are no longer logged.

## Changes since v0.3.4b10

- The copy of the panel memory in diagnostics is added only when the new option **Include a copy of the panel memory in diagnostics** is enabled (default off). Without it, diagnostics hold settings, panel information and live state, and take a moment instead of about 40 seconds.
- Minimum Home Assistant version set to 2025.10 in `hacs.json`, the first one with the service helper API the integration uses.
- The icon derived from the INIM logo is replaced by a neutral shield with a keyhole: the INIM mark is no longer used.
- New example card `Examples/inim_card.yaml` with built-in cards only; README rewritten.

## Upgrade

From v0.3.2 or an older beta: update, restart Home Assistant, then *⋮ → Reconfigure* (PIN empty keeps the stored one). The read-only output sensors of b6-b8 are removed automatically: the output switches carry the same state.

## Rollback

Install v0.3.4b10 (or v0.3.2) and restart Home Assistant.
