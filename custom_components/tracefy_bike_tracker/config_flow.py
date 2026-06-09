"""Config flow for Tracefy Bike Tracker."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL
from homeassistant.data_entry_flow import FlowResult

from .api import TracefyApiError, TracefyClient
from .const import CONF_ACCESS_TOKEN, CONF_REFRESH_TOKEN, DOMAIN


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

            try:
                token = await self.hass.async_add_executor_job(
                    self._validate_input,
                    user_input[CONF_EMAIL],
                    user_input[CONF_REFRESH_TOKEN],
                )
            except TracefyApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_EMAIL],
                    data={
                        **user_input,
                        CONF_ACCESS_TOKEN: token.access_token,
                        CONF_REFRESH_TOKEN: token.refresh_token,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_REFRESH_TOKEN): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    def _validate_input(email: str, refresh_token: str):
        """Validate refresh token and return an Auth0 token."""
        client = TracefyClient(email, refresh_token=refresh_token)
        token = client.refresh_token(refresh_token)
        client.token = token
        client.fetch_bikes()
        return client.token
