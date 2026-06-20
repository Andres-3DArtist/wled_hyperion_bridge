# WLED Hyperion Bridge

Home Assistant custom integration for controlling WLED realtime DDP input used by Hyperion.

The integration creates one bridge per Home Assistant area/zone. Each bridge exposes one switch:

```text
switch.hyperion_sync
```

A bridge contains a named list of WLED devices. Turning the bridge switch on or off applies the same realtime/DDP control behavior to every WLED device in that bridge.

When the switch is turned on, the integration saves the current WLED JSON state for every WLED in the bridge and allows WLED to accept realtime DDP data from Hyperion by setting WLED `lor` to `0`.

When the switch is turned off, the integration tells every WLED in the bridge to ignore realtime input by setting `lor` to `2` and `live` to `false`, then restores each device's saved brightness, colors, effects, palette, preset, and segments.

## Compatibility

- Home Assistant 2026.6.1
- WLED 0.16.x
- ESP32 WLED devices, including Gledopto ESP32 controllers
- Hyperion configured with WLED/DDP output

## WLED API Behavior

This integration uses the documented WLED JSON state API:

- `GET /json/state`
- `POST /json/state`

Relevant WLED fields:

- `lor`: live data override. `0` disables override and allows realtime input. `2` keeps realtime override active until reboot.
- `live`: realtime mode. Posting `false` exits realtime mode.
- `bri`, `seg`, `ps`, and related state keys are captured and restored per WLED device.

## Installation With HACS

1. Add this repository as a custom repository in HACS.
2. Select category `Integration`.
3. Install `WLED Hyperion Bridge`.
4. Restart Home Assistant.
5. Go to **Settings > Devices & services > Add integration**.
6. Search for **WLED Hyperion Bridge**.

## Configuration

First setup:

1. Choose the Home Assistant area for the bridge.
2. Add the first WLED device to the bridge.

Later, when you add the integration again, the flow asks whether to create another bridge or add a WLED to an existing bridge. New bridge names are generated from their selected Home Assistant area.

For each WLED device, enter:

- Host or IP address
- HTTP port, usually `80`
- Optional WLED device name

The bridge switch attributes include the current `wled_devices` list with each WLED name, host, and port.

Brand assets are included at `custom_components/wled_hyperion_bridge/brand/icon.png` for Home Assistant 2026.3+ and HACS.

## Development

Run tests:

```bash
pytest
```

## Notes

WLED must be configured to receive realtime DDP packets on the network. This integration controls WLED's documented live override behavior through the JSON state API; it does not edit WLED network configuration.
