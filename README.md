# Evchargo Home Assistant integration

> **AI-assisted project:** Parts of this repository were created with AI assistance. See [AI-DISCLAIMER.md](./AI-DISCLAIMER.md).

Custom HACS integration for Evchargo chargers using the confirmed mobile-app API path:

- `https://api.evchargo.com:7030/Charge/app/v1/...`

## Current scope

This integration is built around the verified app endpoints discovered in the `evchargo-wrapper` research project.

### Implemented

- UI config flow
- Config items:
  - username/email
  - password
  - charger ID
  - optional base URL
  - optional device ID
- Polling via `DataUpdateCoordinator`
- Read access to the confirmed charger data surface
- Start charging button
- Stop charging button
- Current limit number entity (`PUT /app/v1/home/cp/{cpId}/current?current=<A>`) with safe fallback variants
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

1. Put this repository in Git.
2. Add it to HACS as a custom repository of type **Integration**.
3. Install the integration.
4. Restart Home Assistant.
5. Add **Evchargo** via **Settings → Devices & Services**.

## Important notes

- The manifest currently contains placeholder GitHub URLs for `documentation` and `issue_tracker`.
- Replace those values before publishing publicly.
- `codeowners` is intentionally empty until the final GitHub owner/repository is decided.
- The integration currently follows the confirmed plaintext app login path (`encrypt=false`).
- Trusted-device verification is not implemented yet.
- Only the practically confirmed write actions are exposed right now: start, stop, and current limit.
- Additional writable charger options seen in APK traces should be treated as experimental until their payloads are verified more thoroughly.

## AI disclaimer

This project was developed with AI assistance for code generation, refactoring, structure, and documentation. The integration was then grounded against the confirmed Evchargo app API behavior where possible, but it still needs human review before wider publication or production use.

## Project structure

```text
custom_components/evchargo/
brands/evchargo/
hacs.json
README.md
```
