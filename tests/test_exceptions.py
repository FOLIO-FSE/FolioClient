"""Tests for the exceptions module."""

import inspect
import pytest
from unittest.mock import Mock

import httpx

from folioclient.exceptions import (
    # Base exceptions
    FolioError,
    FolioClientClosed,
    
    # Connection errors
    FolioConnectionError,
    FolioSystemUnavailableError,
    FolioTimeoutError,
    FolioProtocolError,
    FolioNetworkError,
    
    # HTTP errors
    FolioHTTPError,
    
    # 4xx client errors
    FolioClientError,
    FolioBadRequestError,
    FolioAuthenticationError,
    FolioPermissionError,
    FolioResourceNotFoundError,
    FolioDataConflictError,
    FolioValidationError,
    FolioRateLimitError,
    
    # 5xx server errors
    FolioServerError,
    FolioInternalServerError,
    FolioBadGatewayError,
    FolioServiceUnavailableError,
    FolioGatewayTimeoutError,
    
    # Decorator
    folio_errors,
    _create_folio_exception,
    _get_error_detail,
)


class TestFolioClientClosed:
    """Test FolioClientClosed exception."""
    
    def test_default_message(self):
        exc = FolioClientClosed()
        assert str(exc) == "The FolioClient is closed"
    
    def test_custom_message(self):
        exc = FolioClientClosed("Custom message")
        assert str(exc) == "Custom message"


class TestConnectionErrors:
    """Test connection-related exceptions."""
    
    def test_folio_connection_error(self):
        request = Mock(spec=httpx.Request)
        exc = FolioConnectionError("Connection failed", request=request)
        assert exc.message == "Connection failed"
        assert exc.request == request
        assert str(exc) == "FOLIO connection error: Connection failed"
    
    def test_folio_system_unavailable_error(self):
        request = Mock(spec=httpx.Request)
        exc = FolioSystemUnavailableError("System down", request=request)
        assert str(exc) == "FOLIO system unavailable: System down"
    
    def test_folio_timeout_error(self):
        request = Mock(spec=httpx.Request)
        exc = FolioTimeoutError("Request timeout", request=request)
        assert str(exc) == "FOLIO request timeout: Request timeout"
    
    def test_folio_protocol_error(self):
        request = Mock(spec=httpx.Request)
        exc = FolioProtocolError("Protocol issue", request=request)
        assert str(exc) == "FOLIO protocol error: Protocol issue"
    
    def test_folio_network_error(self):
        request = Mock(spec=httpx.Request)
        exc = FolioNetworkError("Network issue", request=request)
        assert str(exc) == "FOLIO network error: Network issue"


