import json
import pytest
from httpx import HTTPError, UnsupportedProtocol
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import httpx

# Import shared test utilities
from .test_utils import folio_auth_patcher

# Now safe to import FolioClient 
from folioclient.FolioClient import FolioClient

# Import all FOLIO exceptions used in tests
from folioclient.exceptions import (
    FolioClientClosed,
)


def test_first():
    with pytest.raises(UnsupportedProtocol):
        FolioClient("", "", "", "")


""" def test_backwards():
    folio = FolioClient(
        "", "", "", ""
    )
    yaml = folio.get_latest_from_github(
        "folio-org", "mod-notes", "src/main/resources/swagger.api/schemas/note.yaml"
    )
    assert yaml["note"]["properties"] """


def test_get_notes_yaml_schema():
    yaml = FolioClient.get_latest_from_github(
        "folio-org", "mod-notes", "src/main/resources/swagger.api/schemas/note.yaml"
    )
    assert yaml["note"]["properties"]


def test_get_json_schema():
    json = FolioClient.get_latest_from_github(
        "folio-org", "mod-user-import", "ramls/schemas/userdataimport.json"
    )
    assert json["properties"]


def test_get_latest_from_github_returns_none_when_failing():
    with pytest.raises(HTTPError):
        FolioClient.get_latest_from_github("branchedelac", "tati", "myfile.json")


def test_get_latest_from_github_returns_file_1():
    schema = FolioClient.get_latest_from_github(
        "folio-org",
        "mod-source-record-manager",
        "/mod-source-record-manager-server/src/main/resources/rules/marc_holdings_rules.json",
    )
    assert schema is not None
    assert schema.get("001", None) is not None


def test_get_latest_from_github_returns_file_orgs_has_no_releases():
    with pytest.raises(HTTPError):
        FolioClient.get_latest_from_github(
            "folio-org",
            "acq-models",
            "/mod-orgs/schemas/organization.json",
        )


@patch.object(FolioClient, '_initial_ecs_check')
def test_folio_client_initialization_with_valid_url(mock_ecs_check):
    with folio_auth_patcher():
        fc = FolioClient("https://example.com", "tenant", "user", "pass")
        assert fc.gateway_url == "https://example.com"
        assert fc.username == "user"


def test_folio_client_initialization_with_invalid_protocol():
    with pytest.raises(UnsupportedProtocol):
        FolioClient("ftp://example.com", "tenant", "user", "pass")


@patch.object(FolioClient, '_initial_ecs_check')
def test_tenant_id_property_getter(mock_ecs_check):
    with folio_auth_patcher() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_auth_instance.tenant_id = "original_tenant"
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "original_tenant", "user", "pass")
        assert fc.tenant_id == "original_tenant"


@patch.object(FolioClient, '_initial_ecs_check')
def test_tenant_id_property_basic_functionality(mock_ecs_check):
    """Test basic tenant_id property functionality without ECS restrictions"""
    with folio_auth_patcher() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_auth_instance.tenant_id = "test_tenant"
        mock_folio_auth.return_value = mock_auth_instance
    
        fc = FolioClient("https://example.com", "test_tenant", "user", "pass")
        
        # Test getter
        assert fc.tenant_id == "test_tenant"
        
        # Test setter (should update the folio_auth.tenant_id)
        fc.tenant_id = "new_tenant"
        # The setter should update the folio_auth.tenant_id, which should be reflected in the getter
        assert fc.folio_auth.tenant_id == "new_tenant"
        # Also verify getter works correctly
        assert fc.tenant_id == "new_tenant"


@patch.object(FolioClient, '_initial_ecs_check')
def test_okapi_headers_contain_required_fields(mock_ecs_check):
    with folio_auth_patcher() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_auth_instance.tenant_id = "test_tenant"
        mock_auth_instance.folio_auth_token = "mock_token"
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "test_tenant", "user", "pass")
        # The `okapi_headers` property is deprecated — capture the warning and
        # validate both the message and the returned headers content.
        with pytest.warns(DeprecationWarning) as record:
            headers = fc.okapi_headers
        # Ensure a single DeprecationWarning was raised with the expected text
        assert len(record) == 1
        assert "FolioClient.okapi_headers is deprecated. Use folio_headers instead." in str(record[0].message)

        assert "content-type" in headers
        assert headers["content-type"] == "application/json"
        assert "x-okapi-token" in headers


