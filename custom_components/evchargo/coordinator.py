from __future__ import annotations

from collections import deque
from datetime import timedelta
import logging
from time import monotonic
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import EvchargoApi, EvchargoApiError, EvchargoAuthError, EvchargoError
from .const import DEFAULT_SCAN_INTERVAL_SECONDS
from .value import first_float, first_value

_LOGGER = logging.getLogger(__name__)

# The Evchargo cloud needs roughly one to three minutes to reflect start/stop
# commands, so HA holds the requested switch state for this long.
_PENDING_COMMAND_GRACE_SECONDS = 180
_FAST_POLL_INTERVAL = timedelta(seconds=15)
_POWER_WINDOW_SECONDS = 300
_POWER_MIN_SPAN_SECONDS = 60
_POWER_STALE_SECONDS = 300

CHARGING_PATHS = (
    "detail.cpInCharging",
    "detail.isCharging",
    "detail.charging",
    "detail.inCharging",
)
SESSION_ENERGY_PATHS = (
    "detail.chargingData.energy",
    "detail.energy",
    "detail.sessionEnergy",
    "detail.kwh",
)
DERIVED_POWER_KEY = "derived_power_kw"


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
        self._normal_update_interval = timedelta(seconds=update_interval_seconds)
        self._charging_enabled: bool | None = None
        self._pending_state: bool | None = None
        self._pending_since: float | None = None
        self._energy_samples: deque[tuple[float, float]] = deque()
        self._last_derived_power: float | None = None

    @property
    def charging_enabled(self) -> bool | None:
        """Return the Home Assistant charging control state."""
        return self._charging_enabled

    async def async_set_charging_enabled(self, enabled: bool) -> None:
        """Execute charging control and keep HA state in sync with the charger."""
        try:
            if enabled:
                await self._async_validate_can_start_charging()
                await self.api.async_start_charging(self.charger_id)
            else:
                await self._async_stop_charging()
        except EvchargoError as err:
            self.async_update_listeners()
            raise HomeAssistantError(str(err)) from err

        self._set_pending_state(enabled)
        self.async_update_listeners()
        await self.async_request_refresh()

    def _set_pending_state(self, enabled: bool) -> None:
        self._charging_enabled = enabled
        self._pending_state = enabled
        self._pending_since = monotonic()
        self.update_interval = _FAST_POLL_INTERVAL

    def _clear_pending_state(self) -> None:
        self._pending_state = None
        self._pending_since = None
        self.update_interval = self._normal_update_interval

    async def _async_stop_charging(self) -> None:
        order_id = first_value(self.data or {}, "detail.chargingData.orderId")
        try:
            await self.api.async_stop_charging(self.charger_id, order_id=order_id)
        except EvchargoApiError as err:
            if _is_completed_stop_response(err):
                _LOGGER.info(
                    "Treating Evchargo stop as complete because the backend reports no active charging record"
                )
                return
            if _is_stop_in_progress_response(err):
                _LOGGER.info(
                    "Evchargo backend is still processing the stop request; waiting for the charger to confirm"
                )
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
            self._reconcile_charging_state(data)
            data[DERIVED_POWER_KEY] = self._derive_power(data)
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
        charging = _coerce_bool(first_value(data, *CHARGING_PATHS))

        if charging is True:
            return

        if run_status == "available":
            self._charging_enabled = False
            raise EvchargoApiError(
                "Cannot start charging: vehicle cable is not connected. Please plug in the cable and try again."
            )

    def _reconcile_charging_state(self, data: dict[str, Any]) -> None:
        """Follow the charger's reported state, honouring recent commands."""
        actual_state = _coerce_bool(first_value(data, *CHARGING_PATHS))

        if self._pending_state is not None and self._pending_since is not None:
            if actual_state == self._pending_state:
                self._clear_pending_state()
            elif monotonic() - self._pending_since < _PENDING_COMMAND_GRACE_SECONDS:
                _LOGGER.debug(
                    "Holding requested charging state %s; charger still reports %s",
                    self._pending_state,
                    actual_state,
                )
                return
            else:
                _LOGGER.warning(
                    "Charger did not confirm the requested charging state %s within %ss; "
                    "showing the reported state %s",
                    self._pending_state,
                    _PENDING_COMMAND_GRACE_SECONDS,
                    actual_state,
                )
                self._clear_pending_state()

        if actual_state is not None:
            self._charging_enabled = actual_state

    def _derive_power(self, data: dict[str, Any]) -> float | None:
        """Estimate charging power (kW) from the growth of session energy."""
        charging = _coerce_bool(first_value(data, *CHARGING_PATHS))
        energy = first_float(data, *SESSION_ENERGY_PATHS)
        now = monotonic()

        if charging is False or energy is None:
            self._energy_samples.clear()
            self._last_derived_power = None
            return 0.0 if charging is False else None

        samples = self._energy_samples
        if samples and energy < samples[-1][1]:
            samples.clear()
        if not samples or energy > samples[-1][1]:
            samples.append((now, energy))
        while len(samples) > 2 and now - samples[1][0] >= _POWER_WINDOW_SECONDS:
            samples.popleft()

        if now - samples[-1][0] > _POWER_STALE_SECONDS:
            self._last_derived_power = 0.0
        elif len(samples) >= 2:
            (first_time, first_energy), (last_time, last_energy) = samples[0], samples[-1]
            span = last_time - first_time
            if span >= _POWER_MIN_SPAN_SECONDS:
                self._last_derived_power = round(
                    (last_energy - first_energy) * 3600 / span, 2
                )
        return self._last_derived_power


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


def _is_completed_stop_response(err: EvchargoApiError) -> bool:
    message = str(err).lower()
    return (
        "api code 80014" in message and "records does not exist" in message
    )


def _is_stop_in_progress_response(err: EvchargoApiError) -> bool:
    message = str(err).lower()
    return "api code 5014" in message
