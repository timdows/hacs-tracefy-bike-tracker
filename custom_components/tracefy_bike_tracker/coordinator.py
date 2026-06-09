"""Data coordinator for Tracefy Bike Tracker."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import TracefyApiError, TracefyClient
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

LOGGER = logging.getLogger(__name__)


class TracefyDataCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    """Fetch Tracefy bike data."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            logger=LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.config_entry = entry
        self.client = TracefyClient(
            entry.data[CONF_EMAIL],
            access_token=entry.data.get(CONF_ACCESS_TOKEN),
            refresh_token=entry.data.get(CONF_REFRESH_TOKEN),
        )

    async def _async_update_data(self) -> list[dict[str, Any]]:
        """Fetch latest data from Tracefy."""
        try:
            bikes = await self.hass.async_add_executor_job(self.client.fetch_bikes)
        except TracefyApiError as err:
            if is_auth_error(err):
                raise ConfigEntryAuthFailed(str(err)) from err
            raise UpdateFailed(str(err)) from err

        await self._async_persist_tokens()
        return bikes

    async def _async_persist_tokens(self) -> None:
        """Persist refreshed tokens into the config entry."""
        updates: dict[str, Any] = {}
        if self.client.token.access_token and self.client.token.access_token != self.config_entry.data.get(CONF_ACCESS_TOKEN):
            updates[CONF_ACCESS_TOKEN] = self.client.token.access_token
        if self.client.token.refresh_token and self.client.token.refresh_token != self.config_entry.data.get(CONF_REFRESH_TOKEN):
            updates[CONF_REFRESH_TOKEN] = self.client.token.refresh_token
        if not updates:
            return

        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={**self.config_entry.data, **updates},
        )


def is_auth_error(error: TracefyApiError) -> bool:
    """Return whether an API error should trigger reauth."""
    message = str(error).lower()
    return (
        "auth0" in message
        or "refresh token" in message
        or "access_token" in message
        or "no password available" in message
    )
