from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .__init__ import EvchargoConfigEntry
from .entity import EvchargoCoordinatorEntity


@dataclass(frozen=True, kw_only=True)
class EvchargoBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], bool | None]


BINARY_SENSORS: tuple[EvchargoBinarySensorDescription, ...] = (
    EvchargoBinarySensorDescription(
        key="charging",
        name="Charging",
        value_fn=lambda data: (data.get("detail") or {}).get("cpInCharging"),
    ),
    EvchargoBinarySensorDescription(
        key="active_appointment",
        name="Active appointment",
        value_fn=lambda data: (data.get("detail") or {}).get("existsActiveAppointment"),
    ),
    EvchargoBinarySensorDescription(
        key="bluetooth_supported",
        name="Bluetooth supported",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: (data.get("detail") or {}).get("supportBlueTooth"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EvchargoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        EvchargoBinarySensor(coordinator, description) for description in BINARY_SENSORS
    )


class EvchargoBinarySensor(EvchargoCoordinatorEntity, BinarySensorEntity):
    """Evchargo binary sensor."""

    def __init__(self, coordinator, description: EvchargoBinarySensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self._charger_id}_{description.key}"
        self._attr_name = description.name

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data)
