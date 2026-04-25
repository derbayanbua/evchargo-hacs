from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "evchargo"
DEFAULT_NAME = "Evchargo"
DEFAULT_BASE_URL = "https://api.evchargo.com:7030/Charge"
DEFAULT_DEVICE_ID = "homeassistant-evchargo"
DEFAULT_CLIENT_TYPE = "ANDROID"
DEFAULT_CLIENT_VERSION = "2.7.0"
DEFAULT_FROM_APP = "Evchargo"
DEFAULT_LANGUAGE = "en"
DEFAULT_SCAN_INTERVAL_SECONDS = 60
MIN_SCAN_INTERVAL_SECONDS = 30
MAX_SCAN_INTERVAL_SECONDS = 240
DEFAULT_SCAN_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS)

CONF_BASE_URL = "base_url"
CONF_CHARGER_ID = "charger_id"
CONF_DEVICE_ID = "device_id"
CONF_SCAN_INTERVAL = "scan_interval"

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
]

ATTR_SETTABLE_CONTROLS = "settable_controls"
ATTR_EXPERIMENTAL_CONTROLS = "experimental_controls"

SERVICE_CONTROLS = ["charging_switch", "current_limit"]
EXPERIMENTAL_CONTROLS = [
    "plug_and_play_on_network",
    "boost_charging",
    "schedule",
    "operator_mode",
]


@dataclass(slots=True)
class EvchargoRuntimeData:
    api: "EvchargoApi"
    coordinator: "EvchargoDataUpdateCoordinator"
    charger_id: str
