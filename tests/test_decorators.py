"""Tests for the decorators module."""

import time
import unittest
import unittest.mock
from types import SimpleNamespace

import httpx
import pytest

from folioclient.decorators import folio_retry_on_server_error, folio_retry_on_auth_error

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
    httpx.HTTPStatusError("error 401", request=None, response=SimpleNamespace(status_code=401)),
    httpx.HTTPStatusError("error 403", request=None, response=SimpleNamespace(status_code=403)),
    "test",
]


@unittest.mock.patch("time.sleep", return_value=None)
@unittest.mock.patch.dict("os.environ", {})
def test_function_pass(_):
    internal_fn = unittest.mock.Mock(return_value="test")

    value = folio_retry_on_server_error(internal_fn)()

    assert internal_fn.call_count == 1
    assert time.sleep.call_count == 0
    assert value == internal_fn.return_value


@unittest.mock.patch("time.sleep", return_value=None)
@unittest.mock.patch.dict("os.environ", {})
def test_function_pass_auth(_):
    internal_fn = unittest.mock.Mock(return_value="test")

    value = folio_retry_on_auth_error(internal_fn)()

    assert internal_fn.call_count == 1
    assert time.sleep.call_count == 0
    assert value == internal_fn.return_value


@unittest.mock.patch("time.sleep", return_value=None)
@unittest.mock.patch.dict("os.environ", {})
def test_fails_default_auth(_):
    internal_fn = unittest.mock.Mock(
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


@unittest.mock.patch("time.sleep", return_value=None)
@unittest.mock.patch.dict("os.environ", {})
def test_fails_default(_):
    internal_fn = unittest.mock.Mock(
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


@unittest.mock.patch("time.sleep", return_value=None)
@unittest.mock.patch.dict(
    "os.environ",
    {"FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES": "1"},
)
def test_handles_single_fail(_):
    internal_fn = unittest.mock.Mock(
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


@unittest.mock.patch("time.sleep", return_value=None)
@unittest.mock.patch.dict(
    "os.environ",
    {"FOLIOCLIENT_MAX_AUTH_ERROR_RETRIES": "1"},
)
def test_handles_single_fail_auth(_):
    internal_fn = unittest.mock.Mock(
        return_value="test",
        side_effect=[
            httpx.HTTPStatusError("test", request=None, response=SimpleNamespace(status_code=401)),
            "test",
        ],
    )
    internal_fn.__name__ = "test_fn"

    result = folio_retry_on_auth_error(internal_fn)()

    assert internal_fn.call_count == 2
    assert time.sleep.call_count == 1
    assert time.sleep.call_args[0][0] == 10
    assert result == internal_fn.return_value


@unittest.mock.patch("time.sleep", return_value=None)
@unittest.mock.patch.dict(
    "os.environ",
    {"FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES": "5"},
)
def test_handles_multiple_failures(_):
    internal_fn = unittest.mock.Mock(return_value="test", side_effect=acceptable_errors_side_effect)
    internal_fn.__name__ = "test_fn"

    result = folio_retry_on_server_error(internal_fn)()

    assert internal_fn.call_count == 4
    assert time.sleep.call_count == 3
    assert time.sleep.call_args_list[0][0][0] == 10
    assert time.sleep.call_args_list[1][0][0] == 30
    assert time.sleep.call_args_list[2][0][0] == 90
    assert result == internal_fn.return_value


@unittest.mock.patch("time.sleep", return_value=None)
@unittest.mock.patch.dict(
    "os.environ",
    {"FOLIOCLIENT_MAX_AUTH_ERROR_RETRIES": "5"},
)
def test_handles_multiple_failures_auth(_):
    internal_fn = unittest.mock.Mock(
        return_value="test", side_effect=acceptable_auth_errors_side_effect
    )
    internal_fn.__name__ = "test_fn"

    result = folio_retry_on_auth_error(internal_fn)()

    assert internal_fn.call_count == 3
    assert time.sleep.call_count == 2
    assert time.sleep.call_args_list[0][0][0] == 10
    assert time.sleep.call_args_list[1][0][0] == 30
    assert result == internal_fn.return_value


@unittest.mock.patch("time.sleep", return_value=None)
@unittest.mock.patch.dict(
    "os.environ",
    {
        "FOLIOCLIENT_MAX_AUTH_ERROR_RETRIES": "4",
        "FOLIOCLIENT_AUTH_ERROR_RETRY_FACTOR": "5",
        "FOLIOCLIENT_AUTH_ERROR_RETRY_DELAY": "2",
    },
)
def test_handles_environment_variables(_):
    internal_fn = unittest.mock.Mock(
        return_value="test",
        side_effect=acceptable_auth_errors_side_effect,
    )
    internal_fn.__name__ = "test_fn"

    result = folio_retry_on_auth_error(internal_fn)()

    assert internal_fn.call_count == 3
    assert time.sleep.call_count == 2
    assert time.sleep.call_args_list[0][0][0] == 2
    assert time.sleep.call_args_list[1][0][0] == 10
    assert result == internal_fn.return_value


@unittest.mock.patch("time.sleep", return_value=None)
@unittest.mock.patch.dict(
    "os.environ",
    {
        "FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES": "4",
        "FOLIOCLIENT_SERVER_ERROR_RETRY_FACTOR": "5",
        "FOLIOCLIENT_SERVER_ERROR_RETRY_DELAY": "2",
    },
)
def test_handles_environment_variables_auth(_):
    internal_fn = unittest.mock.Mock(
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


@unittest.mock.patch("time.sleep", return_value=None)
@unittest.mock.patch.dict(
    "os.environ",
    {
        "FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES": "2",
    },
)
def test_handles_failthrough_on_tries(_):
    internal_fn = unittest.mock.Mock(
        return_value="test",
        side_effect=all_errors_side_effect,
    )
    internal_fn.__name__ = "test_fn"

    with pytest.raises(httpx.HTTPStatusError) as e:
        folio_retry_on_server_error(internal_fn)()

    assert internal_fn.call_count == 3
    assert time.sleep.call_count == 2
    assert e.value.response.status_code == 504


@unittest.mock.patch("time.sleep", return_value=None)
@unittest.mock.patch.dict(
    "os.environ",
    {
        "FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES": "5",
    },
)
def test_handles_failthrough_on_types(_):
    internal_fn = unittest.mock.Mock(return_value="test", side_effect=all_errors_side_effect)
    internal_fn.__name__ = "test_fn"

    with pytest.raises(httpx.HTTPStatusError) as e:
        folio_retry_on_server_error(internal_fn)()

    assert internal_fn.call_count == 4
    assert time.sleep.call_count == 3
    assert e.value.response.status_code == 500


@unittest.mock.patch("time.sleep", return_value=None)
@unittest.mock.patch.dict(
    "os.environ",
    {
        "FOLIOCLIENT_MAX_AUTH_ERROR_RETRIES": "5",
        "FOLIOCLIENT_AUTH_ERROR_RETRY_FACTOR": "5",
        "FOLIOCLIENT_AUTH_ERROR_RETRY_DELAY": "2",
    },
)
def test_handles_auth_environment_variables(_):
    internal_fn = unittest.mock.Mock(
        return_value="test",
        side_effect=acceptable_auth_errors_side_effect,
    )
    internal_fn.__name__ = "test_fn"

    result = folio_retry_on_auth_error(internal_fn)()

    assert internal_fn.call_count == 3
    assert time.sleep.call_count == 2
    assert time.sleep.call_args_list[0][0][0] == 2
    assert time.sleep.call_args_list[1][0][0] == 10
    assert result == internal_fn.return_value
