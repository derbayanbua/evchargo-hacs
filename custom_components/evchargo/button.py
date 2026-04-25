from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .__init__ import EvchargoConfigEntry
from .entity import EvchargoCoordinatorEntity


@dataclass(frozen=True, kw_only=True)
class EvchargoButtonDescription(ButtonEntityDescription):
    press_fn: Callable[["EvchargoButton"], Awaitable[None]]


BUTTONS: tuple[EvchargoButtonDescription, ...] = (
    EvchargoButtonDescription(
        key="start_charging",
        translation_key="start_charging",
        press_fn=lambda entity: entity.coordinator.api.async_start_charging(entity._charger_id),
    ),
    EvchargoButtonDescription(
        key="stop_charging",
        translation_key="stop_charging",
        press_fn=lambda entity: entity.coordinator.api.async_stop_charging(entity._charger_id),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EvchargoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(EvchargoButton(coordinator, description) for description in BUTTONS)


class EvchargoButton(EvchargoCoordinatorEntity, ButtonEntity):
    """Evchargo button entity."""

    def __init__(self, coordinator, description: EvchargoButtonDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self._charger_id}_{description.key}"
        self._attr_translation_key = description.translation_key

    async def async_press(self) -> None:
        await self.entity_description.press_fn(self)
        await self.coordinator.async_refresh()