class TestHTTPErrors:
    """Test HTTP status-related exceptions."""
    
    def setup_method(self):
        self.request = Mock(spec=httpx.Request)
        self.response = Mock(spec=httpx.Response)
        self.response.status_code = 500
    
    def test_folio_http_error(self):
        exc = FolioHTTPError("HTTP error", request=self.request, response=self.response)
        assert exc.message == "HTTP error"
        assert exc.request == self.request
        assert exc.response == self.response
        assert str(exc) == "FOLIO HTTP error: HTTP error (HTTP 500)"
    
    def test_folio_bad_request_error(self):
        self.response.status_code = 400
        exc = FolioBadRequestError("Bad request", request=self.request, response=self.response)
        assert str(exc) == "FOLIO bad request: Bad request"
    
    def test_folio_authentication_error(self):
        self.response.status_code = 401
        exc = FolioAuthenticationError("Auth failed", request=self.request, response=self.response)
        assert str(exc) == "FOLIO authentication failed: Auth failed"
    
    def test_folio_authentication_error_default_message(self):
        self.response.status_code = 401
        exc = FolioAuthenticationError(request=self.request, response=self.response)
        assert "Authentication failed" in exc.message
    
    def test_folio_permission_error(self):
        self.response.status_code = 403
        exc = FolioPermissionError("Permission denied", request=self.request, response=self.response)
        assert str(exc) == "FOLIO permission denied: Permission denied"
    
    def test_folio_resource_not_found_error(self):
        self.response.status_code = 404
        exc = FolioResourceNotFoundError("Not found", request=self.request, response=self.response)
        assert str(exc) == "FOLIO resource not found: Not found"
    
    def test_folio_data_conflict_error(self):
        self.response.status_code = 409
        exc = FolioDataConflictError("Conflict", request=self.request, response=self.response)
        assert str(exc) == "FOLIO data conflict: Conflict"
    
    def test_folio_validation_error(self):
        self.response.status_code = 422
        exc = FolioValidationError("Validation failed", request=self.request, response=self.response)
        assert str(exc) == "FOLIO validation error: Validation failed"
    
    def test_folio_rate_limit_error(self):
        self.response.status_code = 429
        exc = FolioRateLimitError("Rate limited", request=self.request, response=self.response)
        assert str(exc) == "FOLIO rate limit exceeded: Rate limited"
    
    def test_folio_internal_server_error(self):
        self.response.status_code = 500
        exc = FolioInternalServerError("Server error", request=self.request, response=self.response)
        assert str(exc) == "FOLIO internal server error: Server error"
    
    def test_folio_bad_gateway_error(self):
        self.response.status_code = 502
        exc = FolioBadGatewayError("Bad gateway", request=self.request, response=self.response)
        assert str(exc) == "FOLIO bad gateway: Bad gateway"
    
    def test_folio_service_unavailable_error(self):
        self.response.status_code = 503
        exc = FolioServiceUnavailableError("Service unavailable", request=self.request, response=self.response)
        assert str(exc) == "FOLIO service unavailable: Service unavailable"
    
    def test_folio_gateway_timeout_error(self):
        self.response.status_code = 504
        exc = FolioGatewayTimeoutError("Gateway timeout", request=self.request, response=self.response)
        assert str(exc) == "FOLIO gateway timeout: Gateway timeout"


class TestErrorDetailExtraction:
    """Test error detail extraction from responses."""
    
    def test_get_error_detail_with_text(self):
        response = Mock(spec=httpx.Response)
        response.text = "Error message"
        assert _get_error_detail(response) == "Error message"
    
    def test_get_error_detail_empty_text(self):
        response = Mock(spec=httpx.Response)
        response.text = ""
        assert _get_error_detail(response) == "No error details in response"
    
    def test_get_error_detail_no_response(self):
        assert _get_error_detail(None) == "No response available"
    
    def test_get_error_detail_exception(self):
        response = Mock(spec=httpx.Response)
        response.text = Mock(side_effect=Exception("Text error"))
        assert _get_error_detail(response) == "Unable to read error details from response"
    
    def test_get_error_detail_long_text(self):
        response = Mock(spec=httpx.Response)
        response.text = "x" * 600  # Long text
        result = _get_error_detail(response)
        assert len(result) == 503  # 500 + "..."
        assert result.endswith("...")


