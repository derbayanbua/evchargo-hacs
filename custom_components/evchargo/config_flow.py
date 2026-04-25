from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import EvchargoApi, EvchargoApiError, EvchargoAuthError
from .const import (
    CONF_BASE_URL,
    CONF_CHARGER_ID,
    CONF_DEVICE_ID,
    CONF_SCAN_INTERVAL,
    DEFAULT_BASE_URL,
    DEFAULT_DEVICE_ID,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
    MAX_SCAN_INTERVAL_SECONDS,
    MIN_SCAN_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


def _build_user_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
            vol.Required(CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, "")): str,
            vol.Required(CONF_CHARGER_ID, default=defaults.get(CONF_CHARGER_ID, "")): str,
            vol.Optional(CONF_BASE_URL, default=defaults.get(CONF_BASE_URL, DEFAULT_BASE_URL)): str,
            vol.Optional(CONF_DEVICE_ID, default=defaults.get(CONF_DEVICE_ID, DEFAULT_DEVICE_ID)): str,
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=int(defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS)),
            ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL_SECONDS, max=MAX_SCAN_INTERVAL_SECONDS)),
        }
    )


def _build_options_schema(options: dict[str, Any] | None = None) -> vol.Schema:
    options = options or {}
    return vol.Schema(
        {
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=int(options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS)),
            ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL_SECONDS, max=MAX_SCAN_INTERVAL_SECONDS))
        }
    )


class EvchargoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle an Evchargo config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                title = await self._async_validate_input(user_input)
            except EvchargoAuthError:
                errors["base"] = "invalid_auth"
            except EvchargoApiError:
                _LOGGER.debug("Unable to validate Evchargo credentials", exc_info=True)
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(user_input[CONF_CHARGER_ID])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_build_user_schema(user_input),
            errors=errors,
        )

    async def _async_validate_input(self, user_input: dict[str, Any]) -> str:
        session = async_create_clientsession(self.hass)
        api = EvchargoApi(
            session,
            user_input[CONF_USERNAME],
            user_input[CONF_PASSWORD],
            base_url=user_input.get(CONF_BASE_URL, DEFAULT_BASE_URL),
            device_id=user_input.get(CONF_DEVICE_ID, DEFAULT_DEVICE_ID),
            timezone=str(self.hass.config.time_zone),
        )
        try:
            await api.async_login()
            overview = await api.async_get_overview(user_input[CONF_CHARGER_ID])
        finally:
            await api.async_logout()
            await session.close()

        detail = overview.get("detail") or {}
        if not detail:
            raise EvchargoApiError("Charger detail endpoint returned no data")

        cp_name = detail.get("cpName") or user_input[CONF_CHARGER_ID]
        return f"{cp_name} ({user_input[CONF_CHARGER_ID]})"

    @staticmethod
    @config_entries.callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return EvchargoOptionsFlow(config_entry)


class EvchargoOptionsFlow(config_entries.OptionsFlow):
    """Handle Evchargo options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        super().__init__()
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_value = self._config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self._config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS),
        )
        return self.async_show_form(
            step_id="init",
            data_schema=_build_options_schema({CONF_SCAN_INTERVAL: current_value}),
        )
