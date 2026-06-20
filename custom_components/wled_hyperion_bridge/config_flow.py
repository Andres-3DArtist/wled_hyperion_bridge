"""Config flow for WLED Hyperion Bridge."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import WLEDAPIError, WLEDClient
from .const import (
    CONF_AREA_ID,
    CONF_BRIDGE_NAME,
    CONF_DEVICE_NAME,
    CONF_DEVICES,
    CONF_HOST,
    CONF_PORT,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DOMAIN,
)
from .devices import devices_from_entry, merge_device, normalize_device


async def validate_device(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate one WLED device and return normalized device data."""
    device = normalize_device(data)
    client = WLEDClient(
        session=async_get_clientsession(hass),
        host=device[CONF_HOST],
        port=device[CONF_PORT],
    )
    await client.async_get_state()
    return device


def _device_schema() -> vol.Schema:
    """Return the WLED member form schema."""
    return vol.Schema(
        {
            vol.Required(CONF_HOST): str,
            vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
            vol.Optional(CONF_DEVICE_NAME): str,
        }
    )


def _bridge_schema() -> vol.Schema:
    """Return the bridge creation form schema."""
    return vol.Schema(
        {
            vol.Required(CONF_BRIDGE_NAME, default=DEFAULT_NAME): str,
            vol.Required(CONF_AREA_ID): selector.AreaSelector(),
        }
    )


class WLEDHyperionBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for WLED Hyperion Bridge."""

    VERSION = 3

    def __init__(self) -> None:
        """Initialize flow state."""
        self._bridge_name = DEFAULT_NAME
        self._area_id: str | None = None
        self._devices: list[dict[str, Any]] = []
        self._target_entry: config_entries.ConfigEntry | None = None

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return WLEDHyperionBridgeOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Route setup to bridge creation or existing bridge membership."""
        entries = self._async_current_entries()
        if entries:
            return await self.async_step_action()
        return await self.async_step_bridge(user_input)

    async def async_step_action(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Choose whether to create a bridge or add a WLED to an existing one."""
        entries = self._async_current_entries()
        if user_input is not None:
            action = str(user_input["action"])
            if action == "create_bridge":
                return await self.async_step_bridge()

            entry_id = action.removeprefix("add_device:")
            self._target_entry = next(
                entry for entry in entries if entry.entry_id == entry_id
            )
            if CONF_AREA_ID not in self._target_entry.data:
                return await self.async_step_assign_area()
            return await self.async_step_existing_device()

        action_options = {"create_bridge": "Create new bridge"}
        action_options.update(
            {
                f"add_device:{entry.entry_id}": f"Add WLED to {entry.title}"
                for entry in entries
            }
        )
        return self.async_show_form(
            step_id="action",
            data_schema=vol.Schema({vol.Required("action"): vol.In(action_options)}),
        )

    async def async_step_bridge(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Create the bridge and assign it to a Home Assistant area."""
        if user_input is not None:
            self._bridge_name = str(
                user_input.get(CONF_BRIDGE_NAME) or DEFAULT_NAME
            ).strip()
            self._area_id = str(user_input[CONF_AREA_ID])
            return await self.async_step_first_device()

        return self.async_show_form(
            step_id="bridge",
            data_schema=_bridge_schema(),
        )

    async def async_step_first_device(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Add the required first WLED member to a new bridge."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                device = await validate_device(self.hass, user_input)
            except WLEDAPIError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                self._devices = merge_device(self._devices, device)
                await self.async_set_unique_id(
                    f"bridge:{self._area_id}:{self._bridge_name.lower()}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=self._bridge_name,
                    data={
                        CONF_NAME: self._bridge_name,
                        CONF_AREA_ID: self._area_id,
                        CONF_DEVICES: self._devices,
                    },
                )

        return self.async_show_form(
            step_id="first_device",
            data_schema=_device_schema(),
            errors=errors,
            description_placeholders={"bridge": self._bridge_name},
        )

    async def async_step_assign_area(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Assign an existing bridge to a Home Assistant area."""
        if self._target_entry is None:
            return await self.async_step_user()

        if user_input is not None:
            data = dict(self._target_entry.data)
            data[CONF_AREA_ID] = str(user_input[CONF_AREA_ID])
            self.hass.config_entries.async_update_entry(
                self._target_entry,
                data=data,
            )
            return await self.async_step_existing_device()

        return self.async_show_form(
            step_id="assign_area",
            data_schema=vol.Schema(
                {vol.Required(CONF_AREA_ID): selector.AreaSelector()}
            ),
            description_placeholders={"bridge": self._target_entry.title},
        )

    async def async_step_existing_device(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Add one WLED member to an existing bridge."""
        errors: dict[str, str] = {}
        bridge_name = self._target_entry.title if self._target_entry else DEFAULT_NAME

        if user_input is not None and self._target_entry is not None:
            try:
                device = await validate_device(self.hass, user_input)
            except WLEDAPIError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                devices = merge_device(devices_from_entry(self._target_entry), device)
                _update_bridge_devices_and_schedule_reload(
                    self.hass, self._target_entry, devices
                )
                return self.async_abort(reason="wled_device_added")

        return self.async_show_form(
            step_id="existing_device",
            data_schema=_device_schema(),
            errors=errors,
            description_placeholders={"bridge": bridge_name},
        )


class WLEDHyperionBridgeOptionsFlow(config_entries.OptionsFlow):
    """Handle options for a WLED Hyperion Bridge."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Add one WLED member to an existing bridge."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                device = await validate_device(self.hass, user_input)
            except WLEDAPIError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                devices = merge_device(devices_from_entry(self.config_entry), device)
                _update_bridge_devices_and_schedule_reload(
                    self.hass, self.config_entry, devices
                )
                return self.async_create_entry(
                    title="",
                    data={},
                )

        return self.async_show_form(
            step_id="init",
            data_schema=_device_schema(),
            errors=errors,
            description_placeholders={"bridge": self.config_entry.title},
        )


def _update_bridge_devices_and_schedule_reload(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
    devices: list[dict[str, Any]],
) -> None:
    """Persist bridge WLED membership and schedule a bridge reload."""
    data = dict(entry.data)
    data[CONF_DEVICES] = devices
    hass.config_entries.async_update_entry(entry, data=data)
    hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))
