from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime
from datetime import timezone as tz
from typing import Any, AsyncGenerator, Dict, Generator, List, Union
from urllib.parse import urljoin
from warnings import warn

import httpx
import jsonref
import yaml
from httpx._types import CookieTypes
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
from folioclient.exceptions import FolioClientClosed

# Constants
CONTENT_TYPE_JSON = "application/json"

SORTBY_ID = "sortBy id"

try:
    HTTPX_TIMEOUT = int(os.environ.get("FOLIOCLIENT_HTTP_TIMEOUT"))
except TypeError:
    HTTPX_TIMEOUT = None

RAML_UTIL_URL = "https://raw.githubusercontent.com/folio-org/raml/raml1.0"

USER_AGENT_STRING = "Folio Client (https://github.com/FOLIO-FSE/FolioClient)"

# Set up logger
logger = logging.getLogger("FolioClient")


class FolioHeadersDict(dict):
    """Custom dict wrapper for folio_headers that intercepts x-okapi-tenant assignments"""

    def __init__(self, folio_client: "FolioClient", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._folio_client = folio_client

    def __setitem__(self, key: str, value: str) -> None:
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

    def update(self, other: Dict[str, str] = None) -> None:
        """Override update to handle x-okapi-tenant specially"""
        if isinstance(other, dict) and "x-okapi-tenant" in other:
            # Handle x-okapi-tenant specially
            tenant_id = other["x-okapi-tenant"]  # Read-only access
            warn(
                "Setting x-okapi-tenant via okapi_headers is deprecated. "
                "Use folio_client.tenant_id = 'your_tenant' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            self._folio_client.tenant_id = tenant_id
            other = {k: v for k, v in other.items() if k != "x-okapi-tenant"}

        # Update with remaining headers
        super().update(other)


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
        ssl_verify (bool): Whether to verify SSL certificates. Default is True.
        okapi_url (keyword-only, str, optional): Deprecated. Use gateway_url instead.
    """  # noqa: E501

    def __init__(
        self,
        gateway_url: str,
        tenant_id: str,
        username: str,
        password: str,
        *,
        ssl_verify: bool = True,
        okapi_url: str = None,
    ):
        if okapi_url:
            warn(
                "okapi_url argument is deprecated. Use gateway_url instead. Support for okapi_url will be removed in a future release.",  # noqa: E501
                DeprecationWarning,
                stacklevel=2,
            )
        if not ssl_verify:
            warn(
                "ssl_verify argument is deprecated. It will be removed in a future release.",
                DeprecationWarning,
                stacklevel=2,
            )
        self.missing_location_codes = set()
        self.loan_policies = {}
        self.cql_all = "?query=cql.allRecords=1"
        self.folio_parameters: FolioConnectionParameters = FolioConnectionParameters(
            gateway_url=okapi_url or gateway_url,
            tenant_id=tenant_id,
            username=username,
            password=password,
            ssl_verify=ssl_verify,
            timeout=HTTPX_TIMEOUT,
        )
        self.folio_auth: FolioAuth = FolioAuth(self.folio_parameters)
        self.httpx_client: httpx.Client | None = None
        self.async_httpx_client: httpx.AsyncClient | None = None
        self.base_headers = {
            "content-type": CONTENT_TYPE_JSON,
        }
        self._folio_headers: FolioHeadersDict = FolioHeadersDict(self)
        self.is_closed = False
        self._ecs_central_tenant_id: str | None = None
        self._ecs_checked = False

    def __repr__(self) -> str:
        if self.is_ecs:
            return (
                f"FolioClient for ECS central tenant {self._ecs_central_tenant_id}"
                f" (active tenant: {self.tenant_id}) at {self.gateway_url} as {self.username}"
            )
        return f"FolioClient for tenant {self.tenant_id} at {self.gateway_url} as {self.username}"

    def __enter__(self):
        """Context manager for FolioClient"""
        self.httpx_client = self.get_folio_http_client()
        self.async_httpx_client = self.get_folio_http_client_async()
        # Call ECS check after clients are initialized
        self._initial_ecs_check()
        return self

    @handle_remote_protocol_error
    @use_client_session
    def __exit__(self, exc_type, exc_value, traceback):
        """Context manager exit method"""
        if self.cookies:
            logger.info("logging out...")
            logout = self.httpx_client.post(
                urljoin(self.gateway_url, "authn/logout"),
            )
            try:
                logout.raise_for_status()
                logger.info("Logged out")
            except httpx.HTTPStatusError:
                if logout.status_code == 404:
                    logger.warning("Logout endpoint not found, skipping logout.")
                else:
                    logger.error(f"Logout failed: ({logout.status_code}) {logout.text}")
            except httpx.HTTPConnectError:
                logger.warning("Logout endpoint not reachable, skipping logout.")
        if hasattr(self, "httpx_client") and self.httpx_client and not self.httpx_client.is_closed:
            self.httpx_client.close()

        self.is_closed = True
        self.folio_parameters = None
        if hasattr(self, "folio_auth"):
            self.folio_auth._token = None
            self.folio_auth._params = None

    async def __aenter__(self):
        """Asynchronous context manager for FolioClient"""
        self.httpx_client = self.get_folio_http_client()
        self.async_httpx_client = self.get_folio_http_client_async()
        # Call ECS check after clients are initialized
        self._initial_ecs_check()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        """Asynchronous context manager exit method"""
        if self.cookies:
            logger.info("logging out...")
            logout = await self.async_httpx_client.post(
                urljoin(self.gateway_url, "authn/logout"),
            )
            try:
                logout.raise_for_status()
                logger.info("Logged out")
            except httpx.HTTPStatusError:
                if logout.status_code == 404:
                    logger.warning("Logout endpoint not found, skipping logout.")
                else:
                    logger.error(f"Logout failed: ({logout.status_code}) {logout.text}")
            except httpx.HTTPConnectError:
                logger.warning("Logout endpoint not reachable, skipping logout.")
        if (
            hasattr(self, "async_httpx_client")
            and self.async_httpx_client
            and not self.async_httpx_client.is_closed
        ):
            await self.async_httpx_client.aclose()
        if hasattr(self, "httpx_client") and self.httpx_client and not self.httpx_client.is_closed:
            self.httpx_client.close()
        self.is_closed = True
        self.folio_parameters = None
        if hasattr(self, "folio_auth"):
            self.folio_auth._token = None
            self.folio_auth._params = None

    @property
    def okapi_url(self) -> str:
        """
        Convenience property for backwards-compatibility with tools built for
        pre-Sunflower FOLIO systems.
        """
        warn(
            "FolioClient.okapi_url is deprecated. Use gateway_url instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.gateway_url

    @okapi_url.setter
    def okapi_url(self, okapi_url: str) -> None:
        """
        Setter for okapi_url property, to maintain backwards compatibility.
        """
        warn(
            "FolioClient.okapi_url is deprecated. Use gateway_url instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.gateway_url = okapi_url

    def close(self):
        self.__exit__(None, None, None)

    async def async_close(self):
        """Manually close the FolioClient object

        This should only be used when running FolioClient outside a context manager
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
    def tenant_id(self):
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
    def ssl_verify(self) -> bool:
        """Whether SSL verification is enabled [DEPRECATED].

        This is a convenience property that returns the ssl_verify value from the
        FolioConnectionParameters.
        """
        warn(
            "FolioClient.ssl_verify is deprecated and will be removed in a future release.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.folio_parameters.ssl_verify

    @property
    def http_timeout(self) -> int | None:
        """The HTTP timeout value.

        This is a convenience property that returns the timeout value from the
        FolioConnectionParameters.
        """
        return self.folio_parameters.timeout

    def _clear_cached_properties(self, *property_names: str) -> None:
        """Clear cached properties specified or all cached properties if none are specified."""

        # Get the properties to clear
        if property_names:
            props_to_clear = property_names
        else:
            props_to_clear = [
                attr_name
                for attr_name in dir(self.__class__)
                if not attr_name.startswith("_") and self._is_cached_property(attr_name)
            ]
        # Clear each property
        for prop_name in props_to_clear:
            self._clear_single_cached_property(prop_name)

    def _is_cached_property(self, attr_name: str) -> bool:
        """Check if an attribute is a cached_property"""
        try:
            attr = getattr(self.__class__, attr_name)
            return isinstance(attr, cached_property)
        except AttributeError:
            return False

    def _clear_single_cached_property(self, prop_name):
        """Clear a single cached property if it exists"""
        cached_attr_name = f"_{prop_name}"
        if hasattr(self, cached_attr_name):
            delattr(self, cached_attr_name)

    @cached_property
    def current_user(self) -> str:
        """
        This method returns the current user id for the user that is logged in, based on username.
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
        """Returns a list of identifier types."""
        return list(self.folio_get_all("/identifier-types", "identifierTypes", self.cql_all, 1000))

    @cached_property
    def module_versions(self) -> List[str]:
        """Returns a list of module versions for the current tenant."""
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
        """
        Returns a list of statistical codes.
        """
        return list(
            self.folio_get_all("/statistical-codes", "statisticalCodes", self.cql_all, 1000)
        )

    @cached_property
    def contributor_types(self) -> List[Dict[str, Any]]:
        """Returns a list of contributor types."""
        return list(
            self.folio_get_all("/contributor-types", "contributorTypes", self.cql_all, 1000)
        )

    @cached_property
    def contrib_name_types(self) -> List[Dict[str, Any]]:
        """Returns a list of contributor name types."""
        return list(
            self.folio_get_all(
                "/contributor-name-types", "contributorNameTypes", self.cql_all, 1000
            )
        )

    @cached_property
    def instance_types(self) -> List[Dict[str, Any]]:
        """Returns a list of instance types."""
        return list(self.folio_get_all("/instance-types", "instanceTypes", self.cql_all, 1000))

    @cached_property
    def instance_formats(self) -> List[Dict[str, Any]]:
        """Returns a list of instance formats."""
        return list(self.folio_get_all("/instance-formats", "instanceFormats", self.cql_all, 1000))

    @cached_property
    def alt_title_types(self) -> List[Dict[str, Any]]:
        """Returns a list of alternative title types."""
        return list(
            self.folio_get_all(
                "/alternative-title-types", "alternativeTitleTypes", self.cql_all, 1000
            )
        )

    @cached_property
    def locations(self) -> List[Dict[str, Any]]:
        """Returns a list of locations."""
        return list(self.folio_get_all("/locations", "locations", self.cql_all, 1000))

    @cached_property
    def electronic_access_relationships(self) -> List[Dict[str, Any]]:
        """Returns a list of electronic access relationships."""
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
        """Returns a list of instance note types."""
        return list(
            self.folio_get_all("/instance-note-types", "instanceNoteTypes", self.cql_all, 1000)
        )

    @cached_property
    def class_types(self) -> List[Dict[str, Any]]:
        """Returns a list of classification types."""
        return list(
            self.folio_get_all("/classification-types", "classificationTypes", self.cql_all, 1000)
        )

    @cached_property
    def organizations(self) -> List[Dict[str, Any]]:
        """Returns a list of organizations."""
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
        """Returns a list of holding note types."""
        return list(
            self.folio_get_all("/holdings-note-types", "holdingsNoteTypes", self.cql_all, 1000)
        )

    @cached_property
    def call_number_types(self) -> List[Dict[str, Any]]:
        """Returns a list of call number types."""
        return list(
            self.folio_get_all("/call-number-types", "callNumberTypes", self.cql_all, 1000)
        )

    @cached_property
    def holdings_types(self) -> List[Dict[str, Any]]:
        """Returns a list of holdings types."""
        return list(self.folio_get_all("/holdings-types", "holdingsTypes", self.cql_all, 1000))

    @cached_property
    def modes_of_issuance(self) -> List[Dict[str, Any]]:
        """Returns a list of modes of issuance."""
        return list(self.folio_get_all("/modes-of-issuance", "issuanceModes", self.cql_all, 1000))

    @cached_property
    def authority_source_files(self) -> List[Dict[str, Any]]:
        """Cached property for all configured authority source files"""
        return list(
            self.folio_get_all(
                "/authority-source-files", "authoritySourceFiles", self.cql_all, 1000
            )
        )

    @cached_property
    def subject_types(self) -> List[Dict[str, Any]]:
        """Cached property for all configured subject types"""
        return list(self.folio_get_all("/subject-types", "subjectTypes", self.cql_all, 1000))

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
        if self.is_closed:
            raise FolioClientClosed()

        headers = {
            "x-okapi-token": self.okapi_token,
        }
        if self._folio_headers:
            self._folio_headers.update(headers)
        else:
            self._folio_headers = FolioHeadersDict(self)
            self._folio_headers.update(self.base_headers)
            self._folio_headers.update(headers)
        return self._folio_headers

    @folio_headers.setter
    def folio_headers(self, headers_dict: Dict[str, str]) -> None:
        """
        Setter for folio_headers that allows setting custom headers while preserving
        backward compatibility for x-okapi-tenant.

        Parameters:
            headers_dict (Dict[str, str]): Dictionary of headers to set
        """
        if self.is_closed:
            raise FolioClientClosed()

        new_headers = FolioHeadersDict(self)
        new_headers.update(headers_dict)
        self._folio_headers = new_headers

    @folio_headers.deleter
    def folio_headers(self) -> None:
        """
        Deleter for folio_headers that clears the private _folio_headers dictionary, which will
        revert folio_headers to using base_headers
        """
        if self.is_closed:
            raise FolioClientClosed()

        self._folio_headers.clear()

    @property
    def okapi_headers(self) -> Dict[str, str]:
        """
        Property that returns okapi headers with the current valid Okapi token.

        .. deprecated::
           Use :attr:`folio_headers` instead. This property will be removed in a future release.

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
        """
        Setter for okapi_headers that allows setting custom headers while preserving
        backward compatibility for x-okapi-tenant.

        .. deprecated::
           Use :attr:`folio_headers` instead. This property will be removed in a future release.

        Parameters:
            headers_dict (Dict[str, str]): Dictionary of headers to set
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
        """
        Deleter for okapi_headers that clears the private _okapi_headers dictionary.

        .. deprecated::
           Use :attr:`folio_headers` instead. This property will be removed in a future release.
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
        if not self.is_closed:
            return self.folio_auth.folio_auth_token
        else:
            raise FolioClientClosed()

    @property
    def refresh_token(self) -> str:
        if self.is_closed:
            raise FolioClientClosed()
        else:
            _ = self.okapi_token  # Ensure token is valid
            return self.folio_auth.folio_refresh_token

    @property
    def cookies(self) -> CookieTypes:
        """
        Property that returns the httpx cookies object for the current session, and
        refreshes them if needed. Raises FolioClientClosed if the client is closed.
        """
        if not self.is_closed and self.folio_auth._token:
            _ = self.okapi_token  # Ensure token is valid
            return self.folio_auth._token.cookies
        else:
            raise FolioClientClosed()

    def _initial_ecs_check(self):
        """Check if initial tenant_id value is an ecs_central_tenant_id"""
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
    def access_token_expires(self) -> datetime:
        """
        Property that returns the expiration time of the current access token.
        """
        return self.folio_auth._token.expires_at

    @property
    def folio_token_expires(self) -> datetime:
        """
        Property that returns the expiration time of the current access token.

        .. deprecated::
           Use :attr:`access_token_expires` instead. This property will be removed in a future
           release.
        """
        warn(
            "FolioClient.folio_token_expires is deprecated. Use access_token_expires instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.access_token_expires

    @folio_retry_on_server_error
    def login(self):
        """Logs into FOLIO in order to get a new FOLIO access token (synchronous)

        This method should not be necessary to call directly, as FolioClient
        automatically handles token refresh as needed, but is provided for backwards-compatibility.
        """
        if not self.is_closed:
            self.folio_auth._token = (
                self.folio_auth._do_sync_auth()
            )  # Force re-authentication if needed
        else:
            raise FolioClientClosed()

    @folio_retry_on_server_error
    async def async_login(self):
        """Logs into FOLIO in order to get a new FOLIO access token (async)

        This method should not be necessary to call directly, as FolioClient
        automatically handles token refresh as needed, but is provided as a convenience.
        """
        if not self.is_closed:
            self.folio_auth._token = await self.folio_auth._do_async_auth()
        else:
            raise FolioClientClosed()

    def logout(self):
        """Alias for `close`"""
        if not self.is_closed:
            self.close()
        else:
            raise FolioClientClosed()

    async def async_logout(self):
        """Alias for `async_close`"""
        if not self.is_closed:
            await self.async_close()
        else:
            raise FolioClientClosed()

    def folio_get_all(
        self,
        path: str,
        key: str | None = None,
        query: str | None = None,
        limit: int = 10,
        **kwargs,
    ) -> Generator:
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
        if SORTBY_ID in query:
            return self._folio_get_all_by_id_offset(path, key, query, limit, **kwargs)
        else:
            return self._folio_get_all(path, key, query, limit, **kwargs)

    @use_client_session_with_generator
    def _folio_get_all(
        self,
        path: str,
        key: str | None = None,
        query: str | None = None,
        limit: int = 10,
        **kwargs,
    ) -> Generator:
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
        query = query or " ".join((self.cql_all, SORTBY_ID))
        query_params: Dict[str, Any] = self._construct_query_parameters(
            query=query, limit=limit, offset=offset * limit, **kwargs
        )
        temp_res = self.folio_get(path, key, query_params=query_params)
        yield from temp_res
        while len(temp_res) == limit:
            offset += 1
            temp_res = self.folio_get(
                path,
                key,
                query_params=self._construct_query_parameters(
                    query=query, limit=limit, offset=offset * limit, **kwargs
                ),
            )
            yield from temp_res
        offset += 1
        yield from self.folio_get(
            path,
            key,
            query_params=self._construct_query_parameters(
                query=query, limit=limit, offset=offset * limit, **kwargs
            ),
        )

    async def folio_get_all_async(
        self,
        path: str,
        key: str | None = None,
        query: str | None = None,
        limit: int = 10,
        **kwargs,
    ) -> AsyncGenerator:
        """
        Asynchronously fetches ALL data objects from FOLIO matching `query` in
        `limit`-size chunks and provides an async iterable object yielding a single
        record at a time until all records have been returned.

        Automatically uses id-based offset pagination if the query is sorted by id.

        Parameters:
            path (str): The API endpoint path.
            key (str): The key in the JSON response that contains the array of results.
            query (str): The query string to filter the data objects.
            limit (int): The maximum number of records to fetch in each chunk.
            **kwargs: Additional URL parameters to pass to `path`.
        """
        if SORTBY_ID in query or not query:
            return self._folio_get_all_by_id_offset_async(path, key, query, limit, **kwargs)
        else:
            return self._folio_get_all_async(path, key, query, limit, **kwargs)

    @use_client_session_with_generator
    async def _folio_get_all_async(
        self,
        path: str,
        key: str | None = None,
        query: str | None = None,
        limit: int = 10,
        **kwargs,
    ) -> AsyncGenerator:
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
        query = query or " ".join((self.cql_all, SORTBY_ID))
        query_params: Dict[str, Any] = self._construct_query_parameters(
            query=query, limit=limit, offset=offset * limit, **kwargs
        )
        temp_res = await self.folio_get_async(path, key, query_params=query_params)
        for item in temp_res:
            yield item
        while len(temp_res) == limit:
            offset += 1
            temp_res = await self.folio_get_async(
                path,
                key,
                query_params=self._construct_query_parameters(
                    query=query, limit=limit, offset=offset * limit, **kwargs
                ),
            )
            for item in temp_res:
                yield item
        offset += 1
        final_res = await self.folio_get_async(
            path,
            key,
            query_params=self._construct_query_parameters(
                query=query, limit=limit, offset=offset * limit, **kwargs
            ),
        )
        for item in final_res:
            yield item

    @use_client_session_with_generator
    def _folio_get_all_by_id_offset(
        self,
        path: str,
        key: str | None = None,
        query: str | None = None,
        limit: int = 10,
        **kwargs,
    ) -> Generator:
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
        offset = None
        if not query:
            query = "cql.allRecords=1 " + SORTBY_ID
        if SORTBY_ID not in query:
            raise ValueError("FOLIO query must be sorted by ID")
        query = query or " ".join((self.cql_all, SORTBY_ID))
        query_params: Dict[str, Any] = self._construct_query_parameters(
            query=query, limit=limit, **kwargs
        )
        temp_res = self.folio_get(path, key, query_params=query_params)
        try:
            offset = temp_res[-1]["id"]
        except IndexError:
            yield from temp_res
            return
        yield from temp_res
        while len(temp_res) == limit:
            query_params = self._construct_query_parameters(query=query, limit=limit, **kwargs)
            query_params["query"] = f'id>"{offset}" and ' + query_params["query"]
            temp_res = self.folio_get(
                path,
                key,
                query_params=query_params,
            )
            try:
                offset = temp_res[-1]["id"]
            except IndexError:
                yield from temp_res
                return
            yield from temp_res
        query_params = self._construct_query_parameters(query=query, limit=limit, **kwargs)
        query_params["query"] = f'id>"{offset}" and ' + query_params["query"]
        yield from self.folio_get(
            path,
            key,
            query_params=query_params,
        )

    @use_client_session_with_generator
    async def _folio_get_all_by_id_offset_async(
        self,
        path: str,
        key: str | None = None,
        query: str | None = None,
        limit: int = 10,
        **kwargs,
    ) -> AsyncGenerator:
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
        # Set up query and validate
        query = self._prepare_id_offset_query(query)

        # Initial fetch
        query_params: Dict[str, Any] = self._construct_query_parameters(
            query=query, limit=limit, **kwargs
        )
        temp_res = await self.folio_get_async(path, key, query_params=query_params)

        # Process initial results
        if not temp_res:
            return

        for item in temp_res:
            yield item
        offset = self._get_last_id(temp_res)

        # Continue fetching while we get full pages
        while len(temp_res) == limit:
            temp_res = await self._fetch_next_page(path, key, query, limit, offset, **kwargs)
            if not temp_res:
                return
            for item in temp_res:
                yield item
            offset = self._get_last_id(temp_res)

    def _prepare_id_offset_query(self, query: str | None) -> str:
        """Prepare and validate query for ID offset pagination"""
        if not query:
            query = "cql.allRecords=1 " + SORTBY_ID
        if SORTBY_ID not in query:
            raise ValueError("FOLIO query must be sorted by ID")
        return query or " ".join((self.cql_all, SORTBY_ID))

    def _get_last_id(self, results: List[Dict[str, Any]]) -> str | None:
        """Get the last ID from results for pagination"""
        return results[-1]["id"] if results else None

    async def _fetch_next_page(
        self, path: str, key: str, query: str, limit: int, offset: str, **kwargs
    ) -> List[Dict[str, Any]]:
        """Fetch the next page of results using ID offset"""
        query_params = self._construct_query_parameters(query=query, limit=limit, **kwargs)
        query_params["query"] = f'id>"{offset}" and ' + query_params["query"]
        return await self.folio_get_async(path, key, query_params=query_params)

    def _construct_query_parameters(self, **kwargs) -> Dict[str, Any]:
        """Private method to construct query parameters for folio_get or httpx client calls

        Parameters:
            **kwargs: URL parameters to pass to `path`.
        """
        params = kwargs
        if query := kwargs.get("query"):
            if query.startswith(("?", "query=")):  # Handle previous query specification syntax
                params["query"] = query.split("=", maxsplit=1)[1]
            else:
                params["query"] = query
        return params

    def get_all(self, path, key=None, query=""):
        """Alias for `folio_get_all`"""
        return self.folio_get_all(path, key, query)

    async def get_all_async(self, path, key=None, query=""):
        """Async alias for `folio_get_all_async`

        Note: This method wraps folio_get_all_async() for consistency.
        For direct access, use folio_get_all_async() instead.
        """
        async for item in self.folio_get_all_async(path, key, query):
            yield item

    @folio_retry_on_server_error
    @folio_retry_on_auth_error
    def folio_get(self, path, key=None, query="", query_params: dict = None):
        """
        Fetches data from FOLIO and turns it into a json object
        Parameters:
        path: FOLIO API endpoint path
        key: Key in JSON response from FOLIO that includes the array of results for query APIs
        query: For backwards-compatibility
        query_params: Additional query parameters for the specified path. May also be used for
                `query`
        """
        return self._folio_get(path, key, query, query_params=query_params)

    @folio_retry_on_server_error
    @folio_retry_on_auth_error
    async def folio_get_async(self, path, key=None, query="", query_params: dict = None):
        """
        Asynchronously fetches data from FOLIO and turns it into a json object
        Parameters:
        path: FOLIO API endpoint path
        key: Key in JSON response from FOLIO that includes the array of results for query APIs
        query: For backwards-compatibility
        query_params: Additional query parameters for the specified path. May also be used for
                `query`
        """
        return await self._folio_get_async(path, key, query, query_params=query_params)

    @handle_remote_protocol_error
    @use_client_session
    def _folio_get(self, path, key=None, query="", query_params: dict = None):
        """
        Private method that implements `folio_get`
        """
        url = urljoin(self.gateway_url, path.lstrip("/")).rstrip("/")
        if query and query_params:
            query_params = self._construct_query_parameters(query=query, **query_params)
        elif query:
            query_params = self._construct_query_parameters(query=query)
        req = self.httpx_client.get(url, params=query_params)
        req.raise_for_status()
        return req.json()[key] if key else req.json()

    @handle_remote_protocol_error
    @use_client_session
    async def _folio_get_async(self, path, key=None, query="", query_params: dict = None):
        """
        Private async method that implements `folio_get_async`
        """
        url = urljoin(self.gateway_url, path.lstrip("/")).rstrip("/")
        if query and query_params:
            query_params = self._construct_query_parameters(query=query, **query_params)
        elif query:
            query_params = self._construct_query_parameters(query=query)
        req = await self.async_httpx_client.get(url, params=query_params)
        req.raise_for_status()
        return req.json()[key] if key else req.json()

    @folio_retry_on_auth_error
    @handle_remote_protocol_error
    @use_client_session
    def folio_put(self, path, payload, query_params: dict = None):
        """Convenience method to update data in FOLIO"""
        url = path.rstrip("/")
        req = self.httpx_client.put(
            url,
            json=payload,
            params=query_params,
        )
        req.raise_for_status()
        try:
            return req.json()
        except json.JSONDecodeError:
            return None

    @folio_retry_on_auth_error
    @handle_remote_protocol_error
    @use_client_session
    async def folio_put_async(self, path, payload, query_params: dict = None):
        """Asynchronous convenience method to update data in FOLIO"""
        url = path.rstrip("/")
        req = await self.async_httpx_client.put(
            url,
            json=payload,
            params=query_params,
        )
        req.raise_for_status()
        try:
            return req.json()
        except json.JSONDecodeError:
            return None

    @folio_retry_on_auth_error
    @handle_remote_protocol_error
    @use_client_session
    def folio_post(self, path, payload, query_params: dict = None):
        """Convenience method to post data to FOLIO"""
        url = urljoin(self.gateway_url, path.lstrip("/")).rstrip("/")
        req = self.httpx_client.post(
            url,
            json=payload,
            params=query_params,
        )
        req.raise_for_status()
        try:
            return req.json()
        except json.JSONDecodeError:
            return None

    @folio_retry_on_auth_error
    @handle_remote_protocol_error
    @use_client_session
    async def folio_post_async(self, path, payload, query_params: dict = None):
        """Asynchronous convenience method to post data to FOLIO"""
        url = urljoin(self.gateway_url, path.lstrip("/")).rstrip("/")
        req = await self.async_httpx_client.post(
            url,
            json=payload,
            params=query_params,
        )
        req.raise_for_status()
        try:
            return req.json()
        except json.JSONDecodeError:
            return None

    @folio_retry_on_auth_error
    @handle_remote_protocol_error
    @use_client_session
    def folio_delete(self, path, query_params: dict = None):
        """Convenience method to delete data in FOLIO"""
        url = urljoin(self.gateway_url, path.lstrip("/")).rstrip("/")
        req = self.httpx_client.delete(
            url,
            params=query_params,
        )
        try:
            req.raise_for_status()
        except httpx.HTTPStatusError:
            if req.status_code == 404:
                logger.warning(f"Resource not found: {path}")
            else:
                raise
        try:
            return req.json()
        except json.JSONDecodeError:
            # If the response is successful + empty, return None
            if req.status_code == 204:
                logger.info(f"Resource deleted: {path} ({req.status_code})")
                return None
            else:
                logger.error(f"Failed to decode JSON response: {req.text}")
                raise

    @folio_retry_on_auth_error
    @handle_remote_protocol_error
    @use_client_session
    async def folio_delete_async(self, path, query_params: dict = None):
        """Asynchronous convenience method to delete data in FOLIO"""
        url = urljoin(self.gateway_url, path.lstrip("/")).rstrip("/")
        req = await self.async_httpx_client.delete(
            url,
            params=query_params,
        )
        try:
            req.raise_for_status()
        except httpx.HTTPStatusError:
            if req.status_code == 404:
                logger.warning(f"Resource not found: {path}")
            else:
                raise
        try:
            return req.json()
        except json.JSONDecodeError:
            # If the response is successful + empty, return None
            if req.status_code == 204:
                logger.info(f"Resource deleted: {path} ({req.status_code})")
                return None
            else:
                logger.error(f"Failed to decode JSON response: {req.text}")
                raise

    def get_folio_http_client(self):
        """Returns a httpx client for use in FOLIO communication"""
        return httpx.Client(
            timeout=self.http_timeout,
            verify=self.ssl_verify,
            base_url=self.gateway_url,
            auth=self.folio_auth,
            headers=self.base_headers,
        )

    def get_folio_http_client_async(self):
        """Returns an async httpx client for use in FOLIO communication"""
        return httpx.AsyncClient(
            timeout=self.http_timeout,
            verify=self.ssl_verify,
            base_url=self.gateway_url,
            auth=self.folio_auth,
            headers=self.base_headers,
        )

    def folio_get_single_object(self, path):
        """Fetches data from FOLIO and turns it into a json object as is"""
        return self.folio_get(path)

    async def folio_get_single_object_async(self, path):
        """Asynchronously fetches data from FOLIO and turns it into a json object as is"""
        return await self.folio_get_async(path)

    def get_instance_json_schema(self):
        """Fetches the JSON Schema for instances"""
        return self.get_from_github("folio-org", "mod-inventory-storage", "/ramls/instance.json")

    def get_holdings_schema(self):
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

    def get_item_schema(self):
        """Fetches the JSON Schema for holdings"""
        return self.get_from_github("folio-org", "mod-inventory-storage", "/ramls/item.json")

    @staticmethod
    def get_github_request_headers():
        github_headers = {
            "content-type": CONTENT_TYPE_JSON,
            "User-Agent": USER_AGENT_STRING,
        }
        if os.environ.get("GITHUB_TOKEN"):
            logger.info("Using GITHB_TOKEN environment variable for Gihub API Access")
            github_headers["authorization"] = f"token {os.environ.get('GITHUB_TOKEN')}"
        return github_headers

    @staticmethod
    def get_latest_from_github(owner, repo, filepath: str, ssl_verify=True):  # noqa: S107
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

    def get_from_github(self, owner, repo, filepath: str, ssl_verify=True):  # noqa: S107
        version = self.get_module_version(repo)
        if not version:
            f_path = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
            req = httpx.get(
                f_path,
                headers=FolioClient.get_github_request_headers(),
                timeout=self.http_timeout,
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
    def fetch_github_schema(schema_url):
        """
        Fixes relative $ref references in the schema that refer to submodules,
        like raml-util.This method can be used as a loader in
        `jsonref.replace_refs`.

        Params
            schema_url: The URL of the schema to fix.

        Returns
            The fixed schema.
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

    def get_module_version(self, module_name: str):
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

    def get_user_schema(self):
        """Fetches the JSON Schema for users"""
        return self.get_from_github("folio-org", "mod-users", "/ramls/userdata.json")

    def get_location_id(self, location_code):
        """returns the location ID based on a location code"""
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

    def get_metadata_construct(self):
        """creates a metadata construct with the current API user_id
        attached"""
        user_id = self.current_user
        return {
            "createdDate": datetime.now(tz=tz.utc).isoformat(timespec="milliseconds"),
            "createdByUserId": user_id,
            "updatedDate": datetime.now(tz=tz.utc).isoformat(timespec="milliseconds"),
            "updatedByUserId": user_id,
        }

    def get_loan_policy_id(self, item_type_id, loan_type_id, patron_group_id, location_id):
        """retrieves a loan policy from FOLIO, or uses a chached one"""

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
    def put_user(self, user):
        """Fetches data from FOLIO and turns it into a json object as is"""
        url = f"/users/{user['id']}"
        print(url)
        try:
            _ = self.folio_put(url, user)
        except httpx.HTTPStatusError as exc:
            print(f"Error updating user {user['username']}: {exc}")
            raise


def get_loan_policy_hash(item_type_id, loan_type_id, patron_type_id, shelving_location_id):
    """Generate a hash of the circulation rule parameters that key a loan policy"""
    return str(
        hashlib.sha224(
            ("".join([item_type_id, loan_type_id, patron_type_id, shelving_location_id])).encode(
                "utf-8"
            )
        ).hexdigest()
    )


def validate_uuid(my_uuid):
    """Validates that a string is a valid UUID"""
    reg = "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"  # noqa
    pattern = re.compile(reg)
    return bool(pattern.match(my_uuid))
