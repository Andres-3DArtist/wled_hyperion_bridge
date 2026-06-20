"""Coordinator for WLED Hyperion Bridge."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import WLEDClient
from .const import (
    LIVE_OVERRIDE_OFF,
    LIVE_OVERRIDE_UNTIL_REBOOT,
)
from .snapshot import build_restorable_snapshot

_LOGGER = logging.getLogger(__name__)


class WLEDHyperionBridgeCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Coordinate WLED state and Hyperion sync control for one zone."""

    def __init__(
        self,
        hass: HomeAssistant,
        clients: list[WLEDClient],
        devices: list[dict[str, Any]],
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
        self.clients = clients
        self.devices = devices
        self.store = store
        self.saved_snapshots: dict[str, dict[str, Any]] = {}
        self.sync_enabled = False

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch current WLED state for all bridge members."""
        results = await asyncio.gather(
            *(client.async_get_state() for client in self.clients),
            return_exceptions=True,
        )
        data: dict[str, dict[str, Any]] = {}
        errors: list[str] = []

        for device, result in zip(self.devices, results, strict=True):
            if isinstance(result, Exception):
                errors.append(f"{device['name']}: {result}")
                continue
            data[device["id"]] = result

        if errors:
            raise UpdateFailed("; ".join(errors))

        self.sync_enabled = bool(data) and all(
            state.get("lor") == LIVE_OVERRIDE_OFF for state in data.values()
        )
        return data

    async def async_load_saved_snapshot(self) -> None:
        """Load persisted WLED state snapshots."""
        stored = await self.store.async_load()
        if not stored:
            return

        snapshots = stored.get("snapshots")
        if isinstance(snapshots, dict):
            self.saved_snapshots = {
                str(target): snapshot
                for target, snapshot in snapshots.items()
                if isinstance(snapshot, dict)
            }
        else:
            snapshot = stored.get("snapshot")
            if isinstance(snapshot, dict) and self.devices:
                self.saved_snapshots = {self.devices[0]["id"]: snapshot}

        self.sync_enabled = bool(stored.get("sync_enabled", False))

    async def async_set_sync_enabled(self, enabled: bool) -> None:
        """Enable or disable Hyperion realtime sync handling."""
        if enabled:
            await self._async_enable_sync()
        else:
            await self._async_disable_sync()

        await self.async_request_refresh()

    async def _async_enable_sync(self) -> None:
        """Allow all WLED members to accept Hyperion DDP realtime data."""
        states = await self._async_read_all()
        self.saved_snapshots = {
            device["id"]: build_restorable_snapshot(state)
            for device, state in zip(self.devices, states, strict=True)
        }
        await self._async_save_snapshot(sync_enabled=True)
        await self._async_post_all({"lor": LIVE_OVERRIDE_OFF})
        self.sync_enabled = True

    async def _async_disable_sync(self) -> None:
        """Ignore realtime input and restore saved WLED state on all members."""
        errors = await self._async_post_all(
            {"lor": LIVE_OVERRIDE_UNTIL_REBOOT, "live": False},
            raise_on_error=False,
        )

        restore_devices: list[dict[str, Any]] = []
        restore_clients: list[WLEDClient] = []
        restore_payloads: list[dict[str, Any]] = []
        for client, device in zip(self.clients, self.devices, strict=True):
            snapshot = self.saved_snapshots.get(device["id"])
            if snapshot is None:
                continue
            restore_devices.append(device)
            restore_clients.append(client)
            restore_payloads.append(snapshot)

        if restore_payloads:
            errors.extend(
                await self._async_post_many(
                    restore_clients,
                    restore_devices,
                    restore_payloads,
                    "restore state",
                    raise_on_error=False,
                )
            )

        if errors:
            await self._async_save_snapshot(sync_enabled=True)
            raise HomeAssistantError("; ".join(errors))

        self.sync_enabled = False
        self.saved_snapshots = {}
        await self.store.async_remove()

    async def _async_save_snapshot(self, sync_enabled: bool) -> None:
        """Persist the current saved snapshots."""
        await self.store.async_save(
            {
                "sync_enabled": sync_enabled,
                "snapshots": self.saved_snapshots,
            }
        )

    async def _async_read_all(self) -> list[dict[str, Any]]:
        """Read state from every WLED member."""
        results = await asyncio.gather(
            *(client.async_get_state() for client in self.clients),
            return_exceptions=True,
        )
        states: list[dict[str, Any]] = []
        errors: list[str] = []

        for device, result in zip(self.devices, results, strict=True):
            if isinstance(result, Exception):
                errors.append(f"{device['name']}: {result}")
                continue
            states.append(result)

        if errors:
            raise HomeAssistantError(
                "Failed to read state for WLED bridge members: "
                + "; ".join(errors)
            )

        return states

    async def _async_post_all(
        self, payload: dict[str, Any], *, raise_on_error: bool = True
    ) -> list[str]:
        """Post one payload to every WLED member."""
        return await self._async_post_many(
            self.clients,
            self.devices,
            [payload for _client in self.clients],
            "update state",
            raise_on_error=raise_on_error,
        )

    async def _async_post_many(
        self,
        clients: list[WLEDClient],
        devices: list[dict[str, Any]],
        payloads: list[dict[str, Any]],
        action: str,
        *,
        raise_on_error: bool = True,
    ) -> list[str]:
        """Post payloads to selected clients and surface grouped errors."""
        results = await asyncio.gather(
            *(
                client.async_set_state(payload)
                for client, payload in zip(clients, payloads, strict=True)
            ),
            return_exceptions=True,
        )
        errors = [
            f"Failed to {action} for {device['name']}: {result}"
            for device, result in zip(devices, results, strict=True)
            if isinstance(result, Exception)
        ]
        if errors and raise_on_error:
            raise HomeAssistantError("; ".join(errors))
        return errors
