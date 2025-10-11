"""Tests for the decorators module."""

import time
from types import SimpleNamespace
import types
import httpx
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
import httpx

from folioclient.decorators import (
    folio_retry_on_server_error,
    folio_retry_on_auth_error,
    handle_remote_protocol_error,
    folio_retry_all_errors,
    should_retry_server_error,
    should_retry_auth_error,
    ServerErrorRetryCondition,
    AuthErrorRetryCondition,
    auth_refresh_callback,
    use_client_session,
    use_client_session_with_generator,
)

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
        self.is_closed = False
        
        # Mock client properties
        self.httpx_client.is_closed = False
        self.httpx_async_client.is_closed = False
    
    def get_folio_http_client(self):
        """Mock implementation of get_folio_http_client"""
        mock_client = Mock()
        mock_client.is_closed = False
        return mock_client
    
    def get_folio_http_client_async(self):
        """Mock implementation of get_folio_http_client_async"""
        mock_async_client = AsyncMock()
        mock_async_client.is_closed = False
        return mock_async_client


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
        
        # Mock the get_folio_http_client method to return a new client
        mock_new_client = Mock()
        mock_new_client.is_closed = False
        client.get_folio_http_client = Mock(return_value=mock_new_client)
        
        # Set up existing client
        mock_existing_client = Mock()
        mock_existing_client.is_closed = False
        client.httpx_client = mock_existing_client

        result = test_method(client)
        
        # Should succeed after retry
        assert result == "success after retry"
        assert call_count == 2
        
        # Should have closed old client and created new one
        mock_existing_client.close.assert_called_once()
        client.get_folio_http_client.assert_called_once()

    def test_sync_method_client_already_closed(self):
        """Test sync method when client is already closed"""
        client = MockFolioClient()
        client.httpx_client.is_closed = True
        
        # Mock the get_folio_http_client method
        mock_new_client = Mock()
        mock_new_client.is_closed = False  
        client.get_folio_http_client = Mock(return_value=mock_new_client)

        @handle_remote_protocol_error
        def test_method(self):
            raise httpx.RemoteProtocolError("Connection failed")

        with pytest.raises(httpx.RemoteProtocolError):
            test_method(client)
        
        # Should create new client even when existing client is closed
        client.get_folio_http_client.assert_called_once()

    def test_sync_method_no_existing_client(self):
        """Test sync method when no existing client"""
        client = MockFolioClient()
        client.httpx_client = None
        
        # Mock the get_folio_http_client method
        mock_new_client = Mock()
        mock_new_client.is_closed = False
        client.get_folio_http_client = Mock(return_value=mock_new_client)

        @handle_remote_protocol_error
        def test_method(self):
            raise httpx.RemoteProtocolError("Connection failed")

        with pytest.raises(httpx.RemoteProtocolError):
            test_method(client)
        
        # Should create new client
        client.get_folio_http_client.assert_called_once()
    
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
        
        # Mock the get_folio_http_client_async method to return a new async client
        mock_new_async_client = AsyncMock()
        mock_new_async_client.is_closed = False
        client.get_folio_http_client_async = Mock(return_value=mock_new_async_client)
        
        # Set up existing async client
        mock_existing_async_client = AsyncMock()
        mock_existing_async_client.is_closed = False
        client.httpx_async_client = mock_existing_async_client

        result = await test_method(client)
        
        # Should succeed after retry
        assert result == "async success after retry"
        assert call_count == 2
        
        # Should have closed old client and created new one
        mock_existing_async_client.aclose.assert_called_once()
        client.get_folio_http_client_async.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_async_method_no_async_client_attribute(self):
        """Test async method when httpx_async_client attribute doesn't exist"""
        client = MockFolioClient()
        delattr(client, 'httpx_async_client')
        
        # Mock the get_folio_http_client_async method
        mock_new_async_client = AsyncMock()
        mock_new_async_client.is_closed = False
        client.get_folio_http_client_async = Mock(return_value=mock_new_async_client)

        @handle_remote_protocol_error
        async def test_method(self):
            raise httpx.RemoteProtocolError("Connection failed")

        with pytest.raises(httpx.RemoteProtocolError):
            await test_method(client)
        
        # Should create new client even without existing attribute
        client.get_folio_http_client_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_method_client_already_closed(self):
        """Test async method when client is already closed"""
        client = MockFolioClient()
        client.httpx_async_client.is_closed = True
        
        # Mock the get_folio_http_client_async method
        mock_new_async_client = AsyncMock()
        mock_new_async_client.is_closed = False
        client.get_folio_http_client_async = Mock(return_value=mock_new_async_client)
        
        @handle_remote_protocol_error
        async def test_method(self):
            raise httpx.RemoteProtocolError("Connection failed")
        
        with pytest.raises(httpx.RemoteProtocolError):
            await test_method(client)
        
        # Should not try to close already closed client, but should create new one
        client.httpx_async_client.aclose.assert_not_called()
        client.get_folio_http_client_async.assert_called_once()

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
        
        # Mock the get_folio_http_client method
        mock_new_client = Mock()
        mock_new_client.is_closed = False
        client.get_folio_http_client = Mock(return_value=mock_new_client)
        
        @handle_remote_protocol_error
        def test_method(self):
            raise httpx.RemoteProtocolError("Test error")
        
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
        
        # Mock the get_folio_http_client_async method
        mock_new_async_client = AsyncMock()
        mock_new_async_client.is_closed = False
        client.get_folio_http_client_async = Mock(return_value=mock_new_async_client)
        
        @handle_remote_protocol_error
        async def test_method(self):
            raise httpx.RemoteProtocolError("Test error")
        
        with patch('folioclient.decorators.logging.warning') as mock_log:
            with pytest.raises(httpx.RemoteProtocolError):
                await test_method(client)
            
            mock_log.assert_called_once_with(
                "Caught httpx.RemoteProtocolError. Recreate httpx.AsyncClient and retry."
            )


