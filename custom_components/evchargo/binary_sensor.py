from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .__init__ import EvchargoConfigEntry
from .coordinator import _coerce_bool
from .entity import EvchargoCoordinatorEntity
from .value import first_value


@dataclass(frozen=True, kw_only=True)
class EvchargoBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], bool | None]


BINARY_SENSORS: tuple[EvchargoBinarySensorDescription, ...] = (
    EvchargoBinarySensorDescription(
        key="charging",
        translation_key="charging",
        value_fn=lambda data: first_value(
            data,
            "detail.cpInCharging",
            "detail.isCharging",
            "detail.charging",
            "detail.inCharging",
        ),
    ),
    EvchargoBinarySensorDescription(
        key="plugged_in",
        translation_key="plugged_in",
        device_class=BinarySensorDeviceClass.PLUG,
        value_fn=lambda data: first_value(
            data,
            "detail.isPlugged",
            "detail.plugged",
            "detail.connected",
            "detail.connectorPlugged",
            "detail.inOccupied",
        ),
    ),
    EvchargoBinarySensorDescription(
        key="online",
        translation_key="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: first_value(
            data,
            "detail.online",
            "detail.isOnline",
            "detail.netOnline",
            "detail.connectedToNetwork",
        ),
    ),
    EvchargoBinarySensorDescription(
        key="active_appointment",
        translation_key="active_appointment",
        value_fn=lambda data: first_value(
            data,
            "detail.existsActiveAppointment",
            "detail.isPlugged",
            "detail.plugged",
            "detail.connected",
        ),
    ),
    EvchargoBinarySensorDescription(
        key="bluetooth_supported",
        translation_key="bluetooth_supported",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: first_value(
            data,
            "detail.supportBlueTooth",
            "detail.supportBluetooth",
            "detail.bluetoothSupported",
        ),
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
        self._attr_translation_key = description.translation_key

    @property
    def is_on(self) -> bool | None:
        return _coerce_bool(self.entity_description.value_fn(self.coordinator.data))
