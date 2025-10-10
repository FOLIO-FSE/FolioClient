"""This module contains decorators for the FolioClient package."""

import inspect
import logging
import os
from functools import wraps
from http import HTTPStatus
from typing import Callable

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
    after_log,
    RetryCallState,
)

from folioclient.exceptions import FolioClientClosed

logger = logging.getLogger(__name__)


# Retry condition functions
def should_retry_server_error(exception: Exception) -> bool:
    """Check if exception is a retryable server error."""
    if isinstance(exception, httpx.ConnectError):
        return True
    if isinstance(exception, httpx.HTTPStatusError):
        return exception.response.status_code in [502, 503, 504]
    return False


def should_retry_auth_error(exc):
    """
    Determine if a request should be retried. If the exception
    is an HTTPStatusError with a status code of 403,
    the function returns true.

    parameters:
        exc: The exception raised by the request

    returns:
        True if the request should be retried, False otherwise
    """
    return exc.response.status_code == HTTPStatus.FORBIDDEN


# Custom retry condition classes for tenacity
class ServerErrorRetryCondition:
    """Custom retry condition for server errors."""

    def __call__(self, retry_state):
        """Check if we should retry based on server error conditions."""
        if not retry_state.outcome.failed:
            return False
        exception = retry_state.outcome.exception()
        return should_retry_server_error(exception)


class AuthErrorRetryCondition:
    """Custom retry condition for auth errors."""

    def __call__(self, retry_state):
        """Check if we should retry based on auth error conditions."""
        if not retry_state.outcome.failed:
            return False
        exception = retry_state.outcome.exception()
        return should_retry_auth_error(exception)


def auth_refresh_callback(retry_state: RetryCallState) -> None:
    """
    Auth refresh callback for FolioClient instance methods.

    Since these decorators are only used on FolioClient instance methods,
    the first argument (self) is always the FolioClient instance.
    """
    if retry_state.attempt_number > 1:
        # For instance methods, the first argument is always 'self'
        if retry_state.args and hasattr(retry_state.args[0], "login"):
            folio_client = retry_state.args[0]
            logger.info("Refreshing FOLIO authentication before retry")
            folio_client.login()


# Configuration getters (keeping compatibility with existing env vars)
def get_server_retry_config() -> dict:
    """Get server retry configuration from environment."""
    # Support both capped and uncapped max wait behavior
    max_wait_env = os.environ.get("FOLIOCLIENT_SERVER_ERROR_MAX_WAIT")
    if max_wait_env is None:
        # Default to FOLIO-experienced behavior: no cap (like original implementation)
        max_wait = float("inf")
    elif max_wait_env.lower() in ("unlimited", "inf", "none"):
        # Explicit unlimited setting
        max_wait = float("inf")
    else:
        # Use specified maximum
        max_wait = float(max_wait_env)

    # Convert max_retries to attempts (add 1 for initial attempt)
    max_retries = int(
        os.environ.get("FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES", "")
        or os.environ.get("SERVER_ERROR_RETRIES_MAX", "0")
    )
    max_attempts = max_retries + 1  # Convert retries to total attempts

    return {
        "stop": stop_after_attempt(max_attempts),
        "wait": wait_exponential(
            multiplier=float(
                os.environ.get("FOLIOCLIENT_SERVER_ERROR_RETRY_DELAY", "")
                or os.environ.get("SERVER_ERROR_RETRY_DELAY", "10.0")
            ),
            max=max_wait,  # Now configurable: unlimited by default, or specify a cap
            exp_base=float(
                os.environ.get("FOLIOCLIENT_SERVER_ERROR_RETRY_FACTOR", "")
                or os.environ.get("SERVER_ERROR_RETRY_FACTOR", "3.0")
            ),
        ),
        "retry": ServerErrorRetryCondition(),
        "before_sleep": before_sleep_log(logger, logging.INFO),
        "after": after_log(logger, logging.DEBUG),
        "reraise": True,
    }


