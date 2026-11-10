Home Assistant Integration for Inim SmartLiving Alarm Systems
=============================================================

> [!WARNING]
> Unofficial custom integration, not developed, endorsed or supported by Inim Electronics. INIM and SmartLiving are trademarks of their owner and are used here only to name the compatible panels. It does not replace the alarm system or its official apps: use it at your own risk.

[![Open in Home Assistant Marketplace](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=EnrCol&repository=ha-inim_smartliving_alarm_panel&category=integration)

**Version 0.3.4** ([release notes](RELEASE_NOTES_0.3.4.md)). Local control of Inim SmartLiving panels through the SmartLAN/SI network interface: areas, zones, scenarios, outputs and event log. The panel model, names, terminals and outputs are read from the panel, so no manual mapping is needed.

Compatibility
-------------

| Panel | Firmware | Status |
| --- | --- | --- |
| SmartLiving 10100 / 10100L | 6.09 | **Verified on a real installation**: every feature, including scenarios, zone exclusion and output commands. |
| SmartLiving 1050 / 1050L | 6.07 | **Verified on a real installation**: automatic setup, names, areas, zones, scenarios, live states and outputs list. Zone exclusion keeps the method of the original integration. |
| SmartLiving 515 | 6.x | Expected to work: name pointers and scenario pre-check confirmed by another user ([matteoraf#18](https://github.com/matteoraf/ha-inim_smartliving_alarm_panel/pull/18)). Not tested here. |
| SmartLiving 505 | 6.x | Expected to work from the official memory map; not tested. |

Firmware 5.10 and 6.x share the same memory map. Older firmware is not supported. Owners of untested panels can help: see [Helping support other panels](#helping-support-other-panels).

**Home Assistant 2025.10 or later** is required.

Features
--------

* **Alarm control panel**: `arm_home`, `arm_away`, `arm_night`, `arm_vacation` and `disarm` mapped to panel scenarios. Scenarios named `TOTALE`, `DISINSERITO`, `NOTTE`, `VACANZA` (and the English equivalents) are mapped automatically.
* **Areas**: one switch per area (arm/disarm) and one alarm sensor. A sensor *Any area armed* is on when at least one area is armed.
* **Zones**: open/closed sensor, alarm memory sensor and exclusion switch for every programmed zone. Placeholder slots (`AREA 007`, `SCENARIO 010`, empty names) are not created.
* **Scenarios**: one button per scenario, an *active* sensor per scenario and a sensor with the name of the active scenario.
* **Outputs**: switches for relay, OC1, OC2 and every terminal programmed as an output, named after the panel programming.
* **Event log**: last panel events with readable descriptions, users and readers.
* **Panel information**: firmware version and system type.
* **Reconfigure** and **diagnostics** built in.

Prerequisites
-------------

* An Inim SmartLiving panel with a SmartLAN/SI module reachable from Home Assistant.
* IP address and TCP port of the module (usually `5004`).
* A user PIN. Commands are accepted only for the areas, scenarios and outputs that PIN is allowed to use.

Installation
------------

### HACS / Marketplace

1. Open HACS (*Marketplace* in recent Home Assistant versions).
2. ⋮ → **Custom repositories** → `https://github.com/EnrCol/ha-inim_smartliving_alarm_panel`, type **Integration**.
3. Open **INIM SmartLiving Alarm (unofficial)** and download it.
4. Restart Home Assistant.

Beta versions are published as prereleases: enable *Show beta versions* on the repository to receive them.

### Manual installation

Copy `custom_components/inim_smartliving_alarm` into `config/custom_components` and restart Home Assistant.

Setup
-----

*Settings → Devices & services → Add integration → Inim Smartliving Alarm*, then enter:

* **Host** and **Port** of the SmartLAN module;
* **PIN**;
* **Panel model**: leave **Automatic**. The integration reads the type the panel reports and picks the matching profile;
* **Panel name**: used for the entity IDs (default `Inim Smartliving`).

The integration then reads the panel programming (about 30 seconds) and proposes:

* **Fast polling interval** (1-300 s, default 2 s): zones, areas, active scenario.
* **Slow polling interval** (1-300 s, default 10 s): zone exclusions, alarm memory, outputs, event log.
* **Areas / zones / scenarios to import**: set from the last programmed slot.
* **Event log size** and optional **reader names** (read from the panel when available).
* **Scenario mapping** for the Home Assistant alarm modes. Only programmed scenarios are listed. Scenarios with unambiguous names are preselected; the others are left for you to choose.

How it works
------------

### Names

The panel publishes in RAM (`0x4014`-`0x4029`) where each table of names starts: areas, zones, readers, keyboards, scenarios and outputs. The integration reads the names there, so they are right on every model and firmware, and limits each table to the room before the next one. If a pointer cannot be read, the fixed address of the panel profile is used. Technique from [matteoraf#18](https://github.com/matteoraf/ha-inim_smartliving_alarm_panel/pull/18).

### Terminals, zone exclusion and outputs

The exclusion and output commands do not use the zone number but the physical terminal. At setup the integration reads, at the addresses of the INIM installer software memory map, the terminal table and the type of each terminal:

| Model | Logical terminals | Terminal table | Terminal records |
| --- | ---: | ---: | ---: |
| 505 | 10 | `0x3DE0` (40) | `0x2971` |
| 515 | 20 | `0x4595` (70) | `0x306F` |
| 1050 | 50 | `0x78FD` (130) | `0x57D4` |
| 10100 | 100 | `0xCF75` (240) | `0x90CD` |

Terminals programmed as outputs get an output switch instead of an exclusion switch. On the 10100 the exclusion switches use this table; 505/515/1050 keep the indexes of the original integration until the table is confirmed by an exclusion test on one of them.

Output commands write the PIN, the output index and the state at `0x2007`; the result is read at `0x2004`. The state of every output comes from register `0x2003`. Terminal outputs on control panel terminals T1-T3 are not exposed: their command index is the same as relay/OC1/OC2.

### Polling and the SmartLAN connection

The SmartLAN module accepts **one TCP client at a time** and delays a new connection by about 2 seconds after the previous one closes. The integration reads everything over a single connection per cycle and, with a fast interval of 10 s or less, keeps it open between cycles. Commands reuse the same connection, so the new state appears after about one second.

While Home Assistant holds the connection, other local clients (for example the INIM installer software) cannot connect: disable the integration, or set the fast interval above 10 s, before a programming session. The INIM cloud app keeps working.

Entities
--------

Entities are grouped under one device and named after the panel programming. With the default panel name:

* `alarm_control_panel.inim_smartliving`: alarm keypad.
* `sensor.inim_smartliving_active_scenario`, `sensor.inim_smartliving_event_log`, `sensor.inim_smartliving_firmware_version`, `sensor.inim_smartliving_system_type`.
* `button.inim_smartliving_scenario_N`: activate scenario N (numbers start from 0 in the order programmed on the panel), plus a binary sensor *active* per scenario.
* Areas: a switch (on = armed) and a binary sensor for the area alarm; *Any area armed* binary sensor.
* Zones: a binary sensor (on = open), a binary sensor for the alarm memory and a switch (**on = zone active, off = excluded**).
* Outputs: one switch per output. The relay is disabled by default because it usually drives the main siren.

The entity IDs of areas, zones and outputs depend on the names and on the Home Assistant area the device is in: look them up under *Settings → Devices & services → Inim Smartliving*.

Example card
------------

[`Examples/inim_card.yaml`](Examples/inim_card.yaml) is a ready card made of built-in cards only (no HACS cards): alarm keypad, active scenario, a summary of armed areas, open, excluded and alarmed zones and active outputs, and scenario buttons with a confirmation. *Dashboard → Edit → Add card → Manual*, then paste the file. The summary finds the entities of the integration by itself; if your panel is not called `Inim Smartliving`, change the other entity IDs.

[`Examples/alarm_dashboard.yaml`](Examples/alarm_dashboard.yaml) is the richer dashboard of the original project, based on `custom:button-card`.

Options, reconfigure and refresh
--------------------------------

* **Configure** (*Settings → Devices & services → Inim Smartliving → Configure*): polling intervals, import limits, event log, scenario mapping, PIN, memory copy in diagnostics. The stored PIN is never shown; leave the field empty to keep it.
* **Refresh initial panel config** (in Configure): reads names, scenarios, terminals and outputs again after a change in the panel programming. It also happens automatically after an update that changes how the panel is read.
* **Reconfigure** (*⋮ → Reconfigure*): changes host, port, PIN or model and reads the panel again without removing the integration. Use it after upgrading from an old version or when the module IP changes.

Helping support other panels
----------------------------

Support for panels that cannot be tested here is built from data sent by their owners:

1. *Configure* → enable **Include a copy of the panel memory in diagnostics**.
2. *⋮ → Download diagnostics*. It takes about 40 seconds and polling pauses meanwhile.
3. The file contains the entry settings (without PIN and host), the live state and a read-only copy of the panel memory. Before the file is built, user and installer codes, telephone numbers and every occurrence of the configured PIN are overwritten.
4. Names (zones, areas, users, contacts) are kept because they are needed to map the memory. **Do not attach the file to a public issue**: open an issue with model and firmware and ask where to send it privately.
5. Disable the option again afterwards.

Without the option, diagnostics contain only the settings, the panel information and the live state.

Troubleshooting
---------------

### Cannot connect / connection timed out

* Check host, port and that Home Assistant can reach the module (firewall, VLAN).
* Make sure no other local client (installer software, another Home Assistant) holds the single SmartLAN connection.

### A command is refused

* The PIN must be allowed to use that area, scenario or output.
* A scenario is refused when a zone of its areas is open.

### Names are wrong, missing or stale

Run **Refresh initial panel config** from *Configure*, or **Reconfigure**. A zone without a name on the panel is not created: give it a name in the panel programming.

### Entities do not update

* Check the logs for `custom_components.inim_smartliving_alarm`.
* With debug logging, `Finished fetching … in X seconds` shows the duration of each cycle.

Credits
-------

Based on [matteoraf/ha-inim_smartliving_alarm_panel](https://github.com/matteoraf/ha-inim_smartliving_alarm_panel), with contributions from its forks. Memory maps verified against the INIM installer software and real panels.

Contributions and bug reports are welcome: include panel model, firmware, Home Assistant logs and, for new models, the diagnostics file sent privately.
