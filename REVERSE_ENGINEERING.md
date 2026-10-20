# Evchargo API Reverse Engineering

## Charging-state interpretation update (2026-10)

The implementation now distinguishes vehicle connection, charging activity and
charging permission. Observed `runStatus: Available` and `cpInCharging: false`
support disconnected/inactive interpretation. The plug sensor and start guard
share the same interpreter; billing `inOccupied` and cable-holder `connectorSeat`
are not vehicle-connection evidence. `Preparing`, `SuspendedEV`, `SuspendedEVSE`
and `Charging` are recognized OCPP-like names, not proof that every firmware uses
that vocabulary. Unknown/fault/offline states and contradictions do not become
valid A/B/C states. The older fallback lists below describe historical guesses.

No verified enabled/authorization field is currently available. A successful
start/stop response, inactive `cpInCharging` or existing order ID must not be
treated as proof of charging permission. See the README for the new normalized
sensor, unknown control-switch semantics and evcc limitations. No new live
start/stop or vehicle wake-up behavior has been verified by this change.

## Status
Draft created on 2026-05-22 from:
- the HACS integration code in this repository
- local APK artifacts `Evchargo-app`
- static inspection only (no live API traffic captured yet)

---

## Executive summary

There are currently **two different evidence streams**:

1. **Home-charger REST API model** from this HACS repo
2. **EVgo / Driivz mobile app model** from the local APK

These two models **do not match cleanly**.

### Practical conclusion
The HACS integration is built around a REST API rooted at:

`https://api.evchargo.com:7030/Charge/app/v1/...`

The local APK, however, is clearly an **EVgo Fast EV Charging Stations** app with package name:

`com.driivz.mobile.android.evgo.driver`

and Apollo/GraphQL infrastructure.

So the APK is useful as a **platform clue** (Driivz lineage, EV charging domain, GraphQL/mobile architecture), but it is **not a direct proof source** for the REST endpoints used by the home charger integration.

---

## Source evidence

## 1) HACS repository evidence

The repository README states that the integration uses the mobile app path:

- `https://api.evchargo.com:7030/Charge/app/v1/...`

The current implementation in `custom_components/evchargo/api.py` uses:

### Authentication
- `POST /app/v1/user/login`
- `DELETE /app/v1/user/logout`

### Read endpoints
- `GET /app/v1/user/info`
- `GET /app/v1/home/cp/list`
- `GET /app/v1/home/cpList`
- `GET /app/v1/user/home/cp/users`
- `GET /app/v1/user/rfid/cpList`
- `GET /app/v1/home/cp/{cpId}/detail`
- `GET /app/v1/home/cp/{cpId}/authUserList`
- `GET /app/v1/home/cp/{cpId}/latestFirmwareInfo`
- `GET /app/v1/home/cp/{cpId}/upgradeStatus`
- `GET /app/v1/home/cp/settings/lbcAndPv/{cpId}`
- `GET /app/v1/home/{cpId}/rate`
- `GET /app/v1/home/getPlatformList`
- `GET /app/v1/business/payment/config/{cpId}`

### Write endpoints
- `POST /app/v1/home/cp/{cpId}/start`
- `POST /app/v1/home/cp/{cpId}/stop`
- `PUT /app/v1/home/cp/{cpId}/current`

### Auth/request assumptions from code
Headers:
- `satoken: <token>`
- `fromApp: Evchargo`
- `clientType: ANDROID`
- `clientVersion: 2.7.0`
- `timeZone`
- `timeZoneStr`

Login payload assumption:
```json
{
  "loginType": "EMAIL",
  "email": "<username>",
  "password": "<password>",
  "deviceId": "<device-id>",
  "clientType": "ANDROID",
  "encrypt": "false"
}
```

Success/error assumptions:
- success code: `2000`
- auth failure codes: `4001, 4010, 4401, 4402, 80114`

---

## 2) APK evidence

### APK identity
From `Evchargo-app/info.json`:
- App name: `EVgo Fast EV Charging Stations`
- Version: `26.4.0`
- Package: `com.driivz.mobile.android.evgo.driver`
- Release date in metadata: `2026-03-25`

### Architecture evidence from APK contents
Observed in APK/package contents:
- Apollo runtime modules (`apollo-api`, `apollo-runtime`, `apollo-http-cache`)
- GraphQL resource file:
  - `res/raw/delete_payment_method_mutation.graphql`
- DEX strings showing:
  - `StartChargeForMobileMutation`
  - `GetChargersForSiteQuery`
  - `GetSingleChargerPriceQuery`
  - `ChargeMonitoringService`
  - `GraphQLConfiguration`
  - `GraphQLConstants.Keys.URL`
  - `Driivz`
  - `DriivzTariff`

### What the APK strongly suggests
The local APK is built around a **public charging network / EVgo / Driivz GraphQL stack**, not a simple home-charger REST stack.

This means:
- it likely belongs to the same broader EV charging ecosystem lineage
- but it is **not the same API surface** the HACS plugin currently targets

---

## Inferred home-charger REST model

Despite the APK mismatch, the HACS repo still gives a coherent probable REST model for the Evchargo home charger.

## Base URL
`https://api.evchargo.com:7030/Charge`

## Versioned path prefix
`/app/v1`

## Session model
1. Client logs in with email/password
2. API returns a token inside `data.token`
3. Client sends token in `satoken` header
4. All charger reads/writes happen on authenticated routes

## Charger entity model
The charger seems to be addressed primarily by `cpId`.

Code now tolerates alternate IDs from list payloads:
- `cpId`
- `chargerId`
- `id`
- `pileId`

This suggests field drift or multiple backend serializers may exist.

---

## Inferred read schema

The central object is the result of:

`GET /app/v1/home/cp/{cpId}/detail`