def test_should_retry_server_error_and_auth():
    # ConnectError should retry
    assert should_retry_server_error(httpx.ConnectError("c", request=None)) is True

    # HTTP status 502/503/504 should retry
    assert should_retry_server_error(httpx.HTTPStatusError("", request=None, response=SimpleNamespace(status_code=502))) is True
    assert should_retry_server_error(httpx.HTTPStatusError("", request=None, response=SimpleNamespace(status_code=503))) is True
    assert should_retry_server_error(httpx.HTTPStatusError("", request=None, response=SimpleNamespace(status_code=504))) is True

    # Other HTTP statuses should not retry
    assert should_retry_server_error(httpx.HTTPStatusError("", request=None, response=SimpleNamespace(status_code=500))) is False
    assert should_retry_server_error(ValueError("boom")) is False

    # Auth retry helper
    assert should_retry_auth_error(SimpleNamespace(response=SimpleNamespace(status_code=403))) is True
    assert should_retry_auth_error(SimpleNamespace(response=SimpleNamespace(status_code=401))) is False


def test_retry_condition_classes():
    # Create fake retry_state objects
    class FakeOutcome:
        def __init__(self, failed, exc=None):
            self.failed = failed
            self._exc = exc

        def exception(self):
            return self._exc

    class FakeState:
        def __init__(self, outcome, args=()):
            self.outcome = outcome
            self.args = args

    # ServerErrorRetryCondition: when not failed -> False
    cond = ServerErrorRetryCondition()
    assert cond(FakeState(FakeOutcome(False))) is False

    # When failed with ConnectError -> True
    assert cond(FakeState(FakeOutcome(True, httpx.ConnectError("x", request=None)))) is True

    # AuthErrorRetryCondition
    auth_cond = AuthErrorRetryCondition()
    assert auth_cond(FakeState(FakeOutcome(False))) is False
    assert auth_cond(FakeState(FakeOutcome(True, httpx.HTTPStatusError("", request=None, response=SimpleNamespace(status_code=403))))) is True


def test_auth_refresh_callback_invokes_login(monkeypatch):
    # Create fake retry_state with attempt_number > 1 and args with a client that has login()
    class FakeState:
        def __init__(self, attempt_number, args):
            self.attempt_number = attempt_number
            self.args = args

    client = SimpleNamespace()
    client.login = Mock()

    state = FakeState(2, (client,))
    auth_refresh_callback(state)
    client.login.assert_called_once()


def test_use_client_session_sync_and_async():
    # Use existing MockFolioClient from this file
    client = MockFolioClient()

    # Make get_folio_http_client return a context manager
    class CM:
        def __enter__(self):
            m = Mock()
            m.is_closed = False
            return m

        def __exit__(self, exc_type, exc, tb):
            return False

    client.get_folio_http_client = Mock(return_value=CM())

    @use_client_session
    def test_method(self, x):
        return x * 2

    # No existing client -> uses temp client and returns
    result = test_method(client, 3)
    assert result == 6

    # Now set an existing client that's open
    client.httpx_client = Mock()
    client.httpx_client.is_closed = False

    result = test_method(client, 4)
    assert result == 8

    # When closed -> raises FolioClientClosed
    client.is_closed = True
    with pytest.raises(Exception):
        test_method(client, 1)


