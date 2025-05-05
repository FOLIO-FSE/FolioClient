import hashlib
import json
import logging
import os
import random
import re
from datetime import datetime, timedelta
from datetime import timezone as tz
from typing import Any, Dict, List, Union
from urllib.parse import urljoin
from warnings import warn

import httpx
import jsonref
import yaml
from httpx._types import CookieTypes
from dateutil.parser import parse as date_parse
from openapi_schema_to_json_schema import to_json_schema

from folioclient.cached_property import cached_property
from folioclient.decorators import (
    folio_retry_on_auth_error,
    folio_retry_on_server_error,
    handle_remote_protocol_error,
    use_client_session_with_generator,
    use_client_session,
)
from folioclient.exceptions import FolioClientClosed

# Constants
CONTENT_TYPE_JSON = "application/json"

try:
    HTTPX_TIMEOUT = int(os.environ.get("FOLIOCLIENT_HTTP_TIMEOUT"))
except TypeError:
    HTTPX_TIMEOUT = None

RAML_UTIL_URL = "https://raw.githubusercontent.com/folio-org/raml/raml1.0"

USER_AGENT_STRING = "Folio Client (https://github.com/FOLIO-FSE/FolioClient)"

# Set up logger
logger = logging.getLogger("FolioClient")


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
    """

    def __init__(
        self, gateway_url, tenant_id, username, password, ssl_verify=True, *, okapi_url=None
    ):
        if okapi_url:
            warn(
                "okapi_url argument is deprecated. Use gateway_url instead. Support for okapi_url will be removed in a future release.",
                DeprecationWarning,
                stacklevel=2,
            )
        self.http_timeout = HTTPX_TIMEOUT
        self.missing_location_codes = set()
        self.loan_policies = {}
        self.cql_all = "?query=cql.allRecords=1"
        self.gateway_url = okapi_url or gateway_url
        self.tenant_id = tenant_id
        self.username = username
        self.password = password
        self.ssl_verify = ssl_verify
        self.httpx_client = None
        self.refresh_token = None
        self.okapi_token_expires = None
        self.okapi_token_duration = None
        self.okapi_token_time_remaining_threshold = float(
            os.environ.get("FOLIOCLIENT_REFRESH_API_TOKEN_TIME_REMAINING", ".2")
        )
        self.base_headers = {
            "x-okapi-tenant": self.tenant_id,
            "content-type": CONTENT_TYPE_JSON,
        }
        self._okapi_headers = {}
        self.is_closed = False
        self.login()

    def __repr__(self) -> str:
        return f"FolioClient for tenant {self.tenant_id} at {self.gateway_url} as {self.username}"

    def __enter__(self):
        """Context manager for FolioClient"""
        self.httpx_client = httpx.Client(
            timeout=self.http_timeout,
            verify=self.ssl_verify,
            base_url=self.gateway_url,
        )
        return self

    @handle_remote_protocol_error
    @use_client_session
    def __exit__(self, exc_type, exc_value, traceback):
        """Context manager exit method"""
        if self.cookies:
            logger.info("logging out...")
            logout = self.httpx_client.post(
                urljoin(self.gateway_url, "authn/logout"),
                headers=self.base_headers,
                cookies=self.cookies,
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
        self.username = None
        self.password = None
        self._okapi_token = None
        if self.httpx_client and not self.httpx_client.is_closed:
            self.httpx_client.close()
        self.is_closed = True

    @property
    def okapi_url(self):
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
    def okapi_url(self, value):
        """
        Setter for okapi_url property, to maintain backwards compatibility.
        """
        warn(
            "FolioClient.okapi_url is deprecated. Use gateway_url instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.gateway_url = value

    def close(self):
        self.__exit__(None, None, None)

    @cached_property
    def current_user(self):
        """
        This method returns the current user id for the user that is logged in, based on username.
        self.tenant_id is always used as x-okapi-tenant header, and is reset to any existing value
        after the call.
        """
        logger.info("fetching current user..")
        current_tenant_id = self.okapi_headers["x-okapi-tenant"]
        self.okapi_headers["x-okapi-tenant"] = self.tenant_id
        try:
            path = f"/bl-users/by-username/{self.username}"
            resp = self._folio_get(path, "user")
            self.okapi_headers["x-okapi-tenant"] = current_tenant_id
            return resp["id"]
        except httpx.HTTPStatusError:
            logger.info("bl-users endpoint not found, trying /users endpoint instead.")
            try:
                path = "/users"
                query = f"username=={self.username}"
                resp = self._folio_get(path, "users", query=query)
                self.okapi_headers["x-okapi-tenant"] = current_tenant_id
                return resp[0]["id"]
            except Exception as exception:
                logger.error(
                    f"Unable to fetch user id for user {self.username}",
                    exc_info=exception,
                )
                self.okapi_headers["x-okapi-tenant"] = current_tenant_id
                return ""
        except Exception as exception:
            logger.error(f"Unable to fetch user id for user {self.username}", exc_info=exception)
            self.okapi_headers["x-okapi-tenant"] = current_tenant_id
            return ""

    @cached_property
    def identifier_types(self):
        return list(self.folio_get_all("/identifier-types", "identifierTypes", self.cql_all, 1000))

    @cached_property
    def module_versions(self):
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
    def statistical_codes(self):
        """
        Returns a list of statistical codes.
        """
        return list(
            self.folio_get_all("/statistical-codes", "statisticalCodes", self.cql_all, 1000)
        )

    @cached_property
    def contributor_types(self):
        return list(
            self.folio_get_all("/contributor-types", "contributorTypes", self.cql_all, 1000)
        )

    @cached_property
    def contrib_name_types(self):
        return list(
            self.folio_get_all(
                "/contributor-name-types", "contributorNameTypes", self.cql_all, 1000
            )
        )

    @cached_property
    def instance_types(self):
        return list(self.folio_get_all("/instance-types", "instanceTypes", self.cql_all, 1000))

    @cached_property
    def instance_formats(self):
        return list(self.folio_get_all("/instance-formats", "instanceFormats", self.cql_all, 1000))

    @cached_property
    def alt_title_types(self):
        return list(
            self.folio_get_all(
                "/alternative-title-types", "alternativeTitleTypes", self.cql_all, 1000
            )
        )

    @cached_property
    def locations(self):
        return list(self.folio_get_all("/locations", "locations", self.cql_all, 1000))

    @cached_property
    def electronic_access_relationships(self):
        return list(
            self.folio_get_all(
                "/electronic-access-relationships",
                "electronicAccessRelationships",
                self.cql_all,
                1000,
            )
        )

    @cached_property
    def instance_note_types(self):
        return list(
            self.folio_get_all("/instance-note-types", "instanceNoteTypes", self.cql_all, 1000)
        )

    @cached_property
    def class_types(self):
        return list(
            self.folio_get_all("/classification-types", "classificationTypes", self.cql_all, 1000)
        )

    @cached_property
    def organizations(self):
        return list(
            self.folio_get_all(
                "/organizations-storage/organizations",
                "organizations",
                self.cql_all,
                1000,
            )
        )

    @cached_property
    def holding_note_types(self):
        return list(
            self.folio_get_all("/holdings-note-types", "holdingsNoteTypes", self.cql_all, 1000)
        )

    @cached_property
    def call_number_types(self):
        return list(
            self.folio_get_all("/call-number-types", "callNumberTypes", self.cql_all, 1000)
        )

    @cached_property
    def holdings_types(self):
        return list(self.folio_get_all("/holdings-types", "holdingsTypes", self.cql_all, 1000))

    @cached_property
    def modes_of_issuance(self):
        return list(self.folio_get_all("/modes-of-issuance", "issuanceModes", self.cql_all, 1000))

    @cached_property
    def authority_source_files(self):
        """Cached property for all configured authority source files"""
        return list(
            self.folio_get_all(
                "/authority-source-files", "authoritySourceFiles", self.cql_all, 1000
            )
        )

    @cached_property
    def subject_types(self):
        """Cached property for all configured subject types"""
        return list(self.folio_get_all("/subject-types", "subjectTypes", self.cql_all, 1000))

    @property
    def okapi_headers(self):
        """
        Property that returns okapi headers with the current valid Okapi token. All headers except
        x-okapi-token can be modified by key-value assignment. If a new x-okapi-token value is set
        via this method, it will be overwritten with the current, valid okapi token value returned
        by self.okapi_token. To reset all header values to their initial state:

        >>>> del folio_client.okapi_headers

        Returns:
            dict: The okapi headers.
        """
        headers = {
            "x-okapi-token": self.okapi_token,
        }
        if self._okapi_headers:
            self._okapi_headers.update(headers)
        else:
            self._okapi_headers.update(self.base_headers)
            self._okapi_headers.update(headers)
        return self._okapi_headers

    @okapi_headers.deleter
    def okapi_headers(self):
        """
        Deleter for okapi_headers that clears the private _okapi_headers dictionary, which will
        revert okapi_headers to using base_headers
        """
        self._okapi_headers.clear()

    @property
    def okapi_token(self):
        """
        Property that attempts to return a valid Okapi token, refreshing if needed.

        Returns:
            str: The Okapi token.
        """
        if not self.is_closed:
            if datetime.now(tz.utc) > (
                self.okapi_token_expires
                - timedelta(
                    seconds=self.okapi_token_duration.total_seconds()
                    * self.okapi_token_time_remaining_threshold
                )
            ):
                self.login()
            return self._okapi_token
        else:
            raise FolioClientClosed()

    @property
    def cookies(self) -> CookieTypes:
        """
        Property that returns the cookies for the current session, and
        refreshes them if needed.
        """
        if not self.is_closed:
            if self._cookies is None or datetime.now(tz.utc) > (
                self.okapi_token_expires
                - timedelta(
                    seconds=self.okapi_token_duration.total_seconds()
                    * self.okapi_token_time_remaining_threshold
                )
            ):
                self.login()
            return self._cookies
        else:
            raise FolioClientClosed()

    @property
    def is_ecs(self):
        """
        Property that returns True if self.tenant_id is an ECS central tenant.
        """
        return bool(self.ecs_consortium)

    @cached_property
    def ecs_consortium(self) -> Union[Dict[str, Any], None]:
        """
        Property that returns the ECS consortia for the current tenant.
        """
        current_tenant_id = self.okapi_headers["x-okapi-tenant"]
        try:
            self.okapi_headers["x-okapi-tenant"] = self.tenant_id
            consortium = self.folio_get("/consortia", "consortia")[0]
        except (httpx.HTTPStatusError, IndexError):
            consortium = None
        finally:
            self.okapi_headers["x-okapi-tenant"] = current_tenant_id
        return consortium

    @cached_property
    def ecs_members(self) -> List[Dict[str, Any]]:
        """
        Property that returns the tenants of the ECS consortia.
        """
        if self.is_ecs:
            tenants = self.folio_get(
                f"/consortia/{self.ecs_consortium['id']}/tenants",
                "tenants",
                query_params={"limit": 1000},
            )
            tenants.sort(key=lambda x: x["id"])
            return tenants
        else:
            return []

    @folio_retry_on_server_error
    @handle_remote_protocol_error
    @use_client_session
    def login(self):
        """Logs into FOLIO in order to get the folio access token."""
        if not self.is_closed:
            payload = {"username": self.username, "password": self.password}
            # Transitional implementation to support Poppy and pre-Poppy authentication
            url = urljoin(self.gateway_url, "authn/login-with-expiry")
            # Poppy and later
            try:
                req = self.httpx_client.post(
                    url,
                    json=payload,
                    headers=self.base_headers,
                    timeout=self.http_timeout,
                )
                req.raise_for_status()
            except httpx.HTTPStatusError:
                # Pre-Poppy
                if req.status_code == 404:
                    url = urljoin(self.gateway_url, "authn/login")
                    req = self.httpx_client.post(
                        url,
                        json=payload,
                        headers=self.base_headers,
                        timeout=self.http_timeout,
                    )
                    req.raise_for_status()
                else:
                    raise
            response_body = req.json()
            self._cookies = req.cookies
            self._okapi_token = req.headers.get("x-okapi-token") or req.cookies.get(
                "folioAccessToken"
            )
            self.okapi_token_expires = date_parse(
                response_body.get("accessTokenExpiration", "2999-12-31T23:59:59Z")
            )
            self.okapi_token_duration = self.okapi_token_expires - datetime.now(tz.utc)
        else:
            raise FolioClientClosed()

    def logout(self):
        """Alias for `close`"""
        if not self.is_closed:
            self.close()
        else:
            raise FolioClientClosed()

    def get_single_instance(self, instance_id):
        return self.folio_get_single_object(f"inventory/instances/{instance_id}")

    @use_client_session_with_generator
    def folio_get_all(self, path, key=None, query=None, limit=10, **kwargs):
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
        offset = 0
        query = query or " ".join((self.cql_all, "sortBy id"))
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

    @use_client_session_with_generator
    def folio_get_all_by_id_offset(self, path, key=None, query=None, limit=10, **kwargs):
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
            query = "cql.allRecords=1 sortBy id"
        if "sortBy id" not in query:
            raise ValueError("FOLIO query must be sorted by ID")
        query = query or " ".join((self.cql_all, "sortBy id"))
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
        if self.httpx_client and not self.httpx_client.is_closed:
            req = self.httpx_client.get(url, params=query_params, headers=self.okapi_headers)
            req.raise_for_status()
        else:
            req = httpx.get(
                url,
                params=query_params,
                headers=self.okapi_headers,
                timeout=self.http_timeout,
                verify=self.ssl_verify,
            )
            req.raise_for_status()
        return req.json()[key] if key else req.json()

    @folio_retry_on_auth_error
    @handle_remote_protocol_error
    @use_client_session
    def folio_put(self, path, payload, query_params: dict = None):
        """Convenience method to update data in FOLIO"""
        url = urljoin(self.gateway_url, path.lstrip("/")).rstrip("/")
        req = self.httpx_client.put(
            url,
            headers=self.okapi_headers,
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
            headers=self.okapi_headers,
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
            headers=self.okapi_headers,
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
            timeout=self.http_timeout, verify=self.ssl_verify, base_url=self.gateway_url
        )

    def folio_get_single_object(self, path):
        """Fetches data from FOLIO and turns it into a json object as is"""
        return self.folio_get(path)

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

    def get_random_objects(self, path, count=1, query=""):
        # TODO: add exception handling and logging
        resp = self.folio_get(path)
        total = int(resp["totalRecords"])
        name = next(f for f in [*resp] if f != "totalRecords")
        rand = random.randint(0, total)  # noqa # NOSONAR not used in secure context
        query_params = {}
        query_params["query"] = query or self.cql_all
        query_params["limit"] = count
        query_params["offset"] = rand
        print(f"{total} {path} found, picking {count} from {rand} onwards")
        return list(self.folio_get(path, name, query_params=query_params))

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

    def put_user(self, user):
        """Fetches data from FOLIO and turns it into a json object as is"""
        url = urljoin(self.gateway_url, f"users/{user['id']}")
        print(url)
        req = httpx.put(url, headers=self.okapi_headers, json=user, verify=self.ssl_verify)
        print(f"{req.status_code}")
        req.raise_for_status()


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
    reg = "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"  # noqa
    pattern = re.compile(reg)
    return bool(pattern.match(my_uuid))
