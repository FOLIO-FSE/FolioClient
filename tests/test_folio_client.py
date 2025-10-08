import pytest
import sys
import atexit
from contextlib import contextmanager

# Version-specific setup for Python 3.10 compatibility
_PYTHON_3_10 = sys.version_info < (3, 11)

if _PYTHON_3_10:
    # For Python 3.10: Apply source-level patch before any imports
    from unittest.mock import Mock, patch
    
    # Import and immediately patch the source
    import folioclient._httpx
    _original_folio_auth = folioclient._httpx.FolioAuth
    _source_mock = Mock()
    folioclient._httpx.FolioAuth = _source_mock
    
    # Cleanup function
    def _restore_source():
        folioclient._httpx.FolioAuth = _original_folio_auth
    atexit.register(_restore_source)

# Now safe to import FolioClient 
from folioclient.FolioClient import FolioClient
from httpx import HTTPError, UnsupportedProtocol
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import httpx

# Import all FOLIO exceptions used in tests
from folioclient.exceptions import (
    FolioClientClosed,
)


def folio_auth_patch():
    """
    Returns appropriate FolioAuth patch for the current Python version.
    
    Handles version differences in unittest.mock.patch behavior:
    - Python 3.10: Uses pre-configured source mock + module globals patching
    - Python 3.11+: Uses standard imported name patching
    """
    if _PYTHON_3_10:
        @contextmanager
        def python310_auth_patch():
            # Reset source mock for clean test state
            _source_mock.reset_mock()
            
            # Configure mock to return a proper instance
            mock_instance = Mock()
            mock_instance.tenant_id = "test-tenant"
            _source_mock.return_value = mock_instance
            
            # Also patch the module-level reference for double coverage
            import sys
            fc_module = sys.modules['folioclient.FolioClient']
            original_ref = fc_module.__dict__.get('FolioAuth')
            fc_module.__dict__['FolioAuth'] = _source_mock
            
            try:
                yield _source_mock
            finally:
                # Restore module reference
                if original_ref is not None:
                    fc_module.__dict__['FolioAuth'] = original_ref
        
        return python310_auth_patch()
    else:
        # Python 3.11+: Standard import patching works correctly
        return patch('folioclient.FolioClient.FolioAuth')


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
    with folio_auth_patch() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_auth_instance.tenant_id = "tenant"
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "tenant", "user", "pass")
        assert fc.gateway_url == "https://example.com"
        assert fc.username == "user"
    mock_folio_auth.assert_called_once()


def test_folio_client_initialization_with_invalid_protocol():
    with pytest.raises(UnsupportedProtocol):
        FolioClient("ftp://example.com", "tenant", "user", "pass")


@patch.object(FolioClient, '_initial_ecs_check')
def test_tenant_id_property_getter(mock_ecs_check):
    with folio_auth_patch() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_auth_instance.tenant_id = "original_tenant"
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "original_tenant", "user", "pass")
        assert fc.tenant_id == "original_tenant"


@patch.object(FolioClient, '_initial_ecs_check')
def test_tenant_id_property_basic_functionality(mock_ecs_check):
    """Test basic tenant_id property functionality without ECS restrictions"""
    with folio_auth_patch() as mock_folio_auth:
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
    with folio_auth_patch() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_auth_instance.tenant_id = "test_tenant"
        mock_auth_instance.folio_auth_token = "mock_token"
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "test_tenant", "user", "pass")
        headers = fc.okapi_headers
        assert "content-type" in headers
        assert headers["content-type"] == "application/json"
        assert "x-okapi-token" in headers


@patch.object(FolioClient, '_initial_ecs_check')
def test_folio_headers_contain_required_fields(mock_ecs_check):
    with folio_auth_patch() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_auth_instance.tenant_id = "test_tenant"
        mock_auth_instance.folio_auth_token = "mock_token"
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "test_tenant", "user", "pass")
        headers = fc.folio_headers
        assert "content-type" in headers


@patch.object(FolioClient, '_initial_ecs_check')
def test_is_closed_property_initially_false(mock_ecs_check):
    with folio_auth_patch() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "tenant", "user", "pass")
        assert fc.is_closed is False


