from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EvchargoApi
from .const import (
    CONF_BASE_URL,
    CONF_CHARGER_ID,
    CONF_DEVICE_ID,
    CONF_SCAN_INTERVAL,
    DEFAULT_BASE_URL,
    DEFAULT_DEVICE_ID,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
    EvchargoRuntimeData,
    PLATFORMS,
)
from .coordinator import EvchargoDataUpdateCoordinator


EvchargoConfigEntry = ConfigEntry[EvchargoRuntimeData]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Evchargo integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: EvchargoConfigEntry) -> bool:
    """Set up Evchargo from a config entry."""
    api = EvchargoApi(
        async_get_clientsession(hass),
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        base_url=entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
        device_id=entry.data.get(CONF_DEVICE_ID, DEFAULT_DEVICE_ID),
        timezone=str(hass.config.time_zone),
    )
    scan_interval_seconds = int(
        entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS),
        )
    )
    coordinator = EvchargoDataUpdateCoordinator(
        hass,
        entry,
        api,
        entry.data[CONF_CHARGER_ID],
        update_interval_seconds=scan_interval_seconds,
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = EvchargoRuntimeData(
        api=api,
        coordinator=coordinator,
        charger_id=entry.data[CONF_CHARGER_ID],
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EvchargoConfigEntry) -> bool:
    """Unload an Evchargo config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.api.async_logout()
    return unload_ok