class TestCreateFolioException:
    """Test exception creation from httpx errors."""
    
    def setup_method(self):
        self.request = Mock(spec=httpx.Request)
        self.response = Mock(spec=httpx.Response)
    
    def test_create_connection_error(self):
        original_error = httpx.ConnectError("Connection failed", request=self.request)
        folio_error = _create_folio_exception(original_error)
        assert isinstance(folio_error, FolioSystemUnavailableError)
        assert folio_error.request == self.request
    
    def test_create_timeout_error(self):
        original_error = httpx.TimeoutException("Timeout", request=self.request)
        folio_error = _create_folio_exception(original_error)
        assert isinstance(folio_error, FolioTimeoutError)
    
    def test_create_protocol_error(self):
        original_error = httpx.RemoteProtocolError("Protocol error", request=self.request)
        folio_error = _create_folio_exception(original_error)
        assert isinstance(folio_error, FolioProtocolError)
    
    def test_create_unknown_connection_error(self):
        # Create a custom RequestError that's not in our mapping
        class CustomRequestError(httpx.RequestError):
            pass
        
        original_error = CustomRequestError("Unknown error", request=self.request)
        folio_error = _create_folio_exception(original_error)
        assert isinstance(folio_error, FolioConnectionError)
        assert "Connection error" in str(folio_error)
    
    def test_create_http_status_error_401(self):
        self.response.status_code = 401
        self.response.text = "Unauthorized"
        original_error = httpx.HTTPStatusError("Unauthorized", request=self.request, response=self.response)
        folio_error = _create_folio_exception(original_error)
        assert isinstance(folio_error, FolioAuthenticationError)
        assert folio_error.response == self.response
    
    def test_create_http_status_error_404(self):
        self.response.status_code = 404
        self.response.text = "Not found"
        original_error = httpx.HTTPStatusError("Not found", request=self.request, response=self.response)
        folio_error = _create_folio_exception(original_error)
        assert isinstance(folio_error, FolioResourceNotFoundError)
    
    def test_create_http_status_error_500(self):
        self.response.status_code = 500
        self.response.text = "Internal error"
        original_error = httpx.HTTPStatusError("Internal error", request=self.request, response=self.response)
        folio_error = _create_folio_exception(original_error)
        assert isinstance(folio_error, FolioInternalServerError)
    
    def test_create_generic_4xx_error(self):
        self.response.status_code = 418  # I'm a teapot
        self.response.text = "Teapot error"
        original_error = httpx.HTTPStatusError("Teapot", request=self.request, response=self.response)
        folio_error = _create_folio_exception(original_error)
        assert isinstance(folio_error, FolioClientError)
        assert "Client error" in str(folio_error)
    
    def test_create_generic_5xx_error(self):
        self.response.status_code = 599  # Custom server error
        self.response.text = "Custom server error"
        original_error = httpx.HTTPStatusError("Custom error", request=self.request, response=self.response)
        folio_error = _create_folio_exception(original_error)
        assert isinstance(folio_error, FolioServerError)
        assert "Server error" in str(folio_error)
    
    def test_create_unknown_status_code(self):
        self.response.status_code = 123  # Invalid status code
        self.response.text = "Unknown error"
        original_error = httpx.HTTPStatusError("Unknown", request=self.request, response=self.response)
        folio_error = _create_folio_exception(original_error)
        assert isinstance(folio_error, FolioHTTPError)
        assert "HTTP error" in str(folio_error)


