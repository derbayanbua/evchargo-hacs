from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorExtraStoredData,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .__init__ import EvchargoConfigEntry
from .const import (
    ATTR_EXPERIMENTAL_CONTROLS,
    ATTR_SETTABLE_CONTROLS,
    CONF_EXPOSE_SENSITIVE_ATTRIBUTES,
    DEFAULT_EXPOSE_SENSITIVE_ATTRIBUTES,
    EXPERIMENTAL_CONTROLS,
    SERVICE_CONTROLS,
)
from .coordinator import DERIVED_POWER_KEY, SESSION_ENERGY_PATHS, _coerce_bool
from .entity import EvchargoCoordinatorEntity
from .value import first_float, first_value

SAFE_STATUS_ATTRIBUTE_SOURCES = (
    "detail",
    "firmware_info",
    "upgrade_status",
    "lbc_and_pv",
    "rate",
)
SENSITIVE_ATTRIBUTE_KEY_PARTS = (
    "address",
    "auth",
    "email",
    "location",
    "mobile",
    "name",
    "order",
    "password",
    "payment",
    "phone",
    "rfid",
    "serial",
    "token",
    "user",
)
REDACTED_ATTRIBUTE_VALUE = "***"


@dataclass(frozen=True, kw_only=True)
class EvchargoSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]
    extra_attributes: bool = False
    keep_last_value: bool = False


SENSORS: tuple[EvchargoSensorDescription, ...] = (
    EvchargoSensorDescription(
        key="status",
        translation_key="status",
        value_fn=lambda data: _charging_aware_status(data),
        extra_attributes=True,
    ),
    EvchargoSensorDescription(
        key="power",
        translation_key="power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _power(data),
    ),
    EvchargoSensorDescription(
        key="current",
        translation_key="current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: first_float(
            data,
            "detail.chargingData.current",
            "detail.current",
            "detail.ampere",
        ),
    ),
    EvchargoSensorDescription(
        key="voltage",
        translation_key="voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: first_float(
            data,
            "detail.chargingData.voltage",
            "detail.voltage",
        ),
    ),
    EvchargoSensorDescription(
        key="session_energy",
        translation_key="session_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        keep_last_value=True,
        value_fn=lambda data: first_float(data, *SESSION_ENERGY_PATHS),
    ),
    EvchargoSensorDescription(
        key="current_limit_state",
        translation_key="current_limit_state",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: first_float(
            data,
            "detail.setCurrent",
            "detail.currentLimit",
            "detail.maxCurrent",
            "rate.connectorSetCurrentList.0.current",
        ),
    ),
    EvchargoSensorDescription(
        key="minimum_current",
        translation_key="minimum_current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: first_float(
            data,
            "detail.enableMinCurrent",
            "detail.minCurrent",
            "rate.connectorSetCurrentList.0.minCurrent",
        ),
    ),
    EvchargoSensorDescription(
        key="maximum_current",
        translation_key="maximum_current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: first_float(
            data,
            "detail.enableMaxCurrent",
            "detail.maxCurrent",
            "rate.connectorSetCurrentList.0.maxCurrent",
        ),
    ),
    EvchargoSensorDescription(
        key="session_order_id",
        translation_key="session_order_id",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: first_value(
            data,
            "detail.chargingData.orderId",
            "detail.orderId",
            "detail.chargeOrderId",
        ),
    ),
    EvchargoSensorDescription(
        key="signal",
        translation_key="signal",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: first_value(
            data,
            "detail.signal",
            "detail.rssi",
            "detail.csq",
        ),
    ),
    EvchargoSensorDescription(
        key="firmware",
        translation_key="firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: first_value(
            data,
            "firmware_info.currentVer",
            "firmware_info.version",
            "detail.firmwareVersion",
            "detail.currentVer",
        ),
    ),
    EvchargoSensorDescription(
        key="latest_firmware",
        translation_key="latest_firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: first_value(
            data,
            "firmware_info.latestVer",
            "firmware_info.latestVersion",
            "firmware_info.newVer",
            "upgrade_status.version",
        ),
    ),
)


def _power(data: dict[str, Any]) -> float | None:
    """Prefer reported power, falling back to power derived from energy growth."""
    reported = first_float(
        data,
        "detail.chargingData.power",
        "detail.chargingData.ratePower",
        "detail.power",
        "detail.ratePower",
        "detail.kwPower",
    )
    if reported is not None and reported > 0:
        return reported
    derived = data.get(DERIVED_POWER_KEY)
    if derived is not None:
        return derived
    return reported