@patch.object(FolioClient, '_initial_ecs_check')
def test_folio_headers_contain_required_fields(mock_ecs_check):
    with folio_auth_patcher() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_auth_instance.tenant_id = "test_tenant"
        mock_auth_instance.folio_auth_token = "mock_token"
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "test_tenant", "user", "pass")
        headers = fc.folio_headers
        assert "content-type" in headers


@patch.object(FolioClient, '_initial_ecs_check')
def test_is_closed_property_initially_false(mock_ecs_check):
    with folio_auth_patcher() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "tenant", "user", "pass")
        assert fc.is_closed is False


@patch.object(FolioClient, '_initial_ecs_check')
def test_ssl_verify_default_true(mock_ecs_check):
    with folio_auth_patcher() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "tenant", "user", "pass")
        assert fc.ssl_verify is True


@patch.object(FolioClient, '_initial_ecs_check')
def test_ssl_verify_can_be_set_false(mock_ecs_check):
    with folio_auth_patcher() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance

        fc = FolioClient("https://example.com", "tenant", "user", "pass", ssl_verify=False)
        assert fc.ssl_verify is False


@patch.object(FolioClient, '_initial_ecs_check')
def test_gateway_url_property(mock_ecs_check):
    with folio_auth_patcher() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "tenant", "user", "pass")
        assert fc.gateway_url == "https://example.com"


@patch.object(FolioClient, '_initial_ecs_check')
def test_okapi_url_property_same_as_gateway_url(mock_ecs_check):
    with folio_auth_patcher() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "tenant", "user", "pass")
        # The `okapi_url` property is deprecated — capture the warning and
        # validate the message and returned value.
        with pytest.warns(DeprecationWarning) as record:
            assert fc.okapi_url == fc.gateway_url
        assert len(record) == 1
        assert "FolioClient.okapi_url is deprecated. Use gateway_url instead." in str(record[0].message)


@patch.object(FolioClient, '_initial_ecs_check')
def test_close_sets_is_closed_true(mock_ecs_check):
    with folio_auth_patcher() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "tenant", "user", "pass")
        
        # Mock the httpx client to avoid network calls
        mock_httpx_client = Mock()
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_httpx_client.post.return_value = mock_response
        mock_httpx_client.is_closed = False
        fc.httpx_client = mock_httpx_client
        
        fc.close()
        assert fc.is_closed is True


@patch.object(FolioClient, '_initial_ecs_check')
def test_logout_is_alias_for_close(mock_ecs_check):
    with folio_auth_patcher() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "tenant", "user", "pass")
        # Initialize without context manager to avoid automatic closure
        fc.is_closed = False
        
        # Mock httpx client and its post method to avoid network calls
        mock_httpx_client = Mock()
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_httpx_client.post.return_value = mock_response
        mock_httpx_client.is_closed = False
        fc.httpx_client = mock_httpx_client
        
        # Test that logout() calls close()
        with patch.object(fc, 'close', wraps=fc.close) as mock_close:
            fc.logout()
            mock_close.assert_called_once()


@patch.object(FolioClient, '_initial_ecs_check')
def test_operations_on_closed_client_raise_exception(mock_ecs_check):
    with folio_auth_patcher() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "tenant", "user", "pass")
        # Manually set the client as closed
        fc.is_closed = True
        
        # Now test that operations on closed client raise exception
        with pytest.raises(FolioClientClosed):
            _ = fc.folio_headers  # This should raise an exception


def test_context_manager_closes_client():
    with folio_auth_patcher() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        with patch.object(FolioClient, '_initial_ecs_check'):
            with FolioClient("https://example.com", "tenant", "user", "pass") as fc:
                # Mock the httpx client to avoid network calls
                mock_httpx_client = Mock()
                mock_httpx_client.is_closed = False
                fc.httpx_client = mock_httpx_client

                assert fc.is_closed is False
            # After exiting the context, it should be closed
            assert fc.is_closed is True


