# Tracefy Bike Tracker

Custom Home Assistant integration for showing a bike location on the Home Assistant map.

This initial version scaffolds the HACS integration and creates one `device_tracker` entity with:

- Last update
- Account email
- Bike location

The location is configured manually for now. A Tracefy API client can be added later to update it automatically.

## Installation

1. Add this repository to HACS as a custom repository.
2. Select the `Integration` category.
3. Install **Tracefy Bike Tracker**.
4. Restart Home Assistant.
5. Add the integration from **Settings > Devices & services**.

