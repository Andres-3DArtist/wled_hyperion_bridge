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
    CONF_HYPERION,
    LIVE_OVERRIDE_OFF,
    LIVE_OVERRIDE_UNTIL_REBOOT,
)
from .hyperion import HyperionAPIError, HyperionClient
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
        hyperion: HyperionClient | None = None,
        hyperion_config: dict[str, Any] | None = None,
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
        self.unreachable: dict[str, str] = {}
        self.hyperion = hyperion
        self.hyperion_config = hyperion_config
        self.hyperion_state: dict[str, Any] = {
            "configured": hyperion is not None,
            "reachable": None,
            "led": {},
        }
        self._sync_lock = asyncio.Lock()

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch current WLED state for all bridge members."""
        results = await asyncio.gather(
            *(client.async_get_state() for client in self.clients),
            return_exceptions=True,
        )
        data: dict[str, dict[str, Any]] = {}
        unreachable: dict[str, str] = {}

        for device, result in zip(self.devices, results, strict=True):
            if isinstance(result, Exception):
                unreachable[device["id"]] = str(result)
                continue
            data[device["id"]] = result

        self.unreachable = unreachable
        if unreachable:
            _LOGGER.warning(
                "Bridge %s: %d of %d WLED devices unreachable: %s",
                self.name,
                len(unreachable),
                len(self.devices),
                "; ".join(
                    f"{device['name']}: {unreachable[device['id']]}"
                    for device in self.devices
                    if device["id"] in unreachable
                ),
            )

        # Only fail the refresh when *all* members are down so one bad
        # device does not take the whole bridge offline.
        if not data:
            raise UpdateFailed("; ".join(unreachable.values()) or "no WLED data")

        # NOTE: sync state is owned by our snapshots, not by `lor`. A fresh
        # WLED reports lor=0 (realtime allowed), so deriving sync from `lor`
        # would show a never-enabled bridge as ON. Log divergence instead.
        if self.saved_snapshots:
            off_ids = [
                device_id
                for device_id, state in data.items()
                if state.get("lor") != LIVE_OVERRIDE_OFF
            ]
            if off_ids:
                _LOGGER.info(
                    "Bridge %s: %d synced device(s) report lor!=0 "
                    "(possibly changed outside Home Assistant)",
                    self.name,
                    len(off_ids),
                )

        await self._async_poll_hyperion()
        return data

    def _hyperion_targets(self) -> list[int]:
        """Return target Hyperion instances ([] means all)."""
        if self.hyperion is None or self.hyperion_config is None:
            return []
        return list(self.hyperion_config.get("instances", []))

    async def _async_poll_hyperion(self) -> None:
        """Refresh Hyperion LED output state without failing the poll."""
        if self.hyperion is None:
            return
        try:
            led = await self.hyperion.async_read_led_state(self._hyperion_targets())
        except HyperionAPIError as err:
            _LOGGER.warning("Bridge %s: Hyperion unreachable: %s", self.name, err)
            self.hyperion_state = {
                "configured": True,
                "reachable": False,
                "led": {},
                "error": str(err),
            }
            return
        self.hyperion_state = {
            "configured": True,
            "reachable": True,
            "led": led,
        }

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

        self.sync_enabled = bool(self.saved_snapshots)

    async def async_set_sync_enabled(self, enabled: bool) -> None:
        """Enable or disable Hyperion realtime sync handling."""
        async with self._sync_lock:
            if enabled:
                await self._async_enable_sync()
            else:
                await self._async_disable_sync()

        await self.async_request_refresh()

    async def _async_enable_sync(self) -> None:
        """Allow all WLED members to accept Hyperion DDP realtime data."""
        if self.sync_enabled and self.saved_snapshots:
            _LOGGER.debug("Bridge %s already in sync; ensuring lor=0", self.name)
            await self._async_post_all({"lor": LIVE_OVERRIDE_OFF})
            return
        states = await self._async_read_all()
        self.saved_snapshots = {
            device["id"]: build_restorable_snapshot(state)
            for device, state in zip(self.devices, states, strict=True)
        }
        await self._async_save_snapshot(sync_enabled=True)
        _LOGGER.debug(
            "Bridge %s: snapshots saved for %d devices, enabling sync",
            self.name,
            len(self.saved_snapshots),
        )
        await self._async_post_all({"lor": LIVE_OVERRIDE_OFF})
        # Optimistic flip: WLED already reacts to lor, so update the switch
        # now instead of making it wait for Hyperion + the final refresh.
        self.sync_enabled = True
        self.async_update_listeners()
        try:
            await self._async_ensure_hyperion_output()
        except HomeAssistantError:
            self.sync_enabled = False
            self.async_update_listeners()
            raise

    async def _async_ensure_hyperion_output(self) -> None:
        """Enable Hyperion LEDDEVICE output on targets that have it off.

        Hyperion itself is left running otherwise; a bridge OFF never touches
        it. Failures raise so the switch does not claim success while the
        LEDs stay dark.
        """
        if self.hyperion is None:
            return
        targets = self._hyperion_targets()
        try:
            states, changed = await self.hyperion.async_ensure_led_enabled(targets)
        except HyperionAPIError as err:
            self.hyperion_state = {
                "configured": True,
                "reachable": False,
                "led": {},
                "error": str(err),
            }
            raise HomeAssistantError(f"Hyperion output could not be enabled: {err}") from err
        self.hyperion_state = {
            "configured": True,
            "reachable": True,
            "led": states,
        }
        if changed:
            _LOGGER.debug(
                "Bridge %s: enabled Hyperion LED output on instances %s",
                self.name,
                changed,
            )

    async def _async_disable_sync(self) -> None:
        """Ignore realtime input and restore saved WLED state on all members."""
        _LOGGER.debug("Bridge %s: disabling sync", self.name)
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
        # Optimistic flip: WLED already restored, update the switch now
        # instead of making it wait for the final refresh.
        self.async_update_listeners()

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
