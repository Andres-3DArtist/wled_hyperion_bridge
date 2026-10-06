# WLED Hyperion Bridge

[![GitHub release](https://img.shields.io/github/v/release/Andres-3DArtist/wled_hyperion_bridge)](https://github.com/Andres-3DArtist/wled_hyperion_bridge/releases/latest)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://github.com/Andres-3DArtist/wled_hyperion_bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/Andres-3DArtist/wled_hyperion_bridge/actions/workflows/ci.yml)

Home Assistant custom integration for controlling WLED realtime DDP input used by Hyperion.

The integration creates one bridge per Home Assistant area/zone. Each bridge exposes one switch:

```text
switch.<bridge_name>_hyperion_sync
```

A bridge contains a named list of WLED devices. Turning the bridge switch on or off applies the same realtime/DDP control behavior to every WLED device in that bridge.

When the switch is turned on, the integration saves the current WLED JSON state for every WLED in the bridge and allows WLED to accept realtime DDP data from Hyperion by setting WLED `lor` to `0`. If the bridge is linked to Hyperion, it also enables the Hyperion LED output for the bridge's instance (see below).

When the switch is turned off, the integration tells every WLED in the bridge to ignore realtime input by setting `lor` to `2` and `live` to `false`, then restores each device's saved brightness, colors, effects, palette, preset, playlist (`pl`), nightlight (`nl`), and segments. Hyperion itself is never touched on switch-off.

Polling is tolerant to partial failures: the bridge stays available while at least one WLED responds, and unreachable devices are listed in the `unreachable` switch attribute.

## Compatibility

- Home Assistant 2025.1.0+
- WLED 0.16.x
- ESP32 WLED devices, including Gledopto ESP32 controllers
- Hyperion configured with WLED/DDP output (optional output control needs the Hyperion JSON server)

## WLED API Behavior

This integration uses the documented WLED JSON state API:

- `GET /json/state`
- `POST /json/state`

Relevant WLED fields:

- `lor`: live data override. `0` disables override and allows realtime input. `2` keeps realtime override active until reboot.
- `live`: realtime mode. Posting `false` exits realtime mode.
- `bri`, `seg`, `ps`, `pl`, `nl`, and related state keys are captured and restored per WLED device.

## Installation With HACS

1. Add this repository as a custom repository in HACS.
2. Select category `Integration`.
3. Install `WLED Hyperion Bridge`.
4. Restart Home Assistant.
5. Go to **Settings > Devices & services > Add integration**.
6. Search for **WLED Hyperion Bridge**.

## Configuration

First setup:

1. Enter a custom bridge name.
2. Choose the Home Assistant area for the bridge.
3. Optionally link a Hyperion server (leave the host empty to skip).
4. Add the first WLED device to the bridge.

Later, when you add the integration again, the flow asks whether to create another bridge or add a WLED to an existing bridge.

For each WLED device, enter:

- Host or IP address
- HTTP port, usually `80`
- Optional WLED device name

The bridge switch attributes include the current `wled_devices` list with each WLED id, name, host, and port, plus an `unreachable` list when some devices fail to respond.

Manage members later from **Settings > Devices & services > WLED Hyperion Bridge > Configure**: add a WLED device, remove existing ones (at least one device must remain), or configure Hyperion output control.

## Hyperion Output Control (Optional)

Each bridge can be linked to one Hyperion server so that turning the switch **on** also enables the Hyperion LED output (`LEDDEVICE` component) for the bridge's instance. Turning the switch **off** never touches Hyperion: it only restores the saved WLED scene while WLED ignores realtime input (`lor: 2`).

- One bridge maps to one Hyperion instance (default instance `0`), or to all instances.
- Hyperion connection uses its TCP JSON server, default port `19444` (not the `8090` web UI port).
- If Hyperion has API authentication enabled (Hyperion web UI > System > Network Services), paste an API token. Create one in Hyperion under Configuration > Network Services.
- The integration reads the LED output state first and only enables it when it is off. Re-enabling an already-on output resets Hyperion's stream, so blind writes are avoided.
- If Hyperion is linked but unreachable when turning on, the switch reports an error instead of leaving the LEDs dark silently. Live state is visible in the `hyperion` switch attribute (`reachable`, `led_enabled` per instance).

Brand assets are included at `custom_components/wled_hyperion_bridge/brand/icon.png` for Home Assistant 2026.3+ and HACS.

## Development

Run tests:

```bash
pytest
```

## Security

See [SECURITY.md](SECURITY.md) for how to report vulnerabilities.

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Andres-3DArtist.

## Notes

WLED must be configured to receive realtime DDP packets on the network. This integration controls WLED's documented live override behavior through the JSON state API; it does not edit WLED network configuration.
