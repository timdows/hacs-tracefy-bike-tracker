"""Device tracker platform for Tracefy Bike Tracker."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_ACCOUNT_EMAIL,
    ATTR_BIKE_LOCATION,
    ATTR_BUSINESS_NAME,
    ATTR_DISTANCE,
    ATTR_EXTERNAL_VOLTAGE,
    ATTR_FETCHED_AT,
    ATTR_FRAME_NUMBER,
    ATTR_IMEI,
    ATTR_KIWA_CERTIFICATE_NUMBER,
    ATTR_LAST_UPDATE,
    ATTR_MOVEMENT,
    ATTR_POSITIONED_AT,
    ATTR_SPEED,
    ATTR_STARTED_AT,
    DOMAIN,
)
from .coordinator import TracefyDataCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tracefy Bike Tracker device tracker entities."""
    coordinator: TracefyDataCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        TracefyBikeTrackerEntity(coordinator, entry, bike)
        for bike in coordinator.data or []
    )


class TracefyBikeTrackerEntity(CoordinatorEntity[TracefyDataCoordinator], TrackerEntity):
    """Tracker entity representing a Tracefy bike."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: TracefyDataCoordinator,
        entry: ConfigEntry,
        bike: dict[str, Any],
    ) -> None:
        """Initialize the bike tracker."""
        super().__init__(coordinator)
        self._entry = entry
        self._bike_key = bike_key(bike)
        self._attr_unique_id = f"{entry.entry_id}_{self._bike_key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._bike_key)},
            "manufacturer": "Tracefy",
            "name": bike_name(bike),
        }

    @property
    def source_type(self) -> SourceType:
        """Return the source type of the device."""
        return SourceType.GPS

    @property
    def available(self) -> bool:
        """Return if the bike has location coordinates."""
        return self.bike is not None and self.latitude is not None and self.longitude is not None

    @property
    def latitude(self) -> float | None:
        """Return latitude value of the device."""
        bike = self.bike
        if not bike:
            return None
        return bike.get("latitude")

    @property
    def longitude(self) -> float | None:
        """Return longitude value of the device."""
        bike = self.bike
        if not bike:
            return None
        return bike.get("longitude")

    @property
    def location_name(self) -> str | None:
        """Return a location name for the device."""
        return None

    @property
    def bike(self) -> dict[str, Any] | None:
        """Return the latest bike data for this entity."""
        for bike in self.coordinator.data or []:
            if bike_key(bike) == self._bike_key:
                return bike
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        bike = self.bike or {}
        latitude = bike.get("latitude")
        longitude = bike.get("longitude")

        return {
            ATTR_LAST_UPDATE: bike.get("last_seen_at") or bike.get("positioned_at"),
            ATTR_ACCOUNT_EMAIL: self._entry.data[CONF_EMAIL],
            ATTR_IMEI: bike.get("imei"),
            ATTR_SPEED: bike.get("speed"),
            ATTR_MOVEMENT: bike.get("movement"),
            ATTR_EXTERNAL_VOLTAGE: bike.get("external_voltage"),
            ATTR_KIWA_CERTIFICATE_NUMBER: bike.get("kiwa_certificate_number"),
            ATTR_STARTED_AT: bike.get("started_at"),
            ATTR_FRAME_NUMBER: bike.get("frame_number"),
            ATTR_DISTANCE: bike.get("distance"),
            ATTR_POSITIONED_AT: bike.get("positioned_at"),
            ATTR_FETCHED_AT: bike.get("fetched_at"),
            ATTR_BUSINESS_NAME: bike.get("business_name"),
            ATTR_BIKE_LOCATION: {
                "latitude": latitude,
                "longitude": longitude,
            },
        }


def bike_key(bike: dict[str, Any]) -> str:
    """Return a stable bike key."""
    return str(bike.get("imei") or bike.get("name") or "bike")


def bike_name(bike: dict[str, Any]) -> str:
    """Return a display name for a bike."""
    return str(bike.get("name") or bike.get("imei") or "Tracefy Bike")
