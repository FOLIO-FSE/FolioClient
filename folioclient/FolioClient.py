import json
import logging
from datetime import datetime

import requests
from folioclient.cached_property import cached_property


class FolioClient:
    '''handles communication and getting values from FOLIO'''

    def __init__(self, okapi_url, tenant_id, username, password):
        self.missing_location_codes = set()
        self.cql_all = '?query=cql.allRecords=1'
        self.okapi_url = okapi_url
        self.tenant_id = tenant_id
        self.username = username
        self.password = password
        self.login()
        self.okapi_headers = {'x-okapi-token': self.okapi_token,
                              'x-okapi-tenant': self.tenant_id,
                              'content-type': 'application/json'}

    @cached_property
    def current_user(self):
        logging.info('fetching current user..')
        try:
            path = f'/bl-users/by-username/{self.username}'
            resp = self.folio_get(path, 'user')
            return resp['id']
        except Exception as exception:
            logging.error(
                f'Unable to fetch user id for user {self.username}',
                exc_info=exception)
            return ''

    @cached_property
    def identifier_types(self):
        return self.folio_get_all("/identifier-types",
                                  "identifierTypes",
                                  self.cql_all)

    @cached_property
    def contributor_types(self):
        return self.folio_get_all("/contributor-types",
                                  "contributorTypes",
                                  self.cql_all)

    @cached_property
    def contrib_name_types(self):
        return self.folio_get_all("/contributor-name-types",
                                  "contributorNameTypes",
                                  self.cql_all)

    @cached_property
    def instance_types(self):
        return self.folio_get_all("/instance-types",
                                  "instanceTypes",
                                  self.cql_all)

    @cached_property
    def instance_formats(self):
        return self.folio_get_all("/instance-formats",
                                  "instanceFormats",
                                  self.cql_all)

    def get_single_instance(self, instance_id):
        return self.folio_get_all("inventory/instances/{}"
                                  .format(instance_id))

    @cached_property
    def alt_title_types(self):
        return self.folio_get_all("/alternative-title-types",
                                  "alternativeTitleTypes",
                                  self.cql_all)

    @cached_property
    def locations(self):
        return self.folio_get_all("/locations",
                                  "locations",
                                  self.cql_all)

    @cached_property
    def instance_note_types(self):
        return self.folio_get_all("/instance-note-types",
                                  "instanceNoteTypes",
                                  self.cql_all)

    @cached_property
    def class_types(self):
        return self.folio_get_all("/classification-types",
                                  "classificationTypes",
                                  self.cql_all)

    @cached_property
    def organizations(self):
        return self.folio_get_all("/organizations-storage/organizations",
                                  "organizations",
                                  self.cql_all)

    @cached_property
    def modes_of_issuance(self):
        return self.folio_get_all("/modes-of-issuance",
                                  "issuanceModes",
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

    def folio_get_all(self, path, key=None, query=''):
        '''Fetches ALL data objects from FOLIO and turns
        it into a json object'''
        results = list()
        limit = 100
        offset = 0
        q_template = "?limit={}&offset={}" if not query  else "&limit={}&offset={}"
        q = query + q_template.format(limit, offset * limit)
        temp_res = self.folio_get(
            path, key, query + q_template.format(limit, offset * limit))
        results.extend(temp_res)
        while len(temp_res) == limit:
            offset += 1
            temp_res = self.folio_get(
                path, key, query + q_template.format(limit, offset * limit))
            results.extend(temp_res)
        return results

    def folio_get(self, path, key=None, query=''):
        '''Fetches data from FOLIO and turns it into a json object'''
        url = self.okapi_url + path + query
        req = requests.get(url,
                           headers=self.okapi_headers)
        req.raise_for_status()
        result = (json.loads(req.text)[key] if key else json.loads(req.text))
        return result

    def folio_get_single_object(self, path):
        '''Fetches data from FOLIO and turns it into a json object as is'''
        url = self.okapi_url + path
        req = requests.get(url,
                           headers=self.okapi_headers)
        req.raise_for_status()
        result = json.loads(req.text)
        return result

    def get_instance_json_schema(self):
        '''Fetches the JSON Schema for instances'''
        url = 'https://raw.github.com'
        path = '/folio-org/mod-inventory-storage/master/ramls/instance.json'
        req = requests.get(url + path)
        return json.loads(req.text)

    def get_holdings_schema(self):
        '''Fetches the JSON Schema for holdings'''
        url = 'https://raw.github.com'
        path = '/folio-org/mod-inventory-storage/master/ramls/'
        file_name = 'holdingsrecord.json'
        req = requests.get(url + path + file_name)
        return json.loads(req.text)

    def get_item_schema(self):
        '''Fetches the JSON Schema for holdings'''
        url = 'https://raw.githubusercontent.com'
        path = '/folio-org/mod-inventory-storage/master/ramls/item.json'
        req = requests.get(url + path)
        return json.loads(req.text)

    def get_location_id(self, location_code):
        '''returns the location ID based on a location code'''
        try:
            return next((l['id'] for l in self.locations
                         if location_code.strip() == l['code']),
                        (next(l['id'] for l in self.locations
                              if l['code']
                              in ['catch_all', 'default', 'Default', 'ATDM']))
                        )
        except Exception as exception:
            raise ValueError(("No location with code '{}' in locations. "
                              "No catch_all/default location either"))

    def get_metadata_construct(self):
        '''creates a metadata construct with the current API user_id
        attached'''
        user_id = self.current_user
        df = '%Y-%m-%dT%H:%M:%S.%f+0000'
        return {
            "createdDate": datetime.utcnow().strftime(df),
            "createdByUserId": user_id,
            "updatedDate": datetime.utcnow().strftime(df),
            "updatedByUserId": user_id
        }
