import json
import logging
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
        return self.folio_get_all("/identifier-types", "identifierTypes", self.cql_all)

    @cached_property
    def contributor_types(self):
        return self.folio_get_all(
            "/contributor-types", "contributorTypes", self.cql_all
        )

    @cached_property
    def contrib_name_types(self):
        return self.folio_get_all(
            "/contributor-name-types", "contributorNameTypes", self.cql_all
        )

    @cached_property
    def instance_types(self):
        return self.folio_get_all("/instance-types", "instanceTypes", self.cql_all)

    @cached_property
    def instance_formats(self):
        return self.folio_get_all("/instance-formats", "instanceFormats", self.cql_all)

    def get_single_instance(self, instance_id):
        return self.folio_get_all("inventory/instances/{}".format(instance_id))

    @cached_property
    def alt_title_types(self):
        return self.folio_get_all(
            "/alternative-title-types", "alternativeTitleTypes", self.cql_all
        )

    @cached_property
    def locations(self):
        return self.folio_get_all("/locations", "locations", self.cql_all)

    @cached_property
    def instance_note_types(self):
        return self.folio_get_all(
            "/instance-note-types", "instanceNoteTypes", self.cql_all
        )

    @cached_property
    def class_types(self):
        return self.folio_get_all(
            "/classification-types", "classificationTypes", self.cql_all
        )

    @cached_property
    def organizations(self):
        return self.folio_get_all(
            "/organizations-storage/organizations", "organizations", self.cql_all
        )

    @cached_property
    def modes_of_issuance(self):
        return self.folio_get_all("/modes-of-issuance", "issuanceModes", self.cql_all)

    def login(self):
        """Logs into FOLIO in order to get the okapi token"""
        headers = {"x-okapi-tenant": self.tenant_id, "content-type": "application/json"}
        payload = {"username": self.username, "password": self.password}
        path = "/authn/login"
        url = self.okapi_url + path
        req = requests.post(url, data=json.dumps(payload), headers=headers)
        if req.status_code != 201:
            raise ValueError("Request failed {}".format(req.status_code))
        self.okapi_token = req.headers.get("x-okapi-token")
        self.refresh_token = req.headers.get("refreshtoken")

    def folio_get_all(self, path, key=None, query=""):
        """Fetches ALL data objects from FOLIO and turns
        it into a json object"""
        results = list()
        limit = 100
        offset = 0
        q_template = "?limit={}&offset={}" if not query else "&limit={}&offset={}"
        q = query + q_template.format(limit, offset * limit)
        temp_res = self.folio_get(
            path, key, query + q_template.format(limit, offset * limit)
        )
        results.extend(temp_res)
        while len(temp_res) == limit:
            offset += 1
            temp_res = self.folio_get(
                path, key, query + q_template.format(limit, offset * limit)
            )
            results.extend(temp_res)
        return results

    def folio_get(self, path, key=None, query=""):
        """Fetches data from FOLIO and turns it into a json object"""
        url = self.okapi_url + path + query
        req = requests.get(url, headers=self.okapi_headers)
        req.raise_for_status()
        result = json.loads(req.text)[key] if key else json.loads(req.text)
        return result

    def folio_get_single_object(self, path):
        """Fetches data from FOLIO and turns it into a json object as is"""
        url = self.okapi_url + path
        req = requests.get(url, headers=self.okapi_headers)
        req.raise_for_status()
        result = json.loads(req.text)
        return result

    def get_instance_json_schema(self):
        """Fetches the JSON Schema for instances"""
        url = "https://raw.github.com"
        path = "/folio-org/mod-inventory-storage/master/ramls/instance.json"
        req = requests.get(url + path)
        return json.loads(req.text)

    def get_holdings_schema(self):
        """Fetches the JSON Schema for holdings"""
        url = "https://raw.github.com"
        path = "/folio-org/mod-inventory-storage/master/ramls/"
        file_name = "holdingsrecord.json"
        req = requests.get(url + path + file_name)
        return json.loads(req.text)

    def get_item_schema(self):
        """Fetches the JSON Schema for holdings"""
        url = "https://raw.githubusercontent.com"
        path = "/folio-org/mod-inventory-storage/master/ramls/item.json"
        req = requests.get(url + path)
        return json.loads(req.text)

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
        except Exception as exception:
            raise ValueError(
                (
                    "No location with code '{}' in locations. "
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
        self, request_type, patron, item, service_point_id, request_date=datetime.now(),
    ):
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
            path = "/circulation/requests"
            url = f"{self.okapi_url}{path}"
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

    def check_out_by_barcode(
        self, item_barcode, patron_barcode, loan_date: datetime, service_point_id
    ):
        # TODO: add logging instead of print out
        try:
            df = "%Y-%m-%dT%H:%M:%S.%f+0000"
            data = {
                "itemBarcode": item_barcode,
                "userBarcode": patron_barcode,
                "loanDate": loan_date.strftime(df),
                "servicePointId": service_point_id,
            }
            path = "/circulation/check-out-by-barcode"
            url = f"{self.okapi_url}{path}"
            print(f"POST {url}\t{json.dumps(data)}", flush=True)
            req = requests.post(url, headers=self.okapi_headers, data=json.dumps(data))
            print(req.status_code, flush=True)
            if str(req.status_code) == "422":
                print(
                    f"{json.loads(req.text)['errors'][0]['message']}\t{json.dumps(data)}",
                    flush=True,
                )
            elif str(req.status_code) == "201":
                return json.loads(req.text)
            else:
                req.raise_for_status()
        except Exception as exception:
            traceback.print_exc()
            print(exception, flush=True)

    def extend_open_loan(self, loan, extention_due_date):
        # TODO: add logging instead of print out
        try:
            df = "%Y-%m-%dT%H:%M:%S.%f+0000"
            loan_to_put = copy.deepcopy(loan)
            del loan_to_put["metadata"]
            loan_to_put["dueDate"] = extention_due_date.strftime(df)
            url = f"{self.okapi_url}/circulation/loans/{loan_to_put['id']}"
            print(
                f"PUT Extend loan to {loan_to_put['dueDate']}\t  {url}\t{json.dumps(loan_to_put)}",
                flush=True,
            )
            req = requests.put(
                url, headers=self.okapi_headers, data=json.dumps(loan_to_put)
            )
            print(req.status_code)
            if str(req.status_code) == "422":
                print(
                    f"{json.loads(req.text)['errors'][0]['message']}\t{json.dumps(loan_to_put)}",
                    flush=True,
                )
            else:
                req.raise_for_status()
        except Exception as exception:
            traceback.print_exc()
            print(exception, flush=True)

    def get_loan_policy_id(
        self, item_type_id, loan_type_id, patron_group_id, location_id
    ):
        """retrieves a loan policy from FOLIO, or uses a chached one"""

        lp_hash = get_lp_hash(item_type_id, loan_type_id, patron_group_id, location_id)
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
        ids = [f["id"] for f in gs]
        return ids


def get_lp_hash(item_type_id, loan_type_id, patron_type_id, shelving_location_id):
    return str(
        hashlib.sha224(
            (
                "".join(
                    [item_type_id, loan_type_id, patron_type_id, shelving_location_id]
                )
            ).encode("utf-8")
        ).hexdigest()
    )