@pytest.mark.asyncio
async def test_async_context_manager_closes_client():
    with folio_auth_patcher() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        with patch.object(FolioClient, '_initial_ecs_check'):
            # Create an AsyncMock for the async httpx client
            async_mock_client = AsyncMock()
            async_mock_client.is_closed = False
            # Make post() return a plain mock response with a synchronous raise_for_status()
            mock_logout_response = Mock()
            mock_logout_response.raise_for_status.return_value = None
            async_mock_client.post.return_value = mock_logout_response
            
            with patch.object(FolioClient, 'get_folio_http_client_async', return_value=async_mock_client):
                async with FolioClient("https://example.com", "tenant", "user", "pass") as fc:
                    # Mock the httpx clients to avoid network calls
                    mock_httpx_client = Mock()
                    mock_httpx_client.is_closed = False
                    fc.httpx_client = mock_httpx_client

                    assert fc.is_closed is False
                # After exiting the async context, it should be closed
                assert fc.is_closed is True


@patch.object(FolioClient, '_initial_ecs_check')
def test_folio_headers_contain_basic_fields(mock_ecs_check):
    with folio_auth_patcher() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_auth_instance.tenant_id = "tenant"
        mock_auth_instance.folio_auth_token = "mock_token"
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "tenant", "user", "pass")
        headers = fc.folio_headers
        assert "content-type" in headers
        assert "x-okapi-token" in headers


@patch.object(FolioClient, '_initial_ecs_check')
def test_prepare_id_offset_query_handles_sortby_present(mock_ecs_check):
    with folio_auth_patcher() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "tenant", "user", "pass")
        query = fc.prepare_id_offset_query("cql.allRecords=1 sortBy id", fc.cql_all)
        assert "sortBy id" in query


@patch.object(FolioClient, '_initial_ecs_check')
def test_prepare_id_offset_query_handles_none(mock_ecs_check):
    with folio_auth_patcher() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "tenant", "user", "pass")
        query = fc.prepare_id_offset_query(None, fc.cql_all)
        assert query == "cql.allRecords=1 sortBy id"


@patch.object(FolioClient, '_initial_ecs_check')
def test_construct_query_parameters_builds_dict(mock_ecs_check):
    with folio_auth_patcher() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "tenant", "user", "pass")
        params = fc._construct_query_parameters(query="test", limit=50, extra="value")
        assert params["query"] == "test"
        assert params["limit"] == 50
        assert params["extra"] == "value"


@patch.object(FolioClient, '_initial_ecs_check')
def test_get_last_id_extracts_id_from_results(mock_ecs_check):
    with folio_auth_patcher() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "tenant", "user", "pass")
        results = [{"id": "123", "name": "test"}, {"id": "456", "name": "test2"}]
        last_id = fc.get_last_id(results)
        assert last_id == "456"


@patch.object(FolioClient, '_initial_ecs_check')
def test_get_last_id_returns_none_for_empty_results(mock_ecs_check):
    with folio_auth_patcher() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "tenant", "user", "pass")
        last_id = fc.get_last_id([])
        assert last_id is None


@patch.object(FolioClient, '_initial_ecs_check')
def test_get_folio_http_client_returns_client(mock_ecs_check):
    with folio_auth_patcher() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "tenant", "user", "pass")
        client = fc.get_folio_http_client()
        assert client is not None
        assert hasattr(client, "get")
        assert hasattr(client, "post")


@patch.object(FolioClient, '_initial_ecs_check')
def test_get_folio_http_client_async_returns_async_client(mock_ecs_check):
    with folio_auth_patcher() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "tenant", "user", "pass")
        async_client = fc.get_folio_http_client_async()
        assert async_client is not None
        assert hasattr(async_client, "get")
        assert hasattr(async_client, "post")


@patch.object(FolioClient, '_initial_ecs_check')
def test_folio_headers_update_handles_x_okapi_tenant(mock_ecs_check):
    """Ensure updating headers with x-okapi-tenant warns and updates tenant_id."""
    with folio_auth_patcher() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_auth_instance.tenant_id = "initial"
        mock_folio_auth.return_value = mock_auth_instance

        fc = FolioClient("https://example.com", "initial", "user", "pass")

        # Using mapping form
        with pytest.warns(DeprecationWarning):
            fc._folio_headers.update({"x-okapi-tenant": "new-tenant", "x-test": "v"})

        assert fc.tenant_id == "new-tenant"
        assert "x-okapi-tenant" not in fc._folio_headers
        assert fc._folio_headers.get("x-test") == "v"

        # Using kwargs form
        with pytest.warns(DeprecationWarning):
            fc._folio_headers.update(**{"x-okapi-tenant": "another-tenant"})

        assert fc.tenant_id == "another-tenant"