@pytest.mark.asyncio
async def test_use_client_session_async_and_generator():
    client = MockFolioClient()

    class AsyncCM:
        async def __aenter__(self):
            m = AsyncMock()
            m.is_closed = False
            return m

        async def __aexit__(self, exc_type, exc, tb):
            return False

    client.get_folio_http_client_async = Mock(return_value=AsyncCM())

    @use_client_session
    async def test_method(self, x):
        return x + 1

    result = await test_method(client, 5)
    assert result == 6

    # Generator variant (sync)
    client = MockFolioClient()
    class CM2:
        def __enter__(self):
            m = Mock()
            m.is_closed = False
            return m

        def __exit__(self, exc_type, exc, tb):
            return False

    client.get_folio_http_client = Mock(return_value=CM2())

    @use_client_session_with_generator
    def gen_method(self):
        for i in range(3):
            yield i

    assert list(gen_method(client)) == [0, 1, 2]

    # Async generator variant
    client = MockFolioClient()
    client.get_folio_http_client_async = Mock(return_value=AsyncCM())

    @use_client_session_with_generator
    async def agen_method(self):
        for i in range(2):
            yield i

    results = []
    async for v in agen_method(client):
        results.append(v)

    assert results == [0, 1]


def test_use_client_session_with_generator_creates_temp_client():
    class FakeCM:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class C:
        def __init__(self):
            self.is_closed = False

        def get_folio_http_client(self):
            return FakeCM()

        @use_client_session
        def gen(self):
            yield 1
            yield 2

    c = C()
    out = list(c.gen())
    assert out == [1, 2]


@pytest.mark.asyncio
async def test_use_client_session_with_generator_async_creates_temp_client():
    class FakeAsyncCM:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class C:
        def __init__(self):
            self.is_closed = False

        def get_folio_http_client_async(self):
            return FakeAsyncCM()

        @use_client_session_with_generator
        async def gen(self):
            yield 10
            yield 20

    c = C()
    items = []
    async for v in c.gen():
        items.append(v)
    assert items == [10, 20]


def test_server_retry_retries_on_connect_error(monkeypatch):
    monkeypatch.setenv("FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES", "1")
    monkeypatch.setenv("FOLIOCLIENT_SERVER_ERROR_RETRY_DELAY", "0.001")

    calls = {"n": 0}

    @folio_retry_on_server_error
    def flaky():
        if calls["n"] == 0:
            calls["n"] += 1
            raise httpx.ConnectError("boom")
        return "ok"

    assert flaky() == "ok"


def test_server_retry_retries_on_502(monkeypatch):
    monkeypatch.setenv("FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES", "2")
    monkeypatch.setenv("FOLIOCLIENT_SERVER_ERROR_RETRY_DELAY", "0.001")

    calls = {"n": 0}

    @folio_retry_on_server_error
    def flaky():
        if calls["n"] < 2:
            calls["n"] += 1
            resp = httpx.Response(502, request=httpx.Request("GET", "https://a"))
            raise httpx.HTTPStatusError("bad", request=resp.request, response=resp)
        return "ok"

    assert flaky() == "ok"


def test_server_retry_no_retries_propagates(monkeypatch):
    monkeypatch.setenv("FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES", "0")
    monkeypatch.setenv("FOLIOCLIENT_SERVER_ERROR_RETRY_DELAY", "0.001")

    @folio_retry_on_server_error
    def always_fail():
        raise httpx.ConnectError("boom")

    with pytest.raises(httpx.ConnectError):
        always_fail()


def test_auth_refresh_callback_no_login_on_first_attempt(monkeypatch):
    monkeypatch.setenv("FOLIOCLIENT_MAX_AUTH_ERROR_RETRIES", "0")
    monkeypatch.setenv("FOLIOCLIENT_AUTH_ERROR_RETRY_DELAY", "0")

    class C:
        def __init__(self):
            self.login_called = 0

        def login(self):
            self.login_called += 1

        @folio_retry_on_auth_error
        def call(self):
            resp = httpx.Response(403, request=httpx.Request("GET", "https://a"))
            raise httpx.HTTPStatusError("forbidden", request=resp.request, response=resp)

    c = C()
    with pytest.raises(httpx.HTTPStatusError):
        c.call()
    assert c.login_called == 0


