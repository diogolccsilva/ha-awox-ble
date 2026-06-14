# AwoX Smart Plug over Bluetooth — Home Assistant integration

[![hacs][hacs-badge]][hacs] [![validate][validate-badge]][validate-workflow] [![tests][tests-badge]][tests-workflow]

A local **Bluetooth (BLE)** integration for Home Assistant that replicates what
the discontinued **AwoX Smart Control** mobile app did for AwoX / Revogi smart
plugs — but driven entirely from Home Assistant, with **no cloud and no phone
app required**.

The plug's BLE protocol was reverse-engineered from the official AwoX Smart
Control Android app so that Home Assistant can talk to the hardware directly.

## Features

- A single Home Assistant **device** per plug, with:
  - a **switch** (outlet) whose state reflects the plug's *real* on/off status, and
  - a **Power** sensor in watts (`device_class: power`, `state_class: measurement`).
- **100% local** — talks to the plug over BLE via Home Assistant's own Bluetooth
  stack. No internet, no AwoX account, no app.
- **UI configuration** — add it from *Settings → Devices & Services*; pick the
  plug from discovered devices or type its MAC.
- **Adjustable polling** — change how often the plug is polled from the
  integration's *Options* (no restart).
- **Resilient connections** — uses `bleak-retry-connector` (the same library
  Home Assistant uses internally) so it cooperates with the adapter instead of
  fighting other Bluetooth consumers.

## Supported devices

Any AwoX / Revogi BLE smart plug that uses the Revogi GATT protocol
(service `fff0`, write `fff3`, notify `fff4`). Verified with:

| Model        | Notes                          |
| ------------ | ------------------------------ |
| `SMP-B16-GR` | Schuko / German plug (tested)  |
| `SMP-B16-FR` | French plug (same protocol)    |

Other Revogi-based plugs with power metering are likely compatible.

> Not supported: the newer AwoX **Home Control** app devices (different
> hardware/protocol).

## Requirements

- Home Assistant **2024.6** or newer.
- The Home Assistant **Bluetooth** integration configured with an adapter that
  can reach the plug (built-in, USB dongle, or an ESPHome Bluetooth proxy).

## Installation

### HACS (recommended)

1. In HACS, open the **⋮** menu → **Custom repositories**.
2. Add `https://github.com/diogolccsilva/ha-awox-ble` with category
   **Integration**.
3. Search HACS for **AwoX Smart Plug (Revogi)** and **Download** it.
4. **Restart** Home Assistant.

### Manual

Copy `custom_components/awox_plug/` into your Home Assistant
`config/custom_components/` directory and restart Home Assistant.

## Configuration

1. **Settings → Devices & Services → + Add Integration**.
2. Search for **AwoX Smart Plug (Revogi)**.
3. Select the plug from the discovered list, or type its Bluetooth MAC address
   (e.g. `E0:E5:CF:11:C0:6D`), and give it a name.
4. (Optional) Open the device → **Configure** to change the polling interval
   (default `30s`).

## How it works

Commands and responses are framed as:

```
[0x0f][len][cmd][0x00][data...][checksum][0xff][0xff]
   len      = len(data) + 3
   checksum = (cmd + 1 + sum(data)) & 0xFF
```

- **On**: `cmd 0x03`, data `{1,0,0}` → `0f 06 03 00 01 00 00 05 ff ff`
- **Off**: `cmd 0x03`, data `{0,0,0}` → `0f 06 03 00 00 00 00 04 ff ff`
- **Poll**: `cmd 0x04`, data `{0,0}` → `0f 05 04 00 00 00 05 ff ff`

The poll response (`cmd 0x04`) returns the on/off state and the instant power as
a big-endian value in **milliwatts**, so a single poll updates both the switch
and the sensor.

## Development

```bash
python -m venv .venv
.venv/Scripts/activate      # Windows
pip install -r requirements_test.txt
ruff check .
pytest
```

The protocol layer (`custom_components/awox_plug/protocol.py`) is dependency-free
and fully unit-tested in `tests/`.

## Disclaimer

This is an unofficial, community integration. "AwoX" and "Revogi" are trademarks
of their respective owners. Use at your own risk.

## License

[MIT](LICENSE)

[hacs]: https://github.com/hacs/integration
[hacs-badge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[validate-badge]: https://github.com/diogolccsilva/ha-awox-ble/actions/workflows/validate.yml/badge.svg
[validate-workflow]: https://github.com/diogolccsilva/ha-awox-ble/actions/workflows/validate.yml
[tests-badge]: https://github.com/diogolccsilva/ha-awox-ble/actions/workflows/tests.yml/badge.svg
[tests-workflow]: https://github.com/diogolccsilva/ha-awox-ble/actions/workflows/tests.yml
