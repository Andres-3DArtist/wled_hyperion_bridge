# WLED Hyperion Bridge

Home Assistant custom integration for controlling WLED realtime DDP input used by Hyperion.

The integration creates one switch per configured WLED device:

```text
switch.hyperion_sync
```

When the switch is turned on, the integration saves the current WLED JSON state and allows WLED to accept realtime DDP data from Hyperion by setting WLED `lor` to `0`.

When the switch is turned off, the integration tells WLED to ignore realtime input by setting `lor` to `2` and `live` to `false`, then restores the saved brightness, colors, effects, palette, preset, and segments.

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
- `bri`, `seg`, `ps`, and related state keys are captured and restored.

## Installation With HACS

1. Add this repository as a custom repository in HACS.
2. Select category `Integration`.
3. Install `WLED Hyperion Bridge`.
4. Restart Home Assistant.
5. Go to **Settings > Devices & services > Add integration**.
6. Search for **WLED Hyperion Bridge**.

## Configuration

For each WLED device, enter:

- Host or IP address
- HTTP port, usually `80`
- Optional display name

Each configured WLED device creates one `hyperion_sync` switch.

## Development

Run tests:

```bash
pytest
```

## Notes

WLED must be configured to receive realtime DDP packets on the network. This integration controls WLED's documented live override behavior through the JSON state API; it does not edit WLED network configuration.
