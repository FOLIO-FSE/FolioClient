"""Tests for the decorators module."""

import time
import unittest
import unittest.mock
from types import SimpleNamespace

import httpx
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
import httpx

from folioclient.decorators import folio_retry_on_server_error, folio_retry_on_auth_error, handle_remote_protocol_error

acceptable_errors_side_effect = [
    httpx.HTTPStatusError("error 502", request=None, response=SimpleNamespace(status_code=502)),
    httpx.HTTPStatusError("error 503", request=None, response=SimpleNamespace(status_code=503)),
    httpx.HTTPStatusError("error 504", request=None, response=SimpleNamespace(status_code=504)),
    "test",
]

all_errors_side_effect = acceptable_errors_side_effect.copy()
all_errors_side_effect.insert(
    3, httpx.HTTPStatusError("error 500", request=None, response=SimpleNamespace(status_code=500))
)

acceptable_auth_errors_side_effect = [
    httpx.HTTPStatusError("error 403", request=None, response=SimpleNamespace(status_code=403)),
    "test",
]


@patch("time.sleep", return_value=None)
@patch.dict("os.environ", {})
def test_function_pass(_):
    internal_fn = Mock(return_value="test")

    value = folio_retry_on_server_error(internal_fn)()

    assert internal_fn.call_count == 1
    assert time.sleep.call_count == 0
    assert value == internal_fn.return_value


@patch("time.sleep", return_value=None)
@patch.dict("os.environ", {})
def test_function_pass_auth(_):
    internal_fn = Mock(return_value="test")

    value = folio_retry_on_auth_error(internal_fn)()

    assert internal_fn.call_count == 1
    assert time.sleep.call_count == 0
    assert value == internal_fn.return_value


@patch("time.sleep", return_value=None)
@patch.dict("os.environ", {})
def test_fails_default_auth(_):
    internal_fn = Mock(
        return_value="test",
        side_effect=[
            httpx.HTTPStatusError("test", request=None, response=SimpleNamespace(status_code=401)),
            "test",
        ],
    )
    internal_fn.__name__ = "test_fn"

    with pytest.raises(httpx.HTTPStatusError):
        folio_retry_on_auth_error(internal_fn)()

    assert internal_fn.call_count == 1
    assert time.sleep.call_count == 0


@patch("time.sleep", return_value=None)
@patch.dict("os.environ", {})
def test_fails_default(_):
    internal_fn = Mock(
        return_value="test",
        side_effect=[
            httpx.HTTPStatusError("test", request=None, response=SimpleNamespace(status_code=502)),
            "test",
        ],
    )
    internal_fn.__name__ = "test_fn"

    with pytest.raises(httpx.HTTPStatusError):
        folio_retry_on_server_error(internal_fn)()

    assert internal_fn.call_count == 1
    assert time.sleep.call_count == 0


@patch("time.sleep", return_value=None)
@patch.dict(
    "os.environ",
    {"FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES": "1"},
)
def test_handles_single_fail(_):
    internal_fn = Mock(
        return_value="test",
        side_effect=[
            httpx.HTTPStatusError("test", request=None, response=SimpleNamespace(status_code=502)),
            "test",
        ],
    )
    internal_fn.__name__ = "test_fn"

    result = folio_retry_on_server_error(internal_fn)()

    assert internal_fn.call_count == 2
    assert time.sleep.call_count == 1
    assert time.sleep.call_args[0][0] == 10
    assert result == internal_fn.return_value


@patch("time.sleep", return_value=None)
@patch.dict(
    "os.environ",
    {"FOLIOCLIENT_MAX_AUTH_ERROR_RETRIES": "1"},
)
def test_handles_single_fail_auth(_):
    internal_fn = Mock(
        return_value="test",
        side_effect=[
            httpx.HTTPStatusError("test", request=None, response=SimpleNamespace(status_code=403)),
            "test",
        ],
    )
    internal_fn.__name__ = "test_fn"

    result = folio_retry_on_auth_error(internal_fn)()

    assert internal_fn.call_count == 2
    assert time.sleep.call_count == 1
    assert time.sleep.call_args[0][0] == 10
    assert result == internal_fn.return_value


@patch("time.sleep", return_value=None)
@patch.dict(
    "os.environ",
    {"FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES": "5"},
)
def test_handles_multiple_failures(_):
    internal_fn = Mock(return_value="test", side_effect=acceptable_errors_side_effect)
    internal_fn.__name__ = "test_fn"

    result = folio_retry_on_server_error(internal_fn)()

    assert internal_fn.call_count == 4
    assert time.sleep.call_count == 3
    assert time.sleep.call_args_list[0][0][0] == 10
    assert time.sleep.call_args_list[1][0][0] == 30
    assert time.sleep.call_args_list[2][0][0] == 90
    assert result == internal_fn.return_value


