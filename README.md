# Evchargo Home Assistant integration

> **Experimental / use at your own risk:** This integration is an experiment and should be used entirely at your own risk.
>
> **AI-assisted project:** Parts of this repository were created with AI assistance. See [AI-DISCLAIMER.md](./AI-DISCLAIMER.md).

Custom **Home Assistant** integration for Evchargo chargers, installable via **HACS**, using the confirmed mobile-app API path:

- `https://api.evchargo.com:7030/Charge/app/v1/...`

## Current scope

This integration is built around the verified app endpoints discovered in the `evchargo-wrapper` research project.

It has been tested with the charger model **AC011K-AU-25**.

### Implemented

- UI config flow
- German translation for setup/options and entity names
- Config items:
  - username/email
  - password
  - charger ID
  - optional base URL
  - optional device ID
  - polling interval between **30 and 240 seconds** (default: **60 seconds**)
- Polling via `DataUpdateCoordinator`
- Read access to the confirmed charger data surface
- Charging switch (on/off) with immediate execution
- Automatic reset of the Home Assistant charging switch when charging stops after unplugging or interruption, so reconnecting the car does not silently resume a stale HA-issued charge request
- Current limit number entity (`PUT /app/v1/home/cp/{cpId}/current?current=<A>`) with immediate execution and refresh
- Diagnostic buttons for manual refresh and forced re-authentication
- Additional diagnostic sensors for current limits, active charge order ID, latest firmware, plugged-in state, and online state
- Main status sensor with flattened raw attributes from the confirmed app endpoints

### Exposed data

The integration fetches data from these confirmed endpoints when available:

- `/app/v1/user/info`
- `/app/v1/home/cp/list`
- `/app/v1/home/cpList`
- `/app/v1/user/home/cp/users`
- `/app/v1/user/rfid/cpList`
- `/app/v1/home/cp/{cpId}/detail`
- `/app/v1/home/cp/{cpId}/authUserList`
- `/app/v1/home/cp/{cpId}/latestFirmwareInfo`
- `/app/v1/home/cp/{cpId}/upgradeStatus`
- `/app/v1/home/cp/settings/lbcAndPv/{cpId}`
- `/app/v1/home/{cpId}/rate`
- `/app/v1/home/getPlatformList`
- `/app/v1/business/payment/config/{cpId}`

## Installation with HACS

1. Add this repository to HACS as a custom repository of type **Integration**.
2. Install the integration.
3. Restart Home Assistant.
4. Add **Evchargo** via **Settings → Devices & Services**.

## Important notes

- This integration is experimental and is provided without warranty; use it at your own risk.
- The integration currently follows the confirmed plaintext app login path (`encrypt=false`).
- Trusted-device verification is not implemented yet.
- Only the practically confirmed write actions are exposed right now: charging on/off and current limit.
- Status polling is configurable between 30 and 240 seconds, with a default of 60 seconds.
- Switch interactions and current-limit changes are executed immediately and then refreshed right away.
- API errors include the HTTP method, endpoint, HTTP status, Evchargo API code, and backend message where available.
- Use the diagnostic re-authenticate button when the cloud token appears stale without needing to reload the full integration.
- When the charger no longer reports active charging, the integration clears the HA charging switch state without sending another stop command, because the Evchargo API can reject that stale stop with `Records does not exist`.
- Additional writable charger options seen in APK traces should be treated as experimental until their payloads are verified more thoroughly.

## AI disclaimer

This project was developed with AI assistance for code generation, refactoring, structure, and documentation. The integration was then grounded against the confirmed Evchargo app API behavior where possible, but it remains experimental and still needs human review before wider publication or production use.

## Project structure

```text
custom_components/evchargo/
brands/evchargo/
hacs.json
README.md
```
