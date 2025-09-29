from datetime import datetime, timedelta, timezone
import threading
import httpx

from dataclasses import dataclass
from http import HTTPStatus
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator


@dataclass(frozen=True)
class FolioConnectionParameters:
    """Parameters required to connect to a FOLIO instance.

    Attributes:
        gateway_url (str): The base URL of the FOLIO gateway.
        tenant_id (str): The tenant ID for the FOLIO instance.
        username (str): The username for authentication.
        password (str): The password for authentication.
        ssl_verify (bool): Whether to verify SSL certificates.
    """

    gateway_url: str
    tenant_id: str
    username: str
    password: str
    ssl_verify: bool
    timeout: float


class FolioAuth(httpx.Auth):
    """Custom authentication class to support FOLIO authentication tokens and RTR

    This class supports both Okapi and Eureka-based FOLIO systems.
    Works with both synchronous and asynchronous httpx clients.
    """

    class _Token(NamedTuple):
        auth_token: str
        refresh_token: str
        expires_at: datetime | None
        refresh_token_expires_at: datetime | None
        cookies: httpx.Cookies | None = None

    def __init__(self, params: FolioConnectionParameters):
        self._params = params
        self._tenant_id = params.tenant_id
        self._base_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self._token: FolioAuth._Token = self._do_sync_auth()
        self._lock: threading.RLock = threading.RLock()

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    @tenant_id.setter
    def tenant_id(self, value: str):
        if value != self._tenant_id:
            self._tenant_id = value

    def reset_tenant_id(self):
        self.tenant_id = self._params.tenant_id

    def sync_auth_flow(
        self, request: httpx.Request
    ) -> "Generator[httpx.Request, httpx.Response, None]":
        """Synchronous authentication flow for httpx.Client"""
        with self._lock:
            if not self._token or self._token_is_expiring():
                self._token = self._do_sync_auth()

        request.headers["x-okapi-token"] = self._token.auth_token

        # Set tenant header if not already present (allows per-request override)
        if "x-okapi-tenant" not in request.headers:
            request.headers["x-okapi-tenant"] = self.tenant_id

        response = yield request

        if response.status_code == HTTPStatus.UNAUTHORIZED:
            with self._lock:
                if self._token and not self._token_is_expiring():
                    # Another thread refreshed the token while we were waiting for the lock
                    pass
                else:
                    self._token = self._do_sync_auth()
            request.headers["x-okapi-token"] = self._token.auth_token
            retry_response = yield request

            # If still unauthorized after fresh auth, something is seriously wrong
            if retry_response.status_code == HTTPStatus.UNAUTHORIZED:
                raise httpx.HTTPStatusError(
                    "Authentication failed after token refresh."
                    " Check credentials and authorization.",
                    request=request,
                    response=retry_response,
                )

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> "AsyncGenerator[httpx.Request, httpx.Response]":
        """Asynchronous authentication flow for httpx.AsyncClient"""
        with self._lock:
            if not self._token or self._token_is_expiring():
                self._token = await self._do_async_auth()

        request.headers["x-okapi-token"] = self._token.auth_token

        # Set tenant header if not already present (allows per-request override)
        if "x-okapi-tenant" not in request.headers:
            request.headers["x-okapi-tenant"] = self.tenant_id

        response = yield request

        if response.status_code == HTTPStatus.UNAUTHORIZED:
            with self._lock:
                if self._token and not self._token_is_expiring():
                    # Another thread refreshed the token while we were waiting for the lock
                    pass
                else:
                    self._token = await self._do_async_auth()

            request.headers["x-okapi-token"] = self._token.auth_token
            retry_response = yield request

            # If still unauthorized after fresh auth, something is seriously wrong
            if retry_response.status_code == HTTPStatus.UNAUTHORIZED:
                raise httpx.HTTPStatusError(
                    "Authentication failed after token refresh."
                    " Check credentials and authorization.",
                    request=request,
                    response=retry_response,
                )

    def _do_sync_auth(self) -> _Token:
        """Synchronous authentication with the FOLIO system."""
        auth_url = f"{self._params.gateway_url}/authn/login-with-expiry"
        headers = {
            "x-okapi-tenant": self._params.tenant_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        auth_data = {"username": self._params.username, "password": self._params.password}

        with httpx.Client(timeout=self._params.timeout, verify=self._params.ssl_verify) as client:
            response = client.post(auth_url, json=auth_data, headers=headers)
            response.raise_for_status()

            token = response.cookies.get("folioAccessToken")
            refresh_token = response.cookies.get("folioRefreshToken")
            if not token:
                raise ValueError("Authentication failed: No token received.")

            expires_at = None
            if "accessTokenExpiration" in response.json():
                expires_at = datetime.fromisoformat(response.json()["accessTokenExpiration"])

            refresh_token_expires_at = None
            if "refreshTokenExpiration" in response.json():
                refresh_token_expires_at = datetime.fromisoformat(
                    response.json()["refreshTokenExpiration"]
                )

            return FolioAuth._Token(
                auth_token=token,
                refresh_token=refresh_token,
                expires_at=expires_at,
                refresh_token_expires_at=refresh_token_expires_at,
                cookies=response.cookies,
            )

    async def _do_async_auth(self) -> _Token:
        """Asynchronous authentication with the FOLIO system."""
        auth_url = f"{self._params.gateway_url}/authn/login-with-expiry"
        headers = {
            "x-okapi-tenant": self._params.tenant_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        auth_data = {"username": self._params.username, "password": self._params.password}

        async with httpx.AsyncClient(
            timeout=self._params.timeout, verify=self._params.ssl_verify
        ) as client:
            response = await client.post(auth_url, json=auth_data, headers=headers)
            response.raise_for_status()

            token = response.cookies.get("folioAccessToken")
            refresh_token = response.cookies.get("folioRefreshToken")
            if not token:
                raise ValueError("Authentication failed: No token received.")

            expires_at = None
            if "accessTokenExpiration" in response.json():
                expires_at = datetime.fromisoformat(response.json()["accessTokenExpiration"])

            refresh_token_expires_at = None
            if "refreshTokenExpiration" in response.json():
                refresh_token_expires_at = datetime.fromisoformat(
                    response.json()["refreshTokenExpiration"]
                )

            return FolioAuth._Token(
                auth_token=token,
                refresh_token=refresh_token,
                expires_at=expires_at,
                refresh_token_expires_at=refresh_token_expires_at,
                cookies=response.cookies,
            )

    def _token_is_expiring(self) -> bool:
        """Returns true if token is within 60 seconds of expiration"""
        return (
            not self._token
            or not self._token.expires_at
            or (datetime.now(tz=timezone.utc) + timedelta(seconds=60)) >= self._token.expires_at
        )

    @property
    def folio_auth_token(self):
        """Property that returns a currently valid FOLIO auth token"""
        with self._lock:
            if not self._token or self._token_is_expiring():
                self._token = self._do_sync_auth()
            return self._token.auth_token

    @property
    def folio_refresh_token(self):
        """Property that returns the currently valid FOLIO refresh token"""
        with self._lock:
            if not self._token or self._token_is_expiring():
                self._token = self._do_sync_auth()
            return self._token.refresh_token
