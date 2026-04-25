from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .__init__ import EvchargoConfigEntry
from .entity import EvchargoCoordinatorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EvchargoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([EvchargoChargingSwitch(entry.runtime_data.coordinator)])


class EvchargoChargingSwitch(EvchargoCoordinatorEntity, SwitchEntity):
    """Switch to start/stop charging."""

    _attr_translation_key = "charging_control"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._charger_id}_charging_control"

    @property
    def is_on(self) -> bool | None:
        return (self.coordinator.data.get("detail") or {}).get("cpInCharging")

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.api.async_start_charging(self._charger_id)
        await self.coordinator.async_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.api.async_stop_charging(self._charger_id)
        await self.coordinator.async_refresh()
