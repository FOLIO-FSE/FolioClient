"""
Custom exceptions for the folioclient package.

This module provides FOLIO-specific exceptions that wrap httpx exceptions
to give meaningful error context for library management system operations.
"""

import functools
import inspect
from typing import (
    Callable,
    ParamSpec,
    TypeVar,
    Any,
    Dict,
    Type,
    Optional,
    Union,
    cast,
    overload,
    Awaitable,
)

import httpx

P = ParamSpec("P")
T = TypeVar("T")



# Base FOLIO exceptions
class FolioError(Exception):
    """Base exception for all FOLIO-related errors."""

    pass


class FolioClientClosed(FolioError):
    """
    Raised when an operation is attempted on a closed FolioClient.
    """

    def __init__(self, message: str = "The FolioClient is closed") -> None:
        super().__init__(message)


# Connection and network errors
class FolioConnectionError(FolioError, httpx.RequestError):
    """
    Base class for FOLIO connection-related errors.
    Raised when there are network connectivity issues with the FOLIO system.
    """

    def __init__(self, message: str, *, request: httpx.Request) -> None:
        super().__init__(message)
        self.message = message
        self.request = request

    def __str__(self) -> str:
        return f"FOLIO connection error: {self.message}"


class FolioSystemUnavailableError(FolioConnectionError):
    """
    Raised when the FOLIO system is completely unreachable.
    This indicates the FOLIO instance, API gateway, or module is down.
    """

    def __str__(self) -> str:
        return f"FOLIO system unavailable: {self.message}"


class FolioTimeoutError(FolioConnectionError, httpx.TimeoutException):
    """
    Raised when requests to FOLIO time out.
    Could indicate slow FOLIO modules, database issues, or network problems.
    """

    def __str__(self) -> str:
        return f"FOLIO request timeout: {self.message}"


class FolioProtocolError(FolioConnectionError):
    """
    Raised when there are HTTP protocol-level errors with FOLIO.
    Could indicate API gateway issues or module communication problems.
    """

    def __str__(self) -> str:
        return f"FOLIO protocol error: {self.message}"


class FolioNetworkError(FolioConnectionError):
    """
    Raised for general network connectivity issues with FOLIO.
    DNS resolution failures, connection refused, etc.
    """

    def __str__(self) -> str:
        return f"FOLIO network error: {self.message}"


# HTTP Status-based exceptions
class FolioHTTPError(FolioError, httpx.HTTPStatusError):
    """
    Base class for FOLIO HTTP status errors.
    """

    def __init__(self, message: str, *, request: httpx.Request, response: httpx.Response) -> None:
        super().__init__(message, request=request, response=response)
        self.message = message

    def __str__(self) -> str:
        return f"FOLIO HTTP error: {self.message} (HTTP {self.response.status_code})"


# 4xx Client Errors
class FolioClientError(FolioHTTPError):
    """
    Base class for 4xx client errors from FOLIO.
    Indicates issues with the request format, authentication, or permissions.
    """

    def __str__(self) -> str:
        return f"FOLIO client error: {self.message} (HTTP {self.response.status_code})"


class FolioAuthenticationError(FolioClientError):
    """
    Raised for 401 authentication failures with FOLIO.
    Invalid credentials, expired tokens, or authentication module issues.
    """

    def __init__(
        self,
        message: str = "Authentication failed - invalid credentials or expired token",
        *,
        request: httpx.Request,
        response: httpx.Response,
    ) -> None:
        super().__init__(message, request=request, response=response)

    def __str__(self) -> str:
        return f"FOLIO authentication failed: {self.message}"


class FolioPermissionError(FolioClientError):
    """
    Raised for 403 permission denied errors.
    User lacks required FOLIO permissions for the requested operation.
    """

    def __init__(
        self,
        message: str = "Permission denied - insufficient FOLIO permissions",
        *,
        request: httpx.Request,
        response: httpx.Response,
    ) -> None:
        super().__init__(message, request=request, response=response)

    def __str__(self) -> str:
        return f"FOLIO permission denied: {self.message}"


class FolioResourceNotFoundError(FolioClientError):
    """
    Raised for 404 not found errors.
    FOLIO resource specified (user, item, instance, etc.) or endpoint doesn't exist for the
    specified HTTP method.
    """

    def __init__(
        self,
        message: str = "Resource not found - FOLIO record or endpoint missing for the request",
        *,
        request: httpx.Request,
        response: httpx.Response,
    ) -> None:
        super().__init__(message, request=request, response=response)

    def __str__(self) -> str:
        return f"FOLIO resource not found: {self.message}"


