# FolioClient
![example workflow](https://github.com/folio-fse/FolioClient/actions/workflows/python-package.yml/badge.svg)    
FolioClient is a modern, async-capable Python library that provides a comprehensive interface to FOLIO Library Systems Platform APIs. Built on HTTPX with robust authentication, automatic token management, and full support for both synchronous and asynchronous operations.

## Features

### 🚀 **Modern Async Architecture (New in v1.0.0)**
* **Full async/await support** - All API methods now have async counterparts for high-performance concurrent operations
* **HTTPX-based** - Modern HTTP client with HTTP/2 support, connection pooling, and better performance
* **Context manager support** - Proper resource cleanup with `async with` syntax

### 🔐 **Enhanced Authentication**
* **Cookie-based authentication** - Improved session management with automatic cookie handling
* **RTR (Refresh Token Rotation) support** - Seamless token refresh without re-authentication
* **Multi-tenant ECS support** - Easy tenant switching in consortial environments
* **Automatic token lifecycle management** - Tokens refreshed transparently when needed

### 📡 **Comprehensive API Coverage**
* **Complete REST operations** - GET, POST, PUT, DELETE with both sync and async variants
* **Intelligent pagination** - `folio_get_all()` automatically handles large result sets
* **CQL query support** - Full Contextual Query Language support for complex searches
* **Flexible response handling** - Extract specific keys or work with full responses

### 🏗️ **Developer Experience**
* **Pre-configured HTTP clients** - `get_folio_http_client()` and `get_folio_http_client_async()` for advanced use cases
* **Cached reference data** - Common inventory data cached as properties for performance
* **JSON Schema validation** - Latest FOLIO schemas fetched automatically
* **Comprehensive error handling** - Automatic retry logic and detailed error reporting

## Installing

**Requirements:** Python 3.10+ (v1.0.0+)

```bash
pip install folioclient
```

```bash
uv pip install folioclient  # Using uv (recommended)
```

**For development:**
```bash
git clone https://github.com/FOLIO-FSE/FolioClient.git
cd FolioClient
uv sync  # Install with development dependencies
```

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

### 🆕 **Async API Operations (New in v1.0.0)**
```Python
import asyncio
from folioclient import FolioClient

async def main():
    async with FolioClient(
        "https://folio-snapshot-okapi.dev.folio.org",
        "diku",
        "diku_admin",
        os.environ.get("FOLIO_PASSWORD")
    ) as fc:
        # Async queries for better performance
        instances = await fc.folio_get_async(
            "/instance-storage/instances", 
            key="instances", 
            query_params={"limit": 100}
        )
        
        # Process multiple requests concurrently
        tasks = [
            fc.folio_get_async("/instance-storage/instances", query_params={"offset": i*100, "limit": 100})
            for i in range(10)
        ]
        results = await asyncio.gather(*tasks)
        
        # Async bulk operations
        async for instance in fc.folio_get_all_async("/instance-storage/instances", key="instances"):
            # Process each instance as it's fetched
            print(f"Processing instance: {instance['title']}")

# Run the async function
asyncio.run(main())
```

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

### 🔧 **Convenience Methods for FOLIO HTTP Operations**
FolioClient provides both **synchronous** and **asynchronous** methods for all standard HTTP operations:

```Python
# Synchronous operations
instance = instances[0]
put_response = fc.folio_put(f"/instance-storage/instances/{instance['id']}", payload=instance)
post_response = fc.folio_post("/users", payload=new_user)
delete_response = fc.folio_delete(f"/users/{user_id}")

# 🆕 Asynchronous operations (New in v1.0.0)
put_response = await fc.folio_put_async(f"/instance-storage/instances/{instance['id']}", payload=instance)
post_response = await fc.folio_post_async("/users", payload=new_user)
delete_response = await fc.folio_delete_async(f"/users/{user_id}")

# Concurrent operations for better performance
tasks = [
    fc.folio_put_async(f"/instance-storage/instances/{inst['id']}", payload=inst)
    for inst in instances_to_update
]
results = await asyncio.gather(*tasks)
```

## 🔐 Enhanced Authentication & Token Management

### Automatic Token Lifecycle
FolioClient v1.0.0 introduces **cookie-based authentication** with automatic token refresh. Your auth token is managed transparently with RTR (Refresh Token Rotation) support:

```Python
# The token is accessible as a property of the FolioClient instance
auth_token = fc.okapi_token
print(auth_token)
# eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJNQXJBbm10WUV2azV6TTdtQ3puMmIzZDJlZ1NsNk5rZUsxRjBaV1cxd1d3In0...

# Headers automatically include valid auth tokens
print(fc.okapi_headers)
# {'x-okapi-tenant': 'diku', 'x-okapi-token': 'eyJhbGciOiJSUzI1NiIs...', 'content-type': 'application/json'}
```

### 🆕 **Using Pre-configured HTTPX Clients (New)**
For advanced scenarios, get pre-configured HTTPX clients with built-in FOLIO authentication:

```Python
# Synchronous client
with fc.get_folio_http_client() as client:
    response = client.get("/instance-storage/instances?limit=10")
    instances = response.json()

# Asynchronous client  
async with fc.get_folio_http_client_async() as client:
    response = await client.get("/instance-storage/instances?limit=10")
    instances = response.json()
    
    # Perform multiple concurrent requests
    tasks = [
        client.get(f"/instance-storage/instances/{instance_id}")
        for instance_id in instance_ids
    ]
    responses = await asyncio.gather(*tasks)
```

The pre-configured clients include:
- ✅ **Automatic authentication** with cookie-based sessions
- ✅ **Retry logic** for transient authorization errors  
- ✅ **Proper FOLIO headers** (tenant, content-type)
- ✅ **Base URL configuration** - just use relative paths
- ✅ **SSL verification** settings from your FolioClient instance

### Custom HTTP Requests with FOLIO Headers
For custom HTTP implementations, access FOLIO headers with valid auth tokens:

```Python
import requests
import aiohttp
import asyncio

# Synchronous with requests
with requests.Session() as session:
    response = session.get(
        fc.gateway_url + "/instance-storage/instances", 
        headers=fc.okapi_headers
    )
    response.raise_for_status()
    instances = response.json()

# Asynchronous with aiohttp
async def fetch_with_aiohttp():
    async with aiohttp.ClientSession(headers=fc.okapi_headers) as session:
        async with session.get(fc.gateway_url + "/instance-storage/instances") as response:
            response.raise_for_status()
            return await response.json()

instances = asyncio.run(fetch_with_aiohttp())
```

### 🌐 **Enhanced ECS (Consortial) Support**
FolioClient v1.0.0 provides improved support for FOLIO ECS (consortial) environments:

```Python
# Check if connected to ECS environment
if fc.is_ecs:
    print(f"Consortium: {fc.ecs_consortium['name']}")
    print(f"Members: {[member['name'] for member in fc.ecs_members]}")

# Switch between tenants seamlessly
print(f"Current tenant: {fc.tenant_id}")  # 'cs01'

# Switch to member tenant
fc.tenant_id = "cs01m0001"
print(f"Switched to: {fc.tenant_id}")  # 'cs01m0001'

# Reset back to original tenant
del fc.tenant_id
print(f"Back to: {fc.tenant_id}")  # 'cs01'

# All API calls automatically use the correct tenant context
instances = fc.folio_get("/instance-storage/instances", query_params={"limit": 10})
```
