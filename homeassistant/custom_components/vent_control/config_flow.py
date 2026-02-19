"""Config flow for Vent Control integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import (
    CONF_HUB_HOST,
    CONF_HUB_PORT,
    CONF_POLL_INTERVAL,
    DEFAULT_HUB_HOST,
    DEFAULT_HUB_PORT,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HUB_HOST, default=DEFAULT_HUB_HOST): str,
        vol.Required(CONF_HUB_PORT, default=DEFAULT_HUB_PORT): int,
        vol.Optional(CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL): int,
    }
)


class VentControlConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Vent Control."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate connection to hub
            host = user_input[CONF_HUB_HOST]
            port = user_input[CONF_HUB_PORT]

            # Set unique ID to prevent duplicate entries
            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"Vent Hub ({host}:{port})",
                data={
                    CONF_HUB_HOST: host,
                    CONF_HUB_PORT: port,
                    CONF_POLL_INTERVAL: user_input.get(
                        CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                    ),
                    "device_addresses": [],
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