@patch.object(FolioClient, '_initial_ecs_check')
def test_logout_response_handler_branches(mock_ecs_check):
    """Exercise logout_response_handler exception handling for 404, other HTTP errors, and ConnectError."""
    with folio_auth_patcher() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_auth_instance.tenant_id = "t"
        mock_folio_auth.return_value = mock_auth_instance

        fc = FolioClient("https://example.com", "t", "user", "pass")

        # 404 HTTPStatusError path
        mock_resp_404 = Mock()
        mock_resp_404.status_code = 404
        err_404 = httpx.HTTPStatusError("404", request=Mock(), response=mock_resp_404)
        mock_resp_404.raise_for_status.side_effect = err_404
        # Should not raise
        fc._logout_response_handler(mock_resp_404)

        # 500 HTTPStatusError path
        mock_resp_500 = Mock()
        mock_resp_500.status_code = 500
        mock_resp_500.text = "oops"
        err_500 = httpx.HTTPStatusError("500", request=Mock(), response=mock_resp_500)
        mock_resp_500.raise_for_status.side_effect = err_500
        fc._logout_response_handler(mock_resp_500)

        # ConnectError path
        mock_conn = Mock()
        mock_conn.raise_for_status.side_effect = httpx.ConnectError("nope")
        fc._logout_response_handler(mock_conn)


@patch.object(FolioClient, '_initial_ecs_check')
def test_current_user_fallbacks_and_failure(mock_ecs_check):
    """Test current_user primary path, fallback to /users, and final failure returning empty string."""
    with folio_auth_patcher() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_auth_instance.tenant_id = "t"
        mock_folio_auth.return_value = mock_auth_instance

        fc = FolioClient("https://example.com", "t", "user", "pass")

        # Primary path: _folio_get returns dict with id
        def primary(path, *args, **kwargs):
            if path.startswith("/bl-users"):
                return {"id": "abcd"}
            raise RuntimeError("unexpected")

        fc._folio_get = primary
        # cached_property stores value; ensure fresh instance usage by deleting attribute if present
        if hasattr(fc, "current_user"):
            delattr(fc, "current_user")
        assert fc.current_user == "abcd"

        # Fallback path: first call raises HTTPStatusError, second returns list
        def fallback(path, *args, **kwargs):
            if path.startswith("/bl-users"):
                raise httpx.HTTPStatusError("no bl-users", request=Mock(), response=Mock())
            if path == "/users":
                return [{"id": "from-users"}]
            raise RuntimeError()

        fc2 = FolioClient("https://example.com", "t", "user", "pass")
        fc2._folio_get = fallback
        if hasattr(fc2, "current_user"):
            delattr(fc2, "current_user")
        assert fc2.current_user == "from-users"

        # Failure path: both attempts raise
        def failure(path, *args, **kwargs):
            raise Exception("fail")

        fc3 = FolioClient("https://example.com", "t", "user", "pass")
        fc3._folio_get = failure
        if hasattr(fc3, "current_user"):
            delattr(fc3, "current_user")
        assert fc3.current_user == ""


def test_construct_timeout_merge_with_defaults(monkeypatch):
    """Test that _construct_timeout merges provided dict with TIMEOUT_CONFIG defaults."""
    # Temporarily set TIMEOUT_CONFIG in the FolioClient module
    import importlib
    fc_module = importlib.import_module("folioclient.FolioClient")
    monkeypatch.setattr(fc_module, "TIMEOUT_CONFIG", {"read": 11.0})

    # Provide a dict that overrides connect only
    t = fc_module.FolioClient._construct_timeout({"connect": 2.0})
    assert isinstance(t, httpx.Timeout)
    # Provided value used, default read used
    assert t.connect == 2.0
    assert t.read == 11.0



def test_handle_delete_response_raises_httpx_exceptions():
    """Test that handle_delete_response raises httpx exceptions (not FOLIO exceptions)"""
    
    # Create a mock response that will raise an exception
    mock_response = Mock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500 Internal Server Error", request=Mock(), response=mock_response
    )
    
    # The static method should raise httpx exceptions, not FOLIO exceptions
    # The calling method (folio_delete) has the @folio_errors decorator
    with pytest.raises(httpx.HTTPStatusError):
        FolioClient.handle_delete_response(mock_response, "/test")


