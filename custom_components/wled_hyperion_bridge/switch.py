"""Switch platform for WLED Hyperion Bridge."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_AREA_ID, DEFAULT_NAME, DOMAIN
from .coordinator import WLEDHyperionBridgeCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up WLED Hyperion Bridge switch."""
    coordinator: WLEDHyperionBridgeCoordinator = entry.runtime_data
    async_add_entities([HyperionSyncSwitch(hass, coordinator, entry)])


class HyperionSyncSwitch(
    CoordinatorEntity[WLEDHyperionBridgeCoordinator], SwitchEntity
):
    """Switch controlling WLED Hyperion realtime sync for one bridge."""

    _attr_has_entity_name = True
    _attr_translation_key = "hyperion_sync"

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: WLEDHyperionBridgeCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize switch."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_hyperion_sync"
        self._attr_name = "Hyperion Sync"
        self._attr_suggested_object_id = "hyperion_sync"
        device_info: DeviceInfo = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.data.get(CONF_NAME, DEFAULT_NAME),
            "manufacturer": "WLED",
            "model": "WLED DDP realtime bridge",
        }
        area_name = self._area_name(hass)
        if area_name:
            device_info["suggested_area"] = area_name
        self._attr_device_info = device_info

    def _area_name(self, hass: HomeAssistant) -> str | None:
        """Return the configured Home Assistant area name."""
        area_id = self._entry.data.get(CONF_AREA_ID)
        if not area_id:
            return None
        area = ar.async_get(hass).async_get_area(area_id)
        return area.name if area else None

    @property
    def is_on(self) -> bool:
        """Return true if Hyperion sync is enabled for the whole bridge."""
        return self.coordinator.sync_enabled

    @property
    def available(self) -> bool:
        """Return entity availability."""
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return bridge membership attributes."""
        return {
            "area_id": self._entry.data.get(CONF_AREA_ID),
            "wled_devices": [
                {
                    "name": device["name"],
                    "host": device["host"],
                    "port": device["port"],
                }
                for device in self.coordinator.devices
            ],
            "wled_count": len(self.coordinator.devices),
            "snapshot_saved": bool(self.coordinator.saved_snapshots),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on Hyperion sync."""
        await self.coordinator.async_set_sync_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off Hyperion sync."""
        await self.coordinator.async_set_sync_enabled(False)
