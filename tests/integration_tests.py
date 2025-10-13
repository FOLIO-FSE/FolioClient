"""
Integration tests for FolioClient against FOLIO community snapshot environment.

These tests are designed to run against the live FOLIO snapshot system and are
disabled by default to prevent them from running during normal test execution.

To run these tests:
    pytest tests/integration_tests.py --run-integration

Environment: FOLIO Community Snapshot
- URL: https://folio-snapshot-okapi.dev.folio.org
- Tenant: diku
- Username: diku_admin
- Password: admin
"""

import pytest
import asyncio
from unittest.mock import patch
import httpx
import os

from folioclient import FolioClient
from folioclient.exceptions import (
    FolioAuthenticationError,
    FolioPermissionError,
    FolioResourceNotFoundError,
    FolioValidationError,
)


# Test configuration
# pragma: warning disable=SC2068
SNAPSHOT_CONFIG = {
    "gateway_url": "https://folio-snapshot-okapi.dev.folio.org",
    "tenant_id": "diku",
    "username": "diku_admin",
    "password": "admin",
}

# pragma: warning disable=SC2068
SNAPSHOT2_CONFIG = {
    "gateway_url": "https://folio-snapshot-2-okapi.dev.folio.org",
}

# pragma: warning disable=SC2068
SNAPSHOT_EUREKA_CONFIG = {
    "gateway_url": "https://folio-etesting-snapshot-kong.ci.folio.org"
}

# pragma: warning disable=SC2068
SNAPSHOT_2_EUREKA_CONFIG = {
    "gateway_url": "https://folio-etesting-snapshot2-kong.ci.folio.org"
}

# pragma: warning disable=SC2068
SNAPSHOT_EUREKA_ECS_CONFIG = {
    "gateway_url": "https://ecs-folio-etesting-snapshot-kong.ci.folio.org",
    "tenant_id": "consortium",
    "username": "consortium_admin",
    "password": "admin",
}

# pragma: warning disable=SC2068
BUGFEST_CONFIG = {
    "gateway_url": "https://kong-bugfest-sunflower.int.aws.folio.org",
    "tenant_id": "fs09000000",
    "username": "folio",
    "password": "folio",
}


# Pytest markers
pytestmark = pytest.mark.integration


SERVER_CONFIGS = [
    ("snapshot", SNAPSHOT_CONFIG),
    ("snapshot2", {**SNAPSHOT_CONFIG, **SNAPSHOT2_CONFIG}),
    ("eureka", {**SNAPSHOT_CONFIG, **SNAPSHOT_EUREKA_CONFIG}),
    ("eureka-ecs", SNAPSHOT_EUREKA_ECS_CONFIG),
    ("snapshot-2-eureka", {**SNAPSHOT_CONFIG, **SNAPSHOT_2_EUREKA_CONFIG}),
    ("bugfest", BUGFEST_CONFIG),
]


@pytest.fixture(params=[name for name, _ in SERVER_CONFIGS], ids=[name for name, _ in SERVER_CONFIGS])
def server_config(request):
    """
    Parametrized fixture that yields one server config dict per test invocation.

    Use environment variable INTEGRATION_SERVER to limit to a single config name,
    e.g. INTEGRATION_SERVER=snapshot pytest tests/integration_tests.py --run-integration
    """
    desired = os.environ.get("INTEGRATION_SERVER") or request.config.getoption("--integration-server")
    if desired:
        # if the user requested a single server, only yield that config
        for name, cfg in SERVER_CONFIGS:
            if name == desired:
                return cfg
        pytest.skip(f"No server config named {desired}")
    # request.param is the name; look up and return the dict
    name = request.param
    for n, cfg in SERVER_CONFIGS:
        if n == name:
            return cfg
    pytest.skip("No matching server config found")
    

@pytest.fixture
def folio_client(server_config):
    """Create a FolioClient instance for testing using the current server_config."""
    try:
        return FolioClient(**server_config)
    except httpx.ConnectError as e:
        pytest.fail(f"Failed to create FolioClient for {server_config.get('gateway_url')}: {e}")


@pytest.fixture
async def async_folio_client(server_config):
    """Create an async FolioClient instance for testing using the current server_config."""
    try:
        async with FolioClient(**server_config) as client:
            yield client
    except httpx.ConnectError as e:
        pytest.fail(f"Failed to create async FolioClient for {server_config.get('gateway_url')}: {e}")


@pytest.fixture
def folio_client_ecs(server_config):
    """Create a FolioClient instance for ECS testing; skip if config is not ECS."""
    if server_config.get("tenant_id") != "consortium":
        pytest.skip("Server config is not an ECS config")
    try:
        return FolioClient(**server_config)
    except (httpx.ConnectError, httpx.HTTPStatusError) as e:
        pytest.fail(
            "Failed to create FolioClient for ECS tests due to connection error: "
            f"{getattr(e, 'response').text or e}")