def test_auth_refresh_callback_calls_login_on_retry(monkeypatch):
    monkeypatch.setenv("FOLIOCLIENT_MAX_AUTH_ERROR_RETRIES", "2")
    monkeypatch.setenv("FOLIOCLIENT_AUTH_ERROR_RETRY_DELAY", "0.001")

    class C:
        def __init__(self):
            self.login_called = 0
            self._attempts = 0

        def login(self):
            self.login_called += 1

        @folio_retry_on_auth_error
        def call(self):
            if self._attempts < 2:
                self._attempts += 1
                resp = httpx.Response(403, request=httpx.Request("GET", "https://a"))
                raise httpx.HTTPStatusError("forbidden", request=resp.request, response=resp)
            return "ok"

    c = C()
    res = c.call()
    assert res == "ok"
    assert c.login_called >= 1


def test_auth_refresh_callback_missing_login_is_safe(monkeypatch):
    monkeypatch.setenv("FOLIOCLIENT_MAX_AUTH_ERROR_RETRIES", "2")
    monkeypatch.setenv("FOLIOCLIENT_AUTH_ERROR_RETRY_DELAY", "0.001")

    class C:
        def __init__(self):
            self._attempts = 0

        @folio_retry_on_auth_error
        def call(self):
            if self._attempts < 2:
                self._attempts += 1
                resp = httpx.Response(403, request=httpx.Request("GET", "https://a"))
                raise httpx.HTTPStatusError("forbidden", request=resp.request, response=resp)
            return "ok"

    c = C()
    res = c.call()
    assert res == "ok"


def test_handle_remote_protocol_error_missing_client_attr_sync():
    class FakeClient:
        def __init__(self, name):
            self.name = name
            self.is_closed = False

        def close(self):
            self.is_closed = True

    class C:
        def __init__(self):
            pass

        def get_folio_http_client(self):
            return FakeClient("new")

        @handle_remote_protocol_error
        def call(self):
            if not hasattr(self, "_called"):
                self._called = True
                raise httpx.RemoteProtocolError("rp")
            return "ok"

    c = C()
    res = c.call()
    assert res == "ok"
    assert isinstance(c.httpx_client, FakeClient)


def test_handle_remote_protocol_error_closed_client_sync():
    class FakeClient:
        def __init__(self, name):
            self.name = name
            self.is_closed = True

        def close(self):
            self.is_closed = True

    class C:
        def __init__(self):
            self.httpx_client = FakeClient("old")

        def get_folio_http_client(self):
            return FakeClient("new")

        @handle_remote_protocol_error
        def call(self):
            if not hasattr(self, "_called"):
                self._called = True
                raise httpx.RemoteProtocolError("rp")
            return "ok"

    c = C()
    res = c.call()
    assert res == "ok"
    assert isinstance(c.httpx_client, FakeClient)
    assert c.httpx_client.name == "new"


def test_get_server_retry_config_numeric_max_wait(monkeypatch):
    from folioclient.decorators import get_server_retry_config

    monkeypatch.setenv("FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES", "1")
    monkeypatch.setenv("FOLIOCLIENT_SERVER_ERROR_MAX_WAIT", "2.5")
    cfg = get_server_retry_config()
    assert "wait" in cfg and "stop" in cfg


def test_get_auth_retry_config_numeric_max_wait(monkeypatch):
    from folioclient.decorators import get_auth_retry_config

    monkeypatch.setenv("FOLIOCLIENT_MAX_AUTH_ERROR_RETRIES", "1")
    monkeypatch.setenv("FOLIOCLIENT_AUTH_ERROR_MAX_WAIT", "30")
    cfg = get_auth_retry_config()
    assert "wait" in cfg and "stop" in cfg


def test_use_client_session_with_generator_reuse_client_sync():
    class C:
        def __init__(self):
            self.httpx_client = types.SimpleNamespace(is_closed=False)
            self.is_closed = False

        def get_folio_http_client(self):
            raise AssertionError("should not be called")

        @use_client_session_with_generator
        def gen(self):
            yield "a"
            yield "b"

    c = C()
    out = list(c.gen())
    assert out == ["a", "b"]


