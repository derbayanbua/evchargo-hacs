from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .value import first_value

STATUS_PATHS = (
    "detail.runStatus",
    "detail.status",
    "detail.cpStatus",
    "detail.chargeStatus",
    "detail.state",
)
CHARGING_PATHS = (
    "detail.cpInCharging",
    "detail.isCharging",
    "detail.charging",
    "detail.inCharging",
)
PLUG_PATHS = (
    "detail.isPlugged",
    "detail.plugged",
    "detail.connected",
    "detail.connectorPlugged",
)
ONLINE_PATHS = (
    "detail.online",
    "detail.isOnline",
    "detail.netOnline",
    "detail.connectedToNetwork",
)
CONNECTED_STATUSES = {"preparing", "suspendedev", "suspendedevse", "charging"}


def coerce_bool(value: Any) -> bool | None:
    """Parse explicit booleans without treating arbitrary numbers as true."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return None


def _boolean_evidence(
    data: dict[str, Any], paths: tuple[str, ...]
) -> tuple[bool | None, bool]:
    values = {
        coerce_bool(value)
        for path in paths
        if (value := first_value(data, path)) is not None
    }
    if not values:
        return None, False
    if len(values) != 1 or None in values:
        return None, True
    return values.pop(), False


@dataclass(frozen=True)
class ChargingState:
    """Connection/activity evidence, not a charging-authorization claim."""

    plugged_in: bool | None = None
    charging: bool | None = None
    normalized: Literal["A", "B", "C"] | None = None


def interpret_charging_state(data: dict[str, Any]) -> ChargingState:
    """Interpret only explicit connection fields and recognized status names."""
    raw_status = first_value(data, *STATUS_PATHS)
    status = str(raw_status).strip().lower() if raw_status is not None else None
    plugged, plug_conflict = _boolean_evidence(data, PLUG_PATHS)
    charging, charge_conflict = _boolean_evidence(data, CHARGING_PATHS)
    online, online_conflict = _boolean_evidence(data, ONLINE_PATHS)

    if online is False or online_conflict or plug_conflict or charge_conflict:
        return ChargingState()

    # Unknown/fault/offline statuses must not be hidden behind stale booleans.
    if status is not None and status != "available" and status not in CONNECTED_STATUSES:
        return ChargingState(plugged_in=plugged)

    status_plugged = None if status is None else status != "available"
    if (
        plugged is not None
        and status_plugged is not None
        and plugged != status_plugged
    ):
        return ChargingState()
    if plugged is None:
        plugged = status_plugged

    if charging is True:
        if plugged is False or status in {"preparing", "suspendedev", "suspendedevse"}:
            return ChargingState()
        return ChargingState(plugged_in=True, charging=True, normalized="C")

    if plugged is False:
        return ChargingState(plugged_in=False, charging=False, normalized="A")
    if plugged is True:
        if status == "charging" and charging is None:
            return ChargingState(plugged_in=True, charging=True, normalized="C")
        if charging is False or status in CONNECTED_STATUSES:
            return ChargingState(plugged_in=True, charging=False, normalized="B")
        return ChargingState(plugged_in=True)
    return ChargingState(charging=charging)