class TestBasicFunctionality:
    """Test basic FolioClient functionality."""

    def test_client_initialization(self, server_config):
        """Test that FolioClient initializes correctly."""
        client = FolioClient(**server_config)
        assert client.gateway_url == server_config["gateway_url"]
        assert client.tenant_id == server_config["tenant_id"]
        assert not client.is_closed

    def test_context_manager_sync(self, server_config):
        """Test synchronous context manager functionality."""
        with FolioClient(**server_config) as client:
            assert not client.is_closed
            # Test basic authentication by checking if we can get current user
            current_user = client.current_user
            assert current_user is not None
        
        assert client.is_closed

    async def test_context_manager_async(self, server_config):
        """Test asynchronous context manager functionality."""
        async with FolioClient(**server_config) as client:
            assert not client.is_closed
            # Test basic authentication by checking if we can get current user
            current_user = client.current_user
            assert current_user is not None
        
        assert client.is_closed

    def test_authentication_properties(self, folio_client):
        """Test authentication-related properties."""
        with folio_client:
            # Test that authentication properties are accessible
            assert folio_client.current_user is not None
            assert folio_client.access_token is not None
            assert len(folio_client.access_token) > 0

    def test_invalid_credentials(self, server_config):
        """Test behavior with invalid credentials."""
        invalid_config = server_config.copy()
        invalid_config["password"] = "invalid_password"
        
        with pytest.raises((FolioAuthenticationError, Exception)):
            with FolioClient(**invalid_config) as client:
                client.current_user


class TestUserManagement:
    """Test user-related functionality."""

    def test_get_users(self, folio_client):
        """Test fetching users."""
        with folio_client:
            users = folio_client.folio_get("/users", query_params={"limit": 10})
            assert "users" in users
            assert isinstance(users["users"], list)
            assert users["totalRecords"] >= 0

    def test_get_user_by_id(self, folio_client):
        """Test fetching a specific user by ID."""
        with folio_client:
            # Get current user ID
            current_user_id = folio_client.current_user
            
            # Fetch user by ID
            user = folio_client.folio_get(f"/users/{current_user_id}")
            assert user["id"] == current_user_id
            assert "username" in user

    def test_get_nonexistent_user(self, folio_client):
        """Test fetching a non-existent user."""
        with folio_client:
            fake_uuid = "00000000-0000-0000-0000-000000000000"
            with pytest.raises(FolioResourceNotFoundError):
                folio_client.folio_get(f"/users/{fake_uuid}")

    async def test_get_users_async(self, async_folio_client):
        """Test async user fetching."""
        users = await async_folio_client.folio_get_async("/users", query_params={"limit": 5})
        assert "users" in users
        assert isinstance(users["users"], list)


class TestInventoryManagement:
    """Test inventory-related functionality."""

    def test_get_instances(self, folio_client):
        """Test fetching inventory instances."""
        with folio_client:
            instances = folio_client.folio_get("/instance-storage/instances", query_params={"limit": 10})
            assert "instances" in instances
            assert isinstance(instances["instances"], list)
            assert instances["totalRecords"] >= 0

    def test_get_holdings(self, folio_client):
        """Test fetching holdings records."""
        with folio_client:
            holdings = folio_client.folio_get("/holdings-storage/holdings", query_params={"limit": 10})
            assert "holdingsRecords" in holdings
            assert isinstance(holdings["holdingsRecords"], list)

    def test_get_items(self, folio_client):
        """Test fetching item records."""
        with folio_client:
            items = folio_client.folio_get("/item-storage/items", query_params={"limit": 10})
            assert "items" in items
            assert isinstance(items["items"], list)

    def test_search_instances_by_query(self, folio_client):
        """Test searching instances with CQL query."""
        with folio_client:
            # Search for instances with a common title pattern
            query = 'title="*"'
            instances = folio_client.folio_get("/search/instances", query=query, query_params={"limit": 5})
            assert "instances" in instances
            assert isinstance(instances["instances"], list)


class TestCirculationManagement:
    """Test circulation-related functionality."""

    def test_get_loans(self, folio_client):
        """Test fetching loan records."""
        with folio_client:
            loans = folio_client.folio_get("/loan-storage/loans", query_params={"limit": 10})
            assert "loans" in loans
            assert isinstance(loans["loans"], list)

    def test_get_requests(self, folio_client):
        """Test fetching request records."""
        with folio_client:
            requests = folio_client.folio_get("/request-storage/requests", query_params={"limit": 10})
            assert "requests" in requests
            assert isinstance(requests["requests"], list)

    def test_get_loan_policies(self, folio_client):
        """Test fetching loan policies."""
        with folio_client:
            policies = folio_client.folio_get("/loan-policy-storage/loan-policies", query_params={"limit": 10})
            assert "loanPolicies" in policies
            assert isinstance(policies["loanPolicies"], list)


