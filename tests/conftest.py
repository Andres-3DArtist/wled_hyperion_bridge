"""Pytest bootstrap: minimal homeassistant stubs so unit tests run without HA."""

from __future__ import annotations

import logging
import sys
import types
from enum import Enum


def _ensure(name: str) -> types.ModuleType:
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return mod


def _install() -> None:
    try:
        import homeassistant  # noqa: F401
        return
    except ImportError:
        pass

    ha = _ensure("homeassistant")
    ha.__path__ = []  # type: ignore[attr-defined]

    const = _ensure("homeassistant.const")
    const.CONF_NAME = "name"

    class Platform(str, Enum):
        SWITCH = "switch"

    const.Platform = Platform

    config_entries = _ensure("homeassistant.config_entries")

    class ConfigEntry(dict):  # type: ignore[no-redef]
        def __class_getitem__(cls, item):
            return cls

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.data: dict = {}
            self.options: dict = {}
            self.entry_id: str = "test-entry"
            self.title: str = "Test"
            self.runtime_data = None
            self.version: int = 3

    class ConfigFlow:
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__()

    class OptionsFlow:
        """Mimic HA >= 2024.11: config_entry is a read-only property."""

        def __init__(self, *args, **kwargs):
            if args or kwargs:
                raise TypeError(
                    "OptionsFlow takes no constructor arguments; "
                    "HA injects config_entry"
                )
            self._config_entry = None

        @property
        def config_entry(self):
            if self._config_entry is None:
                raise ValueError("config entry not available yet")
            return self._config_entry

    config_entries.ConfigEntry = ConfigEntry
    config_entries.ConfigFlow = ConfigFlow
    config_entries.OptionsFlow = OptionsFlow

    core = _ensure("homeassistant.core")

    class HomeAssistant:
        pass

    core.HomeAssistant = HomeAssistant

    exceptions = _ensure("homeassistant.exceptions")

    class HomeAssistantError(Exception):
        pass

    exceptions.HomeAssistantError = HomeAssistantError

    helpers = _ensure("homeassistant.helpers")
    helpers.__path__ = []  # type: ignore[attr-defined]

    aiohttp_client = _ensure("homeassistant.helpers.aiohttp_client")
    aiohttp_client.async_get_clientsession = lambda hass: None

    storage = _ensure("homeassistant.helpers.storage")

    class Store:
        def __init__(self, hass=None, version=1, key="test"):
            self._data = None

        async def async_load(self):
            return self._data

        async def async_save(self, data):
            self._data = data

        async def async_remove(self):
            self._data = None

    storage.Store = Store

    update_coordinator = _ensure("homeassistant.helpers.update_coordinator")

    class UpdateFailed(Exception):
        pass

    class DataUpdateCoordinator:
        def __class_getitem__(cls, item):
            return cls

        def __init__(self, hass, logger, name=None, update_interval=None):
            self.hass = hass
            self.logger = logger or logging.getLogger(__name__)
            self.name = name
            self.update_interval = update_interval
            self.data = None
            self.last_update_success = True

        async def async_request_refresh(self):
            try:
                self.data = await self._async_update_data()
                self.last_update_success = True
            except Exception:
                self.last_update_success = False
                raise

        async def async_config_entry_first_refresh(self):
            await self.async_request_refresh()

    class CoordinatorEntity:
        def __class_getitem__(cls, item):
            return cls

        def __init__(self, coordinator):
            self.coordinator = coordinator

    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
    update_coordinator.UpdateFailed = UpdateFailed
    update_coordinator.CoordinatorEntity = CoordinatorEntity

    selector_mod = _ensure("homeassistant.helpers.selector")

    class _Base:
        def __init__(self, *args, **kwargs):
            pass

    selector_mod.AreaSelector = _Base
    selector_mod.SelectSelector = _Base
    selector_mod.SelectSelectorConfig = _Base
    selector_mod.SelectOptionDict = _Base
    selector_mod.BooleanSelector = _Base
    selector_mod.NumberSelector = _Base
    selector_mod.NumberSelectorConfig = _Base

    for name in (
        "homeassistant.helpers.area_registry",
        "homeassistant.helpers.device_registry",
        "homeassistant.helpers.entity_platform",
        "homeassistant.helpers.diagnostics",
        "homeassistant.components",
        "homeassistant.components.switch",
    ):
        mod = _ensure(name)
        if name.endswith("device_registry"):
            mod.DeviceInfo = dict
        if name.endswith("entity_platform"):
            mod.AddEntitiesCallback = object
        if name.endswith("diagnostics"):
            mod.async_redact_data = lambda data, keys: data
        if name.endswith("switch"):

            class SwitchEntity:
                pass

            mod.SwitchEntity = SwitchEntity


_install()
