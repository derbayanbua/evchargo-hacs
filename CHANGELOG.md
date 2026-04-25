# Changelog

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