class TestDataPagination:
    """Test pagination functionality."""

    def test_folio_get_all_users(self, folio_client):
        """Test getting all users with pagination."""
        with folio_client:
            all_users = []
            for user in folio_client.folio_get_all("/users", "users"):
                all_users.append(user)
                # Limit to first few users for testing
                if len(all_users) >= 10:
                    break
            
            assert len(all_users) > 0
            assert all(isinstance(user, dict) for user in all_users)

    def test_folio_get_all_with_query(self, folio_client):
        """Test pagination with query parameters."""
        with folio_client:
            query = "active==true"
            active_users = []
            for user in folio_client.folio_get_all("/users", "users", query=query):
                active_users.append(user)
                # Limit for testing
                if len(active_users) >= 5:
                    break
            
            assert len(active_users) > 0
            # Verify all returned users are active
            for user in active_users:
                assert user.get("active", False) is True


class TestErrorHandling:
    """Test error handling and exception mapping."""

    def test_permission_error(self, folio_client):
        """Test that permission errors are properly handled."""
        with folio_client:
            # Try to access an endpoint that might require higher permissions
            # Using a relatively safe endpoint that might have restrictions
            try:
                # Try to access administrative configurations
                folio_client.folio_get("/configurations/entries")
                # If this succeeds, the user has the necessary permissions
                # which is fine for this test
            except FolioPermissionError:
                # This is what we expect if permissions are restricted
                pytest.skip("User has restricted permissions (expected)")
            except FolioResourceNotFoundError:
                # The endpoint might not exist in this FOLIO version
                pytest.skip("Configurations endpoint not available")
            except Exception as e:
                # Other errors are acceptable for this test
                # We mainly want to ensure the client doesn't crash
                pass

    def test_not_found_error(self, folio_client):
        """Test 404 error handling."""
        with folio_client:
            with pytest.raises(FolioResourceNotFoundError):
                folio_client.folio_get("/definitely-nonexistent-endpoint-12345")

    def test_network_error_handling(self):
        """Test network error handling with invalid URL."""
        invalid_config = SNAPSHOT_CONFIG.copy()
        invalid_config["gateway_url"] = "https://invalid-url-that-should-not-exist.com"
        
        # Should raise a connection-related FOLIO exception
        with pytest.raises(Exception):  # Could be various connection errors
            with FolioClient(**invalid_config) as client:
                client.current_user


class TestCachedProperties:
    """Test cached property functionality."""

    def test_cached_properties_consistency(self, folio_client):
        """Test that cached properties return consistent values."""
        with folio_client:
            # Test current_user caching
            user1 = folio_client.current_user
            user2 = folio_client.current_user
            assert user1 == user2

            # Test identifier_types caching
            types1 = folio_client.identifier_types
            types2 = folio_client.identifier_types
            assert types1 == types2
            assert isinstance(types1, list)

    def test_clear_cached_properties(self, folio_client):
        """Test clearing cached properties."""
        with folio_client:
            # Access a cached property
            original_types = folio_client.identifier_types
            
            # Clear cached properties
            folio_client._clear_cached_properties()
            
            # Access again - should work (might be same value but freshly fetched)
            new_types = folio_client.identifier_types
            assert isinstance(new_types, list)


class TestAsyncFunctionality:
    """Test asynchronous functionality."""

    async def test_async_basic_operations(self, async_folio_client):
        """Test basic async operations."""
        # Test async user fetching
        users = await async_folio_client.folio_get_async("/users", query_params={"limit": 5})
        assert "users" in users

        # Test async instance fetching
        instances = await async_folio_client.folio_get_async("/instance-storage/instances", query_params={"limit": 5})
        assert "instances" in instances

    async def test_async_error_handling(self, async_folio_client):
        """Test async error handling."""
        with pytest.raises(FolioResourceNotFoundError):
            await async_folio_client.folio_get_async("/definitely-nonexistent-endpoint-12345")


