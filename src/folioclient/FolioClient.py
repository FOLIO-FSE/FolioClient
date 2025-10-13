from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime
from datetime import timezone as tz
from typing import Any, AsyncGenerator, Dict, Generator, List, Optional, Union, cast, TYPE_CHECKING
from urllib.parse import urljoin
from warnings import warn

import httpx
import jsonref
import yaml
from openapi_schema_to_json_schema import to_json_schema

from folioclient._httpx import FolioAuth, FolioConnectionParameters
from folioclient.cached_property import cached_property
from folioclient.decorators import (
    folio_retry_on_auth_error,
    folio_retry_on_server_error,
    handle_remote_protocol_error,
    use_client_session,
    use_client_session_with_generator,
)
from folioclient.exceptions import FolioClientClosed, folio_errors

if TYPE_CHECKING:  # pragma: no cover
    import ssl


# Conditional import of orjson to support faster JSON processing if available
try:  # pragma: no cover # TODO: remove pragma when this is out of beta
    import orjson  # type: ignore

    if (
        os.environ.get("FOLIOCLIENT_PREFER_ORJSON", "0") != "0"
    ):  # Allow user to disable orjson via env var
        _HAS_ORJSON = True
    else:
        _HAS_ORJSON = False

    def _orjson_loads(data):
        return orjson.loads(data)

    def _orjson_dumps(obj):  # noqa: F841
        return orjson.dumps(obj).decode("utf-8")

    # Define exception tuples for different operations
    JSON_DECODE_ERRORS = (json.JSONDecodeError, orjson.JSONDecodeError)  # type: ignore
    JSON_ENCODE_ERRORS = (TypeError, orjson.JSONEncodeError)  # type: ignore

except ImportError:
    _HAS_ORJSON = False
    JSON_DECODE_ERRORS = (json.JSONDecodeError,)  # type: ignore
    JSON_ENCODE_ERRORS = (TypeError,)  # type: ignore

# Constants
CONTENT_TYPE_JSON = "application/json"

SORTBY_ID = "sortBy id"

# Legacy timeout constant for backward compatibility
try:
    timeout_str = os.environ.get("FOLIOCLIENT_HTTP_TIMEOUT")
    HTTPX_TIMEOUT = int(timeout_str) if timeout_str is not None else None
except (TypeError, ValueError):
    HTTPX_TIMEOUT = None

RAML_UTIL_URL = "https://raw.githubusercontent.com/folio-org/raml/raml1.0"

USER_AGENT_STRING = "Folio Client (https://github.com/FOLIO-FSE/FolioClient)"

PROTECTED_CACHED_PROPERTIES = ["current_user", "ecs_consortium", "ecs_members"]

# Set up logger
logger = logging.getLogger("FolioClient")


# Sentinel value for detecting unset timeout parameter
class _TimeoutUnsetType:
    def __repr__(self):
        return "_TIMEOUT_UNSET"


_TIMEOUT_UNSET = _TimeoutUnsetType()


# Timeout configuration with granular control
def _get_timeout_config() -> dict:
    """Get timeout configuration from environment variables or defaults.

    Returns:
        dict: Timeout configuration dictionary with connect, read, write, and pool timeouts.
    """
    # Granular timeout configuration - these override the default when set
    return {
        "connect": float(os.environ["FOLIOCLIENT_CONNECT_TIMEOUT"])
        if "FOLIOCLIENT_CONNECT_TIMEOUT" in os.environ
        else None,
        "read": float(os.environ["FOLIOCLIENT_READ_TIMEOUT"])
        if "FOLIOCLIENT_READ_TIMEOUT" in os.environ
        else None,
        "write": float(os.environ["FOLIOCLIENT_WRITE_TIMEOUT"])
        if "FOLIOCLIENT_WRITE_TIMEOUT" in os.environ
        else None,
        "pool": float(os.environ["FOLIOCLIENT_POOL_TIMEOUT"])
        if "FOLIOCLIENT_POOL_TIMEOUT" in os.environ
        else None,
    }


TIMEOUT_CONFIG = _get_timeout_config()


