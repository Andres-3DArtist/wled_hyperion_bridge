"""WLED Hyperion Bridge integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .api import WLEDClient
from .const import (
    CONF_HOST,
    CONF_PORT,
    DEFAULT_NAME,
    DOMAIN,
    PLATFORMS,
    SCAN_INTERVAL,
    STORAGE_KEY_TEMPLATE,
    STORAGE_VERSION,
)
from .coordinator import WLEDHyperionBridgeCoordinator

type WLEDHyperionBridgeConfigEntry = ConfigEntry[WLEDHyperionBridgeCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: WLEDHyperionBridgeConfigEntry
) -> bool:
    """Set up WLED Hyperion Bridge from a config entry."""
    session = async_get_clientsession(hass)
    client = WLEDClient(
        session=session,
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
    )
    store: Store[dict[str, object]] = Store(
        hass,
        STORAGE_VERSION,
        STORAGE_KEY_TEMPLATE.format(entry_id=entry.entry_id),
    )
    coordinator = WLEDHyperionBridgeCoordinator(
        hass=hass,
        client=client,
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