class FolioDataConflictError(FolioClientError):
    """
    Raised for 409 conflict errors.
    Data conflicts like duplicate records, optimistic locking failures, or constraint violations.
    """

    def __init__(
        self,
        message: str = "Data conflict - record may have been modified or duplicated",
        *,
        request: httpx.Request,
        response: httpx.Response,
    ) -> None:
        super().__init__(message, request=request, response=response)

    def __str__(self) -> str:
        return f"FOLIO data conflict: {self.message}"


class FolioValidationError(FolioClientError):
    """
    Raised for 422 validation errors.
    Data doesn't meet FOLIO schema requirements or business rules.
    """

    def __init__(
        self,
        message: str = "Validation failed - data doesn't meet FOLIO requirements",
        *,
        request: httpx.Request,
        response: httpx.Response,
    ) -> None:
        super().__init__(message, request=request, response=response)

    def __str__(self) -> str:
        return f"FOLIO validation error: {self.message}"


class FolioRateLimitError(FolioClientError):
    """
    Raised for 429 rate limiting errors.
    Too many requests to FOLIO in a given time period.
    """

    def __init__(
        self,
        message: str = "Rate limit exceeded - too many requests to FOLIO",
        *,
        request: httpx.Request,
        response: httpx.Response,
    ) -> None:
        super().__init__(message, request=request, response=response)

    def __str__(self) -> str:
        return f"FOLIO rate limit exceeded: {self.message}"


class FolioBadRequestError(FolioClientError):
    """
    Raised for 400 bad request errors.
    Malformed request syntax or invalid parameters.
    """

    def __init__(
        self,
        message: str = "Bad request - malformed request or invalid parameters",
        *,
        request: httpx.Request,
        response: httpx.Response,
    ) -> None:
        super().__init__(message, request=request, response=response)

    def __str__(self) -> str:
        return f"FOLIO bad request: {self.message}"


# 5xx Server Errors
class FolioServerError(FolioHTTPError):
    """
    Base class for 5xx server errors from FOLIO.
    Indicates problems within the FOLIO system itself.
    """

    def __str__(self) -> str:
        return f"FOLIO server error: {self.message} (HTTP {self.response.status_code})"


class FolioInternalServerError(FolioServerError):
    """
    Raised for 500 internal server errors.
    Unexpected errors within FOLIO modules or API gateway.
    """

    def __init__(
        self,
        message: str = "Internal server error - unexpected FOLIO system error",
        *,
        request: httpx.Request,
        response: httpx.Response,
    ) -> None:
        super().__init__(message, request=request, response=response)

    def __str__(self) -> str:
        return f"FOLIO internal server error: {self.message}"


class FolioBadGatewayError(FolioServerError):
    """
    Raised for 502 bad gateway errors.
    API gateway received invalid response from a FOLIO module.
    """

    def __init__(
        self,
        message: str = "Bad gateway - invalid response from FOLIO module",
        *,
        request: httpx.Request,
        response: httpx.Response,
    ) -> None:
        super().__init__(message, request=request, response=response)

    def __str__(self) -> str:
        return f"FOLIO bad gateway: {self.message}"


class FolioServiceUnavailableError(FolioServerError):
    """
    Raised for 503 service unavailable errors.
    FOLIO system temporarily unavailable, possibly under maintenance or overloaded.
    """

    def __init__(
        self,
        message: str = "Service unavailable - FOLIO system temporarily unavailable",
        *,
        request: httpx.Request,
        response: httpx.Response,
    ) -> None:
        super().__init__(message, request=request, response=response)

    def __str__(self) -> str:
        return f"FOLIO service unavailable: {self.message}"


class FolioGatewayTimeoutError(FolioServerError):
    """
    Raised for 504 gateway timeout errors.
    API gateway timeout waiting for response from FOLIO module.
    """

    def __init__(
        self,
        message: str = "Gateway timeout - FOLIO API gateway response timeout",
        *,
        request: httpx.Request,
        response: httpx.Response,
    ) -> None:
        super().__init__(message, request=request, response=response)

    def __str__(self) -> str:
        return f"FOLIO gateway timeout: {self.message}"