class FolioHeadersDict(dict):
    """Custom dict wrapper for folio_headers that intercepts x-okapi-tenant assignments"""

    def __init__(self, folio_client: "FolioClient", *args, **kwargs):
        """Initialize the FolioHeadersDict with a reference to the FolioClient.

        Args:
            folio_client (FolioClient): The FolioClient instance this dict belongs to.
            *args: Arguments to pass to the parent dict constructor.
            **kwargs: Keyword arguments to pass to the parent dict constructor.
        """
        super().__init__(*args, **kwargs)
        self._folio_client = folio_client

    def __setitem__(self, key: str, value: str) -> None:
        """Set header value with special handling for x-okapi-tenant.

        Args:
            key (str): The header name.
            value (str): The header value.

        Note:
            Setting x-okapi-tenant via headers is deprecated. Use
            folio_client.tenant_id instead.
        """
        if key == "x-okapi-tenant":
            warn(
                "Setting x-okapi-tenant via headers is deprecated. "
                "Use folio_client.tenant_id = 'your_tenant' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            # Update tenant through the auth system
            self._folio_client.tenant_id = value
            # Don't store in the dict since it's added automatically
            return

        # For all other headers, store normally
        super().__setitem__(key, value)

    def update(self, *args, **kwargs) -> None:
        """Override update to handle x-okapi-tenant specially.

        Note:
            Setting x-okapi-tenant via headers is deprecated. Use
            folio_client.tenant_id instead.
        """
        # Handle the different calling patterns for dict.update()
        if args:
            other = args[0]
            if hasattr(other, "items"):
                # It's a mapping (dict-like)
                if "x-okapi-tenant" in other:
                    # Handle x-okapi-tenant specially
                    tenant_id = other["x-okapi-tenant"]
                    warn(
                        "Setting x-okapi-tenant via headers is deprecated. "
                        "Use folio_client.tenant_id = 'your_tenant' instead.",
                        DeprecationWarning,
                        stacklevel=2,
                    )
                    self._folio_client.tenant_id = tenant_id
                    # Remove x-okapi-tenant from the dict we pass to super()
                    other = {k: v for k, v in other.items() if k != "x-okapi-tenant"}
            # Call parent with the (possibly modified) mapping/iterable
            super().update(other)

        # Handle x-okapi-tenant in kwargs
        if "x-okapi-tenant" in kwargs:
            tenant_id = kwargs.pop("x-okapi-tenant")
            warn(
                "Setting x-okapi-tenant via headers is deprecated. "
                "Use folio_client.tenant_id = 'your_tenant' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            self._folio_client.tenant_id = tenant_id

        # Update with remaining kwargs
        if kwargs:
            super().update(kwargs)


class FolioClient:
    """A Python client for FOLIO APIs

    FOLIO: The Future of Libraries is Open, is a library services platform
    that provides a set of APIs for managing library resources and services.

    This class provides methods to interact with FOLIO APIs, including authentication,
    data retrieval, and data manipulation. It also includes methods for handling
    pagination and constructing query parameters.

    Initialization:
        FolioClient is designed to be used as a context manager

        >>> from folioclient import FolioClient
        >>> with FolioClient(
        ...     "https://folio-snapshot-okapi.dev.folio.org",
        ...     "diku",
        ...     "diku_admin",
        ...     "admin"
        ... ) as folio_client:
        ...     users = folio_client.folio_get("/users", "users", query="username==\"diku_admin\"")
        ...     print(users)
        ...
        [{'username': 'diku_admin', 'id': '03d9f2b5-8429-50f8-a3af-0df1ce8be1d6', 'active': True, 'patronGroup': '3684a786-6671-4268-8ed0-9db82ebca60b', 'departments': [], 'proxyFor': [], 'personal': {'lastName': 'ADMINISTRATOR', 'firstName': 'DIKU', 'email': 'admin@diku.example.org', 'addresses': []}, 'createdDate': '2025-05-01T02:00:17.887+00:00', 'updatedDate': '2025-05-01T02:00:17.887+00:00', 'metadata': {'createdDate': '2025-05-01T01:56:12.945+00:00', 'updatedDate': '2025-05-01T02:00:17.882+00:00', 'updatedByUserId': '03d9f2b5-8429-50f8-a3af-0df1ce8be1d6'}, 'preferredEmailCommunication': []}]

    Parameters:
        gateway_url (str): The base URL for the FOLIO API.
        tenant_id (str): The tenant ID for the FOLIO instance.
        username (str): The username for authentication.
        password (str): The password for authentication.
        ssl_verify (bool | ssl.SSLContext), keyword-only: Whether to verify SSL certificates, or a custom SSL context. Default is True.
        okapi_url (keyword-only, str, optional), keyword-only: Deprecated. Use gateway_url instead.
        timeout (float | dict | httpx.Timeout | None, optional), keyword-only: Timeout configuration for HTTP requests.
    """  # noqa: E501

    def __init__(
        self,
        gateway_url: str,
        tenant_id: str,
        username: str,
        password: str,
        *,
        ssl_verify: bool | ssl.SSLContext = True,
        okapi_url: str | None = None,
        timeout: float | dict | httpx.Timeout | None | _TimeoutUnsetType = _TIMEOUT_UNSET,
    ):
        if okapi_url:
            warn(
                "okapi_url argument is deprecated. Use gateway_url instead. Support for okapi_url will be removed in a future release.",  # noqa: E501
                DeprecationWarning,
                stacklevel=2,
            )
        self.missing_location_codes: set[str] = set()
        self.loan_policies: dict[str, str] = {}
        self.cql_all = "cql.allRecords=1"

        # Determine timeout value to use
        if timeout is _TIMEOUT_UNSET:
            # User didn't specify timeout, use environment variables
            timeout_value: httpx.Timeout = FolioClient._construct_timeout_from_env()
        elif timeout is None:
            # User explicitly passed None, ignore environment variables
            timeout_value = httpx.Timeout(None)
        else:
            # User passed specific value (float, dict, or httpx.Timeout)
            timeout_value = FolioClient._construct_timeout(
                cast(float | dict | httpx.Timeout, timeout)
            )

        self.folio_parameters: FolioConnectionParameters = FolioConnectionParameters(
            gateway_url=okapi_url or gateway_url,
            tenant_id=tenant_id,
            username=username,
            password=password,
            ssl_verify=ssl_verify,
            timeout=timeout_value,
        )
        self.folio_auth: FolioAuth = FolioAuth(self.folio_parameters)
        self.base_headers = {
            "content-type": CONTENT_TYPE_JSON,
        }
        self._folio_headers: FolioHeadersDict = FolioHeadersDict(self)
        self.is_closed = False
        self._ecs_central_tenant_id: str | None = None
        self._ecs_checked = False

    def __repr__(self) -> str:
        """Return string representation of the FolioClient instance.

        Returns:
            str: String representation showing tenant, URL, and username info.

        Note:
            For ECS environments, the central tenant ID is also shown, as well as the
            active tenant ID
        """
        if self.is_ecs:
            return (
                f"FolioClient for ECS central tenant {self._ecs_central_tenant_id}"
                f" (active tenant: {self.tenant_id}) at {self.gateway_url} as {self.username}"
            )
        return f"FolioClient for tenant {self.tenant_id} at {self.gateway_url} as {self.username}"

    def __enter__(self):
        """Context manager entry for FolioClient.

        Returns:
            FolioClient: The FolioClient instance.

        Note:
            Instantiates httpx.Client instance for FOLIO using `self.get_folio_http_client()`
            and performs initial ECS check.
        """
        self.httpx_client = self.get_folio_http_client()
        # Call ECS check after clients are initialized
        self._initial_ecs_check()
        return self

    @handle_remote_protocol_error
    @use_client_session
    def __exit__(self, exc_type, exc_value, traceback):
        """Context manager exit method.

        Args:
            exc_type: Exception type if an exception occurred.
            exc_value: Exception value if an exception occurred.
            traceback: Traceback if an exception occurred.

        Note:
            This method logs out of FOLIO for the current session, invalidates any
            existing startup parameters, and marks the FolioClient instance as closed.
        """
        if (
            self.cookies
            and hasattr(self, "httpx_client")
            and self.httpx_client
            and not self.httpx_client.is_closed
        ):
            logger.info("logging out...")
            logout = self.httpx_client.post(
                urljoin(self.gateway_url, "authn/logout"),
            )
            self.logout_response_handler(logout)
        else:
            logger.debug("No active Client session found, skipping logout.")
        if hasattr(self, "httpx_client") and self.httpx_client and not self.httpx_client.is_closed:
            self.httpx_client.close()
        self._cleanup_folio_parameters()
        self._cleanup_folio_auth()
        self.is_closed = True

    def logout_response_handler(self, logout):
        try:
            logout.raise_for_status()
            logger.info("Logged out")
        except httpx.HTTPStatusError:
            if logout.status_code == 404:
                logger.warning("Logout endpoint not found, skipping logout.")
            else:
                logger.error(f"Logout failed: ({logout.status_code}) {logout.text}")
        except httpx.ConnectError:
            logger.warning("Logout endpoint not reachable, skipping logout.")

    async def __aenter__(self):
        """Asynchronous context manager entry for FolioClient.

        Returns:
            FolioClient: The FolioClient instance.

        Note:
            Instantiates httpx.Client and httpx.AsyncClient instance for FOLIO using
            `self.get_folio_http_client()` and `self.get_folio_http_client_async()`,
            and performs initial ECS check.
        """
        self.httpx_client = self.get_folio_http_client()
        self.async_httpx_client = self.get_folio_http_client_async()
        # Call ECS check after clients are initialized
        self._initial_ecs_check()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        """Asynchronous context manager exit method.

        Args:
            exc_type: Exception type if an exception occurred.
            exc_value: Exception value if an exception occurred.
            traceback: Traceback if an exception occurred.
        """
        if (
            self.cookies
            and hasattr(self, "async_httpx_client")
            and self.async_httpx_client
            and not self.async_httpx_client.is_closed
        ):
            logger.info("logging out...")
            logout = await self.async_httpx_client.post(
                urljoin(self.gateway_url, "authn/logout"),
            )
            self.logout_response_handler(logout)
        else:
            logger.debug("No active AsyncClient session found, skipping logout.")
        if (
            hasattr(self, "async_httpx_client")
            and self.async_httpx_client
            and not self.async_httpx_client.is_closed
        ):
            await self.async_httpx_client.aclose()
        try:
            if (
                hasattr(self, "httpx_client")
                and self.httpx_client
                and not self.httpx_client.is_closed
            ):
                self.httpx_client.close()
            self._cleanup_folio_parameters()
            self._cleanup_folio_auth()
        except Exception as e:
            logger.error(f"Error during async exit cleanup: {e}")
        self.is_closed = True

    def _cleanup_folio_auth(self):
        if hasattr(self, "folio_auth"):
            if hasattr(self.folio_auth, "_token"):
                del self.folio_auth._token
            if hasattr(self.folio_auth, "_params"):
                del self.folio_auth._params

    def _cleanup_folio_parameters(self):
        if hasattr(self, "folio_parameters"):
            del self.folio_parameters

    @staticmethod
    def _construct_timeout_from_env() -> httpx.Timeout:
        """Construct httpx.Timeout object from environment variables only.

        Returns:
            httpx.Timeout: Configured timeout object from environment variables.
                          If no environment configuration is found, returns httpx.Timeout(None).
        """
        default_timeout_config = {k: v for k, v in TIMEOUT_CONFIG.items() if v is not None}

        if not default_timeout_config and HTTPX_TIMEOUT is None:
            return httpx.Timeout(None)

        return httpx.Timeout(HTTPX_TIMEOUT, **default_timeout_config)

    @staticmethod
    def _construct_timeout(timeout: float | dict | httpx.Timeout) -> httpx.Timeout:
        """Construct httpx.Timeout object from user-provided timeout parameter.

        If timeout is a dict, any unspecified values will be replaced by the environment
        default values. If you want full control over every timeout value, set them explicitly
        in the dict.

        Args:
            timeout: Timeout configuration - can be float, dict, or httpx.Timeout.

        Returns:
            httpx.Timeout: Configured timeout object.
        """
        if isinstance(timeout, httpx.Timeout):
            return timeout
        elif isinstance(timeout, dict):
            # For user-provided dict, merge with environment defaults
            default_timeout_config = {k: v for k, v in TIMEOUT_CONFIG.items() if v is not None}
            merged_timeout = {**default_timeout_config, **timeout}
            return httpx.Timeout(HTTPX_TIMEOUT, **merged_timeout)
        else:
            # Handle float/int timeout
            return httpx.Timeout(timeout)

    @property
    def okapi_url(self) -> str:
        """Convenience property for backwards-compatibility with pre-Sunflower FOLIO systems.

        Note:
            This property is deprecated. Use gateway_url instead.

        Returns:
            str: The gateway URL.
        """
        warn(
            "FolioClient.okapi_url is deprecated. Use gateway_url instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.gateway_url

    def close(self) -> None:
        """Manually close the FolioClient object.

        This should only be used when running FolioClient outside a context manager.
        """
        self.__exit__(None, None, None)

    async def async_close(self) -> None:
        """Manually close the FolioClient object asynchronously.

        This should only be used when running FolioClient outside a context manager.
        """
        await self.__aexit__(None, None, None)

    @property
    def tenant_id(self) -> str:
        return self.folio_auth.tenant_id

    @tenant_id.setter
    def tenant_id(self, tenant_id: str) -> None:
        if self.is_ecs:
            tenant_map = {t["id"]: t["name"] for t in self.ecs_members}
            logger.info(
                f"Setting active tenant to {tenant_id} ({tenant_map.get(tenant_id, 'unknown')})"
            )
        else:
            logger.debug(f"Setting active tenant to {tenant_id}")
        self.folio_auth.tenant_id = tenant_id
        self._clear_cached_properties()

    @tenant_id.deleter
    def tenant_id(self) -> None:
        """Reset tenant_id to the initial value and clear cached properties."""
        self.folio_auth.reset_tenant_id()
        self._clear_cached_properties()

    @property
    def username(self) -> str:
        """The username used for authentication.

        This is a convenience property that returns the username from the
        FolioConnectionParameters.
        """
        return self.folio_parameters.username

    @property
    def password(self) -> str:
        """The password used for authentication.

        This is a convenience property that returns the password from the
        FolioConnectionParameters.
        """
        return self.folio_parameters.password

    @property
    def initial_tenant_id(self) -> str:
        """The initial tenant ID used for authentication.

        This is a convenience property that returns the initial tenant ID from the
        FolioConnectionParameters.
        """
        return self.folio_parameters.tenant_id

    @property
    def gateway_url(self) -> str:
        """The gateway URL used for authentication.

        This is a convenience property that returns the gateway URL from the
        FolioConnectionParameters.
        """
        return self.folio_parameters.gateway_url

    @property
    def ssl_verify(self) -> bool | ssl.SSLContext:
        """Whether SSL verification is enabled

        This is a convenience property that returns the ssl_verify value from the
        FolioConnectionParameters.
        """
        return self.folio_parameters.ssl_verify

    @property
    def http_timeout(self) -> httpx.Timeout | None:
        """The HTTP timeout configuration.

        Warning:
            DEPRECATED: This property will be removed in a future release. The return value
            is an httpx.Timeout object which may not be compatible with other HTTP libraries.

            BREAKING CHANGE: This property now returns an httpx.Timeout object instead of
            the original timeout parameter value. This may break backwards compatibility
            if you were using this property with other HTTP libraries.

        Returns the httpx.Timeout object configured during initialization,
        or None for no timeout.

        Returns:
            httpx.Timeout | None: Configured timeout object for HTTP requests,
                or None for no timeout.
        """
        warn(
            "FolioClient.http_timeout is deprecated and will be removed in a future release. "
            "The returned httpx.Timeout object may not be compatible with other HTTP libraries.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.folio_parameters.timeout

    def _clear_cached_properties(self, *property_names: str) -> None:
        """Clear cached properties specified or all cached properties if none specified.

        Args:
            *property_names (str): Names of specific properties to clear. If none
                provided, all cached properties will be cleared.
        """

        # Get the properties to clear
        if property_names:
            props_to_clear: List[str] = list(property_names)
        else:
            props_to_clear = [
                attr_name
                for attr_name in dir(self.__class__)
                if attr_name not in PROTECTED_CACHED_PROPERTIES
                and not attr_name.startswith("_")
                and self._is_cached_property(attr_name)
            ]
        # Clear each property
        for prop_name in props_to_clear:
            self._clear_single_cached_property(prop_name)

    def _is_cached_property(self, attr_name: str) -> bool:
        """Check if an attribute is a cached_property.

        Args:
            attr_name (str): Name of the attribute to check.

        Returns:
            bool: True if the attribute is a cached_property, False otherwise.
        """
        try:
            attr = getattr(self.__class__, attr_name)
            return isinstance(attr, cached_property)
        except AttributeError:
            return False

    def _clear_single_cached_property(self, prop_name: str) -> None:
        """Clear a single cached property if it exists.

        Args:
            prop_name (str): Name of the property to clear.
        """
        # Verify it's actually a cached property before deleting
        if (
            hasattr(self.__class__, prop_name)
            and self._is_cached_property(prop_name)
            and hasattr(self, prop_name)
        ):
            delattr(self, prop_name)

    @cached_property
    def current_user(self) -> str:
        """Returns the current user ID for the logged-in user.

        First tries the bl-users endpoint, then falls back to the users endpoint.

        Returns:
            str: The user ID of the current user, or empty string if unable to fetch.

        Note:
            For ECS environments, the initial tenant_id used for authentication is used.
        """
        logger.info("fetching current user..")
        current_tenant_id = self.tenant_id
        self.folio_auth.reset_tenant_id()

        try:
            # Try bl-users endpoint first
            path = f"/bl-users/by-username/{self.folio_parameters.username}"
            resp = self._folio_get(path, "user")
            return resp["id"]
        except httpx.HTTPStatusError:
            logger.info("bl-users endpoint not found, trying /users endpoint instead.")
            try:
                # Fallback to users endpoint
                path = "/users"
                query = f"username=={self.folio_parameters.username}"
                resp = self._folio_get(path, "users", query=query)
                return resp[0]["id"]
            except Exception as exception:
                logger.error(
                    f"Unable to fetch user id for user {self.folio_parameters.username}",
                    exc_info=exception,
                )
                return ""
        except Exception as exception:
            logger.error(
                f"Unable to fetch user id for user {self.folio_parameters.username}",
                exc_info=exception,
            )
            return ""
        finally:
            self.tenant_id = current_tenant_id

    @cached_property
    def identifier_types(self) -> List[Dict[str, Any]]:
        """Returns a list of identifier types.

        Returns:
            List[Dict[str, Any]]: List of identifier type objects.
        """
        return list(self.folio_get_all("/identifier-types", "identifierTypes", self.cql_all, 1000))

    @cached_property
    def module_versions(self) -> List[str]:
        """Returns a list of module versions for the current tenant.

        Returns:
            List[str]: List of module version IDs.
        """
        try:
            resp = self.folio_get(f"/_/proxy/tenants/{self.tenant_id}/modules")
        except httpx.HTTPError:
            entitlements = self.folio_get(f"/entitlements/{self.tenant_id}/applications")
            resp = []
            for app in entitlements["applicationDescriptors"]:
                for md in app["modules"]:
                    resp.append(md)
        return [a["id"] for a in resp]

    @cached_property
    def statistical_codes(self) -> List[Dict[str, Any]]:
        """Returns a list of statistical codes.

        Returns:
            List[Dict[str, Any]]: List of statistical code objects.
        """
        return list(
            self.folio_get_all("/statistical-codes", "statisticalCodes", self.cql_all, 1000)
        )

    @cached_property
    def contributor_types(self) -> List[Dict[str, Any]]:
        """Returns a list of contributor types.

        Returns:
            List[Dict[str, Any]]: List of contributor type objects.
        """
        return list(
            self.folio_get_all("/contributor-types", "contributorTypes", self.cql_all, 1000)
        )

    @cached_property
    def contrib_name_types(self) -> List[Dict[str, Any]]:
        """Returns a list of contributor name types.

        Returns:
            List[Dict[str, Any]]: List of contributor name type objects.
        """
        return list(
            self.folio_get_all(
                "/contributor-name-types", "contributorNameTypes", self.cql_all, 1000
            )
        )

    @cached_property
    def instance_types(self) -> List[Dict[str, Any]]:
        """Returns a list of instance types.

        Returns:
            List[Dict[str, Any]]: List of instance type objects.
        """
        return list(self.folio_get_all("/instance-types", "instanceTypes", self.cql_all, 1000))

    @cached_property
    def instance_formats(self) -> List[Dict[str, Any]]:
        """Returns a list of instance formats.

        Returns:
            List[Dict[str, Any]]: List of instance format objects.
        """
        return list(self.folio_get_all("/instance-formats", "instanceFormats", self.cql_all, 1000))

    @cached_property
    def alt_title_types(self) -> List[Dict[str, Any]]:
        """Returns a list of alternative title types.

        Returns:
            List[Dict[str, Any]]: List of alternative title type objects.
        """
        return list(
            self.folio_get_all(
                "/alternative-title-types", "alternativeTitleTypes", self.cql_all, 1000
            )
        )

    @cached_property
    def locations(self) -> List[Dict[str, Any]]:
        """Returns a list of locations.

        Returns:
            List[Dict[str, Any]]: List of location objects.
        """
        return list(self.folio_get_all("/locations", "locations", self.cql_all, 1000))

    @cached_property
    def electronic_access_relationships(self) -> List[Dict[str, Any]]:
        """Returns a list of electronic access relationships.

        Returns:
            List[Dict[str, Any]]: List of electronic access relationship objects.
        """
        return list(
            self.folio_get_all(
                "/electronic-access-relationships",
                "electronicAccessRelationships",
                self.cql_all,
                1000,
            )
        )

    @cached_property
    def instance_note_types(self) -> List[Dict[str, Any]]:
        """Returns a list of instance note types.

        Returns:
            List[Dict[str, Any]]: List of instance note type objects.
        """
        return list(
            self.folio_get_all("/instance-note-types", "instanceNoteTypes", self.cql_all, 1000)
        )

    @cached_property
    def class_types(self) -> List[Dict[str, Any]]:
        """Returns a list of classification types.

        Returns:
            List[Dict[str, Any]]: List of classification type objects.
        """
        return list(
            self.folio_get_all("/classification-types", "classificationTypes", self.cql_all, 1000)
        )

    @cached_property
    def organizations(self) -> List[Dict[str, Any]]:
        """Returns a list of organizations.

        Returns:
            List[Dict[str, Any]]: List of organization objects.
        """
        return list(
            self.folio_get_all(
                "/organizations-storage/organizations",
                "organizations",
                self.cql_all,
                1000,
            )
        )

    @cached_property
    def holding_note_types(self) -> List[Dict[str, Any]]:
        """Returns a list of holding note types.

        Returns:
            List[Dict[str, Any]]: List of holding note type objects.
        """
        return list(
            self.folio_get_all("/holdings-note-types", "holdingsNoteTypes", self.cql_all, 1000)
        )

    @cached_property
    def call_number_types(self) -> List[Dict[str, Any]]:
        """Returns a list of call number types.

        Returns:
            List[Dict[str, Any]]: List of call number type objects.
        """
        return list(
            self.folio_get_all("/call-number-types", "callNumberTypes", self.cql_all, 1000)
        )

    @cached_property
    def holdings_types(self) -> List[Dict[str, Any]]:
        """Returns a list of holdings types.

        Returns:
            List[Dict[str, Any]]: List of holdings type objects.
        """
        return list(self.folio_get_all("/holdings-types", "holdingsTypes", self.cql_all, 1000))

    @cached_property
    def modes_of_issuance(self) -> List[Dict[str, Any]]:
        """Returns a list of modes of issuance.

        Returns:
            List[Dict[str, Any]]: List of mode of issuance objects.
        """
        return list(self.folio_get_all("/modes-of-issuance", "issuanceModes", self.cql_all, 1000))

    @cached_property
    def authority_source_files(self) -> List[Dict[str, Any]]:
        """Cached property for all configured authority source files.

        Returns:
            List[Dict[str, Any]]: List of authority source file objects.
        """
        return list(
            self.folio_get_all(
                "/authority-source-files", "authoritySourceFiles", self.cql_all, 1000
            )
        )

    @cached_property
    def subject_types(self) -> List[Dict[str, Any]]:
        """Cached property for all configured subject types.

        Returns:
            List[Dict[str, Any]]: List of subject type objects.
        """
        return list(self.folio_get_all("/subject-types", "subjectTypes", self.cql_all, 1000))

    def validate_client_open(self):
        if self.is_closed:
            raise FolioClientClosed()

    @property
    def folio_headers(self) -> Dict[str, str]:
        """
        Convenience property that returns FOLIO headers with the current valid auth token.

        **INTENDED FOR EXTERNAL USE ONLY**
        This property is designed for users who want to use their own HTTP libraries
        (requests, aiohttp, etc.) while leveraging FolioClient's token management.

        FolioClient's own methods (folio_get, folio_post, etc.) do NOT use this
        property - they use the FolioAuth authentication flow directly.

        All headers except x-okapi-token can be modified by:
        - Bulk assignment: folio_client.folio_headers = {...}
        - Key assignment: folio_client.folio_headers['key'] = 'value'
        - Update method: folio_client.folio_headers.update({...})

        Example:
            >>> import requests
            >>> with FolioClient(...) as client:
            ...     headers = client.folio_headers
            ...     response = requests.get(url, headers=headers)

        Returns:
            FolioHeadersDict: The FOLIO headers with special x-okapi-tenant handling.
        """
        self.validate_client_open()

        headers = {
            "x-okapi-token": self.access_token,
            "x-okapi-tenant": self.tenant_id,
        }
        if not self._folio_headers:
            self._folio_headers = FolioHeadersDict(self)
            self._folio_headers.update(self.base_headers)
        folio_headers = {**self._folio_headers, **headers}
        return folio_headers

    @folio_headers.setter
    def folio_headers(self, headers_dict: Dict[str, str]) -> None:
        """
        Setter for folio_headers that allows setting custom headers while preserving
        backward compatibility for x-okapi-tenant.

        Parameters:
            headers_dict (Dict[str, str]): Dictionary of headers to set
        """
        self.validate_client_open()

        new_headers = FolioHeadersDict(self)
        new_headers.update(headers_dict)
        self._folio_headers = new_headers

    @folio_headers.deleter
    def folio_headers(self) -> None:
        """
        Deleter for folio_headers that clears the private _folio_headers dictionary, which will
        revert folio_headers to using base_headers
        """
        self.validate_client_open()
        self._folio_headers.clear()

    @property
    def okapi_headers(self) -> Dict[str, str]:
        """
        Property that returns okapi headers with the current valid Okapi token.

        Deprecated:
            Since v1.0.0: Use `folio_headers` instead. This property will be removed
            in a future release.

        **INTENDED FOR EXTERNAL USE ONLY**
        This property is designed for users who want to use their own HTTP libraries
        (requests, aiohttp, etc.) while leveraging FolioClient's token management.

        All headers except x-okapi-token can be modified by:
        - Bulk assignment: folio_client.okapi_headers = {...}
        - Key assignment: folio_client.okapi_headers['key'] = 'value'
        - Update method: folio_client.okapi_headers.update({...})

        Example:
            >>> import requests
            >>> with FolioClient(...) as client:
            ...     headers = client.okapi_headers  # Deprecated - use folio_headers
            ...     response = requests.get(url, headers=headers)

        Returns:
            FolioHeadersDict: The okapi headers with special x-okapi-tenant handling.
        """
        warn(
            "FolioClient.okapi_headers is deprecated. Use folio_headers instead. "
            "Support for okapi_headers will be removed in a future release.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.folio_headers

    @okapi_headers.setter
    def okapi_headers(self, headers_dict: Dict[str, str]) -> None:
        """Setter for okapi_headers that allows setting custom headers while preserving
        backward compatibility for x-okapi-tenant.

        Note:
            This property is deprecated. Use folio_headers instead.
            This property will be removed in a future release.

        Args:
            headers_dict (Dict[str, str]): Dictionary of headers to set.
        """
        warn(
            "FolioClient.okapi_headers is deprecated. Use folio_headers instead. "
            "Support for okapi_headers will be removed in a future release.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.folio_headers = headers_dict

    @okapi_headers.deleter
    def okapi_headers(self) -> None:
        """Deleter for okapi_headers that clears the private _okapi_headers dictionary.

        Note:
            This property is deprecated. Use folio_headers instead.
            This property will be removed in a future release.
        """
        warn(
            "FolioClient.okapi_headers is deprecated. Use folio_headers instead. "
            "Support for okapi_headers will be removed in a future release.",
            DeprecationWarning,
            stacklevel=2,
        )
        del self.folio_headers

    @property
    def okapi_token(self) -> str:
        """
        Property that attempts to return a valid Okapi token, refreshing if needed.

        Returns:
            str: The Okapi token.
        """
        warn(
            "FolioClient.okapi_token is deprecated. Use FolioClient.access_token instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.access_token

    @property
    def access_token(self) -> str:
        """
        Property that attempts to return a valid access token, refreshing if needed.

        Returns:
            str: The access token.
        """
        self.validate_client_open()
        return self.folio_auth.folio_auth_token

    @property
    def refresh_token(self) -> str:
        self.validate_client_open()
        _ = self.access_token  # Ensure token is valid
        return self.folio_auth.folio_refresh_token

    @property
    def cookies(self) -> Optional[httpx.Cookies]:
        """
        Property that returns the httpx cookies object for the current session, and
        refreshes them if needed. Raises FolioClientClosed if the client is closed.
        """
        self.validate_client_open()
        _ = self.access_token  # Ensure token is valid
        return self.folio_auth._token.cookies

    def _initial_ecs_check(self) -> None:
        """Check if initial tenant_id value is an ECS central tenant ID.

        Attempts to determine if this is an ECS (multi-tenant consortium) environment
        by checking for consortia and member tenant information.
        """
        if self._ecs_checked:
            return

        try:
            try:
                self._ecs_consortium = self.folio_get("/consortia", "consortia")[0]
                self._ecs_members = self.folio_get(
                    f"/consortia/{self._ecs_consortium['id']}/tenants", "tenants"
                )
                tenant_name_map = {t["id"]: t["name"] for t in self._ecs_members}
                self._ecs_central_tenant_id = self.folio_parameters.tenant_id
                logger.info(
                    f"Connected to ECS central tenant {self.folio_parameters.tenant_id}"
                    f" ({tenant_name_map.get(self.folio_parameters.tenant_id, 'unknown')})"
                )
            except (httpx.HTTPError, IndexError):
                logger.debug(
                    f"Provided tenant_id ({self.folio_parameters.tenant_id}) is not an ECS "
                    "central tenant or user is not authorized to access mod-consortia APIs"
                )
        except ValueError:
            self._ecs_central_tenant_id = None
        finally:
            self._ecs_checked = True

    @property
    def ecs_central_tenant_id(self) -> str | None:
        """
        Property that returns the central tenant ID for an ECS FOLIO system
        """
        # Lazy initialization: check ECS status on first access if not already done
        if not self._ecs_checked:
            self._initial_ecs_check()

        if hasattr(self, "_ecs_central_tenant_id") and self._ecs_central_tenant_id:
            return self._ecs_central_tenant_id
        else:
            logger.debug("No ECS central tenant configured")
        return None

    @ecs_central_tenant_id.setter
    def ecs_central_tenant_id(self, tenant_id: str) -> None:
        """
        Setter for ECS central tenant ID. Validates that the tenant is actually
        an ECS central tenant and the user has sufficient permissions.

        This allows users who authenticated to a member tenant to manually
        set the central tenant and enable ECS functionality.
        """
        if tenant_id != getattr(self, "_ecs_central_tenant_id", None):
            old_central_tenant = getattr(self, "_ecs_central_tenant_id", None)
            old_ecs_consortium = getattr(self, "_ecs_consortium", None)
            current_tenant_id = self.tenant_id

            try:
                # Set the new central tenant ID
                self._ecs_central_tenant_id = tenant_id
                self._clear_cached_properties("ecs_consortium", "ecs_members")

                # Use folio_auth directly to avoid recursion
                self.folio_auth.tenant_id = tenant_id

                try:
                    # Test if this is a valid ECS central tenant
                    consortium = self.folio_get("/consortia", "consortia")[0]
                    self._ecs_consortium = consortium

                    logger.info(
                        f"Set ECS central tenant to {tenant_id} "
                        f"({consortium.get('name', 'unknown')})"
                    )
                    self._clear_cached_properties("ecs_members")

                except (httpx.HTTPStatusError, IndexError) as e:
                    raise ValueError(
                        f"Tenant {tenant_id} is not an ECS central tenant, or user does"
                        " not have sufficient permissions in the central tenant."
                    ) from e
                finally:
                    # Always restore the original tenant
                    self.folio_auth.tenant_id = current_tenant_id

            except Exception:
                # Restore old values on error
                self._ecs_central_tenant_id = old_central_tenant
                if old_ecs_consortium is not None:
                    self._ecs_consortium = old_ecs_consortium
                elif hasattr(self, "_ecs_consortium"):
                    delattr(self, "_ecs_consortium")
                self._clear_cached_properties("ecs_consortium", "ecs_members")
                raise

    @ecs_central_tenant_id.deleter
    def ecs_central_tenant_id(self) -> None:
        self._ecs_central_tenant_id = None
        self._clear_cached_properties("ecs_consortium", "ecs_members")

    @property
    def is_ecs(self) -> bool:
        """
        Property that returns True if self.ecs_central_tenant_id is an ECS central tenant.
        """
        # Ensure ECS check has been performed
        _ = self.ecs_central_tenant_id  # This will trigger the check if needed
        return bool(self.ecs_consortium)

    @cached_property
    def ecs_consortium(self) -> Union[Dict[str, Any], None]:
        """
        Property that returns the ECS consortia object for the current tenant.
        """
        # If no central tenant is set, return None
        if not self.ecs_central_tenant_id:
            return None

        current_tenant_id = self.tenant_id
        # Use folio_auth directly to avoid recursion
        self.folio_auth.tenant_id = self.ecs_central_tenant_id
        try:
            consortium = self.folio_get("/consortia", "consortia")[0]
        except (httpx.HTTPStatusError, IndexError):
            consortium = None
        finally:
            # Use folio_auth directly to avoid recursion
            self.folio_auth.tenant_id = current_tenant_id
        return consortium

    @cached_property
    def ecs_members(self) -> List[Dict[str, Any]]:
        """
        Property that returns the list of tenant objects of the ECS consortia.
        """
        if self.ecs_central_tenant_id:
            current_tenant_id = self.tenant_id
            # Use folio_auth directly to avoid recursion
            self.folio_auth.tenant_id = self.ecs_central_tenant_id
            try:
                tenants = self.folio_get(
                    f"/consortia/{self.ecs_consortium['id']}/tenants",
                    "tenants",
                    query_params={"limit": 1000},
                )
                tenants.sort(key=lambda x: x["id"])
                return tenants
            finally:
                # Use folio_auth directly to avoid recursion
                self.folio_auth.tenant_id = current_tenant_id
        else:
            return []

    @property
    def access_token_expires(self) -> Optional[datetime]:
        """
        Property that returns the expiration time of the current access token.
        """
        return self.folio_auth._token.expires_at

    @property
    def folio_token_expires(self) -> Optional[datetime]:
        """
        Property that returns the expiration time of the current access token.

        Deprecated:
            Since v1.0.0: Use `access_token_expires` instead. This property will be
            removed in a future release.
        """
        warn(
            "FolioClient.folio_token_expires is deprecated. Use access_token_expires instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.access_token_expires

    @folio_retry_on_server_error
    def login(self) -> None:
        """Logs into FOLIO to get a new FOLIO access token (synchronous).

        This method should not be necessary to call directly, as FolioClient
        automatically handles token refresh as needed, but is provided for
        backwards-compatibility.

        Raises:
            FolioClientClosed: If the client has been closed.
        """
        self.validate_client_open()
        with self.folio_auth._lock:
            self.folio_auth._token = (
                self.folio_auth._do_sync_auth()
            )  # Force re-authentication if needed

    @folio_retry_on_server_error
    async def async_login(self) -> None:
        """Logs into FOLIO to get a new FOLIO access token (asynchronous).

        This method should not be necessary to call directly, as FolioClient
        automatically handles token refresh as needed, but is provided as a
        convenience.

        Raises:
            FolioClientClosed: If the client has been closed.
        """
        self.validate_client_open()
        with self.folio_auth._lock:
            self.folio_auth._token = await self.folio_auth._do_async_auth()

    def logout(self) -> None:
        """Alias for close method.

        Raises:
            FolioClientClosed: If the client has already been closed.
        """
        self.validate_client_open()
        self.close()

    async def async_logout(self) -> None:
        """Alias for async_close method.

        Raises:
            FolioClientClosed: If the client has already been closed.
        """
        self.validate_client_open()
        await self.async_close()

    def build_url(self, path: str) -> str:
        """Build complete URL from gateway URL and path.

        Args:
            path (str): The API endpoint path to append to the gateway URL.

        Returns:
            str: The complete URL with leading/trailing slashes normalized.
        """
        return urljoin(self.gateway_url, path.lstrip("/")).rstrip("/")

    @staticmethod
    def handle_json_response(response) -> Any:
        """Handle JSON response with proper error handling.

        Uses orjson for faster parsing if available, otherwise falls back to
        the standard json library.

        Args:
            response: The HTTP response object to parse.

        Returns:
            Any: The parsed JSON data, or None if parsing fails.
        """
        try:
            if _HAS_ORJSON:
                return _orjson_loads(response.content)
            else:
                return response.json()
        except JSON_DECODE_ERRORS:  # Catch both JSONDecodeError types
            return None

    def extract_response_data(self, response, key: str | None) -> Any:
        """Extract data from response, optionally using a key.

        Args:
            response: The HTTP response object to extract data from.
            key (str | None): Optional key to extract specific data from the response.
                If None, returns the entire JSON response.

        Returns:
            Any: The extracted data, either the full response or the value at the key.
        """
        json_data = self.handle_json_response(response)
        return json_data[key] if key and json_data else json_data

    @staticmethod
    def should_continue_pagination(results: List[Dict], limit: int) -> bool:
        """Determine if pagination should continue based on result count.

        Args:
            results (List[Dict]): The current results from the API call.
            limit (int): The maximum number of results per page.

        Returns:
            bool: True if pagination should continue, False otherwise.
        """
        return len(results) == limit

    @staticmethod
    def get_last_id(results: List[Dict[str, Any]]) -> str | None:
        """Extract last ID from results for ID-based pagination.

        Args:
            results (List[Dict[str, Any]]): List of results containing ID fields.

        Returns:
            str | None: The ID of the last result, or None if results is empty.
        """
        return results[-1]["id"] if results else None

    @staticmethod
    def construct_id_offset_query(base_query: str, offset: str) -> str:
        """Construct query with ID offset for pagination.

        Args:
            base_query (str): The base CQL query string.
            offset (str): The ID to use as an offset for pagination.

        Returns:
            str: The constructed query with ID offset condition.
        """
        return f'id>"{offset}" and {base_query}'

    @staticmethod
    def prepare_id_offset_query(query: str | None, cql_all: str) -> str:
        """Prepare and validate query for ID offset pagination.

        Args:
            query (str | None): The CQL query string to validate.
            cql_all (str): Default query to use if no query provided.

        Returns:
            str: Validated query string suitable for ID offset pagination.

        Raises:
            ValueError: If query is provided but not sorted by ID.
        """
        if query and SORTBY_ID not in query:
            raise ValueError("FOLIO query must be sorted by ID")
        return query or f"{cql_all} {SORTBY_ID}"

    @staticmethod
    def handle_delete_response(response, path: str) -> Any:
        """Handle delete response with proper error handling and logging.

        Args:
            response: The HTTP response object from the delete request.
            path (str): The API path that was accessed for logging purposes.

        Returns:
            Any: The response data if successful, None for 204 status.

        Raises:
            httpx.HTTPStatusError: For HTTP status errors (will be converted to FOLIO
                exceptions by the calling method's @folio_errors decorator).
        """
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            if response.status_code == 404:
                logger.warning(f"Resource not found: {path}")
            else:
                raise

        try:
            if _HAS_ORJSON:
                return _orjson_loads(response.content)
            else:
                return response.json()
        except JSON_DECODE_ERRORS:  # Catch both JSONDecodeError types
            # If the response is successful + empty, return None
            if response.status_code == 204:
                logger.info(f"Resource deleted: {path} ({response.status_code})")
                return None
            else:
                logger.error(f"Failed to decode JSON response: {response.text}")
                raise

    def folio_get_all(
        self,
        path: str,
        key: str | None = None,
        query: str | None = None,
        limit: int = 100,
        no_cql: bool = False,
        **kwargs,
    ) -> Generator[Dict[str, Any], None, None]:
        """Fetches ALL data objects from FOLIO matching query in limit-size chunks.

        Provides an iterable object yielding a single record at a time until all
        records have been returned. Automatically uses id-based offset pagination
        if the query is sorted by id.

        Args:
            path (str): The API endpoint path.
            key (str | None): The key in the JSON response that contains the array
                of results. Defaults to None.
            query (str | None): The query string to filter the data objects.
                Defaults to None.
            limit (int): The maximum number of records to fetch in each chunk.
                Defaults to 10.
            no_cql (bool): Whether to skip CQL query processing. Defaults to False.
            **kwargs: Additional URL parameters to pass to the endpoint.

        Yields:
            dict: Individual records from the FOLIO API.

        Example:
            >>> for item in folio_client.folio_get_all(
            ...     "/item-storage/items", "items", "query", limit=100
            ... ):
            ...     process(item)
        """
        if not no_cql and (not query or SORTBY_ID in query):
            query = self.prepare_id_offset_query(query, self.cql_all)
            return self._folio_get_all_by_id_offset(path, key, query, limit, no_cql, **kwargs)
        else:
            query = query or f"{self.cql_all} {SORTBY_ID}"
            return self._folio_get_all(path, key, query, limit, no_cql, **kwargs)

    @use_client_session_with_generator
    def _folio_get_all(
        self,
        path: str,
        key: str | None = None,
        query: str | None = None,
        limit: int = 10,
        no_cql: bool = False,
        **kwargs,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Fetches ALL data objects from FOLIO matching `query` in `limit`-size chunks and provides
        an iterable object yielding a single record at a time until all records have been returned.

        Automatically uses id-based offset pagination if the query is sorted by id.

        Parameters:
            path (str): The API endpoint path.
            key (str): The key in the JSON response that contains the array of results.
            query (str): The query string to filter the data objects.
            limit (int): The maximum number of records to fetch in each chunk.
            **kwargs: Additional URL parameters to pass to `path`.
        """
        offset = 0

        # Initial fetch
        query_params: Dict[str, Any] = self._construct_query_parameters(
            query=query, limit=limit, offset=offset * limit, no_cql=no_cql, **kwargs
        )
        temp_res = self.folio_get(path, key, query_params=query_params)
        yield from temp_res

        # Continue fetching while we get full pages
        while self.should_continue_pagination(temp_res, limit):
            offset += 1
            query_params = self._construct_query_parameters(
                query=query, limit=limit, offset=offset * limit, no_cql=no_cql, **kwargs
            )
            temp_res = self.folio_get(path, key, query_params=query_params)
            yield from temp_res

        # Final fetch (handles edge case)
        offset += 1
        final_query_params = self._construct_query_parameters(
            query=query, limit=limit, offset=offset * limit, no_cql=no_cql, **kwargs
        )
        yield from self.folio_get(path, key, query_params=final_query_params)

    async def folio_get_all_async(
        self,
        path: str,
        key: str | None = None,
        query: str | None = None,
        limit: int = 100,
        no_cql: bool = False,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Asynchronously fetches ALL data objects from FOLIO matching `query` in
        `limit`-size chunks and provides an async iterable object yielding a single
        record at a time until all records have been returned.

        Automatically uses id-based offset pagination if the query is sorted by id.

        Parameters:
            path (str): The API endpoint path.
            key (str): The key in the JSON response that contains the array of results.
            query (str): The query string to filter the data objects, default is None.
            limit (int): The maximum number of records to fetch in each chunk, default is 10.
            no_cql (bool): If True, disables CQL query processing, default is False.
            **kwargs: Additional URL parameters to pass to `path`.

        Yields:
            dict: Individual records from the FOLIO API.

        Example:
            >>> async for item in folio_client.folio_get_all_async(
            ...     "/path/to/resource", "key", "query", limit=100
            ... ):
            ...     process(item)

        """
        if not no_cql and (not query or SORTBY_ID not in query):
            query = self.prepare_id_offset_query(query, self.cql_all)
            async for item in self._folio_get_all_by_id_offset_async(
                path, key, query, limit, no_cql, **kwargs
            ):
                yield item
        else:
            query = query or f"{self.cql_all} {SORTBY_ID}"
            async for item in self._folio_get_all_async(path, key, query, limit, no_cql, **kwargs):
                yield item

    @use_client_session_with_generator
    async def _folio_get_all_async(
        self,
        path: str,
        key: str | None = None,
        query: str | None = None,
        limit: int = 10,
        no_cql: bool = False,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Asynchronously fetches ALL data objects from FOLIO matching `query` in
        `limit`-size chunks and provides an async iterable object yielding a single
        record at a time until all records have been returned.

        Parameters:
            path (str): The API endpoint path.
            key (str): The key in the JSON response that contains the array of results.
            query (str): The query string to filter the data objects.
            limit (int): The maximum number of records to fetch in each chunk.
            **kwargs: Additional URL parameters to pass to `path`.
        """
        offset = 0

        # Initial fetch
        query_params: Dict[str, Any] = self._construct_query_parameters(
            query=query, limit=limit, offset=offset * limit, no_cql=no_cql, **kwargs
        )
        temp_res = await self.folio_get_async(path, key, query_params=query_params)
        for item in temp_res:
            yield item

        # Continue fetching while we get full pages
        while self.should_continue_pagination(temp_res, limit):
            offset += 1
            query_params = self._construct_query_parameters(
                query=query, limit=limit, offset=offset * limit, no_cql=no_cql, **kwargs
            )
            temp_res = await self.folio_get_async(path, key, query_params=query_params)
            for item in temp_res:
                yield item

        # Final fetch (handles edge case)
        offset += 1
        final_query_params = self._construct_query_parameters(
            query=query, limit=limit, offset=offset * limit, no_cql=no_cql, **kwargs
        )
        final_res = await self.folio_get_async(path, key, query_params=final_query_params)
        for item in final_res:
            yield item

    @use_client_session_with_generator
    def _folio_get_all_by_id_offset(
        self,
        path: str,
        key: str | None = None,
        query: str | None = None,
        limit: int = 10,
        no_cql: bool = False,
        **kwargs,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Fetches ALL data objects from FOLIO matching `query` in `limit`-size chunks and provides
        an iterable object yielding a single record at a time until all records have been returned.

        Parameters:
            path (str): The API endpoint path.
            key (str): The key in the JSON response that contains the array of results.
            query (str): The query string to filter the data objects.
            limit (int): The maximum number of records to fetch in each chunk.
            **kwargs: Additional URL parameters to pass to `path`.
        """
        # Prepare and validate query using shared logic
        offset = None

        # Initial fetch
        query_params: Dict[str, Any] = self._construct_query_parameters(
            query=query, limit=limit, no_cql=no_cql, **kwargs
        )
        temp_res = self.folio_get(path, key, query_params=query_params)

        # Handle empty results
        if not temp_res:
            return

        yield from temp_res
        offset = self.get_last_id(temp_res)

        # Continue fetching while we get full pages
        while self.should_continue_pagination(temp_res, limit) and offset:
            query_params = self._construct_query_parameters(
                query=query, limit=limit, no_cql=no_cql, **kwargs
            )
            query_params["query"] = self.construct_id_offset_query(query_params["query"], offset)
            temp_res = self.folio_get(path, key, query_params=query_params)

            if not temp_res:
                return

            yield from temp_res
            offset = self.get_last_id(temp_res)

    @use_client_session_with_generator
    async def _folio_get_all_by_id_offset_async(
        self,
        path: str,
        key: str | None = None,
        query: str | None = None,
        limit: int = 10,
        no_cql: bool = False,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Asynchronously fetches ALL data objects from FOLIO matching `query` in
        `limit`-size chunks and provides an async iterable object yielding a single
        record at a time until all records have been returned.

        Parameters:
            path (str): The API endpoint path.
            key (str): The key in the JSON response that contains the array of results.
            query (str): The query string to filter the data objects.
            limit (int): The maximum number of records to fetch in each chunk.
            **kwargs: Additional URL parameters to pass to `path`.
        """
        # Prepare and validate query using shared logic
        offset = None

        # Initial fetch
        query_params: Dict[str, Any] = self._construct_query_parameters(
            query=query, limit=limit, no_cql=no_cql, **kwargs
        )
        temp_res = await self.folio_get_async(path, key, query_params=query_params)

        # Handle empty results
        if not temp_res:
            return

        for item in temp_res:
            yield item
        offset = self.get_last_id(temp_res)

        # Continue fetching while we get full pages
        while self.should_continue_pagination(temp_res, limit) and offset:
            query_params = self._construct_query_parameters(
                query=query, limit=limit, no_cql=no_cql, **kwargs
            )
            query_params["query"] = self.construct_id_offset_query(query_params["query"], offset)
            temp_res = await self.folio_get_async(path, key, query_params=query_params)

            if not temp_res:
                return

            for item in temp_res:
                yield item
            offset = self.get_last_id(temp_res)

    def _construct_query_parameters(self, no_cql: bool = False, **kwargs) -> Dict[str, Any]:
        """Private method to construct query parameters for folio_get or httpx client calls.

        This method ensures that the query parameter is properly formatted to pass in a
        params dictionary to httpx. If no_cql is True, it will remove any default CQL
        queries such as 'cql.allRecords=1' and 'sortBy id'. This is useful for the
        handful of FOLIO APIs that do not follow the standard CQL query format and
        rely on named query parameters instead (e.g. mod-inn-reach circulation
        transaction APIs).

        Args:
            no_cql (bool): Whether to remove CQL-specific query components.
                Defaults to False.
            **kwargs: URL parameters to pass to the endpoint.

        Returns:
            Dict[str, Any]: Processed query parameters dictionary.
        """
        params = kwargs
        if query := kwargs.get("query"):
            if query.startswith(("?", "query=")):  # Handle previous query specification syntax
                params["query"] = query.split("=", maxsplit=1)[1]
            else:
                params["query"] = query
            if no_cql:
                params["query"] = (
                    params["query"]
                    .replace("cql.allRecords=1", "")
                    .replace("sortBy id", "")
                    .strip()
                )
            if not params.get("query"):
                del params["query"]
        return params

    def get_all(self, path, key=None, query="") -> Generator[Dict[str, Any], None, None]:
        """Alias for `folio_get_all`"""
        return self.folio_get_all(path, key, query)

    async def get_all_async(
        self, path, key=None, query=""
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Async alias for `folio_get_all_async`

        Note: This method wraps folio_get_all_async() for consistency.
        For direct access, use folio_get_all_async() instead.
        """
        async for item in self.folio_get_all_async(path, key, query):
            yield item

    @folio_retry_on_server_error
    @folio_retry_on_auth_error
    def folio_get(
        self, path, key=None, query="", query_params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Fetches data from FOLIO and returns it as a JSON object.

        Args:
            path (str): FOLIO API endpoint path.
            key (str, optional): Key in JSON response that includes the array of results
                for query APIs. Defaults to None.
            query (str, optional): CQL query string for backwards-compatibility.
                Defaults to "".
            query_params (dict, optional): Additional query parameters for the specified
                path. May also be used for query. Defaults to None.

        Returns:
            Any: Returns value matching key or the JSON object as a dict

        Raises:
            FolioAuthenticationError: For 401 authentication failures.
            FolioPermissionError: For 403 permission denied errors.
            FolioResourceNotFoundError: For 404 not found errors.
            FolioValidationError: For 422 validation errors.
            FolioInternalServerError: For 500 internal server errors.
            FolioBadGatewayError: For 502 bad gateway errors.
            FolioServiceUnavailableError: For 503 service unavailable errors.
            FolioGatewayTimeoutError: For 504 gateway timeout errors.
            FolioConnectionError: For network connectivity issues.
        """
        return self._folio_get(path, key, query, query_params=query_params)

    @folio_retry_on_server_error
    @folio_retry_on_auth_error
    async def folio_get_async(
        self, path, key=None, query="", query_params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Asynchronously fetches data from FOLIO and returns it as a JSON object.

        Args:
            path (str): FOLIO API endpoint path.
            key (str, optional): Key in JSON response that includes the array of results
                for query APIs. Defaults to None.
            query (str, optional): CQL query string for backwards-compatibility.
                Defaults to "".
            query_params (dict, optional): Additional query parameters for the specified
                path. May also be used for query. Defaults to None.

        Returns:
            Any: Returns value matching key or the JSON object as a dict
        """
        return await self._folio_get_async(path, key, query, query_params=query_params)

    @folio_errors
    @handle_remote_protocol_error
    @use_client_session
    def _folio_get(
        self, path, key=None, query="", query_params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Private method that implements folio_get.

        Args:
            path (str): FOLIO API endpoint path.
            key (str, optional): Key in JSON response that includes the array of results.
            query (str, optional): CQL query string.
            query_params (dict, optional): Additional query parameters.

        Returns:
            Any: Returns value matching key or the JSON object as a dict
        """
        # Ensure path doesn't start with / for httpx base_url to work properly
        path = path.lstrip("/")
        if query and query_params:
            query_params = self._construct_query_parameters(query=query, **query_params)
        elif query:
            query_params = self._construct_query_parameters(query=query)
        req = self.httpx_client.get(path, params=query_params)
        req.raise_for_status()
        return self.extract_response_data(req, key)

    @folio_errors
    @handle_remote_protocol_error
    @use_client_session
    async def _folio_get_async(
        self, path, key=None, query="", query_params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Private async method that implements `folio_get_async`
        """
        # Ensure path doesn't start with / for httpx base_url to work properly
        path = path.lstrip("/")
        if query and query_params:
            query_params = self._construct_query_parameters(query=query, **query_params)
        elif query:
            query_params = self._construct_query_parameters(query=query)
        req = await self.async_httpx_client.get(path, params=query_params)
        req.raise_for_status()
        return self.extract_response_data(req, key)

    @folio_errors
    @folio_retry_on_auth_error
    @handle_remote_protocol_error
    @use_client_session
    def folio_put(
        self, path, payload, query_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any] | None:
        """Convenience method to update data in FOLIO.

        Args:
            path (str): FOLIO API endpoint path.
            payload (dict): The data to update as JSON.
            query_params (dict, optional): Additional query parameters. Defaults to None.

        Returns:
            dict: The JSON response from FOLIO.
            None: If the response is empty.

        Raises:
            FolioAuthenticationError: For 401 authentication failures.
            FolioPermissionError: For 403 permission denied errors.
            FolioResourceNotFoundError: For 404 not found errors.
            FolioValidationError: For 422 validation errors (invalid data).
            FolioDataConflictError: For 409 conflict errors.
            FolioInternalServerError: For 500 internal server errors.
            FolioBadGatewayError: For 502 bad gateway errors.
            FolioServiceUnavailableError: For 503 service unavailable errors.
            FolioGatewayTimeoutError: For 504 gateway timeout errors.
            FolioConnectionError: For network connectivity issues.
        """
        # Ensure path doesn't start with / for httpx base_url to work properly
        path = path.lstrip("/")
        req = self.httpx_client.put(
            path,
            json=payload,
            params=query_params,
        )
        req.raise_for_status()
        return self.handle_json_response(req)

    @folio_errors
    @folio_retry_on_auth_error
    @handle_remote_protocol_error
    @use_client_session
    async def folio_put_async(
        self, path, payload, query_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any] | None:
        """Asynchronous convenience method to update data in FOLIO.

        Args:
            path (str): FOLIO API endpoint path.
            payload (dict): The data to update as JSON.
            query_params (dict, optional): Additional query parameters. Defaults to None.

        Returns:
            dict: The JSON response from FOLIO.
            None: If the response is empty.
        """
        path = path.lstrip("/")
        req = await self.async_httpx_client.put(
            path,
            json=payload,
            params=query_params,
        )
        req.raise_for_status()
        return self.handle_json_response(req)

    @folio_errors
    @folio_retry_on_auth_error
    @handle_remote_protocol_error
    @use_client_session
    def folio_post(
        self, path, payload, query_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any] | None:
        """Convenience method to post data to FOLIO.

        Args:
            path (str): FOLIO API endpoint path.
            payload (dict): The data to post as JSON.
            query_params (dict, optional): Additional query parameters. Defaults to None.

        Returns:
            dict: The JSON response from FOLIO.
            None: If the response is empty.

        Raises:
            FolioAuthenticationError: For 401 authentication failures.
            FolioPermissionError: For 403 permission denied errors.
            FolioValidationError: For 422 validation errors (invalid data).
            FolioDataConflictError: For 409 conflict errors (duplicate data).
            FolioInternalServerError: For 500 internal server errors.
            FolioBadGatewayError: For 502 bad gateway errors.
            FolioServiceUnavailableError: For 503 service unavailable errors.
            FolioGatewayTimeoutError: For 504 gateway timeout errors.
            FolioConnectionError: For network connectivity issues.
        """
        # Ensure path doesn't start with / for httpx base_url to work properly
        path = path.lstrip("/")
        req = self.httpx_client.post(
            path,
            json=payload,
            params=query_params,
        )
        req.raise_for_status()
        return self.handle_json_response(req)

    @folio_errors
    @folio_retry_on_auth_error
    @handle_remote_protocol_error
    @use_client_session
    async def folio_post_async(
        self, path, payload, query_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any] | None:
        """Asynchronous convenience method to post data to FOLIO.

        Args:
            path (str): FOLIO API endpoint path.
            payload (dict): The data to post as JSON.
            query_params (dict, optional): Additional query parameters. Defaults to None.

        Returns:
            dict: The JSON response from FOLIO.
            None: If the response is empty.
        """
        # Ensure path doesn't start with / for httpx base_url to work properly
        path = path.lstrip("/")
        req = await self.async_httpx_client.post(
            path,
            json=payload,
            params=query_params,
        )
        req.raise_for_status()
        return self.handle_json_response(req)

    @folio_errors
    @folio_retry_on_auth_error
    @handle_remote_protocol_error
    @use_client_session
    def folio_delete(
        self, path, query_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any] | None:
        """Convenience method to delete data in FOLIO.

        Args:
            path (str): FOLIO API endpoint path.
            query_params (dict, optional): Additional query parameters. Defaults to None.

        Returns:
            dict: The response from FOLIO.
            None: If the response is empty.

        Raises:
            FolioAuthenticationError: For 401 authentication failures.
            FolioPermissionError: For 403 permission denied errors.
            FolioResourceNotFoundError: For 404 not found errors (logged but not re-raised).
            FolioInternalServerError: For 500 internal server errors.
            FolioBadGatewayError: For 502 bad gateway errors.
            FolioServiceUnavailableError: For 503 service unavailable errors.
            FolioGatewayTimeoutError: For 504 gateway timeout errors.
            FolioConnectionError: For network connectivity issues.
        """
        # Ensure path doesn't start with / for httpx base_url to work properly
        path = path.lstrip("/")
        req = self.httpx_client.delete(
            path,
            params=query_params,
        )
        return self.handle_delete_response(req, path)

    @folio_errors
    @folio_retry_on_auth_error
    @handle_remote_protocol_error
    @use_client_session
    async def folio_delete_async(
        self, path, query_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any] | None:
        """Asynchronous convenience method to delete data in FOLIO

        Args:
            path (str): FOLIO API endpoint path.
            query_params (dict, optional): Additional query parameters. Defaults to None.

        Returns:
            dict: The response from FOLIO.
            None: If the response is empty.

        Raises:
            FolioAuthenticationError: For 401 authentication failures.
            FolioPermissionError: For 403 permission denied errors.
            FolioResourceNotFoundError: For 404 not found errors (logged but not re-raised).
            FolioInternalServerError: For 500 internal server errors.
            FolioBadGatewayError: For 502 bad gateway errors.
            FolioServiceUnavailableError: For 503 service unavailable errors.
            FolioGatewayTimeoutError: For 504 gateway timeout errors.
            FolioConnectionError: For network connectivity issues.
        """
        # Ensure path doesn't start with / for httpx base_url to work properly
        path = path.lstrip("/")
        req = await self.async_httpx_client.delete(
            path,
            params=query_params,
        )
        return self.handle_delete_response(req, path)

    def get_folio_http_client(self) -> httpx.Client:
        """Returns a httpx client for use in FOLIO communication.

        Creates a synchronous HTTP client configured with the appropriate
        authentication, base URL, timeout, and SSL verification settings.

        Returns:
            httpx.Client: Configured HTTP client for FOLIO API calls.
        """
        return httpx.Client(
            timeout=self.folio_parameters.timeout,
            verify=self.folio_parameters.ssl_verify,
            base_url=self.gateway_url,
            auth=self.folio_auth,
            headers=self.base_headers,
        )

    def get_folio_http_client_async(self) -> httpx.AsyncClient:
        """Returns an async httpx client for use in FOLIO communication.

        Creates an asynchronous HTTP client configured with the appropriate
        authentication, base URL, timeout, and SSL verification settings.

        Returns:
            httpx.AsyncClient: Configured async HTTP client for FOLIO API calls.
        """
        return httpx.AsyncClient(
            timeout=self.folio_parameters.timeout,
            verify=self.folio_parameters.ssl_verify,
            base_url=self.gateway_url,
            auth=self.folio_auth,
            headers=self.base_headers,
        )

    def folio_get_single_object(self, path) -> Dict[str, Any] | None:
        """Fetches data from FOLIO and returns it as a JSON object as-is.

        This is a convenience method that calls folio_get without specifying a key.

        Args:
            path (str): FOLIO API endpoint path.

        Returns:
            dict: The complete JSON response from FOLIO.
        """
        return self.folio_get(path)

    async def folio_get_single_object_async(self, path) -> Dict[str, Any] | None:
        """Asynchronously fetches data from FOLIO and turns it into a json object as is"""
        return await self.folio_get_async(path)

    def get_instance_json_schema(self) -> Dict[str, Any]:
        """Fetches the JSON Schema for instances"""
        return self.get_from_github("folio-org", "mod-inventory-storage", "/ramls/instance.json")

    def get_holdings_schema(self) -> Dict[str, Any]:
        """Fetches the JSON Schema for holdings"""
        try:
            return self.get_from_github(
                "folio-org", "mod-inventory-storage", "/ramls/holdingsrecord.json"
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return self.get_from_github(
                    "folio-org",
                    "mod-inventory-storage",
                    "/ramls/holdings-storage/holdingsRecord.json",
                )
            else:
                raise

    def get_item_schema(self) -> Dict[str, Any]:
        """Fetches the JSON Schema for holdings"""
        return self.get_from_github("folio-org", "mod-inventory-storage", "/ramls/item.json")

    @staticmethod
    def get_github_request_headers() -> Dict[str, str]:
        """Returns headers for GitHub API requests, including optional token.

        If a GITHUB_TOKEN environment variable is set, it will be used for
        authenticated requests to increase rate limits.

        Returns:
            dict: Headers for GitHub API requests.

        Note:
            - Ensure the GITHUB_TOKEN has appropriate permissions for the
              repositories being accessed.
            - Using a token helps avoid hitting GitHub's unauthenticated
              rate limits, which are lower.
        """
        github_headers = {
            "content-type": CONTENT_TYPE_JSON,
            "User-Agent": USER_AGENT_STRING,
        }
        if os.environ.get("GITHUB_TOKEN"):
            logger.info("Using GITHB_TOKEN environment variable for Gihub API Access")
            github_headers["authorization"] = f"token {os.environ.get('GITHUB_TOKEN')}"
        return github_headers

    @staticmethod
    def get_latest_from_github(owner, repo, filepath: str, ssl_verify=True) -> Dict[str, Any]:
        """Fetches the latest version of a FOLIO record schema from a GitHub repository.

        Args:
            owner (str): The GitHub username or organization that owns the repository.
            repo (str): The name of the GitHub repository.
            filepath (str): The path to the file within the repository.
            ssl_verify (bool): Whether to verify SSL certificates. Defaults to True.

        Returns:
            dict: The latest dereferenced version of the schema from the GitHub repository.

        Raises:
            httpx.HTTPStatusError: For HTTP errors from GitHub API.
            httpx.RequestError: For network connectivity issues.
        """
        latest_path = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
        req = httpx.get(
            latest_path,
            headers=FolioClient.get_github_request_headers(),
            timeout=HTTPX_TIMEOUT,
            follow_redirects=True,
            verify=ssl_verify,
        )
        req.raise_for_status()
        latest = json.loads(req.text)
        # print(json.dumps(latest, indent=4))
        latest_tag = latest["tag_name"]
        latest_path = f"https://raw.githubusercontent.com/{owner}/{repo}/{latest_tag}/{filepath}"
        # print(latest_path)
        schema = FolioClient.fetch_github_schema(latest_path)
        dereferenced = jsonref.replace_refs(
            schema,
            loader=FolioClient.fetch_github_schema,
            base_uri=latest_path,
            proxies=False,
        )
        return dereferenced

    def get_from_github(self, owner, repo, filepath: str, ssl_verify=True) -> Dict[str, Any]:  # noqa: S107
        """Fetches a FOLIO record schema from a GitHub repository.

        Args:
            owner (str): The GitHub username or organization that owns the repository.
            repo (str): The name of the GitHub repository.
            filepath (str): The path to the file within the repository.
            ssl_verify (bool): Whether to verify SSL certificates. Defaults to True.

        Returns:
            dict: The dereferenced version of the schema from the GitHub repository.

        Raises:
            httpx.HTTPStatusError: For HTTP errors from GitHub API.
            httpx.RequestError: For network connectivity issues.
        """
        version = self.get_module_version(repo)
        if not version:
            f_path = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
            req = httpx.get(
                f_path,
                headers=FolioClient.get_github_request_headers(),
                timeout=self.folio_parameters.timeout,
                follow_redirects=True,
                verify=ssl_verify,
            )
            req.raise_for_status()
            latest = json.loads(req.text)
            # print(json.dumps(latest, indent=4))
            latest_tag = latest["tag_name"]
            f_path = f"https://raw.githubusercontent.com/{owner}/{repo}/{latest_tag}/{filepath}"
        else:
            f_path = f"https://raw.githubusercontent.com/{owner}/{repo}/{version}/{filepath}"
        # print(latest_path)
        schema = FolioClient.fetch_github_schema(f_path)
        dereferenced = jsonref.replace_refs(
            schema,
            loader=FolioClient.fetch_github_schema,
            base_uri=f_path,
            proxies=False,
        )
        return dereferenced

    @staticmethod
    def fetch_github_schema(schema_url) -> Dict[str, Any]:
        """
        Fixes relative $ref references in the schema that refer to submodules,
        like raml-util.This method can be used as a loader in
        `jsonref.replace_refs`.

        Params
            schema_url: The URL of the schema to fix.

        Returns
            The fixed schema.

        Raises:
            httpx.HTTPStatusError: For HTTP errors from GitHub API.
            httpx.RequestError: For network connectivity issues.
        """
        schema_response = httpx.get(
            schema_url,
            headers=FolioClient.get_github_request_headers(),
            timeout=HTTPX_TIMEOUT,
            follow_redirects=True,
        )
        schema_response.raise_for_status()
        fix_refs = schema_response.text.replace("../raml-util", RAML_UTIL_URL).replace(
            "raml-util", RAML_UTIL_URL
        )
        if schema_url.endswith("yaml"):
            return to_json_schema(yaml.safe_load(fix_refs))
        elif schema_url.endswith("json") or schema_url.endswith("schema"):
            return json.loads(fix_refs)
        else:
            raise ValueError(f"Unknown file ending in {schema_url}")

    def get_module_version(self, module_name: str) -> str | None:
        if res := next(
            (
                f"v{a.replace(f'{module_name}-', '')}"
                for a in self.module_versions
                if a.startswith(module_name)
            ),
            "",
        ):
            print(module_name)
            return res if "snapshot" not in res.lower() else None
        else:
            raise ValueError(f"Module named {module_name} was not found in the tenant")

    def get_user_schema(self) -> Dict[str, Any]:
        """Fetches the JSON Schema for users"""
        return self.get_from_github("folio-org", "mod-users", "/ramls/userdata.json")

    def get_location_id(self, location_code) -> str | None:
        """Returns the location ID based on a location code"""
        try:
            return next(
                (l["id"] for l in self.locations if location_code.strip() == l["code"]),
                (
                    next(
                        loc["id"]
                        for loc in self.locations
                        if loc["code"] in ["catch_all", "default", "Default", "ATDM"]
                    )
                ),
            )
        except Exception as exc:
            raise ValueError(
                (
                    f"No location with code '{location_code}' in locations. "
                    "No catch_all/default location either"
                )
            ) from exc

    def get_metadata_construct(self) -> Dict[str, str]:
        """creates a metadata construct with the current API user_id
        attached"""
        user_id = self.current_user
        return {
            "createdDate": datetime.now(tz=tz.utc).isoformat(timespec="milliseconds"),
            "createdByUserId": user_id,
            "updatedDate": datetime.now(tz=tz.utc).isoformat(timespec="milliseconds"),
            "updatedByUserId": user_id,
        }

    def get_loan_policy_id(self, item_type_id, loan_type_id, patron_group_id, location_id) -> str:
        """Retrieves a loan policy from FOLIO, or uses a cached one"""

        lp_hash = get_loan_policy_hash(item_type_id, loan_type_id, patron_group_id, location_id)
        if lp_hash in self.loan_policies:
            return self.loan_policies[lp_hash]
        payload = {
            "item_type_id": item_type_id,
            "loan_type_id": loan_type_id,
            "patron_type_id": patron_group_id,
            "location_id": location_id,
        }
        path = "/circulation/rules/loan-policy"
        try:
            response = self.folio_get(path, query_params=payload)
        except httpx.HTTPError as response_error:
            response_error.args += ("Request getting Loan Policy ID went wrong!",)
            raise
        lp_id = response["loanPolicyId"]
        self.loan_policies[lp_hash] = lp_id
        return lp_id

    def get_all_ids(self, path, query=""):
        resp = self.folio_get(path)
        name = next(f for f in [*resp] if f != "totalRecords")
        gs = self.folio_get_all(path, name, query)
        return [f["id"] for f in gs]

    @use_client_session
    def put_user(self, user) -> Dict[str, Any] | None:
        """Updates a FOLIO user record"""
        url = f"/users/{user['id']}"
        print(url)
        try:
            return self.folio_put(url, user)
        except httpx.HTTPStatusError as exc:
            print(f"Error updating user {user['username']}: {exc}")
            raise


def get_loan_policy_hash(item_type_id, loan_type_id, patron_type_id, shelving_location_id) -> str:
    """Generate a hash of the circulation rule parameters that key a loan policy"""
    return str(
        hashlib.sha224(
            ("".join([item_type_id, loan_type_id, patron_type_id, shelving_location_id])).encode(
                "utf-8"
            )
        ).hexdigest()
    )


def validate_uuid(my_uuid) -> bool:
    """Validates that a string is a valid UUID"""
    reg = "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"  # noqa
    pattern = re.compile(reg)
    return bool(pattern.match(my_uuid))
