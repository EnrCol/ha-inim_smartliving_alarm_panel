# INIM SmartLiving Alarm — v0.3.4b1 (beta)

This is an **unofficial beta** based on the fork's latest pre-existing SmartLiving 10100 development branch (PR #11 / `0.3.3-test10`). It does **not** include external PR #12 by `scorbacella`.

## Changes since v0.3.2 / previously published v0.3.3-test8

- Carry forward the tested-on-10100 protocol adjustments and panel profiles from the existing experimental series.
- Detect programmed area, zone, and scenario names automatically on the 10100 profile, ignoring empty/default placeholders.
- Derive 10100 runtime import limits from actual named slots while preserving manual scenario mappings.
- Only infer missing scenario mappings when a known exact alias is unambiguous.
- Preserve conservative exclusion behavior: zone Z011 has no verified write-command index and must not receive an exclusion switch.
- Include unofficial INIM-derived icon and logo in `custom_components/inim_smartliving_alarm/brand/`.
- Establish a Marketplace-visible prerelease/stable release process with validation jobs.

## Reference SmartLiving 10100 (firmware 6.09)

Expected programmed values: 5 effective areas, 19 effective zones (Z001–Z014 and Z028–Z032), runtime zone limit 32, and 5 scenarios. The reference unit was still running `v0.3.3-test8` before this release; **these new beta changes have not yet been live-validated on the unit**.

The update does not add OC1/OC2 support or the active-scenario polling changes proposed in PR #12. SmartLAN remains subject to a single active TCP client.

## Installation and rollback

Enable prereleases/beta versions for this custom repository in Home Assistant Marketplace, install `v0.3.4b1`, then restart Home Assistant when requested. Record the previous working version and configuration. If needed, select the previous version in Marketplace and restart Home Assistant. No automatic alarm activation or deactivation should be required by installation.

## Compatibility and safety

Only SmartLiving 10100 is available for physical testing. Other profiles have **not been validated on hardware**; automatic CI checks cannot establish physical compatibility. The fork is unaffiliated with INIM Electronics; the source is experimental and should not be relied upon as the primary life-safety/security control.
