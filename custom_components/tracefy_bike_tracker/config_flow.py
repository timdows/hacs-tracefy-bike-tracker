"""Config flow for Tracefy Bike Tracker."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_BIKE_NAME, DEFAULT_BIKE_NAME, DOMAIN


class TracefyBikeTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tracefy Bike Tracker."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_EMAIL])
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=user_input[CONF_BIKE_NAME],
                data=user_input,
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_BIKE_NAME, default=DEFAULT_BIKE_NAME): str,
                vol.Required(CONF_LATITUDE, default=0.0): vol.Coerce(float),
                vol.Required(CONF_LONGITUDE, default=0.0): vol.Coerce(float),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )
