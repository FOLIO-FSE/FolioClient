import hashlib
import json
import logging
import os
import random
import re
from datetime import datetime

import httpx
import yaml

from folioclient.cached_property import cached_property


class FolioClient:
    """handles communication and getting values from FOLIO"""

    def __init__(self, okapi_url, tenant_id, username, password):
        self.missing_location_codes = set()
        self.loan_policies = {}
        self.cql_all = "?query=cql.allRecords=1"
        self.okapi_url = okapi_url
        self.tenant_id = tenant_id
        self.username = username
        self.password = password
        self.login()
        self.okapi_headers = {
            "x-okapi-token": self.okapi_token,
            "x-okapi-tenant": self.tenant_id,
            "content-type": "application/json",
        }
        self.httpx_client = None

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

    def login(self):
        """Logs into FOLIO in order to get the okapi token"""
        payload = {"username": self.username, "password": self.password}
        headers = {
            "x-okapi-tenant": self.tenant_id,
            "content-type": "application/json",
        }
        url = f"{self.okapi_url}/authn/login"
        req = httpx.post(url, json=payload, headers=headers, timeout=None)
        if req.status_code == 201:
            self.okapi_token = req.headers.get("x-okapi-token")
            self.refresh_token = req.headers.get("refreshtoken")
        elif req.status_code == 422 or req.status_code not in [500, 413]:
            raise ValueError(f"HTTP {req.status_code}\t{req.text}")
        else:
            raise ValueError(f"HTTP {req.status_code}\n{req.text} ")

    def get_single_instance(self, instance_id):
        return self.folio_get_all(f"inventory/instances/{instance_id}")

    def folio_get_all(self, path, key=None, query="", limit=10):
        """Fetches ALL data objects from FOLIO and turns
        it into a json object"""
        with httpx.Client(headers=self.okapi_headers, timeout=None) as httpx_client:
            self.httpx_client = httpx_client
            offset = 0
            q_template = "&limit={}&offset={}" if query else "?limit={}&offset={}"
            temp_res = self.folio_get(path, key, query + q_template.format(limit, offset * limit))
            yield from temp_res
            while len(temp_res) == limit:
                offset += 1
                temp_res = self.folio_get(
                    path, key, query + q_template.format(limit, offset * limit)
                )
                yield from temp_res
            offset += 1
            yield from self.folio_get(path, key, query + q_template.format(limit, offset * limit))

    def get_all(self, path, key=None, query=""):
        return self.folio_get_all(path, key, query)

    def folio_get(self, path, key=None, query=""):
        """Fetches data from FOLIO and turns it into a json object"""
        url = self.okapi_url + path + query
        if self.httpx_client and not self.httpx_client.is_closed:
            req = self.httpx_client.get(url)
            req.raise_for_status()
        else:
            req = httpx.get(url, headers=self.okapi_headers, timeout=None)
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
    def get_latest_from_github(owner, repo, filepath: str, personal_access_token=""):  # noqa: S107
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
        req = httpx.get(latest_path, headers=github_headers, timeout=None, follow_redirects=True)
        req.raise_for_status()
        latest = json.loads(req.text)
        # print(json.dumps(latest, indent=4))
        latest_tag = latest["tag_name"]
        latest_path = f"https://raw.githubusercontent.com/{owner}/{repo}/{latest_tag}/{filepath}"
        # print(latest_path)
        req = httpx.get(latest_path, headers=github_headers, timeout=None, follow_redirects=True)
        req.raise_for_status()
        if filepath.endswith("json"):
            return json.loads(req.text)
        elif filepath.endswith("yaml"):
            return yaml.safe_load(req.text)
        else:
            raise ValueError("Unknown file ending in %s", filepath)

    def get_from_github(self, owner, repo, filepath: str, personal_access_token=""):  # noqa: S107
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
            req = httpx.get(f_path, headers=github_headers, timeout=None, follow_redirects=True)
            req.raise_for_status()
            latest = json.loads(req.text)
            # print(json.dumps(latest, indent=4))
            latest_tag = latest["tag_name"]
            f_path = f"https://raw.githubusercontent.com/{owner}/{repo}/{latest_tag}/{filepath}"
        else:
            f_path = f"https://raw.githubusercontent.com/{owner}/{repo}/{version}/{filepath}"
        # print(latest_path)
        req = httpx.get(f_path, headers=github_headers, timeout=None, follow_redirects=True)
        req.raise_for_status()
        if filepath.endswith("json"):
            return json.loads(req.text)
        elif filepath.endswith("yaml"):
            return yaml.safe_load(req.text)
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
            return res
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
        rand = random.randint(0, total)  # noqa
        query = f"?limit={count}&offset={rand}"
        print(f"{total} {path} found, picking {count} from {rand} onwards")
        return list(self.folio_get(path, name, query))

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
        path = f"{self.okapi_url}/circulation/rules/loan-policy"
        response = httpx.get(path, params=payload, headers=self.okapi_headers, timeout=None)
        if response.status_code != 200:
            print(response.status_code)
            print(response.text)
            raise Exception("Request getting Loan Policy Id went wrong!")
        lp_id = json.loads(response.text)["loanPolicyId"]
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
        req = httpx.put(url, headers=self.okapi_headers, json=user)
        print(f"{req.status_code}")
        req.raise_for_status()


def get_loan_policy_hash(item_type_id, loan_type_id, patron_type_id, shelving_location_id):
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