@patch('httpx.get')
def test_github_methods_raise_httpx_exceptions(mock_httpx_get):
    """Test that GitHub-related methods raise standard httpx exceptions"""
    
    # Mock httpx.get to raise an exception
    mock_response = Mock()
    mock_response.status_code = 404
    mock_response.text = "Not Found"
    mock_httpx_get.return_value.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404 Not Found", request=Mock(), response=mock_response
    )
    
    with pytest.raises(httpx.HTTPStatusError):
        FolioClient.get_latest_from_github("owner", "repo", "file.json")


def test_timeout_configuration():
    """Test various timeout configuration options"""
    
    # Test with float timeout
    with folio_auth_patcher():
        client = FolioClient(
            "https://test.example.com",
            "test_tenant",
            "test_user",
            "test_pass",
            timeout=60.0
        )

        timeout_obj = client.folio_parameters.timeout
        assert isinstance(timeout_obj, httpx.Timeout)
        assert timeout_obj.connect == 60.0
        assert timeout_obj.read == 60.0
        assert timeout_obj.write == 60.0
        assert timeout_obj.pool == 60.0


def test_timeout_configuration_dict():
    """Test timeout configuration with dictionary"""
    
    timeout_config = {
        "connect": 10.0,
        "read": 120.0,
        "write": 30.0,
        "pool": 5.0
    }
    
    with folio_auth_patcher():
        client = FolioClient(
            "https://test.example.com",
            "test_tenant",
            "test_user",
            "test_pass",
            timeout=timeout_config
        )
        
        timeout_obj = client.folio_parameters.timeout
        assert isinstance(timeout_obj, httpx.Timeout)
        assert timeout_obj.connect == 10.0
        assert timeout_obj.read == 120.0
        assert timeout_obj.write == 30.0
        assert timeout_obj.pool == 5.0


def test_timeout_configuration_httpx_object():
    """Test timeout configuration with httpx.Timeout object"""
    
    timeout_obj = httpx.Timeout(connect=15.0, read=45.0, write=25.0, pool=8.0)
    
    with folio_auth_patcher():
        client = FolioClient(
            "https://test.example.com",
            "test_tenant",
            "test_user",
            "test_pass",
            timeout=timeout_obj
        )
        
        client_timeout = client.folio_parameters.timeout
        assert client_timeout is timeout_obj
        assert client_timeout.connect == 15.0
        assert client_timeout.read == 45.0
        assert client_timeout.write == 25.0
        assert client_timeout.pool == 8.0


def test_timeout_configuration_none():
    """Test timeout configuration with None (should use global config)"""
    
    with folio_auth_patcher():
        client = FolioClient(
            "https://test.example.com",
            "test_tenant",
            "test_user",
            "test_pass",
            timeout=None
        )

        timeout_obj = client.folio_parameters.timeout
        # When no environment variables are set, should return Timeout(timeout=None)
        # This ensures httpx always gets a proper Timeout object with default behavior
        assert timeout_obj is not None
        assert timeout_obj.connect is None
        assert timeout_obj.read is None
        assert timeout_obj.write is None
        assert timeout_obj.pool is None


    @patch.object(FolioClient, '_initial_ecs_check')
    def test_validate_client_open_behavior(mock_ecs_check):
        """Validate that validate_client_open() raises when client is closed and is a no-op when open."""
        with folio_auth_patcher() as mock_folio_auth:
            mock_auth_instance = Mock()
            mock_folio_auth.return_value = mock_auth_instance

            fc = FolioClient("https://example.com", "tenant", "user", "pass")

            # Should be no-op when client is open
            fc.is_closed = False
            # Should not raise
            fc.validate_client_open()

            # When closed, should raise FolioClientClosed
            fc.is_closed = True
            with pytest.raises(FolioClientClosed):
                fc.validate_client_open()


def test_http_client_creation_with_timeout():
    """Test that HTTP clients are created with correct timeout configuration"""
    
    timeout_config = {
        "connect": 15.0,
        "read": 180.0,
        "write": 45.0,
        "pool": 12.0
    }
    
    with folio_auth_patcher():
        client = FolioClient(
            "https://test.example.com",
            "test_tenant",
            "test_user",
            "test_pass",
            timeout=timeout_config
        )
        
        # Test sync client creation
        sync_client = client.get_folio_http_client()
        assert isinstance(sync_client.timeout, httpx.Timeout)
        assert sync_client.timeout.connect == 15.0
        assert sync_client.timeout.read == 180.0
        assert sync_client.timeout.write == 45.0
        assert sync_client.timeout.pool == 12.0
        
        # Test async client creation
        async_client = client.get_folio_http_client_async()
        assert isinstance(async_client.timeout, httpx.Timeout)
        assert async_client.timeout.connect == 15.0
        assert async_client.timeout.read == 180.0
        assert async_client.timeout.write == 45.0
        assert async_client.timeout.pool == 12.0