def test_use_client_session_with_generator_closed_raises_sync():
    from folioclient.exceptions import FolioClientClosed

    class C:
        def __init__(self):
            self.httpx_client = types.SimpleNamespace(is_closed=False)
            self.is_closed = True

        def get_folio_http_client(self):
            raise AssertionError("should not be called")

        @use_client_session_with_generator
        def gen(self):
            yield 1

    c = C()
    with pytest.raises(FolioClientClosed):
        list(c.gen())


@pytest.mark.asyncio
async def test_use_client_session_with_generator_reuse_client_async():
    class FakeAsyncClient:
        def __init__(self):
            self.is_closed = False

    class C:
        def __init__(self):
            self.async_httpx_client = FakeAsyncClient()
            self.is_closed = False

        def get_folio_http_client_async(self):
            raise AssertionError("should not be called")

        @use_client_session_with_generator
        async def gen(self):
            yield 7
            yield 8

    c = C()
    items = []
    async for v in c.gen():
        items.append(v)
    assert items == [7, 8]


@pytest.mark.asyncio
async def test_use_client_session_with_generator_closed_raises_async():
    from folioclient.exceptions import FolioClientClosed

    class FakeAsyncClient:
        def __init__(self):
            self.is_closed = False

    class C:
        def __init__(self):
            self.async_httpx_client = FakeAsyncClient()
            self.is_closed = True

        def get_folio_http_client_async(self):
            raise AssertionError("should not be called")

        @use_client_session_with_generator
        async def gen(self):
            yield 1

    c = C()
    with pytest.raises(FolioClientClosed):
        async for _ in c.gen():
            pass


@pytest.mark.asyncio
async def test_handle_remote_protocol_error_missing_client_attr_async():
    class FakeAsyncClient:
        def __init__(self, name):
            self.name = name
            self.is_closed = False

        async def aclose(self):
            self.is_closed = True

    class C:
        def __init__(self):
            pass

        def get_folio_http_client_async(self):
            return FakeAsyncClient("new")

        @handle_remote_protocol_error
        async def call(self):
            if not hasattr(self, "_called"):
                self._called = True
                raise httpx.RemoteProtocolError("rp")
            return "ok"

    c = C()
    res = await c.call()
    assert res == "ok"
    assert isinstance(c.httpx_async_client, FakeAsyncClient)


@pytest.mark.asyncio
async def test_handle_remote_protocol_error_closed_client_async():
    class FakeAsyncClient:
        def __init__(self, name, closed=False):
            self.name = name
            self.is_closed = closed

        async def aclose(self):
            self.is_closed = True

    class C:
        def __init__(self):
            self.httpx_async_client = FakeAsyncClient("old", closed=True)

        def get_folio_http_client_async(self):
            return FakeAsyncClient("new")

        @handle_remote_protocol_error
        async def call(self):
            if not hasattr(self, "_called"):
                self._called = True
                raise httpx.RemoteProtocolError("rp")
            return "ok"

    c = C()
    res = await c.call()
    assert res == "ok"
    assert isinstance(c.httpx_async_client, FakeAsyncClient)
    assert c.httpx_async_client.name == "new"


def test_server_retry_decorator_retries_on_connect_error(monkeypatch):
    monkeypatch.setenv("FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES", "1")
    monkeypatch.setenv("FOLIOCLIENT_SERVER_ERROR_RETRY_DELAY", "0.001")

    calls = {"n": 0}

    @folio_retry_on_server_error
    def flaky():
        if calls["n"] == 0:
            calls["n"] += 1
            raise httpx.ConnectError("boom")
        return "ok"

    assert flaky() == "ok"


def test_auth_retry_decorator_refreshes_login(monkeypatch):
    monkeypatch.setenv("FOLIOCLIENT_MAX_AUTH_ERROR_RETRIES", "2")
    monkeypatch.setenv("FOLIOCLIENT_AUTH_ERROR_RETRY_DELAY", "0.001")

    class Dummy:
        def __init__(self):
            self.login_called = 0

        def login(self):
            self.login_called += 1

        @folio_retry_on_auth_error
        def call(self):
            if not hasattr(self, "_attempts"):
                self._attempts = 0
            if self._attempts < 2:
                self._attempts += 1
                resp = httpx.Response(403, request=httpx.Request("GET", "https://a"))
                raise httpx.HTTPStatusError("forbidden", request=resp.request, response=resp)
            return "ok"

    d = Dummy()
    result = d.call()
    assert result == "ok"
    assert d.login_called >= 1


