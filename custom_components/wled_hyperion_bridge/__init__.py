"""WLED Hyperion Bridge integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .api import WLEDClient
from .const import (
    CONF_AREA_ID,
    CONF_DEVICES,
    DEFAULT_NAME,
    PLATFORMS,
    SCAN_INTERVAL,
    STORAGE_KEY_TEMPLATE,
    STORAGE_VERSION,
)
from .coordinator import WLEDHyperionBridgeCoordinator
from .devices import devices_from_data, devices_from_entry

type WLEDHyperionBridgeConfigEntry = ConfigEntry[WLEDHyperionBridgeCoordinator]


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
