from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN
from .coordinator import EvchargoDataUpdateCoordinator


class EvchargoCoordinatorEntity(CoordinatorEntity[EvchargoDataUpdateCoordinator]):
    """Base entity for Evchargo coordinator-backed entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EvchargoDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._charger_id = coordinator.charger_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._charger_id)},
            manufacturer="EN+",
            model=(coordinator.data.get("detail") or {}).get("deviceModel"),
            name=(coordinator.data.get("detail") or {}).get("cpName") or DEFAULT_NAME,
            sw_version=((coordinator.data.get("firmware_info") or {}).get("currentVer")),
        )