def test_folio_retry_all_errors_combined(monkeypatch):
    monkeypatch.setenv("FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES", "1")
    monkeypatch.setenv("FOLIOCLIENT_SERVER_ERROR_RETRY_DELAY", "0.001")
    monkeypatch.setenv("FOLIOCLIENT_MAX_AUTH_ERROR_RETRIES", "2")
    monkeypatch.setenv("FOLIOCLIENT_AUTH_ERROR_RETRY_DELAY", "0.001")

    state = {"calls": 0}

    @folio_retry_all_errors
    def combo():
        if state["calls"] < 2:
            state["calls"] += 1
            resp = httpx.Response(403, request=httpx.Request("GET", "https://a"))
            raise httpx.HTTPStatusError("forbidden", request=resp.request, response=resp)
        return "ok"

    assert combo() == "ok"


def test_handle_remote_protocol_error_recreates_client_sync():
    class FakeClient:
        def __init__(self, name):
            self.name = name
            self.closed = False
            self.is_closed = False

        def close(self):
            self.closed = True
            self.is_closed = True

    class C:
        def __init__(self):
            self.httpx_client = FakeClient("a")

        def get_folio_http_client(self):
            return FakeClient("new")

        @handle_remote_protocol_error
        def call(self):
            if not hasattr(self, "_called"):
                self._called = True
                raise httpx.RemoteProtocolError("rp")
            return "ok"

    c = C()
    res = c.call()
    assert res == "ok"
    assert isinstance(c.httpx_client, FakeClient)
    assert c.httpx_client.name == "new"


def test_use_client_session_raises_when_closed():
    class C:
        def __init__(self):
            # Provide an existing httpx_client that is not closed so the decorator
            # does not create a temp client. Mark the client as open but the
            # FolioClient itself as closed to trigger the FolioClientClosed path.
            self.httpx_client = __import__('types').SimpleNamespace(is_closed=False)
            self.is_closed = True

        def get_folio_http_client(self):
            class CM:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

            return CM()

        @use_client_session
        def call(self):
            return "ok"

    c = C()
    with pytest.raises(Exception):
        c.call()


def test_get_server_retry_config_numeric_max_wait_top(monkeypatch):
    # Explicit numeric max wait should be parsed into a float without errors
    from folioclient.decorators import get_server_retry_config

    monkeypatch.setenv("FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES", "1")
    monkeypatch.setenv("FOLIOCLIENT_SERVER_ERROR_MAX_WAIT", "2.5")
    cfg = get_server_retry_config()
    assert "wait" in cfg and "stop" in cfg


def test_get_auth_retry_config_numeric_max_wait_top(monkeypatch):
    # Explicit numeric auth max wait should be parsed into a float without errors
    from folioclient.decorators import get_auth_retry_config

    monkeypatch.setenv("FOLIOCLIENT_MAX_AUTH_ERROR_RETRIES", "1")
    monkeypatch.setenv("FOLIOCLIENT_AUTH_ERROR_MAX_WAIT", "30")
    cfg = get_auth_retry_config()
    assert "wait" in cfg and "stop" in cfg


@pytest.mark.asyncio
async def test_use_client_session_reuse_client_async():
    # When an async client already exists and the FolioClient is open,
    # the decorator should simply call the wrapped coroutine and return its value.
    class FakeAsyncClient:
        def __init__(self):
            self.is_closed = False

    class C:
        def __init__(self):
            self.async_httpx_client = FakeAsyncClient()
            self.is_closed = False

        def get_folio_http_client_async(self):
            raise AssertionError("should not be called")

        @use_client_session
        async def call(self):
            return "async-ok"

    c = C()
    res = await c.call()
    assert res == "async-ok"


@pytest.mark.asyncio
async def test_use_client_session_closed_raises_async():
    from folioclient.exceptions import FolioClientClosed

    class FakeAsyncClient:
        def __init__(self):
            self.is_closed = False

    class C:
        def __init__(self):
            self.async_httpx_client = FakeAsyncClient()
            # Mark the FolioClient as closed to force the closed branch
            self.is_closed = True

        def get_folio_http_client_async(self):
            raise AssertionError("should not be called")

        @use_client_session
        async def call(self):
            return "async-ok"

    c = C()
    with pytest.raises(FolioClientClosed):
        await c.call()


