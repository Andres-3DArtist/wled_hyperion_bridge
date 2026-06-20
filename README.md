# WLED Hyperion Bridge

Home Assistant custom integration for controlling WLED realtime DDP input used by Hyperion.

The integration creates one switch per Hyperion sync zone:

```text
switch.hyperion_sync
```

Each zone can contain multiple WLED devices. Turning the zone switch on or off applies the same realtime/DDP control behavior to every WLED device in that zone.

When the switch is turned on, the integration saves the current WLED JSON state for every WLED in the zone and allows WLED to accept realtime DDP data from Hyperion by setting WLED `lor` to `0`.

When the switch is turned off, the integration tells every WLED in the zone to ignore realtime input by setting `lor` to `2` and `live` to `false`, then restores each device's saved brightness, colors, effects, palette, preset, and segments.

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

Create one integration entry per Hyperion zone. During setup:

1. Enter a zone name.
2. Add the first WLED device for that zone.
3. Choose whether to add more WLED devices.

For each WLED device, enter:

- Host or IP address
- HTTP port, usually `80`
- Optional display name

To add another WLED later, open the integration entry's **Options** flow and add the device. Home Assistant will reload the bridge zone and keep one switch for that zone.

## Development

Run tests:

```bash
pytest
```

## Notes

WLED must be configured to receive realtime DDP packets on the network. This integration controls WLED's documented live override behavior through the JSON state API; it does not edit WLED network configuration.
