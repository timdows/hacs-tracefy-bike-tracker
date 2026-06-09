"""Fetch Tracefy bike information into timestamped JSON files.

This debug utility is intentionally separate from the Home Assistant integration.
It keeps sensitive config/token files gitignored in this directory.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

AUTH0_DOMAIN = "tracefy.eu.auth0.com"
APP_CLIENT_ID = "p8FPcTM9ZuvaWoagIL0J9TDOUlEAZycI"
APP_AUDIENCE = "https://app.pro.tracefy.io"
APP_REDIRECT_URI = "com.tracefy.auth0://tracefy.eu.auth0.com/android/com.tracefy/callback"
APP_API_BASE = "https://app-pro.tracefy.io"

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "config.json"
DEFAULT_TOKEN = ROOT / "token.json"
LEGACY_APP_TOKEN = ROOT.parent / "debug_browser" / "app_token.json"
PENDING_PKCE = ROOT / "pending_pkce.json"
USER_DATA_DIR = ROOT / ".user_data"
OUTPUT_DIR = ROOT / "output"


def get_bike_information(config_path: str | Path = DEFAULT_CONFIG) -> Path:
    """Get a valid token, fetch bike data, and write a timestamped JSON file."""
    config = load_config(Path(config_path))
    token_response = get_valid_token(config)
    access_token = token_response["access_token"]

    initialize = app_api_request(access_token, "GET", "/initialize")
    user = app_api_request(access_token, "GET", "/user")
    entities = app_api_request(access_token, "GET", "/entities")
    entity_list = select_entities(entities, initialize, user)
    try:
        locations = app_api_request(
            access_token,
            "POST",
            "/entities/locations",
            body={"entities": entity_list},
        )
    except RuntimeError as exc:
        locations = {"error": str(exc), "request_body": {"entities": entity_list}}

    now = datetime.now(UTC)
    payload = {
        "fetched_at": now.isoformat(),
        "api_base": APP_API_BASE,
        "initialize": initialize,
        "user": user,
        "entities": entities,
        "locations": locations,
        "bikes": build_bike_summary(entities if isinstance(entities, list) else entity_list, locations),
    }

    OUTPUT_DIR.mkdir(exist_ok=True)
    output = OUTPUT_DIR / f"bike_info_{now.strftime('%Y%m%d_%H%M%S')}.json"
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return output


def main() -> int:
    """Run the CLI."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--callback-url", default=os.getenv("TRACEFY_CALLBACK_URL"))
    args = parser.parse_args()

    if args.callback_url:
        token_response = finish_callback(args.callback_url)
        save_token(token_response)
        print(f"Wrote token cache to {DEFAULT_TOKEN}")
        print("Run again without --callback-url to fetch bike information.")
        return 0

    output = get_bike_information(args.config)
    print(f"Wrote bike information to {output}")
    return 0


def get_valid_token(config: dict[str, Any]) -> dict[str, Any]:
    """Return a cached valid token, refresh it, or start the browser login flow."""
    token_response = load_token()
    if token_response and token_is_valid(token_response):
        return token_response

    if token_response and token_response.get("refresh_token"):
        try:
            refreshed = refresh_token(str(token_response["refresh_token"]))
            save_token(refreshed)
            return refreshed
        except RuntimeError as exc:
            print(f"Refresh token failed: {exc}")

    token_response = browser_login(config)
    save_token(token_response)
    return token_response