Historically expected fields in the repo:
- `runStatus`
- `cpInCharging`
- `existsActiveAppointment`
- `supportBlueTooth`
- `setCurrent`
- `enableMinCurrent`
- `enableMaxCurrent`
- `signal`
- `chargingData.power`
- `chargingData.current`
- `chargingData.voltage`
- `chargingData.energy`

Because the plugin recently broke in Home Assistant, field drift is a likely explanation.

### Current fallback fields implemented in the repo
For status-like values the integration now accepts alternates such as:
- `status`
- `cpStatus`
- `chargeStatus`
- `state`

For charging booleans:
- `cpInCharging`
- `isCharging`
- `charging`
- `inCharging`

For plugged/connected state:
- `existsActiveAppointment`
- `isPlugged`
- `plugged`
- `connected`

For Bluetooth capability:
- `supportBlueTooth`
- `supportBluetooth`
- `bluetoothSupported`

For current-limit values:
- `setCurrent`
- `currentLimit`
- `maxCurrent`
- `enableMinCurrent`
- `enableMaxCurrent`
- `minCurrent`

This fallback layer is not proof of backend truth; it is a **defensive compatibility layer** based on likely field renames.

---

## Inferred write semantics

## Start / stop charging
The repo assumes:
- `POST /app/v1/home/cp/{cpId}/start`
- `POST /app/v1/home/cp/{cpId}/stop`

Originally only one payload variant was attempted:
```json
{ "connectorNum": 1 }
```

Because write failures were reported, the implementation now tries multiple variants:
- form body with `connectorNum`
- query param with `connectorNum`
- JSON body with `connectorNum`
- empty payload variants as fallback

### Likely interpretation
The backend probably still has these routes or nearby equivalents, but may have changed:
- accepted content type
- whether `connectorNum` is mandatory
- field name / validation behavior

## Current limit
The repo assumes:
- `PUT /app/v1/home/cp/{cpId}/current`

And tries multiple variants for:
- query params
- form body
- JSON body
- with and without `connectorNum`

This suggests the endpoint contract is not fully known and was already reverse-engineered empirically.

---

## Why Home Assistant likely broke

## High-confidence causes

### 1. Response field drift
If `detail` now returns:
- renamed fields
- flattened metrics
- different boolean formats
- list-only data instead of detail-only data

then HA entities would show `unknown` / `unavailable` / empty values.

### 2. Write contract drift
If `/start`, `/stop`, or `/current` now expect a different payload format, writes will silently fail or return non-`2000` codes.

### 3. Wrong client lineage
If the original reverse engineering came from a specific Evchargo mobile app branch and the vendor moved to a Driivz-backed stack or changed apps, the HACS repo may now target a partially obsolete API.

---

## Relationship between HACS repo and APK

## Best current interpretation

### HACS repo
Likely based on:
- a real Evchargo home charger API
- probably discovered from an earlier or different mobile app path
- REST + token auth + `/Charge/app/v1/...`

### Local APK
Likely represents:
- EVgo public-network app
- Driivz platform implementation
- GraphQL/Apollo architecture
- not the same charger-control surface as the home charger integration

### Therefore
The APK is a **supporting ecosystem artifact**, not the authoritative source for the HACS REST contract.

---

## Confidence levels

### High confidence
- The HACS integration targets a REST API under `https://api.evchargo.com:7030/Charge/app/v1/...`
- The HACS integration uses `satoken` token auth and `code == 2000`
- The local APK is EVgo/Driivz and GraphQL-based, not a direct match to the home charger REST API
- API field drift is a plausible explanation for missing status in HA
- write-contract drift is a plausible explanation for failed start/stop/current changes

### Medium confidence
- `cpId` remains the main charger identifier
- current backend may now emit alternate names like `status`, `isCharging`, `currentLimit`, etc.
- some values may now come from list payloads instead of detail payloads

### Low confidence / unverified
- exact current live schema of `/detail`
- exact accepted payload format of `/start`, `/stop`, `/current`
- whether `encrypt=false` is still required or still accepted
- whether the backend has partially migrated to another platform layer

---

## What still needs live verification

To finish the reverse engineering, capture these real responses from a working account:

### Authentication
`POST /app/v1/user/login`
- full response JSON
- headers if relevant

### Charger detail
`GET /app/v1/home/cp/{cpId}/detail`
- full JSON

### Charger list
`GET /app/v1/home/cp/list`
- full JSON

### Write tests
- start request response
- stop request response
- current-limit request response

### Important observations to record
- exact `code`
- exact field names
- whether booleans are `true/false`, `1/0`, or strings
- whether metrics moved from `chargingData.*` to top-level `detail.*`
- whether the token header is still `satoken`
- whether the API now rejects `encrypt=false`

---

## Recommended next step

Perform a live capture against the actual Evchargo home charger account and compare:
- assumed schema in this repo
- actual JSON returned today

That will let us convert this document from **inference** into a precise protocol description.

Until then, this is the best current reverse-engineered model:

### Protocol summary
- Transport: HTTPS REST
- Base URL: `https://api.evchargo.com:7030/Charge`
- Prefix: `/app/v1`
- Auth: login -> token -> `satoken` header
- Success code: `2000`
- Primary entity: charger identified by `cpId`
- Core read route: `/home/cp/{cpId}/detail`
- Core writes: `/home/cp/{cpId}/start`, `/stop`, `/current`

---

## Local repo changes already made to cope with drift

The local working tree has already been hardened to:
- normalize boolean response values
- accept alternate field names for status/charging/current-limit metrics
- merge list payload data into detail data when useful
- try multiple write payload variants for start/stop/current
- reload the HA config entry when options change

These changes improve resilience, but they are still **compatibility guesses** until validated against live traffic.
