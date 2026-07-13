from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .__init__ import EvchargoConfigEntry
from .entity import EvchargoCoordinatorEntity


@dataclass(frozen=True, kw_only=True)
class EvchargoButtonDescription(ButtonEntityDescription):
    press_fn: Callable[[Any], Coroutine[Any, Any, None]]


async def _async_refresh(coordinator) -> None:
    await coordinator.async_request_refresh()


async def _async_reauthenticate(coordinator) -> None:
    await coordinator.api.async_login(force=True)
    await coordinator.async_request_refresh()


async def _async_start_charging(coordinator) -> None:
    await coordinator.async_set_charging_enabled(True)


async def _async_stop_charging(coordinator) -> None:
    await coordinator.async_set_charging_enabled(False)


BUTTONS: tuple[EvchargoButtonDescription, ...] = (
    EvchargoButtonDescription(
        key="start_charging",
        translation_key="start_charging",
        press_fn=_async_start_charging,
    ),
    EvchargoButtonDescription(
        key="stop_charging",
        translation_key="stop_charging",
        press_fn=_async_stop_charging,
    ),
    EvchargoButtonDescription(
        key="refresh",
        translation_key="refresh",
        entity_category=EntityCategory.DIAGNOSTIC,
        press_fn=_async_refresh,
    ),
    EvchargoButtonDescription(
        key="reauthenticate",
        translation_key="reauthenticate",
        entity_category=EntityCategory.DIAGNOSTIC,
        press_fn=_async_reauthenticate,
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
    """Evchargo diagnostic action button."""

    def __init__(self, coordinator, description: EvchargoButtonDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self._charger_id}_{description.key}"
        self._attr_translation_key = description.translation_key

    async def async_press(self) -> None:
        await self.entity_description.press_fn(self.coordinator)