def browser_login(config: dict[str, Any]) -> dict[str, Any]:
    """Run Auth0 PKCE login in Chromium and return a token response."""
    email = config.get("email") or os.getenv("TRACEFY_EMAIL")
    password = config.get("password") or os.getenv("TRACEFY_PASSWORD")
    use_manual = bool(config.get("manual_login", False))

    if use_manual or not email or not password:
        return manual_login()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Automatic login needs Playwright. Either install/use Playwright or set manual_login=true."
        ) from exc

    headless = bool(config.get("headless", False))
    keep_open = bool(config.get("keep_browser_open_on_failure", True))

    verifier = token_urlsafe(64)
    state = token_urlsafe(32)
    nonce = token_urlsafe(32)
    challenge = pkce_challenge(verifier)
    PENDING_PKCE.write_text(
        json.dumps({"verifier": verifier, "state": state}, indent=2),
        encoding="utf-8",
    )

    callback_url: str | None = None
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(str(USER_DATA_DIR), headless=headless)
        page = context.new_page()

        def remember_callback(url: str) -> None:
            nonlocal callback_url
            if url.startswith(APP_REDIRECT_URI):
                callback_url = url

        page.on("request", lambda request: remember_callback(request.url))
        page.on("requestfailed", lambda request: remember_callback(request.url))
        page.on("framenavigated", lambda frame: remember_callback(frame.url))

        try:
            page.goto(build_authorize_url(challenge, state, nonce), wait_until="domcontentloaded", timeout=60_000)
            if email and password:
                fill_login_if_visible(page, str(email), str(password))

            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                if callback_url:
                    code = code_from_callback_url(callback_url, expected_state=state)
                    token_response = exchange_code(code, verifier)
                    PENDING_PKCE.unlink(missing_ok=True)
                    context.close()
                    return token_response
                if page.url.startswith(APP_REDIRECT_URI):
                    code = code_from_callback_url(page.url, expected_state=state)
                    token_response = exchange_code(code, verifier)
                    PENDING_PKCE.unlink(missing_ok=True)
                    context.close()
                    return token_response
                page.wait_for_timeout(500)

            raise RuntimeError("Timed out waiting for Auth0 callback code")
        except Exception:
            if keep_open and not headless:
                print("Browser left open for inspection. Press Enter here to close it.")
                try:
                    input()
                except EOFError:
                    pass
            context.close()
            raise


def manual_login() -> dict[str, Any]:
    """Run Auth0 PKCE login without third-party Python packages."""
    verifier = token_urlsafe(64)
    state = token_urlsafe(32)
    nonce = token_urlsafe(32)
    challenge = pkce_challenge(verifier)
    PENDING_PKCE.write_text(
        json.dumps({"verifier": verifier, "state": state}, indent=2),
        encoding="utf-8",
    )

    print("Open this URL in your browser and log in:")
    print(build_authorize_url(challenge, state, nonce))
    print()
    print("After login, Windows may show that the com.tracefy.auth0:// URL cannot be opened.")
    callback_url = input("Paste the full callback URL here: ").strip()
    code = code_from_callback_url(callback_url, expected_state=state)
    token_response = exchange_code(code, verifier)
    PENDING_PKCE.unlink(missing_ok=True)
    return token_response


def finish_callback(callback_url: str) -> dict[str, Any]:
    """Exchange a custom-scheme callback URL from a pending browser login."""
    if not PENDING_PKCE.exists():
        raise RuntimeError("No pending PKCE file found. Run without --callback-url first.")
    pending = json.loads(PENDING_PKCE.read_text(encoding="utf-8"))
    verifier = pending["verifier"]
    state = pending["state"]
    code = code_from_callback_url(callback_url, expected_state=state)
    token_response = exchange_code(code, verifier)
    PENDING_PKCE.unlink(missing_ok=True)
    return token_response


