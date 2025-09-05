"""This module contains decorators for the FolioClient package."""

import logging
import os
import time
from functools import wraps

import httpx

logger = logging.getLogger(__name__)


def find_folio_client(*args, **kwargs):
    """
    Find any argument that is an instance of the FolioClient class.

    Args:
        *args: Positional arguments.
        **kwargs: Keyword arguments.

    Returns:
        The first argument that is an instance of FolioClient, or None if not found.
    """
    # Perform a lazy import to avoid circular imports
    from folioclient import FolioClient

    # Check positional arguments
    for arg in args:
        if isinstance(arg, FolioClient):
            return arg

    # Check keyword arguments
    for arg in kwargs.values():
        if isinstance(arg, FolioClient):
            return arg

    return None


def handle_retry(func, exc, retry, max_retries, retry_delay):
    """
    Handle a retry of a request.

    If the maximum number of retries has been reached, log an
    exception and re-raise the original exception.

    Parameters:
        func (Callable): The function that raised the exception.
        exc (Exception): The exception raised by the function.
        retry (int): The current retry number.
        max_retries (int): The maximum number of retries.
        retry_delay (int): The delay between retries in seconds.

    Raises:
        Exception: The original exception raised by the decorated function.
    """
    if retry == max_retries:
        logger.exception(
            f'HTTP request error calling {func.__name__}: "{exc}"'
            "Maximum number of retries reached, giving up."
        )
        raise exc
    logger.info(
        f'HTTP request error calling {func.__name__}: "{exc}"'
        f"Retrying again in {retry_delay} seconds. "
        f"Retry {retry + 1}/{max_retries}"
    )
    time.sleep(retry_delay)


def folio_retry_on_server_error(func):
    """Retry a function if a temporary server error is encountered.

    Args:
        func: The function to be retried.

    Returns:
        The decorated function.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        max_retries = get_max_on_server_error_retries()
        retry_factor = get_retry_on_server_error_factor()
        retry_delay = get_retry_on_server_error_delay()
        for retry in range(max_retries + 1):
            try:
                return func(*args, **kwargs)
            except (httpx.ConnectError, httpx.HTTPStatusError) as exc:
                if should_retry_on_server_error(exc):
                    handle_retry(func, exc, retry, max_retries, retry_delay)
                    retry_delay *= retry_factor
                else:
                    raise exc

    return wrapper


def get_retry_on_server_error_factor():
    """
    Get the retry factor from the environment.

    returns:
        The retry factor as a float.
    """
    return float(
        os.environ.get("FOLIOCLIENT_SERVER_ERROR_RETRY_FACTOR", None)
        or os.environ.get("SERVER_ERROR_RETRY_FACTOR", "3")
    )


def get_max_on_server_error_retries():
    """
    Get the maximum number of retries from the environment or default to 0.

    returns:
        The maximum number of retries as an integer.
    """
    return int(
        os.environ.get("FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES", None)
        or os.environ.get("SERVER_ERROR_RETRIES_MAX", "0")
    )


def get_retry_on_server_error_delay():
    """
    Get the retry delay from the environment, or default to 10.

    returns:
        The retry delay (in seconds) as an integer
    """
    return int(
        os.environ.get("FOLIOCLIENT_SERVER_ERROR_RETRY_DELAY", None)
        or os.environ.get("SERVER_ERROR_RETRY_DELAY", "10")
    )


def should_retry_on_server_error(exc):
    """
    Determine if a request should be retried. If the exception
    is a ConnectError or HTTPStatusError with a status code of 502,
    503, or 504, the function returns true.

    parmeters:
        exc: The exception raised by the request

    returns:
        True if the request should be retried, False otherwise
    """
    return (
        not hasattr(exc, "response") and hasattr(exc, "request")
    ) or exc.response.status_code in [
        502,
        503,
        504,
    ]


def folio_retry_on_auth_error(func):
    """Retry a function if an authentication error is encountered.

    Args:
        func: The function to be retried.

    Returns:
        The decorated function.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        max_retries = get_max_on_auth_error_retries()
        retry_factor = get_retry_on_auth_error_factor()
        retry_delay = get_retry_on_auth_error_delay()
        for retry in range(max_retries + 1):
            if (folio_client := find_folio_client(*args, **kwargs)) and retry:
                folio_client.login()
            try:
                return func(*args, **kwargs)
            except httpx.HTTPStatusError as exc:
                if should_retry_on_auth_error(exc):
                    handle_retry(func, exc, retry, max_retries, retry_delay)
                    retry_delay *= retry_factor
                else:
                    raise exc

    return wrapper


