"""WLED Hyperion Bridge integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .api import WLEDClient
from .const import (
    CONF_AREA_ID,
    CONF_DEVICES,
    CONF_HYPERION,
    DEFAULT_NAME,
    DOMAIN,
    PLATFORMS,
    SCAN_INTERVAL,
    STORAGE_KEY_TEMPLATE,
    STORAGE_VERSION,
)
from .coordinator import WLEDHyperionBridgeCoordinator
from .devices import devices_from_data, devices_from_entry
from .hyperion import HyperionClient, normalize_hyperion_config

_LOGGER = logging.getLogger(__name__)

WLEDHyperionBridgeConfigEntry = ConfigEntry[Any]


async def async_migrate_entry(
    hass: HomeAssistant, entry: WLEDHyperionBridgeConfigEntry
) -> bool:
    """Migrate legacy entries to bridge entries."""
    if entry.version >= 3 and CONF_DEVICES in entry.data:
        return True

    devices = devices_from_entry(entry)
    if not devices:
        devices = devices_from_data(entry.data)

    data = {
        CONF_NAME: entry.data.get(CONF_NAME, entry.title or DEFAULT_NAME),
        CONF_DEVICES: devices,
    }
    if CONF_AREA_ID in entry.data:
        data[CONF_AREA_ID] = entry.data[CONF_AREA_ID]

    hass.config_entries.async_update_entry(
        entry,
        data=data,
        version=3,
    )
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: WLEDHyperionBridgeConfigEntry
) -> bool:
    """Set up WLED Hyperion Bridge from a config entry."""
    session = async_get_clientsession(hass)
    devices = devices_from_entry(entry)
    clients = [
        WLEDClient(session=session, host=device["host"], port=device["port"])
        for device in devices
    ]
    hyperion_config: dict[str, Any] | None = None
    hyperion_client: HyperionClient | None = None
    raw_hyperion = entry.data.get(CONF_HYPERION)
    if isinstance(raw_hyperion, dict) and raw_hyperion.get("host"):
        try:
            hyperion_config = normalize_hyperion_config(raw_hyperion)
        except ValueError as err:
            _LOGGER.warning(
                "Ignoring invalid Hyperion config for bridge %s: %s",
                entry.title,
                err,
            )
            hyperion_config = None
        if hyperion_config is not None:
            hyperion_client = HyperionClient(
                host=hyperion_config["host"],
                port=hyperion_config["port"],
                token=hyperion_config["token"],
            )
    store: Store[dict[str, object]] = Store(
        hass,
        STORAGE_VERSION,
        STORAGE_KEY_TEMPLATE.format(entry_id=entry.entry_id),
    )
    coordinator = WLEDHyperionBridgeCoordinator(
        hass=hass,
        clients=clients,
        devices=devices,
        store=store,
        name=entry.data.get(CONF_NAME, DEFAULT_NAME),
        update_interval=SCAN_INTERVAL,
        hyperion=hyperion_client,
        hyperion_config=hyperion_config,
    )

    await coordinator.async_load_saved_snapshot()
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    platforms = [Platform(platform) for platform in PLATFORMS]
    await hass.config_entries.async_forward_entry_setups(entry, platforms)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: WLEDHyperionBridgeConfigEntry
) -> bool:
    """Unload a config entry."""
    platforms = [Platform(platform) for platform in PLATFORMS]
    return await hass.config_entries.async_unload_platforms(entry, platforms)


async def async_remove_config_entry(
    hass: HomeAssistant, entry: WLEDHyperionBridgeConfigEntry
) -> None:
    """Remove persisted snapshots when the bridge is deleted."""
    store: Store[dict[str, object]] = Store(
        hass,
        STORAGE_VERSION,
        STORAGE_KEY_TEMPLATE.format(entry_id=entry.entry_id),
    )
    await store.async_remove()