@patch("time.sleep", return_value=None)
@patch.dict(
    "os.environ",
    {"FOLIOCLIENT_MAX_AUTH_ERROR_RETRIES": "5"},
)
def test_handles_multiple_failures_auth(_):
    internal_fn = Mock(
        return_value="test", side_effect=acceptable_auth_errors_side_effect
    )
    internal_fn.__name__ = "test_fn"

    result = folio_retry_on_auth_error(internal_fn)()

    assert internal_fn.call_count == 2
    assert time.sleep.call_count == 1
    assert time.sleep.call_args_list[0][0][0] == 10
    assert result == internal_fn.return_value


@patch("time.sleep", return_value=None)
@patch.dict(
    "os.environ",
    {
        "FOLIOCLIENT_MAX_AUTH_ERROR_RETRIES": "4",
        "FOLIOCLIENT_AUTH_ERROR_RETRY_FACTOR": "5",
        "FOLIOCLIENT_AUTH_ERROR_RETRY_DELAY": "2",
    },
)
def test_handles_environment_variables(_):
    internal_fn = Mock(
        return_value="test",
        side_effect=acceptable_auth_errors_side_effect,
    )
    internal_fn.__name__ = "test_fn"

    result = folio_retry_on_auth_error(internal_fn)()

    assert internal_fn.call_count == 2
    assert time.sleep.call_count == 1
    assert time.sleep.call_args_list[0][0][0] == 2
    assert result == internal_fn.return_value


@patch("time.sleep", return_value=None)
@patch.dict(
    "os.environ",
    {
        "FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES": "4",
        "FOLIOCLIENT_SERVER_ERROR_RETRY_FACTOR": "5",
        "FOLIOCLIENT_SERVER_ERROR_RETRY_DELAY": "2",
    },
)
def test_handles_environment_variables_auth(_):
    internal_fn = Mock(
        return_value="test",
        side_effect=acceptable_errors_side_effect,
    )
    internal_fn.__name__ = "test_fn"

    result = folio_retry_on_server_error(internal_fn)()

    assert internal_fn.call_count == 4
    assert time.sleep.call_count == 3
    assert time.sleep.call_args_list[0][0][0] == 2
    assert time.sleep.call_args_list[1][0][0] == 10
    assert time.sleep.call_args_list[2][0][0] == 50
    assert result == internal_fn.return_value


@patch("time.sleep", return_value=None)
@patch.dict(
    "os.environ",
    {
        "FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES": "2",
    },
)
def test_handles_failthrough_on_tries(_):
    internal_fn = Mock(
        return_value="test",
        side_effect=all_errors_side_effect,
    )
    internal_fn.__name__ = "test_fn"

    with pytest.raises(httpx.HTTPStatusError) as e:
        folio_retry_on_server_error(internal_fn)()

    assert internal_fn.call_count == 3
    assert time.sleep.call_count == 2
    assert e.value.response.status_code == 504


@patch("time.sleep", return_value=None)
@patch.dict(
    "os.environ",
    {
        "FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES": "5",
    },
)
def test_handles_failthrough_on_types(_):
    internal_fn = Mock(return_value="test", side_effect=all_errors_side_effect)
    internal_fn.__name__ = "test_fn"

    with pytest.raises(httpx.HTTPStatusError) as e:
        folio_retry_on_server_error(internal_fn)()

    assert internal_fn.call_count == 4
    assert time.sleep.call_count == 3
    assert e.value.response.status_code == 500


@patch("time.sleep", return_value=None)
@patch.dict(
    "os.environ",
    {
        "FOLIOCLIENT_MAX_AUTH_ERROR_RETRIES": "5",
        "FOLIOCLIENT_AUTH_ERROR_RETRY_FACTOR": "5",
        "FOLIOCLIENT_AUTH_ERROR_RETRY_DELAY": "2",
    },
)
def test_handles_auth_environment_variables(_):
    internal_fn = Mock(
        return_value="test",
        side_effect=acceptable_auth_errors_side_effect,
    )
    internal_fn.__name__ = "test_fn"

    result = folio_retry_on_auth_error(internal_fn)()

    assert internal_fn.call_count == 2
    assert time.sleep.call_count == 1
    assert time.sleep.call_args_list[0][0][0] == 2
    assert result == internal_fn.return_value



