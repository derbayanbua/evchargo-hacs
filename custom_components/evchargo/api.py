from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from aiohttp import ClientError, ClientResponse, ClientSession

from .const import (
    DEFAULT_BASE_URL,
    DEFAULT_CLIENT_TYPE,
    DEFAULT_CLIENT_VERSION,
    DEFAULT_DEVICE_ID,
    DEFAULT_FROM_APP,
    DEFAULT_LANGUAGE,
)

_LOGGER = logging.getLogger(__name__)

SUCCESS_CODE = 2000
AUTH_ERROR_CODES = {4001, 4010, 4401, 4402, 80114}
CHARGER_ID_KEYS = ("cpId", "chargerId", "id", "pileId")
SENSITIVE_KEYS = {"password", "token", "satoken", "authorization", "email"}


class EvchargoError(Exception):
    """Base Evchargo error."""


class EvchargoAuthError(EvchargoError):
    """Authentication failed."""


class EvchargoApiError(EvchargoError):
    """API request failed."""


def normalize_base_url(base_url: str) -> str:
    """Return a sanitized Evchargo API base URL."""
    parsed = urlsplit(base_url.strip())
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise EvchargoApiError("Evchargo base URL must be an HTTPS URL")
    if parsed.username or parsed.password:
        raise EvchargoApiError("Evchargo base URL must not contain credentials")
    if parsed.query or parsed.fragment:
        raise EvchargoApiError(
            "Evchargo base URL must not contain query or fragment parts"
        )
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            "",
            "",
        )
    )


