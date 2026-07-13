from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfElectricCurrent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .__init__ import EvchargoConfigEntry
from .entity import EvchargoCoordinatorEntity
from .value import first_float, first_value

CURRENT_LIST_PATHS = (
    "rate.connectorSetCurrentList",
    "detail.connectorSetCurrentList",
    "detail.currentList",
    "detail.currentLimitList",
    "detail.allowedCurrentList",
    "detail.availableCurrentList",
)
CURRENT_VALUE_KEYS = (
    "current",
    "setCurrent",
    "currentLimit",
    "value",
    "ampere",
)
CURRENT_STEP_PATHS = (
    "rate.connectorSetCurrentList.0.step",
    "rate.connectorSetCurrentList.0.currentStep",
    "rate.connectorSetCurrentList.0.stepCurrent",
    "detail.currentStep",
    "detail.stepCurrent",
    "detail.currentInterval",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EvchargoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([EvchargoCurrentLimitNumber(entry.runtime_data.coordinator)])


class EvchargoCurrentLimitNumber(EvchargoCoordinatorEntity, NumberEntity):
    """Current limit control for the charger."""

    _attr_translation_key = "current_limit"
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._charger_id}_current_limit"

    @property
    def native_value(self) -> float | None:
        return first_float(
            self.coordinator.data,
            "detail.setCurrent",
            "detail.currentLimit",
            "detail.maxCurrent",
            "rate.connectorSetCurrentList.0.current",
        )

    @property
    def native_min_value(self) -> float:
        allowed = _allowed_current_values(self.coordinator.data)
        if len(allowed) >= 2:
            return allowed[0]
        return first_float(
            self.coordinator.data,
            "detail.enableMinCurrent",
            "detail.minCurrent",
            "rate.connectorSetCurrentList.0.minCurrent",
        ) or 6.0

    @property
    def native_max_value(self) -> float:
        allowed = _allowed_current_values(self.coordinator.data)
        if len(allowed) >= 2:
            return allowed[-1]
        return first_float(
            self.coordinator.data,
            "detail.enableMaxCurrent",
            "detail.maxCurrent",
            "rate.connectorSetCurrentList.0.maxCurrent",
        ) or 16.0

    @property
    def native_step(self) -> float:
        allowed = _allowed_current_values(self.coordinator.data)
        if len(allowed) >= 2:
            return _smallest_positive_delta(allowed) or 1.0
        return first_float(self.coordinator.data, *CURRENT_STEP_PATHS) or 1.0

    async def async_set_native_value(self, value: float) -> None:
        current = _normalize_current_value(
            value,
            min_value=self.native_min_value,
            max_value=self.native_max_value,
            step=self.native_step,
            allowed_values=_allowed_current_values(self.coordinator.data),
        )
        await self.coordinator.api.async_set_current_limit(self._charger_id, current)
        await self.coordinator.async_refresh()


def _allowed_current_values(data: dict[str, Any]) -> list[float]:
    values: set[float] = set()
    for path in CURRENT_LIST_PATHS:
        values.update(_extract_current_values(first_value(data, path)))
    return sorted(value for value in values if value > 0)


def _extract_current_values(value: Any) -> set[float]:
    values: set[float] = set()
    if isinstance(value, list):
        for item in value:
            values.update(_extract_current_values(item))
    elif isinstance(value, dict):
        for key in CURRENT_VALUE_KEYS:
            parsed = _as_float(value.get(key))
            if parsed is not None:
                values.add(parsed)
    else:
        parsed = _as_float(value)
        if parsed is not None:
            values.add(parsed)
    return values


def _smallest_positive_delta(values: list[float]) -> float | None:
    deltas = [
        later - earlier
        for earlier, later in zip(values, values[1:], strict=False)
        if later > earlier
    ]
    return min(deltas) if deltas else None


def _normalize_current_value(
    value: float,
    *,
    min_value: float,
    max_value: float,
    step: float,
    allowed_values: list[float],
) -> int:
    if len(allowed_values) >= 2:
        return int(
            round(min(allowed_values, key=lambda candidate: abs(candidate - value)))
        )

    bounded = min(max(value, min_value), max_value)
    if step > 0:
        bounded = min_value + round((bounded - min_value) / step) * step
        bounded = min(max(bounded, min_value), max_value)
    return int(round(bounded))


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