def _charging_aware_status(data: dict[str, Any]) -> Any:
    """Avoid showing stale cloud status as active charging."""
    status = first_value(
        data,
        "detail.runStatus",
        "detail.status",
        "detail.cpStatus",
        "detail.chargeStatus",
        "detail.state",
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
    if charging is False and str(status).strip().lower() == "charging":
        return "Not charging"
    return status


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EvchargoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    entities: list[SensorEntity] = [
        EvchargoSensor(coordinator, description) for description in SENSORS
    ]
    entities.append(EvchargoTotalEnergySensor(coordinator))
    async_add_entities(entities)


class EvchargoSensor(EvchargoCoordinatorEntity, SensorEntity):
    """Evchargo sensor."""

    def __init__(self, coordinator, description: EvchargoSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self._charger_id}_{description.key}"
        self._attr_translation_key = description.translation_key
        self._last_value: Any = None

    @property
    def native_value(self) -> Any:
        value = self.entity_description.value_fn(self.coordinator.data)
        if not self.entity_description.keep_last_value:
            return value
        if value is not None:
            self._last_value = value
        return self._last_value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self.entity_description.extra_attributes:
            return None
        expose_sensitive = self.coordinator.config_entry.options.get(
            CONF_EXPOSE_SENSITIVE_ATTRIBUTES, DEFAULT_EXPOSE_SENSITIVE_ATTRIBUTES
        )
        return _build_status_attributes(self.coordinator.data, expose_sensitive)


class EvchargoTotalEnergyStoredData(SensorExtraStoredData):
    """Restore data for the total energy sensor, including session tracking."""

    def __init__(
        self,
        native_value: float | None,
        native_unit_of_measurement: str | None,
        session_key: str | None,
        session_energy: float | None,
    ) -> None:
        super().__init__(native_value, native_unit_of_measurement)
        self.session_key = session_key
        self.session_energy = session_energy

    def as_dict(self) -> dict[str, Any]:
        data = super().as_dict()
        data["session_key"] = self.session_key
        data["session_energy"] = self.session_energy
        return data


class EvchargoTotalEnergySensor(EvchargoCoordinatorEntity, RestoreSensor):
    """Lifetime charged energy accumulated from per-session energy readings."""

    _attr_translation_key = "total_energy"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._charger_id}_total_energy"
        self._total: float = 0.0
        self._session_key: str | None = None
        self._session_energy: float | None = None

    @property
    def native_value(self) -> float:
        return round(self._total, 3)

    @property
    def extra_restore_state_data(self) -> EvchargoTotalEnergyStoredData:
        return EvchargoTotalEnergyStoredData(
            self.native_value,
            self.native_unit_of_measurement,
            self._session_key,
            self._session_energy,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_extra_data()) is not None:
            restored = last.as_dict()
            self._total = _as_float(restored.get("native_value")) or 0.0
            self._session_key = restored.get("session_key")
            self._session_energy = _as_float(restored.get("session_energy"))
        self._accumulate()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._accumulate()
        super()._handle_coordinator_update()

    def _accumulate(self) -> None:
        data = self.coordinator.data or {}
        energy = first_float(data, *SESSION_ENERGY_PATHS)
        if energy is None or energy < 0:
            return
        session_key = _session_key(data)
        previous = self._session_energy

        new_session = (
            session_key is not None and session_key != self._session_key
        ) or previous is None or energy < previous
        delta = energy if new_session else energy - previous

        self._total += delta
        self._session_energy = energy
        if session_key is not None:
            self._session_key = session_key


def _session_key(data: dict[str, Any]) -> str | None:
    order_id = first_value(
        data,
        "detail.chargingData.orderId",
        "detail.orderId",
        "detail.chargeOrderId",
    )
    if order_id is None:
        return None
    return hashlib.sha256(str(order_id).encode()).hexdigest()[:16]


def _as_float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


SENSITIVE_COUNT_BLOBS = {
    "rfid_cp_list": "rfid_card_count",
    "auth_user_list": "authorized_user_count",
    "home_users": "home_user_count",
}

ALL_STATUS_ATTRIBUTE_SOURCES = (
    "user_info",
    "detail",
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
)


def _build_status_attributes(
    data: dict[str, Any], expose_sensitive: bool = False
) -> dict[str, Any]:
    attrs: dict[str, Any] = {
        ATTR_SETTABLE_CONTROLS: SERVICE_CONTROLS,
        ATTR_EXPERIMENTAL_CONTROLS: EXPERIMENTAL_CONTROLS,
    }

    if expose_sensitive:
        for key in ALL_STATUS_ATTRIBUTE_SOURCES:
            value = data.get(key)
            if value is not None:
                attrs.update(_flatten(key, value))
        return attrs

    for key in SAFE_STATUS_ATTRIBUTE_SOURCES:
        value = data.get(key)
        if value is not None:
            attrs.update(_flatten_safe(key, value))
    for key, attr_name in SENSITIVE_COUNT_BLOBS.items():
        value = data.get(key)
        if value is not None:
            attrs[attr_name] = _count_records(value)
    return attrs


def _flatten_safe(prefix: str, value: Any) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    if _is_sensitive_attribute_key(prefix):
        flattened[prefix] = REDACTED_ATTRIBUTE_VALUE
        return flattened
    if isinstance(value, dict):
        for key, inner in value.items():
            flattened.update(_flatten_safe(f"{prefix}.{key}", inner))
        return flattened
    if isinstance(value, list):
        for index, inner in enumerate(value):
            flattened.update(_flatten_safe(f"{prefix}[{index}]", inner))
        return flattened
    flattened[prefix] = value
    return flattened


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


def _count_records(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        for inner_key in ("records", "list", "rows", "data"):
            inner = value.get(inner_key)
            if isinstance(inner, list):
                return len(inner)
    return 0


def _is_sensitive_attribute_key(key: str) -> bool:
    normalized = key.lower()
    return any(part in normalized for part in SENSITIVE_ATTRIBUTE_KEY_PARTS)
