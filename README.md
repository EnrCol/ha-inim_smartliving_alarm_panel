Home Assistant Integration for Inim SmartLiving Alarm Systems
=============================================================

> [!WARNING]
> This is an experimental custom component. It is not affiliated with Inim Electronics and it is not an official Inim integration. Use it at your own risk.

![INIM integration brand](custom_components/inim_smartliving_alarm/brand/logo.png)

[![Open in Home Assistant Marketplace](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=EnrCol&repository=ha-inim_smartliving_alarm_panel&category=integration)

**Beta v0.3.4b8.** Independent, unofficial integration; not developed, endorsed or supported by Inim Electronics. The icon is an unofficial visual adaptation of the INIM name and distinctive dot motif.

**Validation scope:** field tests and protocol verification are available only on SmartLiving **10100** (firmware 6.09); 505/515 and 1050/1050L must not be described as hardware-validated. The automatic 10100 entity-import changes in this beta are pending a new real-installation soak test. Never treat a beta as a replacement for the official security system.

**Marketplace updates:** add this repository as a custom Integration repository and enable **beta/prerelease versions** for it to receive `v0.3.4b4`. Stable updates remain separate. Release notes: [v0.3.4b4](RELEASE_NOTES_0.3.4b4.md), [v0.3.4b3](RELEASE_NOTES_0.3.4b3.md), [v0.3.4b2](RELEASE_NOTES_0.3.4b2.md), [v0.3.4b1](RELEASE_NOTES_0.3.4b1.md).

This custom integration connects Home Assistant to Inim SmartLiving alarm panels equipped with a SmartLAN/SI network interface. It allows local monitoring and control of the alarm system from Home Assistant.

Features
--------

* **Alarm control panel entity**

  * Standard Home Assistant alarm actions such as `arm_home`, `arm_away`, `arm_night` and `disarm` can be mapped to panel scenarios.
  * Scenario activation includes a SmartLiving 10100-compatible pre-check implementation.

* **Selectable panel profiles**

  * `SmartLiving 1050 / 1050L compatible`
  * `SmartLiving 10100 / 10100L`

* **Area management**

  * Switch entities for arming/disarming individual areas.
  * Binary sensor entities for area alarm/triggered state.

* **Zone monitoring**

  * Binary sensor entities for live zone status.
  * Binary sensor entities for triggered zones.
  * Extended attributes with zone configuration data when available.
  * Switch entities for individual zone exclusion.

* **Scenario control**

  * Button entities for direct scenario activation.
  * Binary sensor entities for active scenario indication.
  * A dedicated text sensor shows the currently active scenario name.

* **Event log sensor**

  * Stores recent panel events.
  * Event log size is configurable.
  * Reader names can be read automatically on supported profiles, with a manual fallback option.

* **Panel information sensors**

  * Firmware version.
  * System type.

Supported panel profiles
------------------------

The integration keeps a 1050-compatible profile as the default, then applies larger limits and different memory offsets when the 10100 profile is selected.

| Profile | Areas | Zones | Scenarios | Keyboards | Readers | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| SmartLiving 1050 / 1050L compatible | 10 | 50 | 30 | 10 | 20 | Default compatibility profile. |
| SmartLiving 10100 / 10100L | 15 | 100 | 30 | 15 | 30 | Tested with profile-specific name offsets. |

### SmartLiving 10100 / 10100L name map

For the 10100 profile, static names are read from explicit panel-memory offsets:

| Data block | Offset |
| --- | ---: |
| Area names | `0x0000` |
| Zone names | `0x00F0` |
| Reader names | `0x13B0` |
| Keyboard names | `0x1590` |
| Scenario names | `0x2350` |

This avoids common shifted-name symptoms such as:

* first zones appearing as `AREA 011`, `AREA 012`, etc.;
* scenario names appearing as readers or keyboards;
* active scenario `TOTALE` being shown as a reader name.

### SmartLiving 10100 / 10100L zone exclusion

The exclusion command does not use the zone number but the panel terminal that the zone is wired to. At setup the integration reads the panel's terminal table (configuration memory `0xCF75`, 130 bytes) and builds the zone → command index map from it, so zone exclusion switches match each installation's wiring. Terminals programmed as outputs (type table at `0x9252`) get no exclusion switch, because the panel refuses to exclude them. If the table cannot be read, the built-in map of the reference installation is used and a warning is logged.

Prerequisites
-------------

* An Inim SmartLiving alarm control panel.
* A SmartLAN/SI network interface module.
* The SmartLAN module must be reachable from Home Assistant on the local network.
* The panel IP address, TCP port and a valid user PIN.

The common SmartLAN/SI TCP port is `5004`, but this depends on your configuration.

Installation
------------

### HACS custom repository

1. Open HACS in Home Assistant.
2. Go to **Integrations**.
3. Add this repository as a custom integration repository.
4. Install **Inim Smartliving Alarm**.
5. Restart Home Assistant.

### Manual installation

1. Copy `custom_components/inim_smartliving_alarm` into your Home Assistant `config/custom_components` folder.
2. Restart Home Assistant.

Configuration
-------------

After installation and restart:

1. Go to **Settings** -> **Devices & Services**.
2. Click **+ Add Integration**.
3. Search for **Inim Smartliving Alarm**.
4. Enter:

   * **Host**: the IP address of the SmartLAN module.
   * **Port**: the SmartLAN TCP port, usually `5004`.
   * **PIN**: a valid panel PIN.
   * **Panel Model**: leave `Automatic (detected from the panel)` (default): the integration reads the type the panel reports (`10100` → SmartLiving 10100 / 10100L profile; `1050`, `515`, `505` → 1050-compatible profile) and stores that profile. You can still pick one explicitly:

     * `SmartLiving 1050 / 1050L compatible`
     * `SmartLiving 10100 / 10100L`

     If the selected profile does not match the type the panel reports, a warning is logged at startup.

   * **Panel Name**: friendly Home Assistant name for the panel.

5. Click **Submit**. The integration connects to the panel and reads the initial static configuration.
6. Configure initial options:

   * **Fast polling interval** (1-300 s, default 2 s): how often zones (doors/windows), areas and the active scenario are read. 1 s works on the reference SmartLiving 10100.
   * **Slow polling interval** (1-300 s, default 10 s): how often zone exclusions, zone alarm memory and the event log are also read. After a command sent from Home Assistant everything is read immediately.
   * **Limit Areas / Zones / Scenarios**: maximum number of entities to create.
   * **Event Log Size**: number of recent events stored in the event-log sensor.
   * **Reader Names**: optional manual comma-separated fallback for reader names. Supported profiles can read reader names automatically.

7. Configure scenario mappings:

   * **Arm Home**
   * **Arm Away**
   * **Arm Night**
   * **Arm Vacation**
   * **Disarm**

The scenario dropdown is built from the names read using the currently selected panel profile.

Options and refresh behavior
----------------------------

You can change integration options later from:

**Settings** -> **Devices & Services** -> **Inim Smartliving Alarm** -> **Configure**

The options flow is split into two steps:

1. Connection/profile/static options.
2. Scenario mapping options.

### Polling and the SmartLAN connection

The SmartLAN interface accepts **one TCP client at a time** and delays a new connection by about 2 seconds after the previous one closes. The integration therefore reads everything it needs in a polling cycle over a single connection and, with a fast interval of 10 s or less, keeps that connection open between cycles (the panel drops idle connections after 15-30 s).

Commands sent from Home Assistant (arm/disarm, scenarios, zone exclusion, alarm reset) reuse the same kept connection and leave it open when they succeed, so the new state appears after about 1 second instead of waiting for a new connection. A connection idle for more than 12 s is reopened before a command; any error closes it.

While Home Assistant holds the connection, other local clients — for example installer programming software — cannot connect. Disable the integration or set the fast interval above 10 s before a local programming session. On the reference installation the INIM mobile app (cloud) kept working.

The options form never shows the stored PIN; leave the PIN field empty to keep it.

### Refresh initial panel config

The options screen includes a **Refresh Initial Panel Config** checkbox.

Use it when:

* you changed names, scenarios, areas, zones, readers or keyboards on the alarm panel;
* you changed panel model profile;
* you updated the integration and want to force a new static data read;
* scenario dropdowns show stale or shifted names.

The integration also stores an internal `initial_panel_config_revision`. When profile offsets or initial-data parsing change in a new build, the integration automatically refreshes the stored initial configuration during startup. This avoids needing to switch from 10100 to 1050 and back just to force a refresh.

Entities provided
-----------------

Entity IDs are generated from the configured panel name and the names fetched from the panel.

* **Main alarm control panel**

  * `alarm_control_panel.your_panel_name`

* **Areas**

  * `switch.your_panel_name_area_X`
  * `binary_sensor.your_panel_name_area_X_triggered`

* **Zones**

  * `binary_sensor.your_panel_name_zone_X`
  * `binary_sensor.your_panel_name_zone_X_triggered`
  * `switch.your_panel_name_zone_X`

* **Scenarios**

  * `button.your_panel_name_scenario_X`
  * `binary_sensor.your_panel_name_scenario_X_active`

* **Outputs** (SmartLiving 10100 / 10100L only, read-only)

  * `binary_sensor.your_panel_name_output_oc1`
  * `binary_sensor.your_panel_name_output_oc2`
  * `binary_sensor.your_panel_name_output_expansion_1_t1`

  On = output active. Read during slow polling cycles. Outputs cannot be switched from Home Assistant yet: the activation command is not known.

* **Sensors**

  * `sensor.your_panel_name_event_log`
  * `sensor.your_panel_name_active_scenario`
  * `sensor.your_panel_name_firmware_version`
  * `sensor.your_panel_name_system_type`

Usage examples
--------------

### Basic alarm control

Use `alarm_control_panel.your_panel_name` in a standard Home Assistant alarm panel card. The Home Assistant arm/disarm actions trigger the scenarios mapped during setup.

### Scenario activation

Use the scenario button entities in dashboards or automations to activate panel scenarios directly.

### Active scenario sensor

`sensor.your_panel_name_active_scenario` displays the current active scenario name and index.

For example, on a correctly configured SmartLiving 10100 profile:

* index `0` -> `DISINSERITO`
* index `3` -> `TOTALE`

### Event log

Use `sensor.your_panel_name_event_log` to show recent panel events. A custom table card can make this easier to read in Lovelace.

Helping support other panels
----------------------------

Only a SmartLiving 10100 (firmware 6.09) has been checked on hardware. Memory positions differ between models and firmware, so support for other panels is built from data sent by their owners:

1. In Home Assistant open **Settings** → **Devices & Services** → **Inim Smartliving Alarm** → ⋮ → **Download diagnostics**. It takes about 30-60 seconds and polling pauses meanwhile.
2. The file contains the entry settings without PIN and host, the live state and a read-only copy of the panel memory (configuration and names). Before the file is built, the user/installer code tables, telephone numbers and every occurrence of the configured PIN are overwritten.
3. Zone, area, scenario and user **names** are kept, because they are needed to find the tables. Check the file before attaching it to a public issue; if you prefer, send it privately.
4. Open an issue with the file, the panel model and firmware, and a short description of the installation (which terminals are zones or outputs). An export of the INIM installer software programming is also very useful.

Troubleshooting
---------------

### Cannot connect / connection timed out

* Verify host and port.
* Verify Home Assistant can reach the SmartLAN module.
* Check firewall, VLAN and routing rules.
* Confirm the SmartLAN module is powered and online.
* Make sure no other local client (programming software, another Home Assistant instance) is holding the single SmartLAN connection.

### Scenarios do not activate

* Check that the PIN is valid and has sufficient permissions.
* Verify the Home Assistant alarm actions are mapped to the correct panel scenarios.
* Check for open/alarmed zones preventing activation.

### Scenario names are wrong or stale

* Open integration options.
* Verify the selected panel model profile.
* Enable **Refresh Initial Panel Config**.
* Submit the first options step and review the scenario mapping page.

For SmartLiving 10100 / 10100L, expected first scenario names are usually:

* `DISINSERITO`
* `SOLO P.T.`
* `SOLO SEMINT.`
* `TOTALE`
* `NOTTE`

### First zones show `AREA 011`, `AREA 012`, etc.

This means the static names were likely read with the wrong profile or with stale cached configuration. Select the correct panel profile and enable **Refresh Initial Panel Config**.

### Entities do not appear or do not update

* Check Home Assistant logs for `custom_components.inim_smartliving_alarm`.
* Verify the fast and slow polling intervals. With debug logging, `Finished fetching … in X seconds` shows the duration of each cycle.
* Restart Home Assistant after installing or updating the integration.

### Incorrect number of entities

* Check **Limit Areas / Zones / Scenarios** in the integration options.
* Make sure the selected panel profile matches your panel model.

Development notes
-----------------

This integration is based on reverse engineering and field testing. Panel memory maps can vary by model and firmware. Keep the default profile conservative and add profile-specific behavior only when confirmed by real panel data.

Contributing
------------

Contributions, bug reports and panel-specific diagnostics are welcome. Please include:

* panel model;
* firmware version;
* selected profile;
* relevant Home Assistant logs;
* whether names were read correctly after **Refresh Initial Panel Config**.
