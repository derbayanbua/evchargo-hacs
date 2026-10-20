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
- Charging switch (on/off) plus separate start/stop buttons with immediate execution
- Charging control with separate pending command intent and observed activity; unknown permission is not reported as disabled
- Current limit slider (`PUT /app/v1/home/cp/{cpId}/current?current=<A>`) using API-provided limits/steps where available, with immediate execution and refresh
- Diagnostic buttons for manual refresh and forced re-authentication
- Additional diagnostic sensors for current limits, active charge order ID, latest firmware, plugged-in state, and online state
- Main status sensor with sanitized operational attributes from the confirmed app endpoints
- Separate normalized `Charging state` sensor (`A`/`B`/`C`) for consumers such as evcc, without changing the vendor status sensor
- Energy sensors usable in the Energy dashboard and long-term statistics: `Session energy` (resets per session) and `Total charged energy` (lifetime total accumulated across sessions and restarts)
- Power sensor that falls back to a value derived from session-energy growth when the cloud reports no usable power reading

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

Only non-private operational diagnostics are exposed as Home Assistant state attributes. Account, authorization, RFID, payment, user-list, location, contact, token, and similar fields are either not exposed as attributes or are redacted.

## Installation with HACS

1. Add this repository to HACS as a custom repository of type **Integration**.
2. Install the integration.
3. Restart Home Assistant.
4. Add **Evchargo** via **Settings → Devices & Services**.

## Important notes

- This integration is experimental and is provided without warranty; use it at your own risk.
- The integration currently follows the confirmed app login path (`encrypt=false`) over HTTPS only.
- Custom API base URLs must use HTTPS and must not include embedded credentials, query strings, or fragments.
- Trusted-device verification is not implemented yet.
- Only the practically confirmed write actions are exposed right now: charging on/off and current limit.
- Status polling is configurable between 30 and 240 seconds, with a default of 60 seconds.
- Switch, start/stop button, and current-limit changes are executed immediately. After a start/stop command, polling temporarily speeds up to every 15 seconds for up to 3 minutes while the Evchargo cloud catches up. Command acknowledgement alone does not change the switch to the requested state.
- For charged-energy history, use `Total charged energy` in the Energy dashboard or a utility meter helper instead of integrating the power sensor.
- API errors include the HTTP method, endpoint, HTTP status, Evchargo API code, and backend message where available.
- Use the diagnostic re-authenticate button when the cloud token appears stale without needing to reload the full integration.
- When activity stops or telemetry becomes unknown, the charging switch becomes `unknown`, not `off`. This does not send a stop command or revoke charger-side permission, and cannot guarantee that reconnecting a vehicle will not resume charging.
- The integration icon and logo ship in `custom_components/evchargo/brand/` and are shown by Home Assistant 2026.3 or newer after a restart (hard-refresh the browser if the old placeholder is cached). The HACS store view may still show no icon, because HACS fetches icons from its own source.
- Additional writable charger options seen in APK traces should be treated as experimental until their payloads are verified more thoroughly.

## Connection, activity and charging permission

### Upgrading an ID with surrounding whitespace

Charger IDs are trimmed for API calls and registry identity. On setup, the
integration migrates existing whitespace-bearing device and entity unique IDs
before loading entities. It preserves the original device record, area assignment,
entity IDs and entity customizations, so dashboards, automations and history using
the original entities continue to use those same IDs.

If the earlier trimming change already created a second charger, the migration
keeps the original device and original entities, removes their redundant
normalized-ID registry entries, and moves new-only entities (such as `Charging
state`) to the original device without renaming them. References to the
**duplicate** entities must be changed back to the original IDs; a warning logs
each replacement. Recorder history is not deleted or merged: the original
entities resume their own history/statistics, while any history and accumulated
energy recorded under duplicate entities remain separate.

Back up Home Assistant before installing the fix, then restart Home Assistant.
Do not manually delete the original charger or its entities. Ambiguous identities,
conflicts with another config entry, or a duplicate device shared with another
integration stop setup with an explicit error rather than removing unrelated
registry entries. The migration is safe to run again on subsequent setups.

### Interpreting charger telemetry

`Plugged in`, `Charging`, and `Charging state` share one conservative interpreter.
Explicit connection fields (`isPlugged`, `plugged`, `connected`, `connectorPlugged`)
are considered alongside the recognized status vocabulary below. False is a real
value, not a missing field. Billing/session occupancy (`inOccupied`, including
`chargingData.inOccupied`), appointments, connector-lock support and cable-holder
state (`connectorSeat`) are not evidence that a vehicle is connected.

