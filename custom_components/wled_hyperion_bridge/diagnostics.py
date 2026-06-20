"""Diagnostics for WLED Hyperion Bridge."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import diagnostics as diag

from .coordinator import WLEDHyperionBridgeCoordinator

TO_REDACT = {"host"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: WLEDHyperionBridgeCoordinator = entry.runtime_data

    return {
        "entry": diag.async_redact_data(entry.as_dict(), TO_REDACT),
        "devices": diag.async_redact_data(coordinator.devices, TO_REDACT),
        "last_update_success": coordinator.last_update_success,
        "sync_enabled": coordinator.sync_enabled,
        "snapshot_saved": bool(coordinator.saved_snapshots),
        "state_keys": {
            device_id: sorted(state.keys())
            for device_id, state in (coordinator.data or {}).items()
        },
    }
