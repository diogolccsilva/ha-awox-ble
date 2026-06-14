"""Config and options flow for the AwoX Smart Plug integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import bluetooth
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.device_registry import format_mac

from .const import (
    CONF_ADDRESS,
    CONF_SCAN_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)


class AwoxPlugConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick a discovered device or type a MAC address."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = str(user_input[CONF_ADDRESS]).strip().upper()
            if len(address.replace(":", "").replace("-", "")) != 12:
                errors[CONF_ADDRESS] = "invalid_address"
            else:
                await self.async_set_unique_id(format_mac(address))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME, DEFAULT_NAME),
                    data={
                        CONF_ADDRESS: address,
                        CONF_NAME: user_input.get(CONF_NAME, DEFAULT_NAME),
                    },
                )

        # Offer currently-visible connectable devices as suggestions, but allow
        # any MAC to be typed in (custom_value) since the plug may not be
        # advertising at this exact moment.
        configured = self._async_current_ids()
        options: list[selector.SelectOptionDict] = []
        for info in bluetooth.async_discovered_service_info(
            self.hass, connectable=True
        ):
            if format_mac(info.address) in configured:
                continue
            label = f"{info.name or 'Unknown'} ({info.address})"
            options.append(selector.SelectOptionDict(value=info.address, label=label))

        address_selector = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=options,
                custom_value=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )

        schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): address_selector,
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return AwoxPlugOptionsFlow()


class AwoxPlugOptionsFlow(OptionsFlow):
    """Allow changing the polling interval after setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