class TestFolioErrorsDecorator:
    """Test the folio_errors decorator."""
    
    def test_sync_function_success(self):
        @folio_errors
        def test_function():
            return "success"
        
        result = test_function()
        assert result == "success"
    
    def test_sync_function_http_error(self):
        request = Mock(spec=httpx.Request)
        response = Mock(spec=httpx.Response)
        response.status_code = 404
        response.text = "Not found"
        
        @folio_errors
        def test_function():
            raise httpx.HTTPStatusError("Not found", request=request, response=response)
        
        with pytest.raises(FolioResourceNotFoundError) as exc_info:
            test_function()
        
        assert exc_info.value.response == response
        assert exc_info.value.__cause__.__class__ == httpx.HTTPStatusError
    
    def test_sync_function_connection_error(self):
        request = Mock(spec=httpx.Request)
        
        @folio_errors
        def test_function():
            raise httpx.ConnectError("Connection failed", request=request)
        
        with pytest.raises(FolioSystemUnavailableError) as exc_info:
            test_function()
        
        assert exc_info.value.request == request
        assert exc_info.value.__cause__.__class__ == httpx.ConnectError
    
    def test_sync_function_preserves_other_exceptions(self):
        @folio_errors
        def test_function():
            raise ValueError("Some other error")
        
        with pytest.raises(ValueError):
            test_function()
    
    @pytest.mark.asyncio
    async def test_async_function_success(self):
        @folio_errors
        async def test_function():
            return "async success"
        
        result = await test_function()
        assert result == "async success"
    
    @pytest.mark.asyncio
    async def test_async_function_http_error(self):
        request = Mock(spec=httpx.Request)
        response = Mock(spec=httpx.Response)
        response.status_code = 401
        response.text = "Unauthorized"
        
        @folio_errors
        async def test_function():
            raise httpx.HTTPStatusError("Unauthorized", request=request, response=response)
        
        with pytest.raises(FolioAuthenticationError) as exc_info:
            await test_function()
        
        assert exc_info.value.response == response
        assert exc_info.value.__cause__.__class__ == httpx.HTTPStatusError
    
    @pytest.mark.asyncio
    async def test_async_function_connection_error(self):
        request = Mock(spec=httpx.Request)
        
        @folio_errors
        async def test_function():
            raise httpx.TimeoutException("Timeout", request=request)
        
        with pytest.raises(FolioTimeoutError) as exc_info:
            await test_function()
        
        assert exc_info.value.request == request
        assert exc_info.value.__cause__.__class__ == httpx.TimeoutException
    
    @pytest.mark.asyncio
    async def test_async_function_preserves_other_exceptions(self):
        @folio_errors
        async def test_function():
            raise ValueError("Some other async error")
        
        with pytest.raises(ValueError):
            await test_function()
    
    def test_decorator_preserves_function_metadata(self):
        @folio_errors
        def test_function():
            """Test docstring."""
            return "test"
        
        assert test_function.__name__ == "test_function"
        assert test_function.__doc__ == "Test docstring."
    
    @pytest.mark.asyncio
    async def test_decorator_preserves_async_function_metadata(self):
        @folio_errors
        async def async_test_function():
            """Async test docstring."""
            return "async test"
        
        assert async_test_function.__name__ == "async_test_function"
        assert async_test_function.__doc__ == "Async test docstring."
        assert inspect.iscoroutinefunction(async_test_function)


class TestInheritance:
    """Test that exceptions inherit from the correct httpx exceptions."""
    
    def test_connection_error_inheritance(self):
        request = Mock(spec=httpx.Request)
        exc = FolioSystemUnavailableError("Test", request=request)
        assert isinstance(exc, httpx.RequestError)
        assert isinstance(exc, FolioError)
    
    def test_http_error_inheritance(self):
        request = Mock(spec=httpx.Request)
        response = Mock(spec=httpx.Response)
        response.status_code = 404
        
        exc = FolioResourceNotFoundError("Test", request=request, response=response)
        assert isinstance(exc, httpx.HTTPStatusError)
        assert isinstance(exc, FolioError)
    
    def test_timeout_error_inheritance(self):
        request = Mock(spec=httpx.Request)
        exc = FolioTimeoutError("Test", request=request)
        assert isinstance(exc, httpx.TimeoutException)
        assert isinstance(exc, httpx.RequestError)
        assert isinstance(exc, FolioError)


class TestExceptionChaining:
    """Test that original exceptions are properly chained."""
    
    def test_exception_chaining_with_decorator(self):
        request = Mock(spec=httpx.Request)
        response = Mock(spec=httpx.Response)
        response.status_code = 500
        response.text = "Server error"
        
        @folio_errors
        def failing_function():
            raise httpx.HTTPStatusError("Server error", request=request, response=response)
        
        with pytest.raises(FolioInternalServerError) as exc_info:
            failing_function()
        
        # Check that the original exception is chained
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, httpx.HTTPStatusError)
        assert str(exc_info.value.__cause__) == "Server error"

    def test_create_folio_exception_unexpected_folio_error(self):
        # Create an object that has a response attribute but is not an HTTPStatusError
        class WeirdError(Exception):
            def __init__(self, request=None, response=None):
                self.request = request
                self.response = response

        request = Mock(spec=httpx.Request)
        response = Mock(spec=httpx.Response)
        response.status_code = 999
        original = WeirdError(request=request, response=response)

        folio_err = _create_folio_exception(original)  # type: ignore[arg-type]
        assert isinstance(folio_err, FolioError)
        assert "Unexpected FOLIO error" in str(folio_err)
