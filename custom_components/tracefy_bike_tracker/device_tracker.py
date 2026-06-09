"""Device tracker platform for Tracefy Bike Tracker."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_ACCOUNT_EMAIL,
    ATTR_BIKE_LOCATION,
    ATTR_LAST_UPDATE,
    CONF_BIKE_NAME,
    DOMAIN,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tracefy Bike Tracker device tracker entities."""
    async_add_entities([TracefyBikeTrackerEntity(entry)])


class TracefyBikeTrackerEntity(TrackerEntity):
    """Tracker entity representing a Tracefy bike."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the bike tracker."""
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_bike"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "manufacturer": "Tracefy",
            "name": entry.data[CONF_BIKE_NAME],
        }
        self._last_update = datetime.now(UTC)

    @property
    def source_type(self) -> SourceType:
        """Return the source type of the device."""
        return SourceType.GPS

    @property
    def latitude(self) -> float:
        """Return latitude value of the device."""
        return self._entry.data[CONF_LATITUDE]

    @property
    def longitude(self) -> float:
        """Return longitude value of the device."""
        return self._entry.data[CONF_LONGITUDE]

    @property
    def location_name(self) -> str | None:
        """Return a location name for the device."""
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        latitude = self._entry.data[CONF_LATITUDE]
        longitude = self._entry.data[CONF_LONGITUDE]

        return {
            ATTR_LAST_UPDATE: self._last_update.isoformat(),
            ATTR_ACCOUNT_EMAIL: self._entry.data[CONF_EMAIL],
            ATTR_BIKE_LOCATION: {
                "latitude": latitude,
                "longitude": longitude,
            },
        }