class MockFolioClient:
    """Mock FolioClient for testing the decorator"""
    
    def __init__(self):
        self.httpx_client = Mock()
        self.httpx_async_client = AsyncMock()
        self.http_timeout = 30
        self.ssl_verify = True
        self.gateway_url = "https://test.folio.org"
        self.folio_auth = Mock()
        
        # Mock client properties
        self.httpx_client.is_closed = False
        self.httpx_async_client.is_closed = False


class TestHandleRemoteProtocolErrorDecorator:
    """Test cases for the handle_remote_protocol_error decorator"""

    def test_sync_method_success_no_error(self):
        """Test that sync methods work normally when no error occurs"""
        client = MockFolioClient()
        
        @handle_remote_protocol_error
        def test_method(self):
            return "success"
        
        result = test_method(client)
        assert result == "success"

    def test_sync_method_handles_remote_protocol_error(self):
        """Test that sync methods handle RemoteProtocolError and retry"""
        client = MockFolioClient()
        call_count = 0
        
        @handle_remote_protocol_error
        def test_method(self):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.RemoteProtocolError("Connection failed")
            return "success after retry"
        
        with patch('httpx.Client') as mock_client_class:
            mock_client_instance = Mock()
            mock_client_class.return_value = mock_client_instance
            mock_client_instance.is_closed = False
            client.httpx_client = mock_client_instance

            result = test_method(client)
            
            # Should succeed after retry
            assert result == "success after retry"
            assert call_count == 2
            
            # Should have closed old client and created new one
            client.httpx_client.close.assert_called_once()
            mock_client_class.assert_called_once_with(
                timeout=client.http_timeout,
                verify=client.ssl_verify,
                base_url=client.gateway_url,
                auth=client.folio_auth,
            )

    def test_sync_method_client_already_closed(self):
        """Test sync method when client is already closed"""
        client = MockFolioClient()
        client.httpx_client.is_closed = True
        
        @handle_remote_protocol_error
        def test_method(self):
            raise httpx.RemoteProtocolError("Connection failed")
        
        with patch('httpx.Client') as mock_client_class:
            with pytest.raises(httpx.RemoteProtocolError):
                test_method(client)
            
            # Should not try to close already closed client
            client.httpx_client.close.assert_not_called()

    def test_sync_method_no_existing_client(self):
        """Test sync method when no existing client"""
        client = MockFolioClient()
        client.httpx_client = None
        
        @handle_remote_protocol_error
        def test_method(self):
            raise httpx.RemoteProtocolError("Connection failed")
        
        with patch('httpx.Client') as mock_client_class:
            with pytest.raises(httpx.RemoteProtocolError):
                test_method(client)
            
            # Should create new client
            mock_client_class.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_method_success_no_error(self):
        """Test that async methods work normally when no error occurs"""
        client = MockFolioClient()
        
        @handle_remote_protocol_error
        async def test_method(self):
            return "async success"
        
        result = await test_method(client)
        assert result == "async success"

    @pytest.mark.asyncio
    async def test_async_method_handles_remote_protocol_error(self):
        """Test that async methods handle RemoteProtocolError and retry"""
        client = MockFolioClient()
        call_count = 0
        
        @handle_remote_protocol_error
        async def test_method(self):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.RemoteProtocolError("Async connection failed")
            return "async success after retry"
        
        with patch('httpx.AsyncClient') as mock_async_client_class:
            mock_async_client_instance = AsyncMock()
            mock_async_client_class.return_value = mock_async_client_instance
            mock_async_client_instance.is_closed = False
            client.httpx_async_client = mock_async_client_instance
            
            result = await test_method(client)
            
            # Should succeed after retry
            assert result == "async success after retry"
            assert call_count == 2
            
            # Should have closed old client and created new one
            client.httpx_async_client.aclose.assert_called_once()
            mock_async_client_class.assert_called_once_with(
                timeout=client.http_timeout,
                verify=client.ssl_verify,
                base_url=client.gateway_url,
                auth=client.folio_auth,
            )

    @pytest.mark.asyncio
    async def test_async_method_no_async_client_attribute(self):
        """Test async method when httpx_async_client attribute doesn't exist"""
        client = MockFolioClient()
        delattr(client, 'httpx_async_client')
        
        @handle_remote_protocol_error
        async def test_method(self):
            raise httpx.RemoteProtocolError("Connection failed")
        
        with patch('httpx.AsyncClient') as mock_async_client_class:
            with pytest.raises(httpx.RemoteProtocolError):
                await test_method(client)
            
            # Should create new client even without existing attribute
            mock_async_client_class.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_method_client_already_closed(self):
        """Test async method when client is already closed"""
        client = MockFolioClient()
        client.httpx_async_client.is_closed = True
        
        @handle_remote_protocol_error
        async def test_method(self):
            raise httpx.RemoteProtocolError("Connection failed")
        
        with patch('httpx.AsyncClient') as mock_async_client_class:
            with pytest.raises(httpx.RemoteProtocolError):
                await test_method(client)
            
            # Should not try to close already closed client
            client.httpx_async_client.aclose.assert_not_called()

    def test_other_exceptions_not_caught_sync(self):
        """Test that other exceptions are not caught by sync decorator"""
        client = MockFolioClient()
        
        @handle_remote_protocol_error
        def test_method(self):
            raise ValueError("Different error")
        
        with pytest.raises(ValueError, match="Different error"):
            test_method(client)

    @pytest.mark.asyncio
    async def test_other_exceptions_not_caught_async(self):
        """Test that other exceptions are not caught by async decorator"""
        client = MockFolioClient()
        
        @handle_remote_protocol_error
        async def test_method(self):
            raise ValueError("Different async error")
        
        with pytest.raises(ValueError, match="Different async error"):
            await test_method(client)

    def test_decorator_preserves_function_metadata_sync(self):
        """Test that decorator preserves function metadata for sync functions"""
        @handle_remote_protocol_error
        def test_function():
            """Test docstring"""
            pass
        
        assert test_function.__name__ == "test_function"
        assert test_function.__doc__ == "Test docstring"

    def test_decorator_preserves_function_metadata_async(self):
        """Test that decorator preserves function metadata for async functions"""
        @handle_remote_protocol_error
        async def async_test_function():
            """Async test docstring"""
            pass
        
        assert async_test_function.__name__ == "async_test_function"
        assert async_test_function.__doc__ == "Async test docstring"

    def test_decorator_detects_async_function_correctly(self):
        """Test that decorator correctly detects async vs sync functions"""
        
        @handle_remote_protocol_error
        def sync_func():
            return "sync"
        
        @handle_remote_protocol_error
        async def async_func():
            return "async"
        
        # Sync function should not be a coroutine function
        assert not asyncio.iscoroutinefunction(sync_func)
        
        # Async function should be a coroutine function
        assert asyncio.iscoroutinefunction(async_func)

    def test_method_arguments_passed_through_sync(self):
        """Test that method arguments are correctly passed through for sync methods"""
        client = MockFolioClient()
        
        @handle_remote_protocol_error
        def test_method(self, arg1, arg2, kwarg1=None):
            return f"{arg1}-{arg2}-{kwarg1}"
        
        result = test_method(client, "a", "b", kwarg1="c")
        assert result == "a-b-c"

    @pytest.mark.asyncio
    async def test_method_arguments_passed_through_async(self):
        """Test that method arguments are correctly passed through for async methods"""
        client = MockFolioClient()
        
        @handle_remote_protocol_error
        async def test_method(self, arg1, arg2, kwarg1=None):
            return f"{arg1}-{arg2}-{kwarg1}"
        
        result = await test_method(client, "x", "y", kwarg1="z")
        assert result == "x-y-z"

    def test_logging_on_error_sync(self):
        """Test that logging occurs when error is handled in sync method"""
        client = MockFolioClient()
        
        @handle_remote_protocol_error
        def test_method(self):
            raise httpx.RemoteProtocolError("Test error")
        
        with patch('httpx.Client'):
            with patch('folioclient.decorators.logging.warning') as mock_log:
                with pytest.raises(httpx.RemoteProtocolError):
                    test_method(client)
                
                mock_log.assert_called_once_with(
                    "Caught httpx.RemoteProtocolError. Recreate httpx.Client and retry."
                )

    @pytest.mark.asyncio
    async def test_logging_on_error_async(self):
        """Test that logging occurs when error is handled in async method"""
        client = MockFolioClient()
        
        @handle_remote_protocol_error
        async def test_method(self):
            raise httpx.RemoteProtocolError("Test error")
        
        with patch('httpx.AsyncClient'):
            with patch('folioclient.decorators.logging.warning') as mock_log:
                with pytest.raises(httpx.RemoteProtocolError):
                    await test_method(client)
                
                mock_log.assert_called_once_with(
                    "Caught httpx.RemoteProtocolError. Recreate httpx.AsyncClient and retry."
                )