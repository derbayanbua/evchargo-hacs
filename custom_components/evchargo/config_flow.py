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
    DEFAULT_BASE_URL,
    DEFAULT_DEVICE_ID,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_CHARGER_ID): str,
        vol.Optional(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
        vol.Optional(CONF_DEVICE_ID, default=DEFAULT_DEVICE_ID): str,
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
            data_schema=STEP_USER_DATA_SCHEMA,
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
