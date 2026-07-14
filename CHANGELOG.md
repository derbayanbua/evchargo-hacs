# Changelog

## Unreleased
- treat Evchargo stop responses with API code `5014` / `Processing, please wait` as a failed/incomplete stop again so the minimum-current fallback can still reduce charging load

## 2026.7.14.2
- show `Not charging` instead of a stale Evchargo `Charging` status when the charger explicitly reports `cpInCharging: false`
- stop using `existsActiveAppointment` as the preferred source for the plugged-in sensor so appointments are not shown as cable state

## 2026.7.14.1
- treat Evchargo stop responses with API code `80014` / `Records does not exist` as an already-stopped charger state instead of surfacing a Home Assistant error or forcing a current-limit fallback
- treat Evchargo stop responses with API code `5014` / `Processing, please wait` as an in-progress stop instead of surfacing a Home Assistant error or forcing a current-limit fallback

## 2026.7.13.1
- added integration-local icon/logo assets so HACS installs the Evchargo icon with the custom component
- changed the current-limit control from a numeric input box to a slider that uses API-provided current limits and steps where available
- restored separate start and stop charging buttons alongside the charging switch
- restricted custom API base URLs to sanitized HTTPS URLs without embedded credentials
- changed the config-flow password field to a password selector
- limited status-sensor attributes to sanitized operational diagnostics instead of exposing raw account, user, RFID, auth, or payment payloads
- hardened API response parsing for unexpected JSON shapes

## 2026.7.11.1
- fixed stale charging-state reconciliation so Home Assistant only clears its local charging switch when the charger already reports inactive charging, instead of sending another stop command
- avoided an unwanted current-limit reset to 6 A when the Evchargo backend rejects a stale stop request with `Records does not exist`

## 2026.5.31.1
- added diagnostic refresh and reauthenticate buttons for manual recovery after token or cloud-state issues
- added extra diagnostic sensors for current limits, active charge order ID, latest firmware, plugged-in state, and online state
- improved API error messages with HTTP method, endpoint, HTTP status, API code, and backend message
- fixed nested list path handling so fields like `rate.connectorSetCurrentList.0.current` can be read reliably

## 2026.5.29.1
- added stop-request variants that include the active `chargingData.orderId` for backends that require a session identifier
- added a minimum-current fallback when the Evchargo backend rejects a stop command, so failed stops reduce charging as far as the API allows

## 2026.5.4.4
- verified live start/stop behavior with vehicle cable connected; start and stop both succeed through the form-body `connectorNum` variant
- added a pre-start cable-state guard: when the charger reports `runStatus: Available`, Home Assistant now refuses the start request with a clear "vehicle cable is not connected" message instead of silently accepting a no-op
- kept the post-start reconciliation grace period so Home Assistant does not immediately undo a valid start while the charger is transitioning

## 2026.5.4.3
- made the charging switch operate in assumed-state mode when the backend does not expose a clean boolean, so Home Assistant can still toggle charging
- added an extra power fallback for `chargingData.ratePower` / `ratePower` based on newer API traces

## 2026.5.4.2
- added sanitized debug logging for request/response tracing to help identify API drift without leaking secrets
- logged overview/detail key shapes so Home Assistant logs can show which fields the backend currently returns

## 2026.5.4.1
- fixed stale charging-switch state so unplugging/interruption resets the Home Assistant switch and clears the charger-side charge request to avoid unintended auto-resume on reconnect
- clarified the repository README as a Home Assistant + HACS integration and documented the charging-state reset behavior

## 2026.4.25.8
- adjusted German entity labels for plugged-in state and session energy
- documented testing with charger model AC011K-AU-25

## 2026.4.25.7
- replaced the separate start/stop buttons with a single charging switch

## 2026.4.25.6
- fixed the options/settings flow initialization to prevent server errors when changing settings later

## 2026.4.25.5
- added German translations for config flow, options flow, and current entity names
- switched entities to translation keys so Home Assistant can localize them properly

## 2026.4.25.4
- added configurable polling interval with limits of 30-240 seconds
- set default polling interval to 60 seconds
- added options flow support for changing the polling interval after setup
- made button and current-limit interactions refresh immediately after execution

## 2026.4.25.3
- documented the integration as experimental / use at your own risk
- removed outdated note about needing to put the project in Git first
- updated manifest links and codeowner to the live GitHub repository

## 2026.4.25.2
- added project hygiene files for git/HACS publication prep
- added AI usage disclaimer
- cleaned generated cache files from the repository
- documented current integration scope and publication caveats

## 2026.4.25.1
- initial HACS/Home Assistant custom integration scaffold
- config flow for username, password, charger ID, base URL, and device ID
- coordinator-based polling for confirmed Evchargo app endpoints
- entities for charger status, live metrics, firmware, charging state, start/stop, and current limit
