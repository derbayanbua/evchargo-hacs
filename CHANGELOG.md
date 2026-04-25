# Changelog

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
