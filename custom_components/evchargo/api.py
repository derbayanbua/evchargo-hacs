from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

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


class EvchargoError(Exception):
    """Base Evchargo error."""


class EvchargoAuthError(EvchargoError):
    """Authentication failed."""


class EvchargoApiError(EvchargoError):
    """API request failed."""


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
        self._base_url = base_url.rstrip("/")
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
        try:
            async with self._session.request(
                method,
                url,
                headers=self._headers(include_token=include_token),
                params=params,
                data=data,
                json=json_data,
            ) as response:
                return await self._parse_response(response)
        except ClientError as err:
            raise EvchargoApiError(f"HTTP error calling {path}: {err}") from err

    async def _parse_response(self, response: ClientResponse) -> dict[str, Any]:
        try:
            payload = await response.json(content_type=None)
        except Exception as err:  # noqa: BLE001
            text = await response.text()
            raise EvchargoApiError(
                f"Unexpected non-JSON response ({response.status}): {text[:200]}"
            ) from err

        code = payload.get("code")
        if code in AUTH_ERROR_CODES:
            raise EvchargoAuthError(payload.get("message") or f"Auth code {code}")
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
                response.get("message") or f"Request failed ({response.get('code')}) for {path}"
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
        return result

    async def async_start_charging(self, charger_id: str, connector_num: int = 1) -> None:
        await self._request_authenticated(
            "POST",
            f"/app/v1/home/cp/{charger_id}/start",
            data={"connectorNum": connector_num},
        )

    async def async_stop_charging(self, charger_id: str, connector_num: int = 1) -> None:
        await self._request_authenticated(
            "POST",
            f"/app/v1/home/cp/{charger_id}/stop",
            data={"connectorNum": connector_num},
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
