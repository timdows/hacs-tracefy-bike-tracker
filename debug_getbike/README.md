# Tracefy Get Bike Debug

This directory contains a focused debug client for getting Tracefy bike data.

Sensitive/generated files are gitignored:

- `config.json`
- `token.json`
- `pending_pkce.json`
- `.user_data/`
- `output/`

## Usage

Copy or create `config.json` with your Tracefy login data. The intended config is the same shape as `debug_browser/config.json`.

Run:

```powershell
python debug_getbike/getbike.py
```

The script will:

1. Use `debug_getbike/token.json` if the cached access token is still valid.
2. Refresh with the cached refresh token when possible.
3. Otherwise use Playwright to log in with `config.json` credentials and request a new app-scoped token.
4. Call the app API:
   - `GET https://app-pro.tracefy.io/initialize`
   - `GET https://app-pro.tracefy.io/user`
   - `GET https://app-pro.tracefy.io/entities`
   - `POST https://app-pro.tracefy.io/entities/locations`
5. Write a timestamped file to `debug_getbike/output/bike_info_YYYYMMDD_HHMMSS.json`.

If Windows shows a `com.tracefy.auth0://...callback?...` URL that it cannot open, copy that full URL and run:

```powershell
python debug_getbike/getbike.py --callback-url "com.tracefy.auth0://tracefy.eu.auth0.com/android/com.tracefy/callback?code=...&state=..."
python debug_getbike/getbike.py
```

## Config

For automatic login, use:

```json
{
  "email": "your@email.com",
  "password": "your-password",
  "headless": false,
  "keep_browser_open_on_failure": true
}
```

Run:

```powershell
python debug_getbike/getbike.py
```

## Manual Fallback

If you explicitly want the no-browser-automation flow, use:

```json
{
  "manual_login": true
}
```

With no valid token cache, that prints an Auth0 URL. Open it manually, log in, copy the final `com.tracefy.auth0://...` callback URL, and paste it back into the terminal.