| Vendor status (case-insensitive) | Plugged in | Charging state |
|---|---|---|
| `Available` | off | `A` (disconnected) |
| `Preparing`, `SuspendedEV`, `SuspendedEVSE` | on | `B` (connected, not charging) |
| `Charging` | on | `C` (charging), or `B` when an explicit activity flag is false |
| Missing status | explicit evidence only | `A` for explicit unplugged, `B` for explicit plugged and inactive, `C` for explicit active charging; otherwise unknown |
| New/unknown, faulted or offline status | explicit connection evidence only | unknown |

An explicit offline flag or contradictory connection/activity evidence makes the
interpreted state unknown rather than inventing a valid A/B/C state. A missing
activity flag alone never means disconnected. Starts are rejected with a clear
error when connection is absent, unknown or inconsistent, or no valid normalized
state is available.

`Available` and the `cpInCharging` field have been observed on the home-charger
API. The preparing/suspended names are an explicit OCPP-like compatibility
vocabulary, **not verified claims that every Evchargo firmware emits these names**.
No numeric or unfamiliar vendor statuses are guessed. The existing `Status`
sensor remains compatible (including `Not charging` for a stale `Charging`
status); its sanitized `detail.runStatus` attribute retains the raw vendor value.

The API currently has **no verified charging-enabled/authorization field**.
Actual charging implies enabled permission at that moment, so the control switch
is `on` while charging is confirmed. In all other cases its state is `unknown`
and it uses HA's assumed-state controls. A waiting, suspended, sleeping or full
vehicle is not necessarily disabled; even unplugging does not prove that future
charging permission was revoked. Neither a session order ID nor a successful
start/stop response proves permission. The switch attribute
`requested_charging_enabled` shows only the pending command (`true`/`false`),
clearing when matching activity is seen or after 180 seconds. A timeout logs a
warning; clearing a pending stop means activity stopped, not that authorization
was independently verified.

These changes do not wake a sleeping vehicle (including a Skoda Enyaq), override
vehicle schedules, or provide real-time local charger feedback.

## evcc Home Assistant setup

For evcc **0.317.2**, use the new `Charging state` entity as the charger `status`
source, not the vendor `Status` entity. Find its actual entity ID in HA; the
following names are examples, not guaranteed generated IDs:

```yaml
# Relevant fields within an evcc type: homeassistant charger:
status: sensor.garden_home_charging_state
power: sensor.garden_home_power
energy: sensor.garden_home_total_charged_energy
```

`A`, `B`, and `C` are accepted case-insensitively without custom mappings.
If retaining a vendor-status source, evcc offers comma-separated `statusA`,
`statusB`, and `statusC` mappings, for example:

```yaml
statusA: Available
statusB: Preparing,SuspendedEV,SuspendedEVSE
statusC: Charging
```

That legacy mapping only translates vocabulary: it cannot detect stale
`Charging` values or contradictory telemetry. Prefer the normalized sensor.
Do not map unknown, unavailable, faults, or every unrecognized state to `A`/`B`.

**This is not a complete, verified automatic-control configuration.** evcc also
requires `enabled`, `enable`, and `maxcurrent` sources. The integration switch and
current-limit number can issue commands, but neither the switch (unknown while
idle) nor the actual `Charging` binary sensor is reliable `enabled` feedback.
evcc rejects unknown boolean states. Do not work around this with a template
that coerces unknown to off, or a helper that merely remembers API commands.
Reliable closed-loop control needs independently verified authorization telemetry
from the charger; that remains unsupported by this API integration.

The integration's power sensor is **kW**. evcc's HA adapter in 0.317.2 reads the
HA `unit_of_measurement` and automatically scales kW to its internal **W**;
**do not multiply by 1000 again**. Energy in kWh is already compatible. For a
different adapter/version that reads only numeric values, verify its unit
handling separately. Cloud-derived power is delayed and estimated from session
energy growth, not a fast feedback meter.

Upstream references:
[charger configuration](https://github.com/evcc-io/evcc/blob/0.317.2/charger/homeassistant.go),
[state/boolean mapping](https://github.com/evcc-io/evcc/blob/0.317.2/util/homeassistant/connection.go),
[unit conversion](https://github.com/evcc-io/evcc/blob/0.317.2/util/homeassistant/types.go).

## Development

Run offline regression tests with Python 3.13 and Home Assistant test dependencies:

```sh
python3 -m pip install -r requirements-test.txt
python3 -m unittest discover -s tests -v
```

The tests use synthetic payloads and mocked HA/cloud boundaries; they do not
connect to Home Assistant, the Evchargo cloud or a vehicle.

## AI disclaimer

This project was developed with AI assistance for code generation, refactoring, structure, and documentation. The integration was then grounded against the confirmed Evchargo app API behavior where possible, but it remains experimental and still needs human review before wider publication or production use.

## Project structure

```text
custom_components/evchargo/
custom_components/evchargo/brand/   # icon/logo served locally by Home Assistant 2026.3+
brands/evchargo/
hacs.json
README.md
```
