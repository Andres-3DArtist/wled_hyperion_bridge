"""Helpers for WLED bridge member devices."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME

from .const import CONF_DEVICE_NAME, CONF_DEVICES, CONF_HOST, CONF_PORT, DEFAULT_NAME

_LOGGER = logging.getLogger(__name__)

MAX_HOST_LENGTH = 253
MAX_DEVICE_NAME_LENGTH = 255


def target_id(host: str, port: int) -> str:
    """Return a stable target identifier."""
    return f"{host.strip().lower()}:{int(port)}"


def validate_host(host: Any) -> str:
    """Validate a host value and return the stripped host."""
    cleaned = str(host or "").strip()
    if not cleaned or len(cleaned) > MAX_HOST_LENGTH:
        raise ValueError("invalid_host")
    if "://" in cleaned or "/" in cleaned or "\\" in cleaned or " " in cleaned:
        raise ValueError("invalid_host")
    return cleaned


def validate_port(port: Any) -> int:
    """Validate a port value and return it as int."""
    try:
        parsed = int(port)  # type: ignore[arg-type]
    except (TypeError, ValueError) as err:
        raise ValueError("invalid_port") from err
    if not 1 <= parsed <= 65535:
        raise ValueError("invalid_port")
    return parsed


def normalize_device(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize one WLED device config dict."""
    host = validate_host(data.get(CONF_HOST))
    port = validate_port(data.get(CONF_PORT))
    name = str(data.get(CONF_DEVICE_NAME) or data.get(CONF_NAME) or host).strip()
    if not name:
        name = host
    if len(name) > MAX_DEVICE_NAME_LENGTH:
        raise ValueError("invalid_device_name")
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
        normalized: list[dict[str, Any]] = []
        for device in devices:
            if not isinstance(device, dict):
                continue
            if CONF_HOST not in device or CONF_PORT not in device:
                continue
            try:
                normalized.append(normalize_device(device))
            except ValueError as err:
                _LOGGER.warning("Skipping invalid WLED device %r: %s", device, err)
        return normalized

    if CONF_HOST in data and CONF_PORT in data:
        try:
            return [
                normalize_device(
                    {
                        CONF_NAME: data.get(CONF_NAME, DEFAULT_NAME),
                        CONF_HOST: data[CONF_HOST],
                        CONF_PORT: data[CONF_PORT],
                    }
                )
            ]
        except ValueError as err:
            _LOGGER.warning("Skipping invalid legacy WLED device: %s", err)
            return []

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


def remove_devices(
    devices: list[dict[str, Any]], target_ids: set[str]
) -> list[dict[str, Any]]:
    """Return bridge members without the given target ids."""
    return [device for device in devices if device.get("id") not in target_ids]