@patch.object(FolioClient, '_initial_ecs_check')
def test_ssl_verify_default_true(mock_ecs_check):
    with folio_auth_patch() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "tenant", "user", "pass")
        assert fc.ssl_verify is True


@patch.object(FolioClient, '_initial_ecs_check')
def test_ssl_verify_can_be_set_false(mock_ecs_check):
    with folio_auth_patch() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "tenant", "user", "pass", ssl_verify=False)
        assert fc.ssl_verify is False


@patch.object(FolioClient, '_initial_ecs_check')
def test_gateway_url_property(mock_ecs_check):
    with folio_auth_patch() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "tenant", "user", "pass")
        assert fc.gateway_url == "https://example.com"


@patch.object(FolioClient, '_initial_ecs_check')
def test_okapi_url_property_same_as_gateway_url(mock_ecs_check):
    with folio_auth_patch() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "tenant", "user", "pass")
        assert fc.okapi_url == fc.gateway_url


@patch.object(FolioClient, '_initial_ecs_check')
def test_close_sets_is_closed_true(mock_ecs_check):
    with folio_auth_patch() as mock_folio_auth:
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
    with folio_auth_patch() as mock_folio_auth:
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
    with folio_auth_patch() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "tenant", "user", "pass")
        # Manually set the client as closed
        fc.is_closed = True
        
        # Now test that operations on closed client raise exception
        with pytest.raises(FolioClientClosed):
            _ = fc.folio_headers  # This should raise an exception


def test_context_manager_closes_client():
    with folio_auth_patch() as mock_folio_auth:
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
    with folio_auth_patch() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        with patch.object(FolioClient, '_initial_ecs_check'):
            # Create an AsyncMock for the async httpx client
            async_mock_client = AsyncMock()
            async_mock_client.is_closed = False
            
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
    with folio_auth_patch() as mock_folio_auth:
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
    with folio_auth_patch() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "tenant", "user", "pass")
        query = fc.prepare_id_offset_query("cql.allRecords=1 sortBy id", fc.cql_all)
        assert "sortBy id" in query


@patch.object(FolioClient, '_initial_ecs_check')
def test_prepare_id_offset_query_handles_none(mock_ecs_check):
    with folio_auth_patch() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "tenant", "user", "pass")
        query = fc.prepare_id_offset_query(None, fc.cql_all)
        assert query == "cql.allRecords=1 sortBy id"


@patch.object(FolioClient, '_initial_ecs_check')
def test_construct_query_parameters_builds_dict(mock_ecs_check):
    with folio_auth_patch() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "tenant", "user", "pass")
        params = fc._construct_query_parameters(query="test", limit=50, extra="value")
        assert params["query"] == "test"
        assert params["limit"] == 50
        assert params["extra"] == "value"


@patch.object(FolioClient, '_initial_ecs_check')
def test_get_last_id_extracts_id_from_results(mock_ecs_check):
    with folio_auth_patch() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "tenant", "user", "pass")
        results = [{"id": "123", "name": "test"}, {"id": "456", "name": "test2"}]
        last_id = fc.get_last_id(results)
        assert last_id == "456"


@patch.object(FolioClient, '_initial_ecs_check')
def test_get_last_id_returns_none_for_empty_results(mock_ecs_check):
    with folio_auth_patch() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "tenant", "user", "pass")
        last_id = fc.get_last_id([])
        assert last_id is None


@patch.object(FolioClient, '_initial_ecs_check')
def test_get_folio_http_client_returns_client(mock_ecs_check):
    with folio_auth_patch() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "tenant", "user", "pass")
        client = fc.get_folio_http_client()
        assert client is not None
        assert hasattr(client, "get")
        assert hasattr(client, "post")


@patch.object(FolioClient, '_initial_ecs_check')
def test_get_folio_http_client_async_returns_async_client(mock_ecs_check):
    with folio_auth_patch() as mock_folio_auth:
        mock_auth_instance = Mock()
        mock_folio_auth.return_value = mock_auth_instance
        
        fc = FolioClient("https://example.com", "tenant", "user", "pass")
        async_client = fc.get_folio_http_client_async()
        assert async_client is not None
        assert hasattr(async_client, "get")
        assert hasattr(async_client, "post")


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
