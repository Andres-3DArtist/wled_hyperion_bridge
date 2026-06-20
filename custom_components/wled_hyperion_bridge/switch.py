"""Switch platform for WLED Hyperion Bridge."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN
from .coordinator import WLEDHyperionBridgeCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up WLED Hyperion Bridge switch."""
    coordinator: WLEDHyperionBridgeCoordinator = entry.runtime_data
    async_add_entities([HyperionSyncSwitch(coordinator, entry)])


class HyperionSyncSwitch(
    CoordinatorEntity[WLEDHyperionBridgeCoordinator], SwitchEntity
):
    """Switch controlling WLED Hyperion realtime sync for one zone."""

    _attr_has_entity_name = True
    _attr_translation_key = "hyperion_sync"

    def __init__(
        self,
        coordinator: WLEDHyperionBridgeCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize switch."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_hyperion_sync"
        self._attr_name = "Hyperion Sync"
        self._attr_suggested_object_id = "hyperion_sync"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_NAME, DEFAULT_NAME),
            manufacturer="WLED",
            model="WLED DDP realtime zone bridge",
        )

    @property
    def is_on(self) -> bool:
        """Return true if Hyperion sync is enabled for the whole zone."""
        return self.coordinator.sync_enabled

    @property
    def available(self) -> bool:
        """Return entity availability."""
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return diagnostic state attributes."""
        return {
            "members": [
                {
                    "name": device["name"],
                    "host": device["host"],
                    "port": device["port"],
                }
                for device in self.coordinator.devices
            ],
            "member_count": len(self.coordinator.devices),
            "snapshot_saved": bool(self.coordinator.saved_snapshots),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on Hyperion sync."""
        await self.coordinator.async_set_sync_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off Hyperion sync."""
        await self.coordinator.async_set_sync_enabled(False)