def get_auth_retry_config() -> dict:
    """Get auth retry configuration from environment."""
    # Support both capped and uncapped max wait behavior for auth retries too
    auth_max_wait_env = os.environ.get("FOLIOCLIENT_AUTH_ERROR_MAX_WAIT")
    if auth_max_wait_env is None:
        # Default: reasonable cap for auth errors (they should be faster to resolve)
        auth_max_wait = 60.0
    elif auth_max_wait_env.lower() in ("unlimited", "inf", "none"):
        # Explicit unlimited setting
        auth_max_wait = float("inf")
    else:
        # Use specified maximum
        auth_max_wait = float(auth_max_wait_env)

    # Convert max_retries to attempts (add 1 for initial attempt)
    max_retries = int(
        os.environ.get("FOLIOCLIENT_MAX_AUTH_ERROR_RETRIES", "")
        or os.environ.get("AUTH_ERROR_RETRIES_MAX", "0")
    )
    max_attempts = max_retries + 1  # Convert retries to total attempts

    return {
        "stop": stop_after_attempt(max_attempts),
        "wait": wait_exponential(
            multiplier=float(
                os.environ.get("FOLIOCLIENT_AUTH_ERROR_RETRY_DELAY", "")
                or os.environ.get("AUTH_ERROR_RETRY_DELAY", "10.0")
            ),
            max=auth_max_wait,  # Configurable: 60s default, or specify cap/unlimited
            exp_base=float(
                os.environ.get("FOLIOCLIENT_AUTH_ERROR_RETRY_FACTOR", "")
                or os.environ.get("AUTH_ERROR_RETRY_FACTOR", "3.0")
            ),
        ),
        "retry": AuthErrorRetryCondition(),
        "before_sleep": auth_refresh_callback,
        "after": after_log(logger, logging.DEBUG),
        "reraise": True,
    }


# Modern retry decorators
def folio_retry_on_server_error(func: Callable) -> Callable:
    """
    Modern retry decorator for server errors using tenacity.

    - Single decorator that works for both sync and async
    - Configuration through environment variables
    - Built-in exponential backoff with optional jitter
    - Comprehensive logging

    Environment Variables:
        FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES: Max attempts (default: 0 - no retries)
        SERVER_ERROR_RETRIES_MAX: Legacy fallback (default: 0 - no retries)
        FOLIOCLIENT_SERVER_ERROR_RETRY_DELAY: Initial delay (default: 10.0)
        SERVER_ERROR_RETRY_DELAY: Legacy fallback (default: 10.0)
        FOLIOCLIENT_SERVER_ERROR_MAX_WAIT: Max wait time (default: unlimited)
            - Set to a number (e.g., "60") for a cap in seconds
            - Set to "unlimited", "inf", or "none" for no cap
            - Unset (default) = unlimited (matches original behavior)
        FOLIOCLIENT_SERVER_ERROR_RETRY_FACTOR: Backoff factor (default: 3.0)
        SERVER_ERROR_RETRY_FACTOR: Legacy fallback (default: 3.0)
    """
    return retry(**get_server_retry_config())(func)


def folio_retry_on_auth_error(func: Callable) -> Callable:
    """
    Modern retry decorator for auth errors using tenacity.

    - Single decorator that works for both sync and async
    - Automatic authentication refresh before retries
    - Configuration through environment variables
    - Built-in exponential backoff with optional jitter

    Environment Variables:
        FOLIOCLIENT_MAX_AUTH_ERROR_RETRIES: Max attempts (default: 0 - no retries)
        AUTH_ERROR_RETRIES_MAX: Legacy fallback (default: 0 - no retries)
        FOLIOCLIENT_AUTH_ERROR_RETRY_DELAY: Initial delay (default: 10.0)
        AUTH_ERROR_RETRY_DELAY: Legacy fallback (default: 10.0)
        FOLIOCLIENT_AUTH_ERROR_MAX_WAIT: Max wait time (default: 60.0)
            - Set to a number (e.g., "30") for a cap in seconds
            - Set to "unlimited", "inf", or "none" for no cap
            - Default: 60 seconds (auth issues should resolve quickly)
        FOLIOCLIENT_AUTH_ERROR_RETRY_FACTOR: Backoff factor (default: 3.0)
        AUTH_ERROR_RETRY_FACTOR: Legacy fallback (default: 3.0)
    """
    return retry(**get_auth_retry_config())(func)


# Combined decorator for convenience
def folio_retry_all_errors(func: Callable) -> Callable:
    """
    Convenience decorator that combines both server and auth error retries.

    This applies both retry strategies, with auth retries happening first
    (inner decorator) and server retries happening second (outer decorator).
    """
    # Apply auth retry first, then server retry
    return folio_retry_on_server_error(folio_retry_on_auth_error(func))