def app_api_request(
    token: str,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
) -> Any:
    """Call the Tracefy app API and return the response data field when present."""
    url = APP_API_BASE.rstrip("/") + "/" + path.lstrip("/")
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "TracefyGetBikeDebug/0.1",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=30) as res:
            parsed = json.loads(res.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed HTTP {err.code}: {raw[:1000]}") from err

    if isinstance(parsed, dict) and "data" in parsed:
        return parsed["data"]
    return parsed


def select_entities(entities: Any, initialize: Any, user: Any) -> list[Any]:
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
    """Build a compact bike summary while preserving full raw data elsewhere."""
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
        bikes.append(
            {
                "imei": imei or None,
                "name": entity.get("user_bike_name") or entity.get("name"),
                "last_seen_at": entity.get("last_seen_at"),
                "positioned_at": device_data.get("positioned_at") if isinstance(device_data, dict) else None,
                "device_data": device_data,
                "entity": entity,
                "location": location,
            }
        )
    return bikes


def load_config(path: Path) -> dict[str, Any]:
    """Load JSON config."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_token() -> dict[str, Any] | None:
    """Load cached token response."""
    if DEFAULT_TOKEN.exists():
        return json.loads(DEFAULT_TOKEN.read_text(encoding="utf-8"))
    if LEGACY_APP_TOKEN.exists():
        return json.loads(LEGACY_APP_TOKEN.read_text(encoding="utf-8"))
    return None


def save_token(token_response: dict[str, Any]) -> None:
    """Save token response to the gitignored token cache."""
    DEFAULT_TOKEN.write_text(json.dumps(token_response, indent=2), encoding="utf-8")


def token_is_valid(token_response: dict[str, Any], *, min_seconds_left: int = 120) -> bool:
    """Check JWT exp without verifying the signature."""
    access_token = token_response.get("access_token")
    if not isinstance(access_token, str):
        return False
    payload = decode_jwt_payload(access_token)
    exp = payload.get("exp")
    if not isinstance(exp, int):
        return False
    return exp > int(time.time()) + min_seconds_left


def decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode a JWT payload without verification."""
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    raw = parts[1] + "=" * (-len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8"))


def refresh_token(refresh_token_value: str) -> dict[str, Any]:
    """Refresh the Auth0 access token."""
    body = {
        "grant_type": "refresh_token",
        "client_id": APP_CLIENT_ID,
        "refresh_token": refresh_token_value,
    }
    refreshed = auth0_token_request(body)
    if "refresh_token" not in refreshed:
        refreshed["refresh_token"] = refresh_token_value
    return refreshed


def exchange_code(code: str, verifier: str) -> dict[str, Any]:
    """Exchange Auth0 authorization code for tokens."""
    return auth0_token_request(
        {
            "grant_type": "authorization_code",
            "client_id": APP_CLIENT_ID,
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": APP_REDIRECT_URI,
        }
    )


def auth0_token_request(body: dict[str, Any]) -> dict[str, Any]:
    """Call Auth0 /oauth/token."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"https://{AUTH0_DOMAIN}/oauth/token",
        data=data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "TracefyGetBikeDebug/0.1",
        },
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=30) as res:
            parsed = json.loads(res.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Auth0 token request failed HTTP {err.code}: {raw[:1000]}") from err

    if "access_token" not in parsed:
        raise RuntimeError(f"Auth0 token response did not include access_token: {parsed}")
    return parsed


def token_urlsafe(size: int) -> str:
    """Return a URL-safe random token without padding."""
    return secrets.token_urlsafe(size).rstrip("=")


def pkce_challenge(verifier: str) -> str:
    """Return an S256 PKCE challenge."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def build_authorize_url(challenge: str, state: str, nonce: str) -> str:
    """Build the mobile Auth0 authorize URL."""
    params = {
        "scope": "openid profile email offline_access",
        "client_id": APP_CLIENT_ID,
        "redirect_uri": APP_REDIRECT_URI,
        "response_type": "code",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "nonce": nonce,
        "audience": APP_AUDIENCE,
    }
    return f"https://{AUTH0_DOMAIN}/authorize?{urllib.parse.urlencode(params)}"


def code_from_callback_url(callback_url: str, *, expected_state: str | None) -> str:
    """Extract and validate the authorization code from the mobile callback URL."""
    parsed = urllib.parse.urlparse(callback_url)
    query = urllib.parse.parse_qs(parsed.query)
    if query.get("error"):
        raise RuntimeError(f"{query.get('error', [''])[0]}: {query.get('error_description', [''])[0]}")
    code = query.get("code", [None])[0]
    if not code:
        raise RuntimeError("Callback URL did not contain a code")
    if expected_state is not None and query.get("state", [None])[0] != expected_state:
        raise RuntimeError("Auth0 returned a mismatching state")
    return code


def fill_login_if_visible(page: Any, email: str, password: str) -> None:
    """Best-effort fill for Auth0 Universal Login."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    try:
        page.get_by_label("Email").fill(email, timeout=10_000)
    except PlaywrightTimeoutError:
        try:
            page.locator("input[type='email']").first.fill(email, timeout=5_000)
        except PlaywrightTimeoutError:
            return

    page.locator("input[type='password']").first.fill(password, timeout=5_000)

    for label in ("Continue", "Log in", "Login", "Inloggen"):
        try:
            page.get_by_role("button", name=label).click(timeout=2_000)
            return
        except PlaywrightTimeoutError:
            continue

    page.locator("button[type='submit']").first.click(timeout=5_000)


if __name__ == "__main__":
    raise SystemExit(main())
