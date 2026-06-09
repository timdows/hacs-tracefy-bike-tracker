# Tracefy Bike Tracker

Custom Home Assistant integration for showing a bike location on the Home Assistant map.

This integration signs in to the Tracefy app API and creates a `device_tracker` entity for each bike returned by your account.

Entity attributes include:

- last update
- account email
- bike location
- imei
- speed
- movement
- external voltage
- kiwa certificate number
- started at
- frame number
- distance
- positioned at
- fetched at
- business name

## Installation

### HACS custom repository

1. Add this repository to HACS as a custom repository.
2. Select the `Integration` category.
3. Install **Tracefy Bike Tracker**.
4. Restart Home Assistant.
5. Add the integration from **Settings > Devices & services**.

### Manual install

1. Copy `custom_components/tracefy_bike_tracker` into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.
3. Add the integration from **Settings > Devices & services**.

## Configuration

When adding the integration, enter:

- your Tracefy account email
- an app refresh token

The integration uses the same app API flow as the Tracefy mobile app:

```text
Auth0 domain: tracefy.eu.auth0.com
Auth0 audience: https://app.pro.tracefy.io
API base: https://app-pro.tracefy.io
```

No extra Python packages are required by the Home Assistant integration.

### Getting A Refresh Token

Auth0 rejects username/password token exchange for the Tracefy mobile client:

```text
Grant type 'http://auth0.com/oauth/grant-type/password-realm' not allowed for the client.
```

Because of that, the integration cannot use only email/password. Use the local debug helper once to create an app token:

```powershell
python debug_getbike/getbike.py
```

Then copy the `refresh_token` value from:

```text
debug_getbike/token.json
```

Paste that value into the Home Assistant integration setup form.

### Updating From The First Version

The first scaffold version stored only manual latitude/longitude data. After updating to the API-backed version, that old entry does not have a refresh token yet, so no new entities can be created until authentication is updated.

After installing the update and restarting Home Assistant:

1. Go to **Settings > Devices & services > Tracefy Bike Tracker**.
2. If Home Assistant shows a reauthentication prompt, enter the refresh token from `debug_getbike/token.json`.
3. If no prompt appears, remove the old Tracefy Bike Tracker integration entry and add it again with your email and refresh token.

## Options

After setup, open the integration options to configure the fetch interval.

The interval is in seconds. The default is `300` seconds, with a minimum of `60` seconds.

## Notes

The integration stores the access/refresh token in the Home Assistant config entry and refreshes the access token when needed.

Do not publish Home Assistant diagnostics or logs that contain tokens, bike IMEIs, or exact bike coordinates.
