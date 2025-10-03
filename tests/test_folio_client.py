import pytest
from folioclient.FolioClient import FolioClient
from httpx import HTTPError, UnsupportedProtocol
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from folioclient.exceptions import FolioClientClosed


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


@patch('folioclient.FolioClient.FolioClient._initial_ecs_check')
@patch('folioclient.FolioClient.FolioAuth')
def test_folio_client_initialization_with_valid_url(mock_folio_auth, mock_ecs_check):
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


@patch('folioclient.FolioClient.FolioClient._initial_ecs_check')
@patch('folioclient.FolioClient.FolioAuth')
def test_tenant_id_property_getter(mock_folio_auth, mock_ecs_check):
    mock_auth_instance = Mock()
    mock_auth_instance.tenant_id = "original_tenant"
    mock_folio_auth.return_value = mock_auth_instance
    
    fc = FolioClient("https://example.com", "original_tenant", "user", "pass")
    assert fc.tenant_id == "original_tenant"


@patch('folioclient.FolioClient.FolioClient._initial_ecs_check')
@patch('folioclient.FolioClient.FolioAuth')
def test_tenant_id_property_basic_functionality(mock_folio_auth, mock_ecs_check):
    """Test basic tenant_id property functionality without ECS restrictions"""
    mock_auth_instance = Mock()
    mock_auth_instance.tenant_id = "original_tenant"
    mock_folio_auth.return_value = mock_auth_instance
    
    fc = FolioClient("https://example.com", "original_tenant", "user", "pass")
    assert fc.tenant_id == "original_tenant"


@patch('folioclient.FolioClient.FolioClient._initial_ecs_check')
@patch('folioclient.FolioClient.FolioAuth')
def test_tenant_id_property_getter(mock_folio_auth, mock_ecs_check):
    """Test tenant_id property getter delegates to folio_auth"""
    mock_auth_instance = Mock()
    mock_auth_instance.tenant_id = "test_tenant"
    mock_folio_auth.return_value = mock_auth_instance
    
    fc = FolioClient("https://example.com", "test_tenant", "user", "pass")
    assert fc.tenant_id == "test_tenant"


@patch('folioclient.FolioClient.FolioClient._initial_ecs_check')
@patch('folioclient.FolioClient.FolioAuth')
def test_okapi_headers_contain_required_fields(mock_folio_auth, mock_ecs_check):
    mock_auth_instance = Mock()
    mock_auth_instance.tenant_id = "test_tenant"
    mock_auth_instance.folio_auth_token = "mock_token"
    mock_folio_auth.return_value = mock_auth_instance
    
    fc = FolioClient("https://example.com", "test_tenant", "user", "pass")
    headers = fc.okapi_headers
    assert "content-type" in headers
    assert headers["content-type"] == "application/json"
    assert "x-okapi-token" in headers


@patch('folioclient.FolioClient.FolioClient._initial_ecs_check')
@patch('folioclient.FolioClient.FolioAuth')
def test_folio_headers_contain_required_fields(mock_folio_auth, mock_ecs_check):
    mock_auth_instance = Mock()
    mock_auth_instance.tenant_id = "test_tenant"
    mock_auth_instance.folio_auth_token = "mock_token"
    mock_folio_auth.return_value = mock_auth_instance
    
    fc = FolioClient("https://example.com", "test_tenant", "user", "pass")
    headers = fc.folio_headers
    assert "content-type" in headers


@patch('folioclient.FolioClient.FolioClient._initial_ecs_check')
@patch('folioclient.FolioClient.FolioAuth')
def test_is_closed_property_initially_false(mock_folio_auth, mock_ecs_check):
    mock_auth_instance = Mock()
    mock_folio_auth.return_value = mock_auth_instance
    
    fc = FolioClient("https://example.com", "tenant", "user", "pass")
    assert fc.is_closed is False


@patch('folioclient.FolioClient.FolioClient._initial_ecs_check')
@patch('folioclient.FolioClient.FolioAuth')
def test_ssl_verify_default_true(mock_folio_auth, mock_ecs_check):
    mock_auth_instance = Mock()
    mock_folio_auth.return_value = mock_auth_instance
    
    fc = FolioClient("https://example.com", "tenant", "user", "pass")
    assert fc.ssl_verify is True


@patch('folioclient.FolioClient.FolioClient._initial_ecs_check')
@patch('folioclient.FolioClient.FolioAuth')
def test_ssl_verify_can_be_set_false(mock_folio_auth, mock_ecs_check):
    mock_auth_instance = Mock()
    mock_folio_auth.return_value = mock_auth_instance
    
    fc = FolioClient("https://example.com", "tenant", "user", "pass", ssl_verify=False)
    assert fc.ssl_verify is False


@patch('folioclient.FolioClient.FolioClient._initial_ecs_check')
@patch('folioclient.FolioClient.FolioAuth')
def test_gateway_url_property(mock_folio_auth, mock_ecs_check):
    mock_auth_instance = Mock()
    mock_folio_auth.return_value = mock_auth_instance
    
    fc = FolioClient("https://example.com", "tenant", "user", "pass")
    assert fc.gateway_url == "https://example.com"


@patch('folioclient.FolioClient.FolioClient._initial_ecs_check')
@patch('folioclient.FolioClient.FolioAuth')
def test_okapi_url_property_same_as_gateway_url(mock_folio_auth, mock_ecs_check):
    mock_auth_instance = Mock()
    mock_folio_auth.return_value = mock_auth_instance
    
    fc = FolioClient("https://example.com", "tenant", "user", "pass")
    assert fc.okapi_url == fc.gateway_url