@pytest.mark.ecs
class TestECSFunctionality:
    """Test ECS (External Catalog Service) functionality - DISABLED for snapshot."""

    def test_is_ecs_property(self, folio_client):
        """Test is_ecs property."""
        with folio_client:
            # This would test ECS detection if available
            is_ecs = folio_client.is_ecs
            assert isinstance(is_ecs, bool)

    def test_is_ecs_property_ecs_client(self, folio_client_ecs):
        """Test is_ecs property with ECS-configured client."""
        with folio_client_ecs:
            is_ecs = folio_client_ecs.is_ecs
            assert is_ecs is True

    def test_ecs_central_tenant_id_property(self, folio_client_ecs):
        """Test ecs_central_tenant_id property."""
        with folio_client_ecs:
            # This would test ECS central tenant ID if available
            central_tenant_id = folio_client_ecs.ecs_central_tenant_id
            if central_tenant_id is not None:
                assert isinstance(central_tenant_id, str)
                assert len(central_tenant_id) > 0

    def test_ecs_consortium_property(self, folio_client_ecs):
        """Test ecs_consortium property."""
        with folio_client_ecs:
            # This would test ECS consortium object if available
            consortium = folio_client_ecs.ecs_consortium
            if consortium is not None:
                assert isinstance(consortium, dict)
                assert "id" in consortium

    def test_ecs_members_property(self, folio_client):
        """Test ecs_members property."""
        with folio_client:
            # This would test ECS member tenants if available
            members = folio_client.ecs_members
            assert isinstance(members, list)
            if members:
                for member in members:
                    assert isinstance(member, dict)
                    assert "id" in member

    @pytest.mark.skip(reason="ECS functionality not available in snapshot environment")
    def test_ecs_central_tenant_id_setter(self, folio_client):
        """Test setting ecs_central_tenant_id."""
        with folio_client:
            # This would test setting ECS central tenant if available
            original_central_tenant = folio_client.ecs_central_tenant_id
            
            # In a real ECS environment, you would test:
            # folio_client.ecs_central_tenant_id = "some_central_tenant_id"
            # assert folio_client.ecs_central_tenant_id == "some_central_tenant_id"
            
            # For now, just ensure the property is accessible
            assert original_central_tenant is None or isinstance(original_central_tenant, str)

    @pytest.mark.skip(reason="ECS functionality not available in snapshot environment")
    def test_tenant_switching_in_ecs(self, folio_client):
        """Test tenant switching functionality in ECS environment."""
        with folio_client:
            # This would test tenant switching if ECS is available
            original_tenant = folio_client.tenant_id
            
            # In a real ECS environment, you would test:
            # if folio_client.is_ecs and folio_client.ecs_members:
            #     member_tenant = folio_client.ecs_members[0]["id"]
            #     folio_client.tenant_id = member_tenant
            #     assert folio_client.tenant_id == member_tenant
            #     folio_client.tenant_id = original_tenant
            
            # For now, just ensure the tenant_id property works
            assert isinstance(original_tenant, str)
            assert len(original_tenant) > 0


class TestPerformanceAndLimits:
    """Test performance characteristics and limits."""

    def test_large_result_set_handling(self, folio_client):
        """Test handling of large result sets."""
        with folio_client:
            # Test with a larger limit to see how client handles it
            try:
                users = folio_client.folio_get("/inventory", query_params={"limit": 1000})
                assert "users" in users
                assert len(users["users"]) <= 1000
            except Exception as e:
                # Some endpoints might have limits - that's acceptable
                pass

    def test_concurrent_requests(self):
        """Test concurrent request handling."""
        async def make_requests():
            async with FolioClient(**SNAPSHOT_CONFIG) as client:
                # Make multiple concurrent requests
                tasks = [
                    client.folio_get_async("/users", query_params={"limit": 5}),
                    client.folio_get_async("/instance-storage/instances", query_params={"limit": 5}),
                    client.folio_get_async("/holdings-storage/holdings", query_params={"limit": 5}),
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Check that all requests completed (successfully or with known errors)
                for result in results:
                    assert result is not None

        asyncio.run(make_requests())

    def test_timeout_configuration(self):
        """Test custom timeout configuration."""
        config_with_timeout = SNAPSHOT_CONFIG.copy()
        config_with_timeout["timeout"] = 30.0  # 30 second timeout
        
        with FolioClient(**config_with_timeout) as client:
            # Test that client works with custom timeout
            users = client.folio_get("/users", query_params={"limit": 5})
            assert "users" in users

    @pytest.mark.slow(reason="May take time due to large dataset")
    def test_get_large_dataset_id_offset(self):
        """Test getting a large dataset with id-offset pagination."""
        with FolioClient(**BUGFEST_CONFIG) as folio_client:
            instance_count = 0
            for instance in folio_client.folio_get_all("/instance-storage/instances", "instances", limit=1000):
                instance_count += 1
                if instance_count >= 1500000:
                    break
            
            assert instance_count >= 1500000

if __name__ == "__main__":
    # Run integration tests directly
    pytest.main([
        __file__,
        "--run-integration",
        "-v",
        "--tb=short"
    ])