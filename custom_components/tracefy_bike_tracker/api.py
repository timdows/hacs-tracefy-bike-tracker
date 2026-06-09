"""Tracefy app API client."""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .const import (
    APP_API_BASE,
    AUTH0_AUDIENCE,
    AUTH0_CLIENT_ID,
    AUTH0_DOMAIN,
    AUTH0_REALM,
    AUTH0_SCOPE,
)


class TracefyApiError(Exception):
    """Raised when Tracefy API communication fails."""


@dataclass
class TracefyToken:
    """Auth0 token response."""

    access_token: str
    refresh_token: str | None = None

    @classmethod
    def from_response(cls, response: dict[str, Any], old_refresh_token: str | None = None) -> "TracefyToken":
        """Create token data from an Auth0 response."""
        access_token = response.get("access_token")
        if not isinstance(access_token, str):
            raise TracefyApiError("Auth0 response did not include access_token")
        refresh_token = response.get("refresh_token")
        if not isinstance(refresh_token, str):
            refresh_token = old_refresh_token
        return cls(access_token=access_token, refresh_token=refresh_token)


class TracefyClient:
    """Small synchronous client for the Tracefy app API."""

    def __init__(
        self,
        email: str,
        password: str = "",
        *,
        access_token: str | None = None,
        refresh_token: str | None = None,
    ) -> None:
        """Initialize the client."""
        self.email = email
        self.password = password
        self.token = TracefyToken(access_token=access_token or "", refresh_token=refresh_token)

    def fetch_bikes(self) -> list[dict[str, Any]]:
        """Fetch bike data with location information."""
        self.ensure_token()

        initialize = self.app_api_request("GET", "/initialize")
        user = self.app_api_request("GET", "/user")
        entities = self.app_api_request("GET", "/entities")
        location_entities = select_location_entities(entities, initialize, user)
        locations = self.app_api_request(
            "POST",
            "/entities/locations",
            body={"entities": location_entities},
        )
        return build_bike_summary(entities if isinstance(entities, list) else location_entities, locations)

    def ensure_token(self) -> None:
        """Ensure the client has a valid access token."""
        if self.token.access_token and token_is_valid(self.token.access_token):
            return

        if self.token.refresh_token:
            try:
                self.token = self.refresh_token(self.token.refresh_token)
                return
            except TracefyApiError:
                pass

        self.token = self.login_with_password()

    def login_with_password(self) -> TracefyToken:
        """Login using Auth0 password realm grant."""
        if not self.password:
            raise TracefyApiError("No password available and refresh token failed")
        response = auth0_token_request(
            {
                "grant_type": "http://auth0.com/oauth/grant-type/password-realm",
                "client_id": AUTH0_CLIENT_ID,
                "username": self.email,
                "password": self.password,
                "realm": AUTH0_REALM,
                "audience": AUTH0_AUDIENCE,
                "scope": AUTH0_SCOPE,
            }
        )
        return TracefyToken.from_response(response)

    def refresh_token(self, refresh_token: str) -> TracefyToken:
        """Refresh the access token."""
        response = auth0_token_request(
            {
                "grant_type": "refresh_token",
                "client_id": AUTH0_CLIENT_ID,
                "refresh_token": refresh_token,
            }
        )
        return TracefyToken.from_response(response, old_refresh_token=refresh_token)

    def app_api_request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> Any:
        """Call the Tracefy app API and return the data field when present."""
        url = APP_API_BASE.rstrip("/") + "/" + path.lstrip("/")
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token.access_token}",
            "User-Agent": "HomeAssistantTracefyBikeTracker/0.1",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        parsed = request_json(req)
        if isinstance(parsed, dict) and "data" in parsed:
            return parsed["data"]
        return parsed


def auth0_token_request(body: dict[str, Any]) -> dict[str, Any]:
    """Call Auth0 /oauth/token."""
    req = urllib.request.Request(
        f"https://{AUTH0_DOMAIN}/oauth/token",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "HomeAssistantTracefyBikeTracker/0.1",
        },
        method="POST",
    )
    parsed = request_json(req)
    if not isinstance(parsed, dict):
        raise TracefyApiError("Auth0 returned a non-JSON response")
    if "access_token" not in parsed:
        error = parsed.get("error_description") or parsed.get("error") or parsed
        raise TracefyApiError(f"Auth0 token request failed: {error}")
    return parsed