def test_use_client_session_with_generator_closed_raises_sync_explicit():
    # Explicitly advance the generator to ensure the wrapper body executes
    from folioclient.exceptions import FolioClientClosed

    class C:
        def __init__(self):
            self.httpx_client = __import__('types').SimpleNamespace(is_closed=False)
            self.is_closed = True

        @use_client_session_with_generator
        def gen(self):
            yield 1

    c = C()
    g = c.gen()
    with pytest.raises(FolioClientClosed):
        next(g)


@pytest.mark.asyncio
async def test_use_client_session_with_generator_closed_raises_async_explicit():
    # Explicitly advance the async generator to ensure the async wrapper body executes
    from folioclient.exceptions import FolioClientClosed

    class C:
        def __init__(self):
            class FakeAsyncClient:
                def __init__(self):
                    self.is_closed = False

            self.async_httpx_client = FakeAsyncClient()
            self.is_closed = True

        @use_client_session_with_generator
        async def gen(self):
            yield 1

    c = C()
    agen = c.gen()
    with pytest.raises(FolioClientClosed):
        await agen.asend(None)


@pytest.mark.asyncio
async def test_use_client_session_with_generator_reuse_client_async_advance():
    # Advance the async generator manually to ensure the async-for and yield
    # statements in the decorator are executed (covers lines 320-321).
    class FakeAsyncClient:
        def __init__(self):
            self.is_closed = False

    class C:
        def __init__(self):
            self.async_httpx_client = FakeAsyncClient()
            self.is_closed = False

        @use_client_session_with_generator
        async def gen(self):
            yield "x"
            yield "y"

    c = C()
    agen = c.gen()
    first = await agen.asend(None)
    assert first == "x"
    second = await agen.asend(None)
    assert second == "y"
    # generator should now be exhausted
    with pytest.raises(StopAsyncIteration):
        await agen.asend(None)


def test_get_server_retry_config_defaults(monkeypatch):
    # Ensure environment is clean
    monkeypatch.delenv("FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES", raising=False)
    monkeypatch.delenv("FOLIOCLIENT_SERVER_ERROR_RETRY_DELAY", raising=False)
    # Import inside test to avoid circular import in module-level import ordering
    from folioclient.decorators import get_server_retry_config

    cfg = get_server_retry_config()
    # Should return tenacity kwargs: stop, wait, retry, before_sleep, after, reraise
    assert "stop" in cfg and "wait" in cfg and "retry" in cfg
    assert callable(cfg["retry"])
    assert isinstance(cfg.get("before_sleep"), object)


def test_get_server_retry_config_unlimited_and_legacy(monkeypatch):
    from folioclient.decorators import get_server_retry_config

    # Test unlimited semantics for max wait via the MAX_WAIT env var
    monkeypatch.setenv("FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES", "2")
    monkeypatch.setenv("FOLIOCLIENT_SERVER_ERROR_MAX_WAIT", "unlimited")
    monkeypatch.setenv("FOLIOCLIENT_SERVER_ERROR_RETRY_DELAY", "0.01")
    cfg = get_server_retry_config()
    assert "stop" in cfg and "wait" in cfg

    # Test legacy fallback variable names for retries (older env names)
    monkeypatch.delenv("FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES", raising=False)
    monkeypatch.setenv("SERVER_ERROR_RETRIES_MAX", "3")
    monkeypatch.setenv("SERVER_ERROR_RETRY_DELAY", "0.02")
    cfg2 = get_server_retry_config()
    assert "stop" in cfg2 and "wait" in cfg2


def test_get_auth_retry_config_numeric_and_none(monkeypatch):
    from folioclient.decorators import get_auth_retry_config

    monkeypatch.setenv("FOLIOCLIENT_MAX_AUTH_ERROR_RETRIES", "0")
    monkeypatch.setenv("FOLIOCLIENT_AUTH_ERROR_RETRY_DELAY", "0")
    cfg = get_auth_retry_config()
    assert "stop" in cfg and "wait" in cfg and "retry" in cfg

    # now test 'inf' mapping for the max wait env var
    monkeypatch.setenv("FOLIOCLIENT_MAX_AUTH_ERROR_RETRIES", "2")
    monkeypatch.setenv("FOLIOCLIENT_AUTH_ERROR_MAX_WAIT", "inf")
    cfg2 = get_auth_retry_config()
    assert "stop" in cfg2 and "wait" in cfg2

