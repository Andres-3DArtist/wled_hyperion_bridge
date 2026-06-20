"""Coordinator for WLED Hyperion Bridge."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import WLEDAPIError, WLEDClient
from .const import (
    DOMAIN,
    LIVE_OVERRIDE_OFF,
    LIVE_OVERRIDE_UNTIL_REBOOT,
)
from .snapshot import build_restorable_snapshot

_LOGGER = logging.getLogger(__name__)


class WLEDHyperionBridgeCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate WLED state and Hyperion sync control."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: WLEDClient,
        store: Store[dict[str, object]],
        name: str,
        update_interval,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=update_interval,
        )
        self.client = client
        self.store = store
        self.saved_snapshot: dict[str, Any] | None = None
        self.sync_enabled = False

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch current WLED state."""
        try:
            state = await self.client.async_get_state()
        except WLEDAPIError as err:
            raise UpdateFailed(str(err)) from err

        self.sync_enabled = state.get("lor") == LIVE_OVERRIDE_OFF
        return state

    async def async_load_saved_snapshot(self) -> None:
        """Load a persisted WLED state snapshot."""
        stored = await self.store.async_load()
        if not stored:
            return

        snapshot = stored.get("snapshot")
        if isinstance(snapshot, dict):
            self.saved_snapshot = snapshot

        self.sync_enabled = bool(stored.get("sync_enabled", False))

    async def async_set_sync_enabled(self, enabled: bool) -> None:
        """Enable or disable Hyperion realtime sync handling."""
        if enabled:
            await self._async_enable_sync()
        else:
            await self._async_disable_sync()

        await self.async_request_refresh()

    async def _async_enable_sync(self) -> None:
        """Allow WLED to accept Hyperion DDP realtime data."""
        state = await self.client.async_get_state()
        self.saved_snapshot = build_restorable_snapshot(state)
        await self._async_save_snapshot(sync_enabled=True)
        await self.client.async_set_state({"lor": LIVE_OVERRIDE_OFF})
        self.sync_enabled = True

    async def _async_disable_sync(self) -> None:
        """Ignore realtime input and restore saved WLED state."""
        await self.client.async_set_state(
            {"lor": LIVE_OVERRIDE_UNTIL_REBOOT, "live": False}
        )

        if self.saved_snapshot:
            await self.client.async_set_state(self.saved_snapshot)

        self.sync_enabled = False
        self.saved_snapshot = None
        await self.store.async_remove()

    async def _async_save_snapshot(self, sync_enabled: bool) -> None:
        """Persist the current saved snapshot."""
        await self.store.async_save(
            {
                "sync_enabled": sync_enabled,
                "snapshot": self.saved_snapshot,
            }
        )