@patch('folioclient.FolioClient.FolioClient._initial_ecs_check')
@patch('folioclient.FolioClient.FolioAuth')
def test_close_sets_is_closed_true(mock_folio_auth, mock_ecs_check):
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
    
    # Test that close sets is_closed to True
    fc.close()
    assert fc.is_closed is True


@patch('folioclient.FolioClient.FolioClient._initial_ecs_check')
@patch('folioclient.FolioClient.FolioAuth')
def test_logout_is_alias_for_close(mock_folio_auth, mock_ecs_check):
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


@patch('folioclient.FolioClient.FolioClient._initial_ecs_check')
@patch('folioclient.FolioClient.FolioAuth')
def test_operations_on_closed_client_raise_exception(mock_folio_auth, mock_ecs_check):
    mock_auth_instance = Mock()
    mock_folio_auth.return_value = mock_auth_instance
    
    fc = FolioClient("https://example.com", "tenant", "user", "pass")
    # Manually set the client as closed
    fc.is_closed = True
    
    # Now test that operations on closed client raise exception
    with pytest.raises(FolioClientClosed):
        _ = fc.folio_headers  # This should raise an exception


@patch('folioclient.FolioClient.FolioAuth')
def test_context_manager_closes_client(mock_folio_auth):
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
@patch('folioclient.FolioClient.FolioAuth')
async def test_async_context_manager_closes_client(mock_folio_auth):
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


@patch('folioclient.FolioClient.FolioClient._initial_ecs_check')
@patch('folioclient.FolioClient.FolioAuth')
def test_folio_headers_contain_basic_fields(mock_folio_auth, mock_ecs_check):
    mock_auth_instance = Mock()
    mock_auth_instance.tenant_id = "tenant"
    mock_auth_instance.folio_auth_token = "mock_token"
    mock_folio_auth.return_value = mock_auth_instance
    
    fc = FolioClient("https://example.com", "tenant", "user", "pass")
    headers = fc.folio_headers
    assert "content-type" in headers
    assert "x-okapi-token" in headers


@patch('folioclient.FolioClient.FolioClient._initial_ecs_check')
@patch('folioclient.FolioClient.FolioAuth')
def test_prepare_id_offset_query_handles_sortby_present(mock_folio_auth, mock_ecs_check):
    mock_auth_instance = Mock()
    mock_folio_auth.return_value = mock_auth_instance
    
    fc = FolioClient("https://example.com", "tenant", "user", "pass")
    query = fc._prepare_id_offset_query("cql.allRecords=1 sortBy id")
    assert "sortBy id" in query


@patch('folioclient.FolioClient.FolioClient._initial_ecs_check')
@patch('folioclient.FolioClient.FolioAuth')
def test_prepare_id_offset_query_handles_none(mock_folio_auth, mock_ecs_check):
    mock_auth_instance = Mock()
    mock_folio_auth.return_value = mock_auth_instance
    
    fc = FolioClient("https://example.com", "tenant", "user", "pass")
    query = fc._prepare_id_offset_query(None)
    assert query == "cql.allRecords=1 sortBy id"


@patch('folioclient.FolioClient.FolioClient._initial_ecs_check')
@patch('folioclient.FolioClient.FolioAuth')
def test_construct_query_parameters_builds_dict(mock_folio_auth, mock_ecs_check):
    mock_auth_instance = Mock()
    mock_folio_auth.return_value = mock_auth_instance
    
    fc = FolioClient("https://example.com", "tenant", "user", "pass")
    params = fc._construct_query_parameters(query="test", limit=50, extra="value")
    assert params["query"] == "test"
    assert params["limit"] == 50
    assert params["extra"] == "value"


@patch('folioclient.FolioClient.FolioClient._initial_ecs_check')
@patch('folioclient.FolioClient.FolioAuth')
def test_get_last_id_extracts_id_from_results(mock_folio_auth, mock_ecs_check):
    mock_auth_instance = Mock()
    mock_folio_auth.return_value = mock_auth_instance
    
    fc = FolioClient("https://example.com", "tenant", "user", "pass")
    results = [{"id": "123", "name": "test"}, {"id": "456", "name": "test2"}]
    last_id = fc._get_last_id(results)
    assert last_id == "456"


@patch('folioclient.FolioClient.FolioClient._initial_ecs_check')
@patch('folioclient.FolioClient.FolioAuth')
def test_get_last_id_returns_none_for_empty_results(mock_folio_auth, mock_ecs_check):
    mock_auth_instance = Mock()
    mock_folio_auth.return_value = mock_auth_instance
    
    fc = FolioClient("https://example.com", "tenant", "user", "pass")
    last_id = fc._get_last_id([])
    assert last_id is None


@patch('folioclient.FolioClient.FolioClient._initial_ecs_check')
@patch('folioclient.FolioClient.FolioAuth')
def test_get_folio_http_client_returns_client(mock_folio_auth, mock_ecs_check):
    mock_auth_instance = Mock()
    mock_folio_auth.return_value = mock_auth_instance
    
    fc = FolioClient("https://example.com", "tenant", "user", "pass")
    client = fc.get_folio_http_client()
    assert client is not None
    assert hasattr(client, "get")
    assert hasattr(client, "post")


@patch('folioclient.FolioClient.FolioClient._initial_ecs_check')
@patch('folioclient.FolioClient.FolioAuth')
def test_get_folio_http_client_async_returns_async_client(mock_folio_auth, mock_ecs_check):
    mock_auth_instance = Mock()
    mock_folio_auth.return_value = mock_auth_instance
    
    fc = FolioClient("https://example.com", "tenant", "user", "pass")
    async_client = fc.get_folio_http_client_async()
    assert async_client is not None
    assert hasattr(async_client, "get")
    assert hasattr(async_client, "post")