def handle_remote_protocol_error(func):
    """
    Decorator to catch httpx.RemoteProtocolError, recreate the httpx.Client,
    and retry the request. Works with both sync and async methods.
    """

    @wraps(func)
    def sync_wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except httpx.RemoteProtocolError:
            logging.warning("Caught httpx.RemoteProtocolError. Recreate httpx.Client and retry.")
            # Close the existing client if it exists
            if (
                hasattr(self, "httpx_client")
                and self.httpx_client
                and not self.httpx_client.is_closed
            ):
                self.httpx_client.close()
            # Recreate the httpx.Client
            self.httpx_client = self.get_folio_http_client()
            # Retry the request
            return func(self, *args, **kwargs)

    @wraps(func)
    async def async_wrapper(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except httpx.RemoteProtocolError:
            logging.warning(
                "Caught httpx.RemoteProtocolError. Recreate httpx.AsyncClient and retry."
            )
            # Close the existing async client if it exists
            if (
                hasattr(self, "httpx_async_client")
                and self.httpx_async_client
                and not self.httpx_async_client.is_closed
            ):
                await self.httpx_async_client.aclose()
            # Recreate the httpx.AsyncClient
            self.httpx_async_client = self.get_folio_http_client_async()
            # Retry the request
            return await func(self, *args, **kwargs)

    # Return the appropriate wrapper based on whether the function is async
    if inspect.iscoroutinefunction(func) or inspect.isasyncgenfunction(func):
        return async_wrapper
    else:
        return sync_wrapper


def use_client_session_with_generator(func):
    """
    Decorator to use or create an httpx.Client session for the FolioClient
    if one is not already created or the existing httpx.Client is closed

    This decorator assumes it is decorating an instance method on a FolioClient object
    """

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        needs_temp_client = (
            not hasattr(self, "httpx_client")
            or not self.httpx_client
            or self.httpx_client.is_closed
        )
        if needs_temp_client:
            with self.get_folio_http_client() as httpx_client:
                self.httpx_client = httpx_client
                yield from func(self, *args, **kwargs)
        elif not self.is_closed:
            yield from func(self, *args, **kwargs)
        else:
            raise FolioClientClosed()

    @wraps(func)
    async def async_wrapper(self, *args, **kwargs):
        needs_temp_client = (
            not hasattr(self, "async_httpx_client")
            or not self.async_httpx_client
            or self.async_httpx_client.is_closed
        )
        if needs_temp_client:
            async with self.get_folio_http_client_async() as async_httpx_client:
                self.async_httpx_client = async_httpx_client
                async for item in func(self, *args, **kwargs):
                    yield item
        elif not self.is_closed:
            async for item in func(self, *args, **kwargs):
                yield item
        else:
            raise FolioClientClosed()

    if inspect.iscoroutinefunction(func) or inspect.isasyncgenfunction(func):
        return async_wrapper
    else:
        return wrapper


def use_client_session(func):
    """
    Decorator to use or create an httpx.Client session for the FolioClient
    if one is not already created or the existing httpx.Client is closed
    """

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        needs_temp_client = (
            not hasattr(self, "httpx_client")
            or not self.httpx_client
            or self.httpx_client.is_closed
        )
        if needs_temp_client:
            with self.get_folio_http_client() as httpx_client:
                self.httpx_client = httpx_client
                return func(self, *args, **kwargs)
        elif not self.is_closed:
            return func(self, *args, **kwargs)
        else:
            raise FolioClientClosed()

    @wraps(func)
    async def async_wrapper(self, *args, **kwargs):
        needs_temp_client = (
            not hasattr(self, "async_httpx_client")
            or not self.async_httpx_client
            or self.async_httpx_client.is_closed
        )
        if needs_temp_client:
            async with self.get_folio_http_client_async() as async_httpx_client:
                self.async_httpx_client = async_httpx_client
                return await func(self, *args, **kwargs)
        elif not self.is_closed:
            return await func(self, *args, **kwargs)
        else:
            raise FolioClientClosed()

    if inspect.iscoroutinefunction(func) or inspect.isasyncgenfunction(func):
        return async_wrapper
    else:
        return wrapper
