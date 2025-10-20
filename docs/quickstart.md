# Quick Start Guide

This guide is to help get you up and running with FolioClient quickly. 

## Making Your First Request

Fetch some data from FOLIO using the context manager:

```python
with FolioClient(gateway_url="...", tenant_id="...", username="...", password="...") as client:
    # Get all users
    users = client.folio_get("/users", "users")
    print(f"Found {len(users)} users")

    # Get first user details
    if users:
        first_user = users[0]
        print(f"First user: {first_user['username']}")
```

## Basic Setup

First, import FolioClient and create a client instance. **Note: Using context managers is recommended** for automatic cleanup:

```python
from folioclient import FolioClient

# Recommended: Use context manager for automatic cleanup
with FolioClient(
    gateway_url="https://your-folio-instance.com",
    tenant_id="your_tenant",
    username="your_username", 
    password="your_password"
) as client:
    # Your code here - client automatically closed when done
    users = client.folio_get("/users", "users")
    print(f"Found {len(users)} users")

# Alternative: Manual cleanup (not recommended)
client = FolioClient(
    gateway_url="https://your-folio-instance.com",
    tenant_id="your_tenant",
    username="your_username", 
    password="your_password"
)
# Remember to call client.close() when done!
```

## Filtering with Queries

Use CQL queries to filter results:

```python
with FolioClient(gateway_url="...", tenant_id="...", username="...", password="...") as client:
    # Get active users only
    active_users = client.folio_get(
        "/users", 
        "users", 
        query="active==true"
    )

    # Get users by username pattern
    admin_users = client.folio_get(
        "/users",
        "users", 
        query="username=admin*"
    )

    # Complex query with sorting
    recent_users = client.folio_get(
        "/users",
        "users",
        query="metadata.createdDate>2024-01-01 sortBy metadata.createdDate/sort.descending"
    )
```

:::{note}
Some APIs in FOLIO do not support CQL queries. For these endpoints, you will need to specify the query parameters used to perform a query/filter manually using the `query_params` keyword argument to `folio_get()` or passing them as extra keyword arguments to the `folio_get_all()` methods. For `folio_get_all*` methods, these APIs may also require specifying a keyword argument `no_cql=True`, to prevent default CQL queries from being used. 
:::

## Working with Large Datasets

For large datasets, use the pagination methods:

```python
with FolioClient(gateway_url="...", tenant_id="...", username="...", password="...") as client:
    # Process all users one by one
    for user in client.folio_get_all("/users", "users"):
        print(f"Processing: {user['username']}")

    # Process with query filtering
    for active_user in client.folio_get_all("/users", "users", query="active==true"):
        print(f"Active user: {active_user['username']}")
```

