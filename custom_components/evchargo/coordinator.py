from __future__ import annotations

from datetime import timedelta
import logging
from time import monotonic
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import EvchargoApi, EvchargoApiError, EvchargoAuthError
from .const import DEFAULT_SCAN_INTERVAL_SECONDS
from .value import first_value

_LOGGER = logging.getLogger(__name__)

_START_RECONCILE_GRACE_SECONDS = 30


class EvchargoDataUpdateCoordinator(DataUpdateCoordinator[dict]):
    """Coordinate Evchargo API updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        api: EvchargoApi,
        charger_id: str,
        *,
        update_interval_seconds: int = DEFAULT_SCAN_INTERVAL_SECONDS,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"Evchargo {charger_id}",
            config_entry=config_entry,
            update_interval=timedelta(seconds=update_interval_seconds),
            always_update=True,
        )
        self.api = api
        self.charger_id = charger_id
        self._charging_enabled: bool | None = None
        self._last_start_requested_at: float | None = None

    @property
    def charging_enabled(self) -> bool | None:
        """Return the Home Assistant charging control state."""
        return self._charging_enabled

    async def async_set_charging_enabled(self, enabled: bool) -> None:
        """Execute charging control and keep HA state in sync with the charger."""
        previous_state = self._charging_enabled
        previous_start_requested_at = self._last_start_requested_at
        self._charging_enabled = enabled
        try:
            if enabled:
                await self._async_validate_can_start_charging()
                self._last_start_requested_at = monotonic()
                await self.api.async_start_charging(self.charger_id)
            else:
                self._last_start_requested_at = None
                await self._async_stop_charging()
        except EvchargoApiError:
            self._charging_enabled = previous_state
            self._last_start_requested_at = previous_start_requested_at
            raise

        await self.async_refresh()

    async def _async_stop_charging(self) -> None:
        order_id = first_value(self.data or {}, "detail.chargingData.orderId")
        try:
            await self.api.async_stop_charging(self.charger_id, order_id=order_id)
        except EvchargoApiError as err:
            if _is_missing_charging_record_error(err):
                _LOGGER.info(
                    "Treating Evchargo stop as complete because the backend reports no active charging record"
                )
                self._charging_enabled = False
                self._last_start_requested_at = None
                return

            min_current = _coerce_int(
                first_value(
                    self.data or {},
                    "detail.enableMinCurrent",
                    "detail.minCurrent",
                    "rate.connectorSetCurrentList.0.current",
                )
            )
            if min_current is None:
                raise

            try:
                await self.api.async_set_current_limit(self.charger_id, min_current)
            except EvchargoApiError:
                raise err

            raise EvchargoApiError(
                f"Stop charging failed ({err}); reduced charging current to {min_current} A"
            ) from err

    async def _async_update_data(self) -> dict:
        try:
            data = await self.api.async_get_overview(self.charger_id)
            await self._async_reconcile_charging_state(data)
            return data
        except EvchargoAuthError as err:
            raise ConfigEntryAuthFailed from err
        except EvchargoApiError as err:
            raise UpdateFailed(f"Error communicating with Evchargo API: {err}") from err

    async def _async_validate_can_start_charging(self) -> None:
        """Fail early with a clear message when no vehicle cable is connected."""
        data = await self.api.async_get_overview(self.charger_id)
        run_status = _coerce_string(
            first_value(
                data,
                "detail.runStatus",
                "detail.status",
                "detail.cpStatus",
                "detail.chargeStatus",
                "detail.state",
            )
        )
        charging = _coerce_bool(
            first_value(
                data,
                "detail.cpInCharging",
                "detail.isCharging",
                "detail.charging",
                "detail.inCharging",
            )
        )

        if charging is True:
            return

        if run_status == "available":
            self._charging_enabled = False
            raise EvchargoApiError(
                "Cannot start charging: vehicle cable is not connected. Please plug in the cable and try again."
            )

    async def _async_reconcile_charging_state(self, data: dict[str, Any]) -> None:
        """Reset stale HA charging state once charging is no longer active."""
        actual_state = _coerce_bool(
            first_value(
                data,
                "detail.cpInCharging",
                "detail.isCharging",
                "detail.charging",
                "detail.inCharging",
            )
        )

        if self._charging_enabled is None:
            self._charging_enabled = actual_state
            return

        if actual_state is True and self._charging_enabled is False:
            self._charging_enabled = True
            self._last_start_requested_at = None
            return

        if self._charging_enabled and actual_state is False:
            if self._last_start_requested_at is not None:
                elapsed = monotonic() - self._last_start_requested_at
                if elapsed < _START_RECONCILE_GRACE_SECONDS:
                    _LOGGER.debug(
                        "Skipping stale charging reset %.1fs after start request; charger has not reported active charging yet",
                        elapsed,
                    )
                    return

            _LOGGER.info(
                "Resetting Home Assistant charging state because the charger no longer reports active charging"
            )
            self._charging_enabled = False
            self._last_start_requested_at = None


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return None


def _coerce_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).strip().lower() or None


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _is_missing_charging_record_error(err: EvchargoApiError) -> bool:
    message = str(err).lower()
    return "api code 80014" in message and "records does not exist" in message
