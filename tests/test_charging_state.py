"""Regression coverage using synthetic payloads, with no cloud/device access."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.exceptions import HomeAssistantError

from custom_components.evchargo.api import (
    EvchargoApi,
    EvchargoApiError,
    normalize_charger_id,
)
from custom_components.evchargo.binary_sensor import (
    BINARY_SENSORS,
    EvchargoBinarySensor,
)
from custom_components.evchargo.charging_state import (
    ChargingState,
    coerce_bool,
    interpret_charging_state,
)
from custom_components.evchargo.coordinator import EvchargoDataUpdateCoordinator
from custom_components.evchargo.config_flow import _build_user_schema
from custom_components.evchargo.sensor import SENSORS, EvchargoSensor
from custom_components.evchargo.switch import EvchargoChargingSwitch


def payload(**detail):
    return {"detail": detail}


def coordinator(data, charger_id="test-charger"):
    """Construct a real coordinator with mocked HA and cloud boundaries."""
    entry = MagicMock()
    entry.pref_disable_polling = False
    result = EvchargoDataUpdateCoordinator(
        MagicMock(), entry, MagicMock(), charger_id
    )
    result.data = data
    result.api.async_get_overview = AsyncMock(return_value=data)
    result.api.async_start_charging = AsyncMock()
    result.api.async_stop_charging = AsyncMock()
    result.async_request_refresh = AsyncMock()
    result.async_update_listeners = MagicMock()
    return result


class InterpretationTests(unittest.TestCase):
    def test_charger_id_is_trimmed_at_config_and_runtime_boundaries(self):
        self.assertEqual(normalize_charger_id("  CP-123 \n"), "CP-123")
        with self.assertRaisesRegex(EvchargoApiError, "must not be empty"):
            normalize_charger_id(" \t ")
        validated = _build_user_schema()({
            "username": "user@example.invalid",
            "password": "password",
            "charger_id": "  CP-123 ",
            "base_url": "https://api.evchargo.com:7030/Charge",
            "device_id": "test-device",
            "scan_interval": 60,
        })
        self.assertEqual(validated["charger_id"], "CP-123")
        instance = coordinator({}, charger_id="  CP-123 \n")
        self.assertEqual(instance.charger_id, "CP-123")

    def test_status_mapping(self):
        cases = (
            ({}, ChargingState()),
            (payload(cpInCharging=False), ChargingState(charging=False)),
            (payload(runStatus="Available"), ChargingState(False, False, "A")),
            (payload(runStatus=" Preparing "), ChargingState(True, False, "B")),
            (payload(runStatus="SuspendedEV"), ChargingState(True, False, "B")),
            (payload(runStatus="SuspendedEVSE"), ChargingState(True, False, "B")),
            (payload(runStatus="Charging"), ChargingState(True, True, "C")),
            (payload(cpInCharging=True), ChargingState(True, True, "C")),
            (payload(runStatus="Charging", cpInCharging=False),
             ChargingState(True, False, "B")),
            (payload(isPlugged=False), ChargingState(False, False, "A")),
            (payload(isPlugged=True), ChargingState(plugged_in=True)),
            (payload(isPlugged=True, cpInCharging=False),
             ChargingState(True, False, "B")),
            (payload(isPlugged=False, cpInCharging=False),
             ChargingState(False, False, "A")),
        )
        for data, expected in cases:
            with self.subTest(data=data):
                self.assertEqual(interpret_charging_state(data), expected)

    def test_occupancy_and_cable_holder_are_not_connection_evidence(self):
        for value in (True, False):
            self.assertEqual(
                interpret_charging_state(payload(
                    inOccupied=value,
                    chargingData={"inOccupied": value},
                    connectorSeat=value,
                    supportConnectorLock=value,
                    existsActiveAppointment=value,
                )),
                ChargingState(),
            )

    def test_unknown_faulted_and_offline_do_not_become_valid_states(self):
        for status in ("FutureStatus", "Faulted", "Offline", "Unavailable"):
            with self.subTest(status=status):
                self.assertIsNone(interpret_charging_state(payload(
                    runStatus=status, cpInCharging=True,
                )).normalized)
        self.assertEqual(
            interpret_charging_state(payload(
                runStatus="Charging", cpInCharging=True, online=False,
            )),
            ChargingState(),
        )

    def test_contradictions_remain_unknown(self):
        cases = (
            payload(runStatus="Available", cpInCharging=True),
            payload(runStatus="Available", isPlugged=True),
            payload(runStatus="Charging", isPlugged=False),
            payload(runStatus="SuspendedEV", cpInCharging=True),
            payload(isPlugged=False, cpInCharging=True),
            payload(isPlugged=False, connected=True),
            payload(cpInCharging=False, isCharging=True),
            payload(runStatus="Available", online=True, isOnline=False),
            payload(runStatus="Available", isPlugged="invalid"),
        )
        for data in cases:
            with self.subTest(data=data):
                self.assertEqual(interpret_charging_state(data), ChargingState())

    def test_explicit_booleans(self):
        for value in (False, 0, "false", "0", "off", "no"):
            self.assertIs(coerce_bool(value), False)
        for value in (True, 1, "true", "1", "on", "yes"):
            self.assertIs(coerce_bool(value), True)
        for value in (None, "", "unknown", 2, -1, float("nan")):
            self.assertIsNone(coerce_bool(value))

    def test_fallback_field_names(self):
        for key in ("runStatus", "status", "cpStatus", "chargeStatus", "state"):
            with self.subTest(key=key):
                self.assertEqual(
                    interpret_charging_state(payload(**{key: "Available"})),
                    ChargingState(False, False, "A"),
                )
        for key in ("isPlugged", "plugged", "connected", "connectorPlugged"):
            with self.subTest(key=key):
                self.assertEqual(
                    interpret_charging_state(payload(**{key: "false"})),
                    ChargingState(False, False, "A"),
                )
        for key in ("cpInCharging", "isCharging", "charging", "inCharging"):
            with self.subTest(key=key):
                self.assertEqual(
                    interpret_charging_state(payload(**{key: "true"})),
                    ChargingState(True, True, "C"),
                )


class CoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_api_write_paths_trim_charger_id(self):
        api = EvchargoApi(MagicMock(), "user", "password")
        api._request_authenticated = AsyncMock(return_value={"code": 2000})
        await api.async_start_charging("  CP-123 ")
        api._request_authenticated.assert_awaited_once()
        self.assertEqual(
            api._request_authenticated.await_args.args,
            ("POST", "/app/v1/home/cp/CP-123/start"),
        )
        api._request_authenticated.reset_mock()
        await api.async_set_current_limit("CP-123\t", 16)
        self.assertEqual(
            api._request_authenticated.await_args.args,
            ("PUT", "/app/v1/home/cp/CP-123/current"),
        )

    async def test_start_guard_uses_same_connection_interpreter(self):
        cases = (
            (payload(runStatus="Available"), False),
            (payload(isPlugged=False), False),
            (payload(cpInCharging=False), False),
            (payload(runStatus="Preparing"), True),
            (payload(runStatus="SuspendedEV"), True),
            (payload(runStatus="SuspendedEVSE"), True),
            (payload(runStatus="Charging", cpInCharging=False), True),
            (payload(cpInCharging=True), True),
            (payload(runStatus="Available", cpInCharging=True), False),
            (payload(runStatus="Faulted", isPlugged=True), False),
            (payload(runStatus="NewStatus", isPlugged=True), False),
            (payload(runStatus="Charging", online=False), False),
        )
        for data, allowed in cases:
            with self.subTest(data=data):
                instance = coordinator(data)
                if allowed:
                    await instance._async_validate_can_start_charging()
                else:
                    with self.assertRaises(EvchargoApiError):
                        await instance._async_validate_can_start_charging()

    async def test_rejected_start_never_calls_start_api(self):
        instance = coordinator(payload(runStatus="Available"))
        with self.assertRaisesRegex(HomeAssistantError, "not connected"):
            await instance.async_set_charging_enabled(True)
        instance.api.async_start_charging.assert_not_awaited()
        self.assertIsNone(instance.requested_charging_enabled)

    async def test_delayed_start_intent_is_not_permission_confirmation(self):
        instance = coordinator(payload(runStatus="Preparing", cpInCharging=False))
        with patch("custom_components.evchargo.coordinator.monotonic", return_value=0):
            await instance.async_set_charging_enabled(True)
        instance.api.async_start_charging.assert_awaited_once_with("test-charger")
        self.assertIsNone(instance.charging_enabled)
        self.assertIs(instance.requested_charging_enabled, True)
        for now in (60, 179):
            with patch("custom_components.evchargo.coordinator.monotonic", return_value=now):
                instance._reconcile_charging_state(instance.data)
            self.assertIsNone(instance.charging_enabled)
            self.assertIs(instance.requested_charging_enabled, True)
        instance._reconcile_charging_state(payload(runStatus="Charging", cpInCharging=True))
        self.assertIs(instance.charging_enabled, True)
        self.assertIsNone(instance.requested_charging_enabled)
        self.assertEqual(instance.update_interval.total_seconds(), 60)

    async def test_start_timeout_clears_intent_without_claiming_disabled(self):
        instance = coordinator(payload(runStatus="SuspendedEV", cpInCharging=False))
        with patch("custom_components.evchargo.coordinator.monotonic", return_value=0):
            instance._set_pending_state(True)
        with (
            patch("custom_components.evchargo.coordinator.monotonic", return_value=180),
            self.assertLogs("custom_components.evchargo.coordinator", level="WARNING"),
        ):
            instance._reconcile_charging_state(instance.data)
        self.assertIsNone(instance.requested_charging_enabled)
        self.assertIsNone(instance.charging_enabled)
        self.assertEqual(instance.update_interval.total_seconds(), 60)

    async def test_suspension_unplug_and_missing_data_do_not_mean_disabled(self):
        instance = coordinator({})
        for detail in (
            {"runStatus": "SuspendedEV", "cpInCharging": False},
            {"runStatus": "SuspendedEVSE", "cpInCharging": False},
            {"runStatus": "Available", "cpInCharging": False},
            {"cpInCharging": False},
            {},
            {"runStatus": "Faulted", "cpInCharging": True},
            {"runStatus": "Charging", "online": False},
        ):
            with self.subTest(detail=detail):
                instance._reconcile_charging_state(payload(cpInCharging=True))
                self.assertIs(instance.charging_enabled, True)
                instance._reconcile_charging_state(payload(**detail))
                self.assertIsNone(instance.charging_enabled)

    async def test_stop_confirmation_is_activity_only(self):
        instance = coordinator(payload(runStatus="Charging", cpInCharging=True))
        instance._reconcile_charging_state(instance.data)
        await instance.async_set_charging_enabled(False)
        self.assertIs(instance.charging_enabled, True)
        self.assertIs(instance.requested_charging_enabled, False)
        instance._reconcile_charging_state(payload(runStatus="SuspendedEVSE"))
        self.assertIsNone(instance.requested_charging_enabled)
        self.assertIsNone(instance.charging_enabled)

    async def test_failed_start_does_not_create_pending_intent(self):
        instance = coordinator(payload(runStatus="Preparing"))
        instance.api.async_start_charging.side_effect = EvchargoApiError("failed")
        with self.assertRaisesRegex(HomeAssistantError, "failed"):
            await instance.async_set_charging_enabled(True)
        self.assertIsNone(instance.requested_charging_enabled)
        self.assertIsNone(instance.charging_enabled)

    async def test_stop_timeout_does_not_claim_disabled_while_still_charging(self):
        instance = coordinator(payload(runStatus="Charging", cpInCharging=True))
        with patch("custom_components.evchargo.coordinator.monotonic", return_value=0):
            instance._set_pending_state(False)
        with (
            patch("custom_components.evchargo.coordinator.monotonic", return_value=180),
            self.assertLogs("custom_components.evchargo.coordinator", level="WARNING"),
        ):
            instance._reconcile_charging_state(instance.data)
        self.assertIsNone(instance.requested_charging_enabled)
        self.assertIs(instance.charging_enabled, True)

    async def test_overview_update_publishes_interpreted_state(self):
        instance = coordinator(payload(
            runStatus="Available", cpInCharging=False,
            chargingData={"inOccupied": False}, connectorSeat=False,
            supportConnectorLock=False,
        ))
        result = await instance._async_update_data()
        self.assertEqual(result["derived_power_kw"], 0)
        self.assertIsNone(instance.charging_enabled)
        self.assertEqual(interpret_charging_state(result), ChargingState(False, False, "A"))

    async def test_entities_preserve_raw_status_and_expose_unknown_switch(self):
        instance = coordinator(payload(runStatus="Available", cpInCharging=False))
        sensors = {item.key: EvchargoSensor(instance, item) for item in SENSORS}
        binary = {item.key: EvchargoBinarySensor(instance, item) for item in BINARY_SENSORS}
        self.assertEqual(sensors["status"].native_value, "Available")
        self.assertEqual(sensors["charging_state"].native_value, "A")
        self.assertIs(binary["plugged_in"].is_on, False)
        self.assertEqual(sensors["status"].extra_state_attributes["detail.runStatus"], "Available")
        instance.data = payload(runStatus="Charging", cpInCharging=False)
        self.assertEqual(sensors["status"].native_value, "Not charging")
        self.assertEqual(sensors["charging_state"].native_value, "B")
        self.assertIs(binary["charging"].is_on, False)
        switch = EvchargoChargingSwitch(instance)
        self.assertIsNone(switch.is_on)
        self.assertIsNone(switch.state)
        self.assertTrue(switch.assumed_state)
        instance._set_pending_state(True)
        self.assertIsNone(switch.is_on)
        self.assertEqual(switch.extra_state_attributes, {"requested_charging_enabled": True})
        instance._reconcile_charging_state(payload(cpInCharging=True))
        self.assertIs(switch.is_on, True)
        self.assertEqual(switch.state, "on")
        self.assertFalse(switch.assumed_state)
        instance.data = payload(runStatus="Faulted")
        self.assertIsNone(sensors["charging_state"].native_value)
        self.assertEqual(sensors["status"].native_value, "Faulted")