# Exception mapping dictionaries
_HTTP_STATUS_EXCEPTIONS: Dict[int, Type[FolioHTTPError]] = {
    # 4xx Client Errors
    400: FolioBadRequestError,
    401: FolioAuthenticationError,
    403: FolioPermissionError,
    404: FolioResourceNotFoundError,
    409: FolioDataConflictError,
    422: FolioValidationError,
    429: FolioRateLimitError,
    # 5xx Server Errors
    500: FolioInternalServerError,
    502: FolioBadGatewayError,
    503: FolioServiceUnavailableError,
    504: FolioGatewayTimeoutError,
}

_CONNECTION_EXCEPTIONS: Dict[Type[httpx.RequestError], Type[FolioConnectionError]] = {
    httpx.ConnectError: FolioSystemUnavailableError,
    httpx.TimeoutException: FolioTimeoutError,
    httpx.RemoteProtocolError: FolioProtocolError,
    httpx.NetworkError: FolioNetworkError,
}


def _get_error_detail(response: Optional[httpx.Response]) -> str:
    """Extract error details from FOLIO response, safely handling any exceptions."""
    if not response:
        return "No response available"
    try:
        # Try to get error details from response text
        error_text = response.text or "No error details in response"
        # Limit length to prevent extremely long error messages
        return error_text[:500] + "..." if len(error_text) > 500 else error_text
    except Exception:
        return "Unable to read error details from response"


def _create_folio_exception(
    original_error: Union[httpx.RequestError, httpx.HTTPStatusError],
) -> FolioError:
    """Create appropriate FOLIO exception based on the original httpx error."""

    # Handle connection errors (no response)
    if not hasattr(original_error, "response") or original_error.response is None:
        req_err = cast(httpx.RequestError, original_error)
        error_type = type(req_err) # silence type checker
        if error_type in _CONNECTION_EXCEPTIONS:
            exception_class = _CONNECTION_EXCEPTIONS[error_type]
            return exception_class(str(original_error), request=original_error.request)
        else:
            # Fallback for unknown connection errors
            return FolioConnectionError(
                f"Connection error: {original_error}", request=original_error.request
            )

    # Handle HTTP status errors (have response)
    if isinstance(original_error, httpx.HTTPStatusError):
        status_code = original_error.response.status_code
        error_detail = _get_error_detail(original_error.response)

        # Check for specific status code mappings
        if status_code in _HTTP_STATUS_EXCEPTIONS:
            http_exception_class: Type[FolioHTTPError] = _HTTP_STATUS_EXCEPTIONS[status_code]
            return http_exception_class(
                error_detail, request=original_error.request, response=original_error.response
            )

        # Handle general 4xx and 5xx errors
        if 400 <= status_code < 500:
            return FolioClientError(
                f"Client error: {error_detail}",
                request=original_error.request,
                response=original_error.response,
            )
        elif 500 <= status_code < 600:
            return FolioServerError(
                f"Server error: {error_detail}",
                request=original_error.request,
                response=original_error.response,
            )
        else:
            return FolioHTTPError(
                f"HTTP error: {error_detail}",
                request=original_error.request,
                response=original_error.response,
            )

    # Fallback for any other request errors
    return FolioError(f"Unexpected FOLIO error: {original_error}")


@overload
def folio_errors(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
    ...  # pragma: no cover


@overload
def folio_errors(func: Callable[P, T]) -> Callable[P, T]:
    ...  # pragma: no cover


def folio_errors(func: Callable[P, Any]) -> Callable[P, Any]:
    """
    Decorator that converts httpx exceptions to FOLIO-specific exceptions.

    This decorator catches both httpx.RequestError (connection issues) and
    httpx.HTTPStatusError (HTTP status errors) and re-raises them as more
    specific FOLIO exceptions with meaningful names in the FOLIO context.

    Works with both synchronous and asynchronous functions.

    Usage:
        >>> @folio_errors
        ... def get_user(self, user_id: str):
        ...     response = self._client.get(f"/users/{user_id}")
        ...     response.raise_for_status()
        ...     return response.json()

        >>> @folio_errors
        ... async def get_user_async(self, user_id: str):
        ...     response = await self._async_client.get(f"/users/{user_id}")
        ...     response.raise_for_status()
        ...     return response.json()
    """
    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                folio_exception = _create_folio_exception(e)
                raise folio_exception from e

        return cast(Callable[P, Awaitable[T]], async_wrapper)
    else:

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                folio_exception = _create_folio_exception(e)
                raise folio_exception from e

        return cast(Callable[P, T], sync_wrapper)