def request_json(req: urllib.request.Request) -> Any:
    """Open a URL and parse JSON."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=30) as res:
            raw = res.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", errors="replace")
        raise TracefyApiError(f"HTTP {err.code}: {raw[:500]}") from err
    except urllib.error.URLError as err:
        raise TracefyApiError(str(err.reason)) from err

    try:
        return json.loads(raw)
    except json.JSONDecodeError as err:
        raise TracefyApiError(f"Expected JSON response: {raw[:500]}") from err


def token_is_valid(token: str, *, min_seconds_left: int = 120) -> bool:
    """Check JWT exp without verifying the signature."""
    payload = decode_jwt_payload(token)
    exp = payload.get("exp")
    return isinstance(exp, int) and exp > int(time.time()) + min_seconds_left


def decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode a JWT payload without verification."""
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    raw = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return {}


def select_location_entities(entities: Any, initialize: Any, user: Any) -> list[Any]:
    """Choose the entity list expected by /entities/locations."""
    if isinstance(initialize, dict) and isinstance(initialize.get("verified_entities"), list):
        return initialize["verified_entities"]
    if isinstance(user, dict) and isinstance(user.get("entities"), list):
        return user["entities"]
    if isinstance(entities, list):
        return minimal_location_entities(entities)
    return []


def minimal_location_entities(entities: list[Any]) -> list[Any]:
    """Fallback for /entities/locations when only full entities are available."""
    minimal = []
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        for key in ("id", "entity_id", "device_id"):
            if entity.get(key) is not None:
                minimal.append({key: entity[key]})
                break
    return minimal


def build_bike_summary(entities: list[Any], locations: Any) -> list[dict[str, Any]]:
    """Build bike summaries from entity and location responses."""
    location_by_imei: dict[str, Any] = {}
    if isinstance(locations, list):
        for item in locations:
            if isinstance(item, dict) and item.get("imei") is not None:
                location_by_imei[str(item["imei"])] = item

    bikes = []
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        imei = str(entity.get("imei") or "")
        location = location_by_imei.get(imei)
        device_data = location.get("device_data") if isinstance(location, dict) else entity.get("device_data")
        coordinates = find_coordinates(device_data) or find_coordinates(location) or find_coordinates(entity)
        bikes.append(
            {
                "imei": imei or None,
                "name": entity.get("user_bike_name") or entity.get("name") or imei or "Bike",
                "last_seen_at": entity.get("last_seen_at"),
                "positioned_at": device_data.get("positioned_at") if isinstance(device_data, dict) else None,
                "latitude": coordinates[0] if coordinates else None,
                "longitude": coordinates[1] if coordinates else None,
                "device_data": device_data,
                "entity": entity,
                "location": location,
            }
        )
    return bikes


def find_coordinates(value: Any) -> tuple[float, float] | None:
    """Find latitude/longitude in a nested API object."""
    if not isinstance(value, (dict, list)):
        return None

    if isinstance(value, dict):
        latitude = first_number(value, ("latitude", "lat"))
        longitude = first_number(value, ("longitude", "lng", "lon"))
        if latitude is not None and longitude is not None:
            return latitude, longitude

        coordinates = value.get("coordinates") or value.get("coordinate")
        if isinstance(coordinates, list) and len(coordinates) >= 2:
            first = coerce_float(coordinates[0])
            second = coerce_float(coordinates[1])
            if first is not None and second is not None:
                # GeoJSON usually stores [longitude, latitude].
                return second, first

        for item in value.values():
            found = find_coordinates(item)
            if found:
                return found

    if isinstance(value, list):
        for item in value:
            found = find_coordinates(item)
            if found:
                return found

    return None


def first_number(value: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    """Return the first numeric value for any key."""
    for key in keys:
        number = coerce_float(value.get(key))
        if number is not None:
            return number
    return None


def coerce_float(value: Any) -> float | None:
    """Coerce a value to float."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
