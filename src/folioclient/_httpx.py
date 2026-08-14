from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
import threading
import weakref
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

        # Serializes the *synchronous* paths. NOTE: this lock is deliberately held
        # across network I/O (see sync_auth_flow and FolioClient.login), which is fine
        # for worker threads but means it must never be awaited on by an event loop.
        # That is why _get_async_lock does not use it. See _get_async_lock.
        self._lock: threading.RLock = threading.RLock()

        # One asyncio.Lock per event loop, keyed weakly so that entries disappear when
        # a loop is garbage collected (a long-lived client used across many
        # asyncio.run() calls must not accumulate locks). See _get_async_lock.
        self._async_locks: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]" = (
            weakref.WeakKeyDictionary()
        )
        # Guards _async_locks only. Separate from _lock on purpose: this one is held
        # for a dictionary lookup and nothing else, so acquiring it from the event
        # loop thread cannot stall the loop.
        self._async_locks_guard: threading.Lock = threading.Lock()

        # Locks must exist before the first authentication: _do_sync_auth does not take
        # them, but the token properties it feeds do.
        self._token: FolioAuth._Token = self._do_sync_auth()

    def _get_async_lock(self) -> asyncio.Lock:
        """Return the asyncio.Lock for the currently running event loop.

        Must be called from inside a coroutine; asyncio.get_running_loop() raises
        RuntimeError otherwise.

        WHY NOT JUST USE self._lock (threading.RLock)?
            An RLock is reentrant *per thread*. All coroutines on one event loop share
            a thread, so when coroutine A holds it across an `await`, coroutine B
            acquires it too -- reentrantly, immediately, successfully. It provides zero
            mutual exclusion between coroutines: 10 concurrent flows produced 10
            logins in testing.

        WHY NOT A PLAIN threading.Lock?
            That does exclude, by blocking the calling *thread*. On an event loop that
            thread is the loop, so it can never resume the coroutine holding the lock:
            a hard deadlock. Verified -- it hangs. No threading primitive is usable
            here; the lock must suspend the coroutine, not the thread.

        WHY ONE LOCK PER LOOP RATHER THAN ONE CACHED LOCK?
            asyncio.Lock binds itself to a loop the first time it actually has to wait
            (see _LoopBoundMixin._get_loop) and then raises "is bound to a different
            event loop" if reused elsewhere. Crucially it binds only on the *contended*
            path -- an uncontended acquire returns before _get_loop() is reached -- so a
            single cached lock passes every light test and then fails once real
            concurrency arrives.

            The binding is also permanent, which makes even strictly *sequential* reuse
            fail. One cached lock breaks when a single client is reused across two
            asyncio.run() calls: verified to raise "is bound to a different event loop"
            on the second run. That is easy to reach by accident -- a script calling
            asyncio.run() twice, a module- or session-scoped client fixture under
            pytest-asyncio (which builds a fresh loop per test), or a re-run notebook
            cell -- and it surfaces only under contention, i.e. in production rather
            than in tests. test_async_lock_survives_sequential_event_loops covers it.

            Rebuilding one cached lock on loop change fixes that but is worse overall:
            with two live loops they replace each other's lock continuously (measured:
            39 rebuilds and 16 distinct lock objects per loop), destroying exclusion
            *within* each loop as well as between them. Keying by loop costs about two
            more lines than either and is correct for both cases.

            Note that N separate FolioAuth instances across N loops is always fine --
            each owns its own lock. The constraint only ever applied to sharing one
            instance, and keying by loop removes it.

        RESIDUAL GAP, ACCEPTED DELIBERATELY:
            The sync path uses _lock and each loop uses its own asyncio.Lock, so these
            are mutually unaware. Two event loops, or one loop plus sync worker
            threads, can therefore each perform one login concurrently. That is
            bounded and benign: assigning self._token is a single attribute store, so
            no reader ever observes a torn value, and the worst outcome is a redundant
            login or discarding a marginally newer token. Closing the gap would mean
            holding a cross-thread lock across an `await`, i.e. reintroducing the
            deadlock above.
        """
        loop = asyncio.get_running_loop()
        with self._async_locks_guard:
            lock = self._async_locks.get(loop)
            if lock is None:
                lock = asyncio.Lock()
                self._async_locks[loop] = lock
            return lock

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
                # Ensure response body is available to callers inspecting exception.response.text
                retry_response.read()
                raise httpx.HTTPStatusError(
                    "Authentication failed after token refresh."
                    " Check credentials and authorization.",
                    request=request,
                    response=retry_response,
                )

        elif response.status_code == HTTPStatus.FORBIDDEN:
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
        async with self._get_async_lock():
            if not self._token or self._token_is_expiring():
                self._token = await self._do_async_auth()

        self._set_auth_cookies_on_request(request)

        # Set tenant header if not already present (allows per-request override)
        if "x-okapi-tenant" not in request.headers:
            request.headers["x-okapi-tenant"] = self.tenant_id

        response = yield request

        if response.status_code == HTTPStatus.UNAUTHORIZED:
            logger.debug("Received 401 Unauthorized, refreshing token")
            async with self._get_async_lock():
                if self._token and not self._token_is_expiring():
                    # Another coroutine refreshed the token while we awaited the lock
                    pass
                else:
                    self._token = await self._do_async_auth()

            self._set_auth_cookies_on_request(request)
            retry_response = yield request

            # If still unauthorized after fresh auth, something is seriously wrong
            if retry_response.status_code == HTTPStatus.UNAUTHORIZED:
                # Ensure response body is available to callers inspecting exception.response.text
                await retry_response.aread()
                raise httpx.HTTPStatusError(
                    "Authentication failed after token refresh."
                    " Check credentials and authorization.",
                    request=request,
                    response=retry_response,
                )

        elif response.status_code == HTTPStatus.FORBIDDEN:
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
                "Could not parse token expiration %r; proactive refresh disabled for this token.",
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