:::{attention}
The `folio_get_all*` methods do not currently support APIs that do not utilize a `limit`/`offset` [argument pairing for paging](./pagination.md#offset-based-pagination), unless you are able to sort your query by ID, which will utilize the [offset by ID approach](./pagination.md#id-based-pagination) to retrie the requested records. For more information about working with paged results, visit the [pagination](./pagination) docs.
:::

## Creating and Updating Data

Create new records:

```python
# Create a new user group
new_group = {
    "group": "students",
    "desc": "Student user group"
}

result = client.folio_post("/groups", new_group)
print(f"Created group with ID: {result['id']}")
```

Update existing records:

```python
import uuid
# Update a user group
group_id = result['id'] # Previously created group object
updated_group = {
    "id": group_id,
    "group": "graduate_students", 
    "desc": "Graduate student user group"
}

client.folio_put(f"/groups/{group_id}", updated_group)
```

## Deleting Records

```python
# Delete a record
record_id = record['id'] # Previously created group object
client.folio_delete(f"/users/{record_id}")
```

## Error Handling

FolioClient includes automatic retry logic for common error conditions. Always handle potential errors:

```python
import httpx
from folioclient.exceptions import FolioClientClosed

try:
    users = client.folio_get("/users", "users")
except httpx.HTTPStatusError as e:
    if e.response.status_code == 404:
        print("Endpoint not found")
    elif e.response.status_code == 401:
        print("Authentication failed")
    else:
        print(f"HTTP error: {e.response.status_code}")
except FolioClientClosed:
    print("Client has been closed")
```

### Automatic Retry Behavior

FolioClient automatically retries certain error conditions when configured:

```python
import os

# Enable automatic retries for server errors
os.environ['FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES'] = '3'

# Enable automatic retries for auth errors (with re-authentication)
os.environ['FOLIOCLIENT_MAX_AUTH_ERROR_RETRIES'] = '2'

# Client methods now automatically retry on transient errors
users = client.folio_get("/users", "users")
```

The retry system handles:
- **Server errors** (502, 503, 504) with exponential backoff
- **Connection errors** with automatic reconnection
- **Authorization (permission) errors** (403) with automatic re-authentication

:::{note}
401 errors (authentication) are handled by the `httpx` auth flow process that manages your FOLIO access token. If a 401 error is returned by FOLIO after your have previously authenticated, FolioClient will attempt to re-authenticate you and re-submit the original request. For more information, see the [authentication](./authentication) docs.
:::

For detailed retry configuration, see the [Retry Configuration Guide](retry_configuration.md).

## Cleaning Up

Always close the client when done:

```python
# Synchronous cleanup
client.close()

# Async cleanup
await client.async_close

# Or use context manager (recommended)
with FolioClient(gateway_url="...", tenant_id="...", username="...", password="...") as client:
    users = client.folio_get("/users", "users")
    # Client automatically closed when exiting the block

# Async context manager
async with FolioClient(gateway_url="...", tenant_id="...", username="...", password="...") as client:
    users = await client.folio_get_async("/users", "users")
    ...
```

## Environment Variables

For security, use environment variables for credentials:

```python
import os
from folioclient import FolioClient

client = FolioClient(
    gateway_url=os.getenv("FOLIO_URL"),
    tenant_id=os.getenv("FOLIO_TENANT"),
    username=os.getenv("FOLIO_USERNAME"),
    password=os.getenv("FOLIO_PASSWORD")
)
```

## Common Patterns

Here are some common usage patterns:

### Batch Processing

```python
with FolioClient(gateway_url="...", tenant_id="...", username="...", password="...") as client:
    # Process all users one by one (recommended approach)
    for user in client.folio_get_all("/users", "users"):
        process_user(user)
    
    # Process users with filtering
    for active_user in client.folio_get_all("/users", "users", query="active==true"):
        process_user(active_user)
    
    # Process in larger chunks for better performance
    for user in client.folio_get_all("/users", "users", limit=1000):
        process_user(user)
```

:::{note}
`folio_get_all` automatically handles pagination for you, so you don't need to manually manage offsets and batching. However, you can experiment with `limit` values to tune the number of records retrieved per request. For more information, see the [pagination](./pagination) docs.
:::

### Finding Specific Records

```python
# Find user by exact username
users = client.folio_get("/users", "users", query="username==johndoe")
if users:
    user = users[0]
    print(f"Found user: {user['id']}")
```

### Working with Related Data

```python
# Get user and their loans
user_id = user['id'] # ID from previously fetched user object
loans = client.folio_get("/circulation/loans", "loans", query=f"userId=={user_id}")

print(f"User {user['username']} has {len(loans)} active loans")
```

## Sync vs Async Usage

FolioClient supports both synchronous and asynchronous APIs. Here’s a side-by-side example:

**Synchronous:**
```python
from folioclient import FolioClient
client = FolioClient(...)
users = client.folio_get("/users", "users")
print(f"Found {len(users)} users")
client.close()
```

**Asynchronous:**
```python
import asyncio
from folioclient import FolioClient
async def main():
    client = FolioClient(...)
    users = await client.folio_get_async("/users", "users")
    print(f"Found {len(users)} users")
    await client.close()
asyncio.run(main())
```

See [Async Usage](async_usage.md) for more advanced patterns.

## Troubleshooting

**Common issues:**
- Authentication errors: Double-check your username, password, and tenant. Use environment variables for credentials when possible.
- Endpoint not found: Make sure your FOLIO instance URL and endpoint paths are correct.
- Connection errors: Check network connectivity and firewall settings.
- Client closed: Always use context managers or remember to call `client.close()`/`await client.close()`.

See [Authentication](authentication.md) and [Retry Configuration](retry_configuration.md) for more help.

## Next Steps

* Learn about [async_usage](async_usage.md) for high-performance applications
* Understand [authentication](authentication.md) options and security
* Explore [pagination](pagination.md) strategies for large datasets
* Check the [API Reference](api/folioclient.md) for all available methods
