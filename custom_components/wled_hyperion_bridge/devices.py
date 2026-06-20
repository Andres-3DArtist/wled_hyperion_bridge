"""Helpers for WLED bridge member devices."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME

from .const import CONF_DEVICE_NAME, CONF_DEVICES, CONF_HOST, CONF_PORT, DEFAULT_NAME


def target_id(host: str, port: int) -> str:
    """Return a stable target identifier."""
    return f"{host.strip().lower()}:{int(port)}"


def normalize_device(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize one WLED device config dict."""
    host = str(data[CONF_HOST]).strip()
    port = int(data[CONF_PORT])
    name = str(data.get(CONF_DEVICE_NAME) or data.get(CONF_NAME) or host).strip()
    return {
        "id": target_id(host, port),
        CONF_NAME: name,
        CONF_HOST: host,
        CONF_PORT: port,
    }


def devices_from_data(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return configured WLED devices, migrating legacy single-device data."""
    devices = data.get(CONF_DEVICES)
    if isinstance(devices, list):
        return [
            normalize_device(device)
            for device in devices
            if isinstance(device, dict)
            and CONF_HOST in device
            and CONF_PORT in device
        ]

    if CONF_HOST in data and CONF_PORT in data:
        return [
            normalize_device(
                {
                    CONF_NAME: data.get(CONF_NAME, DEFAULT_NAME),
                    CONF_HOST: data[CONF_HOST],
                    CONF_PORT: data[CONF_PORT],
                }
            )
        ]

    return []


def devices_from_entry(entry: ConfigEntry) -> list[dict[str, Any]]:
    """Return WLED devices from entry data with options as a legacy fallback."""
    data = dict(entry.data)
    if CONF_DEVICES not in data and CONF_DEVICES in entry.options:
        data[CONF_DEVICES] = entry.options[CONF_DEVICES]
    return devices_from_data(data)


def merge_device(
    devices: list[dict[str, Any]], device: dict[str, Any]
) -> list[dict[str, Any]]:
    """Add or replace one WLED device in a bridge."""
    normalized = normalize_device(device)
    merged = [
        existing
        for existing in devices
        if existing.get("id") != normalized["id"]
    ]
    merged.append(normalized)
    return merged
