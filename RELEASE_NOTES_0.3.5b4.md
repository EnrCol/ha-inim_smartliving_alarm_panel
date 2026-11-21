# INIM SmartLiving Alarm — v0.3.5b4 (beta)

Unofficial prerelease, based on v0.3.5b3.

## Changes since v0.3.5b3

- Scenario area actions also decode **partial** (`arm_partial`, code 2) and **instant** (`arm_instant`, code 3, no entry delay) arming, the same codes the panel uses for the area status. On the reference 10100 the NOTTE scenario arms the perimeter areas without entry delay and was shown as `unknown`.
- A failed scenario is treated as a disarm scenario only if it arms no area in any mode.
- Initial configuration revision 6 → 7 (scenario actions read again on the first start).

## Validation

- Automated tests (64).

## Rollback

Install v0.3.5b3 and restart Home Assistant.
