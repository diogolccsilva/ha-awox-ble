# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.3.0] - 2026-06-15

Device-measured energy is validated against the plug, so energy reporting is
now exclusively read from the device (no derived/approximate values).

### Added
- **Energy today** now feeds the Energy Dashboard (state_class `total` with a
  midnight `last_reset`).

### Changed
- **Energy today / last 24h / yesterday** values confirmed correct (Wh) and
  finalized.

### Removed
- The derived Riemann-integration **Energy** sensor (approximate). If you added
  it to a dashboard, remove it; use **Energy today** instead.

### Fixed
- Device info no longer shows placeholder "Firmware Revision" / "Hardware
  Revision" text when the plug returns the characteristic label instead of an
  actual version.

## [1.2.0] - 2026-06-15

### Added
- Reads the plug's own stored energy history each poll (hourly command `0x0A`,
  daily command `0x0B`) over Home Assistant's cooperative Bluetooth stack.
- New device-measured energy sensors (validation pre-release, no `state_class`
  yet): **Energy today**, **Energy last 24h**, **Energy yesterday**.
- The first decoded hourly/daily history per session is logged at INFO (raw
  bytes + decoded values) to validate the Wh scaling against the device.

### Notes
- The device-measured energy values are provisional pending validation of the
  unit scaling; they are not yet wired into the Energy Dashboard.

## [1.1.0] - 2026-06-15

### Added
- **Energy** sensor (kWh, `total_increasing`) that integrates the live power
  reading (trapezoidal Riemann sum), suitable for the Energy Dashboard. The
  running total is restored across restarts. This is an approximation limited
  by the polling interval; a device-measured energy figure is planned.

## [1.0.1] - 2026-06-14

### Fixed
- Entities no longer become unclickable/empty when the plug is briefly
  unreachable at startup. Setup now always creates the entities (showing
  "unavailable" until the first successful poll) instead of aborting.
- The coordinator now retries transient Bluetooth failures (adapter contention,
  device asleep, missed notification) instead of failing on the first error.

### Added
- Reads the standard BLE Device Information Service (when the plug exposes it)
  to populate the device's **Firmware** and **Hardware** version fields.

## [1.0.0] - 2026-06-14

### Added
- Initial release.
- Local Bluetooth (BLE) control of AwoX / Revogi smart plugs (e.g. SMP-B16-GR).
- Single Home Assistant device exposing:
  - a **switch** (outlet) reflecting the plug's real on/off state, and
  - a **Power** sensor (watts).
- UI config flow (device discovery picker or manual MAC entry).
- Options flow to change the polling interval at runtime.
- Cooperative connections via Home Assistant's Bluetooth stack
  (`bleak-retry-connector`) to avoid adapter contention.

[Unreleased]: https://github.com/diogolccsilva/ha-awox-ble/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/diogolccsilva/ha-awox-ble/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/diogolccsilva/ha-awox-ble/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/diogolccsilva/ha-awox-ble/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/diogolccsilva/ha-awox-ble/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/diogolccsilva/ha-awox-ble/releases/tag/v1.0.0
