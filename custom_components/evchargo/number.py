from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfElectricCurrent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .__init__ import EvchargoConfigEntry
from .entity import EvchargoCoordinatorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EvchargoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([EvchargoCurrentLimitNumber(entry.runtime_data.coordinator)])


class EvchargoCurrentLimitNumber(EvchargoCoordinatorEntity, NumberEntity):
    """Current limit control for the charger."""

    _attr_name = "Current limit"
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._charger_id}_current_limit"

    @property
    def native_value(self) -> float | None:
        value = (self.coordinator.data.get("detail") or {}).get("setCurrent")
        return None if value is None else float(value)

    @property
    def native_min_value(self) -> float:
        return float((self.coordinator.data.get("detail") or {}).get("enableMinCurrent") or 6)

    @property
    def native_max_value(self) -> float:
        return float((self.coordinator.data.get("detail") or {}).get("enableMaxCurrent") or 16)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.api.async_set_current_limit(self._charger_id, int(value))
        await self.coordinator.async_request_refresh()
