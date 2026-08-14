from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import threading
import httpx

from dataclasses import dataclass
from dateutil.parser import isoparse
from http import HTTPStatus
from typing import TYPE_CHECKING, NamedTuple, Optional

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import AsyncGenerator, Generator
    import ssl

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FolioConnectionParameters:
    """Parameters required to connect to a FOLIO instance.

    Attributes:
        gateway_url (str): The base URL of the FOLIO gateway.
        tenant_id (str): The tenant ID for the FOLIO instance.
        username (str): The username for authentication.
        password (str): The password for authentication.
        ssl_verify (bool): Whether to verify SSL certificates.
        timeout (httpx.Timeout | None): Configured timeout object for HTTP requests,
            or None for unlimited timeout (default behavior)
    """

    gateway_url: str
    tenant_id: str
    username: str
    password: str
    ssl_verify: bool | ssl.SSLContext
    timeout: httpx.Timeout


class FolioAuth(httpx.Auth):
    """Custom authentication class to support FOLIO authentication tokens and RTR

    This class supports both Okapi and Eureka-based FOLIO systems.
    Works with both synchronous and asynchronous httpx clients.
    """

    class _Token(NamedTuple):
        auth_token: Optional[str]
        refresh_token: Optional[str]
        expires_at: Optional[datetime]
        refresh_token_expires_at: Optional[datetime]
        cookies: Optional[httpx.Cookies]

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
            logger.debug("Switching tenant_id from %s to %s", self._tenant_id, value)
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

        self._set_auth_cookies_on_request(request)

        # Set tenant header if not already present (allows per-request override)
        if "x-okapi-tenant" not in request.headers:
            request.headers["x-okapi-tenant"] = self.tenant_id

        response = yield request

        if response.status_code == HTTPStatus.UNAUTHORIZED:
            logger.debug("Received 401 Unauthorized, refreshing token")
            with self._lock:
                if self._token and not self._token_is_expiring():
                    # Another thread refreshed the token while we were waiting for the lock
                    pass
                else:
                    self._token = self._do_sync_auth()

            self._set_auth_cookies_on_request(request)
            retry_response = yield request

            # If still unauthorized after fresh auth, something is seriously wrong
            if retry_response.status_code == HTTPStatus.UNAUTHORIZED:
                raise httpx.HTTPStatusError(
                    "Authentication failed after token refresh."
                    " Check credentials and authorization.",
                    request=request,
                    response=retry_response,
                )

        if response.status_code == HTTPStatus.FORBIDDEN:
            logger.debug("Received unexpected 403 Forbidden. Will retry request once.")
            retry_response = yield request
            if retry_response.status_code == HTTPStatus.FORBIDDEN:
                # Ensure response body is available to callers inspecting exception.response.text
                retry_response.read()
                retry_response.raise_for_status()  # Raise 403 if still forbidden after retry

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> "AsyncGenerator[httpx.Request, httpx.Response]":
        """Asynchronous authentication flow for httpx.AsyncClient"""
        with self._lock:
            if not self._token or self._token_is_expiring():
                self._token = await self._do_async_auth()

        self._set_auth_cookies_on_request(request)

        # Set tenant header if not already present (allows per-request override)
        if "x-okapi-tenant" not in request.headers:
            request.headers["x-okapi-tenant"] = self.tenant_id

        response = yield request

        if response.status_code == HTTPStatus.UNAUTHORIZED:
            logger.debug("Received 401 Unauthorized, refreshing token")
            with self._lock:
                if self._token and not self._token_is_expiring():
                    # Another thread refreshed the token while we were waiting for the lock
                    pass
                else:
                    self._token = await self._do_async_auth()

            self._set_auth_cookies_on_request(request)
            retry_response = yield request

            # If still unauthorized after fresh auth, something is seriously wrong
            if retry_response.status_code == HTTPStatus.UNAUTHORIZED:
                raise httpx.HTTPStatusError(
                    "Authentication failed after token refresh."
                    " Check credentials and authorization.",
                    request=request,
                    response=retry_response,
                )

        if response.status_code == HTTPStatus.FORBIDDEN:
            logger.debug("Received unexpected 403 Forbidden. Will retry request once.")
            retry_response = yield request
            if retry_response.status_code == HTTPStatus.FORBIDDEN:
                # Ensure response body is available to callers inspecting exception.response.text
                await retry_response.aread()
                retry_response.raise_for_status()  # Raise 403 if still forbidden after retry

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
            logger.debug("Authenticating synchronously with URL: %s", auth_url)
            response = client.post(auth_url, json=auth_data, headers=headers)
            response.raise_for_status()
            return self._token_from_response(response)

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
            logger.debug("Authenticating asynchronously with URL: %s", auth_url)
            response = await client.post(auth_url, json=auth_data, headers=headers)
            response.raise_for_status()
            return self._token_from_response(response)

    @classmethod
    def _token_from_response(cls, response: httpx.Response) -> _Token:
        """Build a _Token from an /authn/login-with-expiry response.

        Shared by the sync and async auth methods so that the response parsing --
        including the expiration handling in _parse_expiration -- exists in exactly
        one place.
        """
        token = response.cookies.get("folioAccessToken")
        if not token:
            raise ValueError("Authentication failed: No token received.")

        payload = response.json()
        return cls._Token(
            auth_token=token,
            refresh_token=response.cookies.get("folioRefreshToken"),
            expires_at=cls._parse_expiration(payload.get("accessTokenExpiration")),
            refresh_token_expires_at=cls._parse_expiration(payload.get("refreshTokenExpiration")),
            cookies=response.cookies,
        )

    @staticmethod
    def _parse_expiration(value: Optional[str]) -> Optional[datetime]:
        """Parse a FOLIO token expiration timestamp into an aware UTC datetime.

        CARE POINT: this must not use datetime.fromisoformat. FOLIO emits ISO-8601 with
        a trailing 'Z' (verified against live Okapi and Eureka instances, e.g.
        '2026-08-07T18:13:36Z'), and fromisoformat cannot parse a 'Z' suffix before
        Python 3.11. Since this package supports 3.10, fromisoformat raised ValueError
        during authentication and made the client unusable there entirely. isoparse
        handles 'Z' and offsets written without a colon on every supported version.

        A value with no UTC offset is coerced to UTC so that comparisons in
        _token_is_expiring never mix naive and aware datetimes (which would raise
        TypeError on every request).

        An unparseable value degrades to None rather than raising: losing the proactive
        expiry check is far better than failing authentication outright.
        """
        if not value:
            return None
        try:
            parsed = isoparse(value)
        except (ValueError, OverflowError, TypeError):
            logger.warning(
                "Could not parse token expiration %r; proactive refresh disabled for"
                " this token.",
                value,
            )
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _set_auth_cookies_on_request(self, request: httpx.Request) -> None:
        """Set authentication cookies on request, overriding any existing FOLIO auth cookies"""
        existing_cookie_header = request.headers.get("Cookie", "")

        # Parse existing cookies and filter out FOLIO auth cookies
        existing_cookies = self._parse_existing_cookies(existing_cookie_header)

        # Add our authentication cookies
        auth_cookies = {}
        if self._token and self._token.cookies:
            for name, value in self._token.cookies.items():
                auth_cookies[name] = value

        # Combine all cookies
        all_cookies = {**existing_cookies, **auth_cookies}

        # Set the combined cookie header
        if all_cookies:
            cookie_pairs = [f"{name}={value}" for name, value in all_cookies.items()]
            request.headers["Cookie"] = "; ".join(cookie_pairs)
        elif existing_cookie_header:
            # If we only had FOLIO cookies and removed them, clear the header
            request.headers.pop("Cookie", None)

    @staticmethod
    def _parse_existing_cookies(existing_cookie_header):
        existing_cookies = {}
        if existing_cookie_header:
            for cookie_pair in existing_cookie_header.split("; "):
                if "=" in cookie_pair:
                    name, value = cookie_pair.split("=", 1)
                    # Skip FOLIO auth cookies - we'll override them
                    if name not in ("folioAccessToken", "folioRefreshToken"):
                        existing_cookies[name] = value
        return existing_cookies

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