class EvchargoApi:
    """Async Evchargo API client for the confirmed app endpoints."""

    def __init__(
        self,
        session: ClientSession,
        username: str,
        password: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        device_id: str = DEFAULT_DEVICE_ID,
        language: str = DEFAULT_LANGUAGE,
        timezone: str = "Europe/Berlin",
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._base_url = normalize_base_url(base_url)
        self._device_id = device_id
        self._language = language
        self._timezone = timezone
        self._token: str | None = None
        self._auth_lock = asyncio.Lock()

    @property
    def token(self) -> str | None:
        return self._token

    def _headers(self, include_token: bool = True) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": self._language,
            "User-Agent": "okhttp/4.12.0",
            "fromApp": DEFAULT_FROM_APP,
            "clientType": DEFAULT_CLIENT_TYPE,
            "clientVersion": DEFAULT_CLIENT_VERSION,
            "timeZone": self._timezone,
            "timeZoneStr": self._timezone,
        }
        if include_token and self._token:
            headers["satoken"] = self._token
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
        json_data: Mapping[str, Any] | None = None,
        include_token: bool = True,
    ) -> dict[str, Any]:
        url = f"{self._base_url}/{path.lstrip('/')}"
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                "Evchargo request %s %s include_token=%s params=%s data=%s json=%s",
                method,
                path,
                include_token,
                _sanitize_mapping(params),
                _sanitize_mapping(data),
                _sanitize_mapping(json_data),
            )
        try:
            async with self._session.request(
                method,
                url,
                headers=self._headers(include_token=include_token),
                params=params,
                data=data,
                json=json_data,
            ) as response:
                return await self._parse_response(response, method=method, path=path)
        except TimeoutError as err:
            raise EvchargoApiError(f"Timeout calling {method} {path}") from err
        except ClientError as err:
            raise EvchargoApiError(f"HTTP error calling {method} {path}: {err}") from err

    async def _parse_response(
        self, response: ClientResponse, *, method: str, path: str
    ) -> dict[str, Any]:
        try:
            payload = await response.json(content_type=None)
        except Exception as err:  # noqa: BLE001
            text = await response.text()
            raise EvchargoApiError(
                f"Unexpected non-JSON response from {method} {path} "
                f"(HTTP {response.status}): {text[:200]}"
            ) from err
        if not isinstance(payload, dict):
            raise EvchargoApiError(
                f"Unexpected JSON response from {method} {path} "
                f"(HTTP {response.status}): {type(payload).__name__}"
            )

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                "Evchargo response %s %s status=%s summary=%s",
                method,
                path,
                response.status,
                _summarize_payload(payload),
            )

        code = payload.get("code")
        message = payload.get("message")
        if code in AUTH_ERROR_CODES or response.status in {401, 403}:
            raise EvchargoAuthError(
                f"{method} {path} authentication failed with HTTP {response.status}, "
                f"API code {code}: {message or 'no message'}"
            )
        if response.status >= 400:
            raise EvchargoApiError(
                f"{method} {path} failed with HTTP {response.status}, "
                f"API code {code}: {message or 'no message'}"
            )
        return payload

    async def async_login(self, *, force: bool = False) -> str:
        if self._token and not force:
            return self._token

        async with self._auth_lock:
            if self._token and not force:
                return self._token

            payload = {
                "loginType": "EMAIL",
                "email": self._username,
                "password": self._password,
                "deviceId": self._device_id,
                "clientType": DEFAULT_CLIENT_TYPE,
                "encrypt": "false",
            }
            response = await self._request(
                "POST",
                "/app/v1/user/login",
                data=payload,
                include_token=False,
            )
            if response.get("code") != SUCCESS_CODE or not response.get("data"):
                raise EvchargoAuthError(
                    response.get("message") or f"Login failed ({response.get('code')})"
                )
            token = response["data"].get("token")
            if not token:
                raise EvchargoAuthError("Login succeeded but token is missing")
            self._token = token
            return token

    async def async_logout(self) -> None:
        if not self._token:
            return
        try:
            await self._request("DELETE", "/app/v1/user/logout")
        except EvchargoError:
            _LOGGER.debug("Logout failed", exc_info=True)
        finally:
            self._token = None

    async def _request_authenticated(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
        json_data: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        await self.async_login()
        try:
            response = await self._request(
                method,
                path,
                params=params,
                data=data,
                json_data=json_data,
                include_token=True,
            )
        except EvchargoAuthError:
            await self.async_login(force=True)
            response = await self._request(
                method,
                path,
                params=params,
                data=data,
                json_data=json_data,
                include_token=True,
            )

        if response.get("code") != SUCCESS_CODE:
            raise EvchargoApiError(
                f"{method} {path} failed with API code {response.get('code')}: "
                f"{response.get('message') or 'no message'}"
            )
        return response

    async def async_get_json(self, path: str) -> dict[str, Any]:
        response = await self._request_authenticated("GET", path)
        return response.get("data") or {}

    async def async_get_optional_json(self, path: str) -> dict[str, Any] | None:
        try:
            return await self.async_get_json(path)
        except EvchargoError:
            _LOGGER.debug("Optional endpoint failed: %s", path, exc_info=True)
            return None

    async def async_get_overview(self, charger_id: str) -> dict[str, Any]:
        detail = await self.async_get_json(f"/app/v1/home/cp/{charger_id}/detail")
        cp_list = await self.async_get_json("/app/v1/home/cp/list")
        user_info = await self.async_get_json("/app/v1/user/info")

        optional_paths = {
            "cp_list_alt": "/app/v1/home/cpList",
            "home_users": "/app/v1/user/home/cp/users",
            "rfid_cp_list": "/app/v1/user/rfid/cpList",
            "auth_user_list": f"/app/v1/home/cp/{charger_id}/authUserList",
            "firmware_info": f"/app/v1/home/cp/{charger_id}/latestFirmwareInfo",
            "upgrade_status": f"/app/v1/home/cp/{charger_id}/upgradeStatus",
            "lbc_and_pv": f"/app/v1/home/cp/settings/lbcAndPv/{charger_id}",
            "rate": f"/app/v1/home/{charger_id}/rate",
            "platforms": "/app/v1/home/getPlatformList",
            "payment_config": f"/app/v1/business/payment/config/{charger_id}",
        }

        optional_data = await asyncio.gather(
            *(self.async_get_optional_json(path) for path in optional_paths.values())
        )

        result = {
            "charger_id": charger_id,
            "detail": detail,
            "cp_list": cp_list,
            "user_info": user_info,
        }
        result.update(dict(zip(optional_paths.keys(), optional_data, strict=True)))

        result["detail"] = self._merge_charger_detail(
            charger_id,
            result.get("detail"),
            result.get("cp_list"),
            result.get("cp_list_alt"),
        )
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                "Evchargo overview for charger=%s detail_keys=%s cp_list_type=%s cp_list_alt_type=%s",
                charger_id,
                sorted((result.get("detail") or {}).keys()),
                type(result.get("cp_list")).__name__,
                type(result.get("cp_list_alt")).__name__,
            )
        return result

    async def async_start_charging(self, charger_id: str, connector_num: int = 1) -> None:
        await self._request_charge_action("start", charger_id, connector_num)

    async def async_stop_charging(
        self,
        charger_id: str,
        connector_num: int = 1,
        *,
        order_id: int | str | None = None,
    ) -> None:
        await self._request_charge_action(
            "stop",
            charger_id,
            connector_num,
            order_id=order_id,
        )

    async def async_set_current_limit(
        self,
        charger_id: str,
        current: int,
        *,
        connector_num: int = 1,
    ) -> None:
        attempts: tuple[tuple[str, dict[str, Mapping[str, Any]]], ...] = (
            ("PUT", {"params": {"current": current}}),
            ("PUT", {"params": {"connectorNum": connector_num, "current": current}}),
            ("POST", {"params": {"current": current}}),
            ("POST", {"params": {"connectorNum": connector_num, "current": current}}),
            ("PUT", {"data": {"current": current}}),
            ("PUT", {"data": {"connectorNum": connector_num, "current": current}}),
            ("POST", {"data": {"current": current}}),
            ("POST", {"data": {"connectorNum": connector_num, "current": current}}),
            ("PUT", {"json_data": {"current": current}}),
            ("PUT", {"json_data": {"connectorNum": connector_num, "current": current}}),
        )
        last_error: Exception | None = None
        path = f"/app/v1/home/cp/{charger_id}/current"
        for method, kwargs in attempts:
            try:
                await self._request_authenticated(method, path, **kwargs)
                return
            except EvchargoError as err:
                last_error = err
                _LOGGER.debug(
                    "Current limit variant failed (%s %s): %s", method, kwargs, err
                )
        raise EvchargoApiError(f"Unable to set current limit: {last_error}")

    async def _request_charge_action(
        self,
        action: str,
        charger_id: str,
        connector_num: int = 1,
        *,
        order_id: int | str | None = None,
    ) -> None:
        path = f"/app/v1/home/cp/{charger_id}/{action}"
        payloads: list[dict[str, Any]] = [{"connectorNum": connector_num}]
        if action == "stop" and order_id not in (None, ""):
            payloads.extend(
                [
                    {"connectorNum": connector_num, "orderId": order_id},
                    {"connectorNum": connector_num, "chargeOrderId": order_id},
                    {"connectorNum": connector_num, "chargingOrderId": order_id},
                ]
            )

        attempts: tuple[tuple[str, dict[str, Mapping[str, Any]]], ...] = tuple(
            (method, {kind: payload})
            for payload in payloads
            for method, kind in (
                ("POST", "data"),
                ("POST", "params"),
                ("POST", "json_data"),
            )
        ) + (
            ("POST", {"data": {}}),
            ("POST", {"params": {}}),
            ("POST", {"json_data": {}}),
        )
        last_error: Exception | None = None
        for method, kwargs in attempts:
            try:
                await self._request_authenticated(method, path, **kwargs)
                return
            except EvchargoError as err:
                last_error = err
                _LOGGER.debug(
                    "Charge action variant failed (%s %s %s): %s",
                    action,
                    method,
                    kwargs,
                    err,
                )
        raise EvchargoApiError(f"Unable to {action} charging: {last_error}")

    def _merge_charger_detail(
        self,
        charger_id: str,
        detail: dict[str, Any] | None,
        cp_list: Any,
        cp_list_alt: Any,
    ) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        matched = self._find_charger_entry(charger_id, cp_list) or self._find_charger_entry(
            charger_id, cp_list_alt
        )
        if isinstance(matched, dict):
            merged.update(matched)
        if isinstance(detail, dict):
            merged.update(detail)
        return merged

    def _find_charger_entry(self, charger_id: str, payload: Any) -> dict[str, Any] | None:
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            items = []
            for key in ("records", "list", "rows", "data"):
                value = payload.get(key)
                if isinstance(value, list):
                    items = value
                    break
        else:
            items = []

        for item in items:
            if not isinstance(item, dict):
                continue
            for key in CHARGER_ID_KEYS:
                value = item.get(key)
                if value is not None and str(value) == str(charger_id):
                    return item
        return None


def _sanitize_mapping(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    sanitized: dict[str, Any] = {}
    for key, inner in value.items():
        if key.lower() in SENSITIVE_KEYS:
            sanitized[key] = "***"
        else:
            sanitized[key] = inner
    return sanitized



def _summarize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "code": payload.get("code"),
        "message": payload.get("message"),
        "keys": sorted(payload.keys()),
    }
    data = payload.get("data")
    if isinstance(data, dict):
        summary["data_keys"] = sorted(data.keys())
    elif isinstance(data, list):
        summary["data_len"] = len(data)
        first = data[0] if data else None
        if isinstance(first, dict):
            summary["data_first_keys"] = sorted(first.keys())
    else:
        summary["data_type"] = type(data).__name__
    return summary
