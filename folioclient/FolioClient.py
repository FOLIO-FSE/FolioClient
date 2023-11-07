import hashlib
import json
import logging
import os
import random
import re
from datetime import datetime
from datetime import timedelta
from datetime import timezone as tz
from typing import Any
from typing import Dict
from urllib.parse import urljoin
from dateutil.parser import parse as date_parse
import httpx
import yaml
from openapi_schema_to_json_schema import to_json_schema
from openapi_schema_to_json_schema import patternPropertiesHandler

from folioclient.cached_property import cached_property

class FolioClient:
    """handles communication and getting values from FOLIO"""

    def __init__(self, okapi_url, tenant_id, username, password, ssl_verify=True):
        self.missing_location_codes = set()
        self.loan_policies = {}
        self.cql_all = "?query=cql.allRecords=1"
        self.okapi_url = okapi_url
        self.tenant_id = tenant_id
        self.username = username
        self.password = password
        self.ssl_verify = ssl_verify
        self.httpx_client = None
        self.refresh_token = None
        self.cookies = None
        self.okapi_token_expires = None
        self.okapi_token_duration = None
        self.okapi_token_time_remaining_threshold = float(
            os.environ.get("FOLIOCLIENT_REFRESH_API_TOKEN_TIME_REMAINING", ".2")
        )
        self.base_headers = {
            "x-okapi-tenant": self.tenant_id,
            "content-type": "application/json",
        }
        self._okapi_headers = {}
        self.login()

    def __repr__(self) -> str:
        return f"FolioClient for tenant {self.tenant_id} at {self.okapi_url} as {self.username}"

    @cached_property
    def current_user(self):
        logging.info("fetching current user..")
        try:
            path = f"/bl-users/by-username/{self.username}"
            resp = self.folio_get(path, "user")
            return resp["id"]
        except Exception as exception:
            logging.error(f"Unable to fetch user id for user {self.username}", exc_info=exception)
            return ""

    @cached_property
    def identifier_types(self):
        return list(self.folio_get_all("/identifier-types", "identifierTypes", self.cql_all, 1000))

    @cached_property
    def module_versions(self):
        resp = self.folio_get(f"/_/proxy/tenants/{self.tenant_id}/modules")
        return [a["id"] for a in resp]

    @cached_property
    def statistical_codes(self):
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

    @property
    def okapi_headers(self):
        """
        Property that returns okapi headers with the current valid Okapi token. All headers except
        x-okapi-token can be modified by key-value assignment. If a new x-okapi-token value is set
        via this method, it will be overwritten with the current, valid okapi token value returned
        by self.okapi_token. To reset all header values to their initial state:

        >>>> del folio_client.okapi_headers
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
        """Property that attempts to return a valid Okapi token, refreshing if needed"""
        if datetime.now(tz.utc) > (self.okapi_token_expires - timedelta(seconds=self.okapi_token_duration.total_seconds() * self.okapi_token_time_remaining_threshold)):
            self.login()
        return self._okapi_token

    @okapi_token.setter
    def okapi_token(self, value):
        self._okapi_token = value

    @okapi_token.deleter
    def okapi_token(self):
        del self._okapi_token

    def login(self):
        """Logs into FOLIO in order to get the okapi token"""
        payload = {"username": self.username, "password": self.password}
        # Transitional implementation to support Poppy and pre-Poppy authentication
        url = f"{self.okapi_url}/authn/login-with-expiry"
        # Poppy and later
        req = httpx.post(url, json=payload, headers=self.base_headers, timeout=None, verify=self.ssl_verify)
        try:
            req.raise_for_status()
        except httpx.HTTPError:
            # Pre-Poppy
            if req.status_code == 404:
                url = f"{self.okapi_url}/authn/login"
                req = httpx.post(url, json=payload, headers=self.base_headers, timeout=None, verify=self.ssl_verify)
                req.raise_for_status()
            else:
                raise
        response_body = req.json()
        self.okapi_token = req.headers.get("x-okapi-token") or req.cookies.get("folioAccessToken")
        self.okapi_token_expires = date_parse(response_body.get("accessTokenExpiration", "2999-12-31T23:59:59Z"))
        self.okapi_token_duration = self.okapi_token_expires - datetime.now(tz.utc)

    def get_single_instance(self, instance_id):
        return self.folio_get_all(f"inventory/instances/{instance_id}")

    def folio_get_all(self, path, key=None, query=None, limit=10, **kwargs):
        """
        Fetches ALL data objects from FOLIO matching `query` in `limit`-size chunks and provides
        an iterable object yielding a single record at a time until all records have been returned.
        - kwargs are passed as additional url parameters to `path`
        """
        with httpx.Client(headers=self.okapi_headers, timeout=None, verify=self.ssl_verify) as httpx_client:
            self.httpx_client = httpx_client
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
                    path, key, query_params=self._construct_query_parameters(
                        query=query, limit=limit, offset=offset * limit, **kwargs
                    )
                )
                yield from temp_res
            offset += 1
            yield from self.folio_get(path, key, query_params=self._construct_query_parameters(
                query=query, limit=limit, offset=offset * limit, **kwargs
            ))

    def _construct_query_parameters(self, **kwargs) -> Dict[str, Any]:
        """Private method to construct query parameters for folio_get or httpx client calls"""
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

    def folio_get(self, path, key=None, query="", query_params=None):
        """
        Fetches data from FOLIO and turns it into a json object
        * path: FOLIO API endpoint path
        * key: Key in JSON response from FOLIO that includes the array of results for query APIs
        * query: For backwards-compatibility
        * query_params: Additional query parameters for the specified path. May also be used for
                        `query`
        """
        url = f"{self.okapi_url}{path}"
        if query and query_params:
            query_params = self._construct_query_parameters(query=query, **query_params)
        elif query:
            query_params = self._construct_query_parameters(query=query)
        if self.httpx_client and not self.httpx_client.is_closed:
            req = self.httpx_client.get(url, params=query_params)
            req.raise_for_status()
        else:
            req = httpx.get(
                url, params=query_params,
                headers=self.okapi_headers,
                timeout=None,
                verify=self.ssl_verify
            )
            req.raise_for_status()
        return req.json()[key] if key else req.json()

    def folio_get_single_object(self, path):
        """Fetches data from FOLIO and turns it into a json object as is"""
        return self.folio_get(path)

    def get_instance_json_schema(self):
        """Fetches the JSON Schema for instances"""
        return self.get_from_github("folio-org", "mod-inventory-storage", "/ramls/instance.json")

    def get_holdings_schema(self):
        """Fetches the JSON Schema for holdings"""
        return self.get_from_github(
            "folio-org", "mod-inventory-storage", "/ramls/holdingsrecord.json"
        )

    def get_item_schema(self):
        """Fetches the JSON Schema for holdings"""
        return self.get_from_github("folio-org", "mod-inventory-storage", "/ramls/item.json")

    @staticmethod
    def get_latest_from_github(
        owner, repo, filepath: str, personal_access_token="", ssl_verify=True  
    ):  # noqa: S107
        github_headers = {
            "content-type": "application/json",
            "User-Agent": "Folio Client (https://github.com/FOLIO-FSE/FolioClient)",
        }
        if personal_access_token:
            github_headers["authorization"] = f"token {personal_access_token}"
        elif os.environ.get("GITHUB_TOKEN"):
            logging.info("Using GITHB_TOKEN environment variable for Gihub API Access")
            github_headers["authorization"] = f"token {os.environ.get('GITHUB_TOKEN')}"
        latest_path = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
        req = httpx.get(latest_path, headers=github_headers, timeout=None, follow_redirects=True, verify=ssl_verify)
        req.raise_for_status()
        latest = json.loads(req.text)
        # print(json.dumps(latest, indent=4))
        latest_tag = latest["tag_name"]
        latest_path = f"https://raw.githubusercontent.com/{owner}/{repo}/{latest_tag}/{filepath}"
        # print(latest_path)
        req = httpx.get(latest_path, headers=github_headers, timeout=None, follow_redirects=True, verify=ssl_verify)
        req.raise_for_status()
        if filepath.endswith("json"):
            return json.loads(req.text)
        elif filepath.endswith("yaml"):
            yaml_rep = yaml.safe_load(req.text)
            return to_json_schema(yaml_rep)
        else:
            raise ValueError(f"Unknown file ending in {filepath}")

    def get_from_github(
            self, owner, repo, filepath: str, personal_access_token="", ssl_verify=True
    ):  # noqa: S107
        version = self.get_module_version(repo)
        github_headers = {
            "content-type": "application/json",
            "User-Agent": "Folio Client (https://github.com/FOLIO-FSE/FolioClient)",
        }
        if personal_access_token:
            github_headers["authorization"] = f"token {personal_access_token}"
        elif os.environ.get("GITHUB_TOKEN"):
            logging.info("Using GITHB_TOKEN environment variable for Gihub API Access")
            github_headers["authorization"] = f"token {os.environ.get('GITHUB_TOKEN')}"
        if not version:
            f_path = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
            req = httpx.get(
                f_path,
                headers=github_headers,
                timeout=None,
                follow_redirects=True,
                verify=ssl_verify
            )
            req.raise_for_status()
            latest = json.loads(req.text)
            # print(json.dumps(latest, indent=4))
            latest_tag = latest["tag_name"]
            f_path = f"https://raw.githubusercontent.com/{owner}/{repo}/{latest_tag}/{filepath}"
        else:
            f_path = f"https://raw.githubusercontent.com/{owner}/{repo}/{version}/{filepath}"
        # print(latest_path)
        req = httpx.get(
            f_path, headers=github_headers, timeout=None, follow_redirects=True, verify=ssl_verify
        )
        req.raise_for_status()
        if filepath.endswith("json"):
            return json.loads(req.text)
        elif filepath.endswith("yaml"):
            yaml_rep = yaml.safe_load(req.text)
            return to_json_schema(yaml_rep)
        else:
            raise ValueError("Unknown file ending in %s", filepath)

    def get_module_version(self, module_name: str):
        if res := next(
            (
                f'v{a.replace(f"{module_name}-", "")}'
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
            "createdDate": datetime.utcnow().isoformat(timespec="milliseconds"),
            "createdByUserId": user_id,
            "updatedDate": datetime.utcnow().isoformat(timespec="milliseconds"),
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
        url = f"{self.okapi_url}/users/{user['id']}"
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
