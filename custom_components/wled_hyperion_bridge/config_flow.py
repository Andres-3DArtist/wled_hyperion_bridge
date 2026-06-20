"""Config flow for WLED Hyperion Bridge."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import WLEDAPIError, WLEDClient
from .const import CONF_DEVICES, CONF_HOST, CONF_PORT, DEFAULT_NAME, DEFAULT_PORT, DOMAIN
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


def _device_schema(default_name: str | None = None) -> vol.Schema:
    """Return the WLED member form schema."""
    schema: dict[Any, Any] = {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
    }
    if default_name is None:
        schema[vol.Optional(CONF_NAME)] = str
    else:
        schema[vol.Optional(CONF_NAME, default=default_name)] = str
    return vol.Schema(schema)


class WLEDHyperionBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for WLED Hyperion Bridge."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize flow state."""
        self._zone_name = DEFAULT_NAME
        self._devices: list[dict[str, Any]] = []

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return WLEDHyperionBridgeOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Create a bridge zone."""
        if user_input is not None:
            self._zone_name = str(user_input.get(CONF_NAME) or DEFAULT_NAME).strip()
            return await self.async_step_device()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_NAME, default=DEFAULT_NAME): str}
            ),
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Add one WLED member to the zone."""
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
                return await self.async_step_more_devices()

        return self.async_show_form(
            step_id="device",
            data_schema=_device_schema(),
            errors=errors,
        )

    async def async_step_more_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Ask whether another WLED member should be added."""
        if user_input is not None:
            if bool(user_input.get("add_another", False)):
                return await self.async_step_device()

            unique_members = ",".join(sorted(device["id"] for device in self._devices))
            await self.async_set_unique_id(f"zone:{unique_members}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=self._zone_name,
                data={
                    CONF_NAME: self._zone_name,
                    CONF_DEVICES: self._devices,
                },
            )

        return self.async_show_form(
            step_id="more_devices",
            data_schema=vol.Schema({vol.Required("add_another", default=False): bool}),
            description_placeholders={"count": str(len(self._devices))},
        )


class WLEDHyperionBridgeOptionsFlow(config_entries.OptionsFlow):
    """Handle options for a WLED Hyperion Bridge zone."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Add one WLED member to an existing zone."""
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
                return self.async_create_entry(
                    title="",
                    data={CONF_DEVICES: devices},
                )

        return self.async_show_form(
            step_id="init",
            data_schema=_device_schema(),
            errors=errors,
        )
