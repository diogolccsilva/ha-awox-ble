# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/diogolccsilva/ha-awox-ble/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/diogolccsilva/ha-awox-ble/releases/tag/v1.0.0