def get_retry_on_auth_error_factor():
    """
    Get the retry factor from the environment.

    returns:
        The retry factor as a float.
    """
    return float(
        os.environ.get("FOLIOCLIENT_AUTH_ERROR_RETRY_FACTOR", None)
        or os.environ.get("AUTH_ERROR_RETRY_FACTOR", "3")
    )


def get_max_on_auth_error_retries():
    """
    Get the maximum number of retries from the environment or default to 0.

    returns:
        The maximum number of retries as an integer.
    """
    return int(
        os.environ.get("FOLIOCLIENT_MAX_AUTH_ERROR_RETRIES", None)
        or os.environ.get("AUTH_ERROR_RETRIES_MAX", "0")
    )


def get_retry_on_auth_error_delay():
    """
    Get the retry delay from the environment, or default to 10.

    returns:
        The retry delay (in seconds) as an integer
    """
    return int(
        os.environ.get("FOLIOCLIENT_AUTH_ERROR_RETRY_DELAY", None)
        or os.environ.get("AUTH_ERROR_RETRY_DELAY", "10")
    )


def should_retry_on_auth_error(exc):
    """
    Determine if a request should be retried. If the exception
    is a ConnectError or HTTPStatusError with a status code of 401,
    the function returns true.

    parmeters:
        exc: The exception raised by the request

    returns:
        True if the request should be retried, False otherwise
    """
    return exc.response.status_code in [401, 403]


def handle_remote_protocol_error(func):
    """
    Decorator to catch httpx.RemoteProtocolError, recreate the httpx.Client,
    and retry the request.
    """

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except httpx.RemoteProtocolError:
            logging.warning("Caught httpx.RemoteProtocolError. Recreate httpx.Client and retry.")
            # Close the existing client if it exists
            if self.httpx_client and not self.httpx_client.is_closed:
                self.httpx_client.close()
            # Recreate the httpx.Client
            self.httpx_client = httpx.Client(
                timeout=self.http_timeout,
                verify=self.ssl_verify,
                base_url=self.gateway_url,
            )
            # Retry the request
            return func(self, *args, **kwargs)

    return wrapper


def use_client_session_with_generator(func):
    """
    Decorator to use or create an httpx.Client session for the FolioClient
    if one is not already created or the existing httpx.Client is closed
    """

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self.httpx_client or self.httpx_client.is_closed:
            with httpx.Client(
                timeout=self.http_timeout,
                verify=self.ssl_verify,
                base_url=self.gateway_url,
            ) as httpx_client:
                self.httpx_client = httpx_client
                yield from func(self, *args, **kwargs)
        else:
            yield from func(self, *args, **kwargs)

    return wrapper


def use_client_session(func):
    """
    Decorator to use or create an httpx.Client session for the FolioClient
    if one is not already created or the existing httpx.Client is closed
    """

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self.httpx_client or self.httpx_client.is_closed:
            with httpx.Client(
                timeout=self.http_timeout,
                verify=self.ssl_verify,
                base_url=self.gateway_url,
            ) as httpx_client:
                self.httpx_client = httpx_client
                return func(self, *args, **kwargs)
        else:
            return func(self, *args, **kwargs)

    return wrapper
