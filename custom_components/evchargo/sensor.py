from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfElectricCurrent, UnitOfElectricPotential, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .__init__ import EvchargoConfigEntry
from .const import ATTR_EXPERIMENTAL_CONTROLS, ATTR_SETTABLE_CONTROLS, EXPERIMENTAL_CONTROLS, SERVICE_CONTROLS
from .entity import EvchargoCoordinatorEntity


@dataclass(frozen=True, kw_only=True)
class EvchargoSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]
    extra_attributes: bool = False


SENSORS: tuple[EvchargoSensorDescription, ...] = (
    EvchargoSensorDescription(
        key="status",
        name="Status",
        value_fn=lambda data: (data.get("detail") or {}).get("runStatus"),
        extra_attributes=True,
    ),
    EvchargoSensorDescription(
        key="power",
        name="Power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: ((data.get("detail") or {}).get("chargingData") or {}).get("power"),
    ),
    EvchargoSensorDescription(
        key="current",
        name="Current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: ((data.get("detail") or {}).get("chargingData") or {}).get("current"),
    ),
    EvchargoSensorDescription(
        key="voltage",
        name="Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: ((data.get("detail") or {}).get("chargingData") or {}).get("voltage"),
    ),
    EvchargoSensorDescription(
        key="session_energy",
        name="Session energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: ((data.get("detail") or {}).get("chargingData") or {}).get("energy"),
    ),
    EvchargoSensorDescription(
        key="signal",
        name="Signal",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: (data.get("detail") or {}).get("signal"),
    ),
    EvchargoSensorDescription(
        key="firmware",
        name="Firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: (data.get("firmware_info") or {}).get("currentVer"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EvchargoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(EvchargoSensor(coordinator, description) for description in SENSORS)


class EvchargoSensor(EvchargoCoordinatorEntity, SensorEntity):
    """Evchargo sensor."""

    def __init__(self, coordinator, description: EvchargoSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self._charger_id}_{description.key}"
        self._attr_name = description.name

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self.entity_description.extra_attributes:
            return None
        return _build_status_attributes(self.coordinator.data)


def _build_status_attributes(data: dict[str, Any]) -> dict[str, Any]:
    attrs: dict[str, Any] = {
        ATTR_SETTABLE_CONTROLS: SERVICE_CONTROLS,
        ATTR_EXPERIMENTAL_CONTROLS: EXPERIMENTAL_CONTROLS,
    }
    attrs.update(_flatten("detail", data.get("detail") or {}))
    for key in (
        "user_info",
        "cp_list",
        "cp_list_alt",
        "home_users",
        "rfid_cp_list",
        "auth_user_list",
        "firmware_info",
        "upgrade_status",
        "lbc_and_pv",
        "rate",
        "platforms",
        "payment_config",
    ):
        value = data.get(key)
        if value is not None:
            attrs.update(_flatten(key, value))
    return attrs


def _flatten(prefix: str, value: Any) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, inner in value.items():
            flattened.update(_flatten(f"{prefix}.{key}", inner))
        return flattened
    if isinstance(value, list):
        for index, inner in enumerate(value):
            flattened.update(_flatten(f"{prefix}[{index}]", inner))
        return flattened
    flattened[prefix] = value
    return flattened
