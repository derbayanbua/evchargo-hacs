# Evchargo Home Assistant integration

> **Experimental / use at your own risk:** This integration is an experiment and should be used entirely at your own risk.
>
> **AI-assisted project:** Parts of this repository were created with AI assistance. See [AI-DISCLAIMER.md](./AI-DISCLAIMER.md).

Custom HACS integration for Evchargo chargers using the confirmed mobile-app API path:

- `https://api.evchargo.com:7030/Charge/app/v1/...`

## Current scope

This integration is built around the verified app endpoints discovered in the `evchargo-wrapper` research project.

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
- Start charging button with immediate execution
- Stop charging button with immediate execution
- Current limit number entity (`PUT /app/v1/home/cp/{cpId}/current?current=<A>`) with immediate execution and refresh
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
- Only the practically confirmed write actions are exposed right now: start, stop, and current limit.
- Status polling is configurable between 30 and 240 seconds, with a default of 60 seconds.
- Button interactions and current-limit changes are executed immediately and then refreshed right away.
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
