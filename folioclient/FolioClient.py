import json
import requests
from folioclient.cached_property import cached_property


class FolioClient:
    '''handles communication and getting values from FOLIO'''
    def __init__(self, okapi_url, tenant_id, username, password):
        self.missing_location_codes = set()
        self.cql_all = '?limit=100&query=cql.allRecords=1 sortby name'
        self.okapi_url = okapi_url
        self.tenant_id = tenant_id
        self.username = username
        self.password = password
        self.login()
        self.okapi_headers = {'x-okapi-token': self.okapi_token,
                              'x-okapi-tenant': self.tenant_id,
                              'content-type': 'application/json'}

    @cached_property
    def identifier_types(self):
            return self.folio_get("/identifier-types",
                                    "identifierTypes",
                                    cql_all)

    @cached_property
    def contributor_types(self):
        return self.folio_get("/contributor-types",
                              "contributorTypes",
                              cql_all)

    @cached_property
    def contrib_name_types(self):
        return self.folio_get("/contributor-name-types",
                              "contributorNameTypes",
                              cql_all)

    @cached_property
    def instance_types(self):
        return self.folio_get("/instance-types",
                              "instanceTypes",
                              cql_all)

    @cached_property
    def instance_formats(self):
        return self.folio_get("/instance-formats",
                              "instanceFormats",
                              cql_all)

    @cached_property
    def alt_title_types(self):
        return self.folio_get("/alternative-title-types",
                              "alternativeTitleTypes",
                              cql_all)

    @cached_property
    def locations(self):
        return self.folio_get("/locations",
                              "locations",
                              cql_all)

    @cached_property
    def class_types(self):
        return self.folio_get("/classification-types",
                              "classificationTypes",
                              cql_all)

    @cached_property
    def organizations(self):
        return self.folio_get("/organizations-storage/organizations",
                              "organizations",
                              self.cql_all)

    def login(self):
        '''Logs into FOLIO in order to get the okapi token'''
        headers = {
            'x-okapi-tenant': self.tenant_id,
            'content-type': 'application/json'}
        payload = {"username": self.username,
                   "password": self.password}
        path = "/authn/login"
        url = self.okapi_url + path
        req = requests.post(url, data=json.dumps(payload), headers=headers)
        if req.status_code != 201:
            raise ValueError("Request failed {}".format(req.status_code))
        self.okapi_token = req.headers.get('x-okapi-token')
        self.refresh_token = req.headers.get('refreshtoken')

    def folio_get(self, path, key, query=''):
        '''Fetches data from FOLIO and turns it into a json object'''
        url = self.okapi_url+path+query
        req = requests.get(url,
                           headers=self.okapi_headers)
        req.raise_for_status()
        result = json.loads(req.text)[key]
        if not any(result):
            raise ValueError("No {} setup in tenant".format(key))
        return result

    def get_instance_json_schema(self):
        '''Fetches the JSON Schema for instances'''
        url = 'https://raw.github.com'
        path = '/folio-org/mod-inventory-storage/master/ramls/instance.json'
        req = requests.get(url+path)
        return json.loads(req.text)

    def get_holdings_schema(self):
        '''Fetches the JSON Schema for holdings'''
        url = 'https://raw.github.com'
        path = '/folio-org/mod-inventory-storage/master/ramls/holdingsrecord.json'
        req = requests.get(url+path)
        return json.loads(req.text)

    def get_item_schema(self):
        '''Fetches the JSON Schema for holdings'''
        url = 'https://raw.github.com'
        path = '/folio-org/mod-inventory-storage/master/ramls/item.json'
        req = requests.get(url+path)
        return json.loads(req.text)

    def get_location_id(self, location_code):
        try:
            return next((l['id'] for l in self.locations
                         if location_code.strip() == l['code']),
                        (next(l['id'] for l in self.locations
                              if l['code']
                              in ['catch_all', 'default', 'Default']))
                        )
        except Exception as exception:
            raise ValueError(("No location with code '{}' in locations. "
                              "No catch_all/default location either"))