def test_http_client_creation_with_no_timeout():
    """Test that HTTP clients are created with no timeout by default"""
    
    with folio_auth_patcher():
        client = FolioClient(
            "https://test.example.com",
            "test_tenant",
            "test_user",
            "test_pass"
            # No timeout parameter provided
        )
        
        # Test sync client creation
        sync_client = client.get_folio_http_client()
        # httpx creates a default Timeout object when None is passed
        assert isinstance(sync_client.timeout, httpx.Timeout)
        # All individual timeout values should be None (unlimited)
        assert sync_client.timeout.connect is None
        assert sync_client.timeout.read is None
        assert sync_client.timeout.write is None
        assert sync_client.timeout.pool is None
        
        # Test async client creation
        async_client = client.get_folio_http_client_async()
        assert isinstance(async_client.timeout, httpx.Timeout)
        assert async_client.timeout.connect is None
        assert async_client.timeout.read is None
        assert async_client.timeout.write is None
        assert async_client.timeout.pool is None


class TestPreparePayload:
    """Tests for the prepare_payload helper function."""

    def test_prepare_payload_with_dict(self):
        """Test that prepare_payload correctly encodes a dictionary to JSON bytes."""
        from folioclient.FolioClient import prepare_payload
        
        payload = {"key": "value", "number": 42}
        result = prepare_payload(payload)
        
        assert isinstance(result, bytes)
        # Verify the JSON is valid by decoding
        decoded = json.loads(result)
        assert decoded == payload

    def test_prepare_payload_with_string(self):
        """Test that prepare_payload correctly encodes a string to bytes."""
        from folioclient.FolioClient import prepare_payload
        
        payload = '{"key": "value"}'
        result = prepare_payload(payload)
        
        assert isinstance(result, bytes)
        assert result == payload.encode("utf-8")

    def test_prepare_payload_with_invalid_type(self):
        """Test that prepare_payload raises TypeError for invalid input types."""
        from folioclient.FolioClient import prepare_payload
        
        with pytest.raises(TypeError, match="Payload must be a dictionary or a string"):
            prepare_payload([1, 2, 3])
        
        with pytest.raises(TypeError, match="Payload must be a dictionary or a string"):
            prepare_payload(42)
        
        with pytest.raises(TypeError, match="Payload must be a dictionary or a string"):
            prepare_payload(None)

    def test_prepare_payload_uses_orjson_when_available(self):
        """Test that prepare_payload uses orjson when available for dicts."""
        from folioclient.FolioClient import prepare_payload, _HAS_ORJSON
        
        payload = {"key": "value", "nested": {"data": [1, 2, 3]}}
        result = prepare_payload(payload)
        
        # Result should always be valid JSON bytes
        assert isinstance(result, bytes)
        decoded = json.loads(result)
        assert decoded == payload
        
        # If orjson is available, verify the module can be imported
        if _HAS_ORJSON:
            import orjson
            # orjson.dumps returns bytes directly
            orjson_result = orjson.dumps(payload)
            assert isinstance(orjson_result, bytes)

    def test_prepare_payload_with_unicode_string(self):
        """Test that prepare_payload correctly handles unicode strings."""
        from folioclient.FolioClient import prepare_payload
        
        payload = '{"name": "Müller", "emoji": "🎉"}'
        result = prepare_payload(payload)
        
        assert isinstance(result, bytes)
        assert result == payload.encode("utf-8")

    def test_prepare_payload_with_unicode_dict(self):
        """Test that prepare_payload correctly handles dicts with unicode values."""
        from folioclient.FolioClient import prepare_payload
        
        payload = {"name": "Müller", "emoji": "🎉", "chinese": "你好"}
        result = prepare_payload(payload)
        
        assert isinstance(result, bytes)
        # Verify the JSON is valid and preserves unicode
        decoded = json.loads(result)
        assert decoded == payload
