"""Tests for WLED bridge device helpers."""

from homeassistant.const import CONF_NAME

from custom_components.wled_hyperion_bridge.const import (
    CONF_DEVICE_NAME,
    CONF_DEVICES,
    CONF_HOST,
    CONF_PORT,
)
from custom_components.wled_hyperion_bridge.devices import (
    devices_from_data,
    merge_device,
    normalize_device,
)


def test_normalize_device_adds_stable_id() -> None:
    """Device data gets a stable lowercase host:port id."""
    device = normalize_device(
        {CONF_NAME: "Cabinet", CONF_HOST: "WLED-KITCHEN.local", CONF_PORT: 80}
    )

    assert device == {
        "id": "wled-kitchen.local:80",
        CONF_NAME: "Cabinet",
        CONF_HOST: "WLED-KITCHEN.local",
        CONF_PORT: 80,
    }


def test_normalize_device_uses_device_name_from_flow() -> None:
    """WLED member name is separate from the bridge name field."""
    device = normalize_device(
        {
            CONF_NAME: "Bridge Name",
            CONF_DEVICE_NAME: "TV Left",
            CONF_HOST: "192.168.1.30",
            CONF_PORT: 80,
        }
    )

    assert device[CONF_NAME] == "TV Left"


def test_devices_from_data_migrates_legacy_single_device() -> None:
    """Old one-WLED config entries still produce a bridge member list."""
    devices = devices_from_data(
        {CONF_NAME: "Living Room", CONF_HOST: "192.168.1.20", CONF_PORT: 80}
    )

    assert len(devices) == 1
    assert devices[0]["id"] == "192.168.1.20:80"
    assert devices[0][CONF_NAME] == "Living Room"


def test_devices_from_data_reads_multi_device_config() -> None:
    """New zone config stores multiple WLED devices."""
    devices = devices_from_data(
        {
            CONF_DEVICES: [
                {CONF_NAME: "Left", CONF_HOST: "192.168.1.21", CONF_PORT: 80},
                {CONF_NAME: "Right", CONF_HOST: "192.168.1.22", CONF_PORT: 81},
            ]
        }
    )

    assert [device["id"] for device in devices] == [
        "192.168.1.21:80",
        "192.168.1.22:81",
    ]


def test_merge_device_replaces_existing_member() -> None:
    """Adding the same host and port updates that member instead of duplicating it."""
    devices = [
        normalize_device({CONF_NAME: "Old", CONF_HOST: "192.168.1.21", CONF_PORT: 80})
    ]

    merged = merge_device(
        devices,
        {CONF_NAME: "New", CONF_HOST: "192.168.1.21", CONF_PORT: 80},
    )

    assert len(merged) == 1
    assert merged[0][CONF_NAME] == "New"
