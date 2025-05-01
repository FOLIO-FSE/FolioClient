# FolioClient
![example workflow](https://github.com/folio-fse/FolioClient/actions/workflows/python-package.yml/badge.svg)    
FOLIO Client is a simple python (3) wrapper over the FOLIO LMS system API:s

## Features
* Convenient FOLIO login and OKAPI Token creation
* Wrappers for various REST operations
* Most common reference data for inventory are retrieved as cached properties. 
* Fetches the latest released schemas for instances, holdings and items. Very useful for JSON Schema based validation.

## Installing
```pip install folioclient ```

## Basic Usage

### Create a new FolioClient instance
```Python
import os
from folioclient import FolioClient

fc = FolioClient(
    "https://folio-snapshot-okapi.dev.folio.org", 
    "diku", 
    "diku_admin", 
    os.environ.get("FOLIO_PASSWORD")
) # Best Practice: use an environment variable to store your passwords
```

### Query an endpoint in FOLIO
```Python
# Basic query, limit=100
instances = fc.folio_get("/instance-storage/instances", key="instances", query_params={"limit": 100})

# mod-search query for all instances without holdings records, expand all sub-objects
instance_search = fc.folio_get(
    "/search/instances",
    key="instances", 
    query='cql.allRecords=1 not holdingsId=""', 
    query_params={
        "expandAll": True,
        "limit": 100
    }
)
```
> NOTE: mod-search has a hard limit of 100, with a maximum offset of 900 (will only return the first 1000)

### Get all records matching a query without retrieving all records at once
```Python
# Get all instances. When performing this operation, you should sort results by id to avoid random reordering of results
get_all_instances = fc.folio_get_all(
    "/instance-storage/instances", 
    key="instances", 
    limit=1000, 
    query="cql.allRecords=1 sortBy id"
)

"""
Now you can iterate over get_all_instances, and FolioClient will retrieve them in batches of 1000, 
yielding each record until all records matching the query are retrieved.
"""
for instance in get_all_instances:
    ...
```

### Convenience methods for basic FOLIO HTTP Actions (GET, PUT, POST)
FolioClient objects provide convenience methods for standard GET, PUT, POST and DELETE HTTP requests. In addition to the `folio_get` examples above:
```Python
# Put an existing object, return is based on the endpoint, often an empty 204 response
instance = instances[0]
put_object = fc.folio_put(f"/instance-storage/instances/{instance['id']}", payload=instance)

# Post a new object, 
user = {}
post_user = fc.folio_post("/users", payload=user)
```

## Auth Token management
Once you have instantiated a FolioClient object, it will manage the lifecycle of your auth token, 
retrieving a new valid token as needed. If you need to access the auth token directly:
```Python
# The token is accessible as a property of the FolioClient instance
auth_token = fc.okapi_token
print(auth_token)
eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJNQXJBbm10WUV2azV6TTdtQ3puMmIzZDJlZ1NsNk5rZUsxRjBaV1cxd1d3In0.eyJleHAiOjE3NDU1MDk3NzUsImlhdCI6MTc0NTUwOTE3NSwianRpIjoiOTIyMGEyODktMzRlZS00ODcwLWIwMGQtMTQ5N2UyNzNlYmYyIiwiaXNzIjoiaHR0cHM6Ly9rZXljbG9hay1zZWJmLmludC5hd3MuZm9saW8ub3JnL3JlYWxtcy9mczA5MDAwMDAwIiwiYXVkIjoiYWNjb3VudCIsInN1YiI6ImNoYW5pIiwidHlwIjoiQmVhcmVyIiwiYXpwIjoiZnMwOTAwMDAwMC1hcHBsaWNhdGlvbiIsInNpZCI6Ijg2MzhkZGYzLWQ0YmMtNDA0Ny04YjQzLTdmYjU4N2FjZjk5NCIsImFjciI6IjEiLCJhbGxvd2VkLW9yaWdpbnMiOlsiLyoiXSwicmVhbG1fYWNjZXNzIjp7InJvbGVzIjpbImRlZmF1bHQtcm9sZXMtZnMwOTAwMDAwMCIsIm9mZmxpbmVfYWNjZXNzIiwidW1hX2F1dGhvcml6YXRpb24iLCIyNWUxOWFkMDhjMmVkMDhiYzAwNjk1NzMwMWUzOGNhYzMwNTU3MDk5Il19LCJyZXNvdXJjZV9hY2Nlc3MiOnsiYWNjb3VudCI6eyJyb2xlcyI6WyJtYW5hZ2UtYWNjb3VudCIsIm1hbmFnZS1hY2NvdW50LWxpbmtzIiwidmlldy1wcm9maWxlIl19fSwic2NvcGUiOiJwcm9maWxlIGVtYWlsIiwiZW1haWxfdmVyaWZpZWQiOmZhbHNlLCJ1c2VyX2lkIjoiNzM0NmQ3NmMtMTQyYi00MjhlLThhZWQtMTQ2Mzg4NmM5ZmMxIiwibmFtZSI6IkNoYW5pIEF0cmVpZGVzIiwicHJlZmVycmVkX3VzZXJuYW1lIjoiY2hhbmkiLCJnaXZlbl9uYW1lIjoiQ2hhbmkiLCJmYW1pbHlfbmFtZSI6IkF0cmVpZGVzIiwiZW1haWwiOiJicm9va3N0cmF2aXNAbWlzc291cmlzdGF0ZS5lZHUifQ.nWSz8W88uDr3qq5Qlmh4M3z8VuPXHCB1y3gJiFtEPfLY8haTvELAqOkQUqodhhXiNbyRcN0ywxbsFsidAlCuSpaBEdZItxFaJMxg00du3Cpqd7QkHTHXt8pvqMtYq7rTbYRe98S_nVSVtHczP2OzJ5Tf5ONW_sbleu2xPG11Cv6asibhIToVF2zGWEQYMBPl-m91BQdx7s8aNqKYpiL5G-zuhD4SkstEA1Zbp4n-pSAeTb7XcWCA__lYllKVMPFLEt_C1lt46u8nS3i5eixx2ANblCDK_RHcOEuHisiTett8kKoQL8CeqDT4DzNTr8EzC-XBV9jOnCc6el59_nzVOw
```

## FOLIO request headers
If you would rather roll your own http requests, you can use FolioClient simply to manage your auth session with FOLIO. You can access the FOLIO headers object containing the current valid auth token via the `okapi_headers` property of the FolioClient object:
```Python
import requests
with requests.Session() as client:
    response = client.get(fc.gateway_url + "/instance-storage/instances", headers=fc.okapi_headers)
    response.raise_for_status()
    print(response.json())
```

### Switching tenants in a consortial (ECS) environment
When working with an ECS environment, you can authenticate as a user with multiple tenant affiliations and switch affiliations simply by assigning the desired tenant's tenant ID value to the `okapi_headers['x-okapi-tenant']` key:
```Python
fc.okapi_headers['x-okapi-tenant']
'cs01'

# Assign member tenant ID
fc.okapi_headers['x-okapi-tenant'] = "cs01m0001"

# Reset the headers back to original tenant
del fc.okapi_headers
fc.okapi_headers['x-okapi-tenant']
'cs01'
```
