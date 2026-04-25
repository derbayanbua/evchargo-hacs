from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import EvchargoApi, EvchargoApiError, EvchargoAuthError
from .const import DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class EvchargoDataUpdateCoordinator(DataUpdateCoordinator[dict]):
    """Coordinate Evchargo API updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        api: EvchargoApi,
        charger_id: str,
        *,
        update_interval: timedelta = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"Evchargo {charger_id}",
            config_entry=config_entry,
            update_interval=update_interval,
            always_update=True,
        )
        self.api = api
        self.charger_id = charger_id

    async def _async_update_data(self) -> dict:
        try:
            return await self.api.async_get_overview(self.charger_id)
        except EvchargoAuthError as err:
            raise ConfigEntryAuthFailed from err
        except EvchargoApiError as err:
            raise UpdateFailed(f"Error communicating with Evchargo API: {err}") from err
