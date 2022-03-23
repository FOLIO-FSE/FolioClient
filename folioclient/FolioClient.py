import json
import re
import logging
import yaml
import random
import copy
from datetime import datetime
import hashlib
import traceback
import requests
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

    @cached_property
    def current_user(self):
        logging.info("fetching current user..")
        try:
            path = f"/bl-users/by-username/{self.username}"
            resp = self.folio_get(path, "user")
            return resp["id"]
        except Exception as exception:
            logging.error(
                f"Unable to fetch user id for user {self.username}", exc_info=exception
            )
            return ""

    @cached_property
    def identifier_types(self):
        return list(
            self.folio_get_all(
                "/identifier-types", "identifierTypes", self.cql_all, 1000
            )
        )

    @cached_property
    def statistical_codes(self):
        return list(
            self.folio_get_all(
                "/statistical-codes", "statisticalCodes", self.cql_all, 1000
            )
        )

    @cached_property
    def contributor_types(self):
        return list(
            self.folio_get_all(
                "/contributor-types", "contributorTypes", self.cql_all, 1000
            )
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
        return list(
            self.folio_get_all("/instance-types", "instanceTypes", self.cql_all, 1000)
        )

    @cached_property
    def instance_formats(self):
        return list(
            self.folio_get_all(
                "/instance-formats", "instanceFormats", self.cql_all, 1000
            )
        )

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
            self.folio_get_all(
                "/instance-note-types", "instanceNoteTypes", self.cql_all, 1000
            )
        )

    @cached_property
    def class_types(self):
        return list(
            self.folio_get_all(
                "/classification-types", "classificationTypes", self.cql_all, 1000
            )
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
            self.folio_get_all(
                "/holdings-note-types", "holdingsNoteTypes", self.cql_all, 1000
            )
        )

    @cached_property
    def call_number_types(self):
        return list(
            self.folio_get_all(
                "/call-number-types", "callNumberTypes", self.cql_all, 1000
            )
        )

    @cached_property
    def holdings_types(self):
        return list(
            self.folio.folio_get_all(
                "/holdings-types", "holdingsTypes", self.cql_all, 1000
            )
        )

    @cached_property
    def modes_of_issuance(self):
        return list(
            self.folio_get_all(
                "/modes-of-issuance", "issuanceModes", self.cql_all, 1000
            )
        )

    def login(self):
        """Logs into FOLIO in order to get the okapi token"""
        headers = {"x-okapi-tenant": self.tenant_id, "content-type": "application/json"}
        payload = {"username": self.username, "password": self.password}
        path = "/authn/login"
        url = self.okapi_url + path
        req = requests.post(url, data=json.dumps(payload), headers=headers)
        if req.status_code == 201:
            self.okapi_token = req.headers.get("x-okapi-token")
            self.refresh_token = req.headers.get("refreshtoken")
        elif req.status_code == 422:
            raise ValueError(f"HTTP {req.status_code}\t{req.text}")
        elif req.status_code in [500, 413]:
            raise ValueError(f"HTTP {req.status_code}\n{req.text} ")
        else:
            raise ValueError(f"HTTP {req.status_code}\t{req.text}")

    def get_single_instance(self, instance_id):
        return self.folio_get_all("inventory/instances/{}".format(instance_id))

    def folio_get_all(self, path, key=None, query="", limit=10):
        """Fetches ALL data objects from FOLIO and turns
        it into a json object"""
        offset = 0
        q_template = "?limit={}&offset={}" if not query else "&limit={}&offset={}"
        temp_res = self.folio_get(
            path, key, query + q_template.format(limit, offset * limit)
        )
        yield from temp_res
        while len(temp_res) == limit:
            offset += 1
            temp_res = self.folio_get(
                path, key, query + q_template.format(limit, offset * limit)
            )
            yield from temp_res
        offset += 1
        temp_res = self.folio_get(
            path, key, query + q_template.format(limit, offset * limit)
        )
        yield from temp_res

    def get_all(self, path, key=None, query=""):
        return self.folio_get_all(path, key, query)

    def folio_get(self, path, key=None, query=""):
        """Fetches data from FOLIO and turns it into a json object"""
        url = self.okapi_url + path + query
        req = requests.get(url, headers=self.okapi_headers)
        if req.status_code == 200:
            return json.loads(req.text)[key] if key else json.loads(req.text)
        elif req.status_code == 422:
            raise Exception(f"HTTP {req.status_code}\n{req.text}")
        elif req.status_code in [500, 413]:
            raise Exception(f"HTTP {req.status_code}\n{req.text} ")
        else:
            raise Exception(f"HTTP {req.status_code}\n{req.text}")

    def folio_get_single_object(self, path):
        """Fetches data from FOLIO and turns it into a json object as is"""
        url = self.okapi_url + path
        req = requests.get(url, headers=self.okapi_headers)
        req.raise_for_status()
        return json.loads(req.text)

    def get_instance_json_schema(self, latest_release=True):
        """Fetches the JSON Schema for instances"""
        return self.get_latest_from_github(
            "folio-org", "mod-inventory-storage", "/ramls/instance.json"
        )

    def get_holdings_schema(self):
        """Fetches the JSON Schema for holdings"""
        return self.get_latest_from_github(
            "folio-org", "mod-inventory-storage", "/ramls/holdingsrecord.json"
        )

    def get_item_schema(self):
        """Fetches the JSON Schema for holdings"""
        return self.get_latest_from_github(
            "folio-org", "mod-inventory-storage", "/ramls/item.json"
        )

    @staticmethod
    def get_latest_from_github(owner, repo, filepath: str):
        latest_path = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
        req = requests.get(latest_path)
        req.raise_for_status()
        latest = json.loads(req.text)
        # print(json.dumps(latest, indent=4))
        latest_tag = latest["tag_name"]
        latest_path = (
            f"https://raw.githubusercontent.com/{owner}/{repo}/{latest_tag}/{filepath}"
        )
        # print(latest_path)
        req = requests.get(latest_path)
        req.raise_for_status()
        if filepath.endswith("json"):
            return json.loads(req.text)
        elif filepath.endswith("yaml"):
            return yaml.safe_load(req.text)
        else:
            raise ValueError("Unknown file ending in %s", filepath)

    def get_user_schema(self):
        """Fetches the JSON Schema for users"""
        return self.get_latest_from_github(
            "folio-org", "mod-users", "/ramls/userdata.json"
        )

    def get_location_id(self, location_code):
        """returns the location ID based on a location code"""
        try:
            return next(
                (l["id"] for l in self.locations if location_code.strip() == l["code"]),
                (
                    next(
                        l["id"]
                        for l in self.locations
                        if l["code"] in ["catch_all", "default", "Default", "ATDM"]
                    )
                ),
            )
        except Exception:
            raise ValueError(
                (
                    f"No location with code '{location_code}' in locations. "
                    "No catch_all/default location either"
                )
            )

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

    def create_request(
        self,
        request_type,
        patron,
        item,
        service_point_id,
        request_date=datetime.now(),
    ):
        """For migrating open request. Deprecated."""
        try:
            df = "%Y-%m-%dT%H:%M:%S.%f+0000"
            data = {
                "requestType": request_type,
                "fulfilmentPreference": "Hold Shelf",
                "requester": {"barcode": patron["barcode"]},
                "requesterId": patron["id"],
                "item": {"barcode": item["barcode"]},
                "itemId": item["id"],
                "pickupServicePointId": service_point_id,
                "requestDate": request_date.strftime(df),
            }
            url = f"{self.okapi_url}/circulation/requests"
            print(f"POST {url}\t{json.dumps(data)}", flush=True)
            req = requests.post(url, headers=self.okapi_headers, data=json.dumps(data))
            print(req.status_code, flush=True)
            if str(req.status_code) == "422":
                print(
                    f"{json.loads(req.text)['errors'][0]['message']}\t{json.dumps(data)}",
                    flush=True,
                )
            else:
                print(req.status_code, flush=True)
                # print(req.text)
                req.raise_for_status()
        except Exception as exception:
            print(exception, flush=True)
            traceback.print_exc()

    def get_random_objects(self, path, count=1, query=""):
        # TODO: add exception handling and logging
        resp = self.folio_get(path)
        total = int(resp["totalRecords"])
        name = next(f for f in [*resp] if f != "totalRecords")
        rand = random.randint(0, total)
        query = f"?limit={count}&offset={rand}"
        print(f"{total} {path} found, picking {count} from {rand} onwards")
        return list(self.folio_get(path, name, query))

    def extend_open_loan(self, loan, extention_due_date, extend_out_date):
        # TODO: add logging instead of print out
        # Deprecated
        try:
            loan_to_put = copy.deepcopy(loan)
            del loan_to_put["metadata"]
            loan_to_put["dueDate"] = extention_due_date.isoformat()
            loan_to_put["loanDate"] = extend_out_date.isoformat()
            url = f"{self.okapi_url}/circulation/loans/{loan_to_put['id']}"

            req = requests.put(
                url, headers=self.okapi_headers, data=json.dumps(loan_to_put)
            )
            print(
                f"{req.status_code}\tPUT Extend loan {loan_to_put['id']} to {loan_to_put['dueDate']}\t {url}",
                flush=True,
            )
            if str(req.status_code) == "422":
                print(
                    f"{json.loads(req.text)['errors'][0]['message']}\t{json.dumps(loan_to_put)}",
                    flush=True,
                )
                return False
            else:
                req.raise_for_status()
            return True
        except Exception as exception:
            print(
                f"PUT FAILED Extend loan to {loan_to_put['dueDate']}\t {url}\t{json.dumps(loan_to_put)}",
                flush=True,
            )
            traceback.print_exc()
            print(exception, flush=True)
            return False

    def get_loan_policy_id(
        self, item_type_id, loan_type_id, patron_group_id, location_id
    ):
        """retrieves a loan policy from FOLIO, or uses a chached one"""

        lp_hash = get_loan_policy_hash(
            item_type_id, loan_type_id, patron_group_id, location_id
        )
        if lp_hash in self.loan_policies:
            return self.loan_policies[lp_hash]
        payload = {
            "item_type_id": item_type_id,
            "loan_type_id": loan_type_id,
            "patron_type_id": patron_group_id,
            "location_id": location_id,
        }
        path = f"{self.okapi_url}/circulation/rules/loan-policy"
        response = requests.get(path, params=payload, headers=self.okapi_headers)
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
        req = requests.put(url, headers=self.okapi_headers, data=json.dumps(user))
        print(f"{req.status_code}")
        req.raise_for_status()


def get_loan_policy_hash(
    item_type_id, loan_type_id, patron_type_id, shelving_location_id
):
    return str(
        hashlib.sha224(
            (
                "".join(
                    [item_type_id, loan_type_id, patron_type_id, shelving_location_id]
                )
            ).encode("utf-8")
        ).hexdigest()
    )


def validate_uuid(my_uuid):
    reg = "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
    pattern = re.compile(reg)
    return bool(pattern.match(my_uuid))
