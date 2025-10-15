# Authentication

FolioClient handles FOLIO authentication automatically, but it's important to understand how it works and the available options.

## Connect to FOLIO

Connecting to FOLIO requires a username and password:

```python
from folioclient import FolioClient

client = FolioClient(
    folio_url="https://your-folio-instance.com",
    tenant="your_tenant",
    username="your_username",
    password="your_password"
)
```
:::{note}
`FolioClient` does not support single-sign-on (SSO) authentication workflows. You will need to use a user account with a FOLIO username and password to authenticate.
:::

## How Authentication Works

FolioClient uses FOLIO's token-based authentication system:

1. **Initial Login**: Client authenticates with username/password to receive a token
2. **Token Storage**: The token is stored and used for subsequent requests
3. **Automatic Refresh**: When the token expires, the client automatically refreshes it
4. **Session Management**: Tokens are managed transparently across sync and async operations

:::{note}
The auth flow will attempt to reauthenticate (using credentials provided when instantiating the FolioClient instance) whenever it receives a `401 (UNAUTHORIZED)` response from FOLIO in response to an `httpx.Request` and then resubmit the request that raised the `401`. `403 (FORBIDDEN)` errors are handled by the [new retry handling](./retry_configuration.md).
:::

### Token Lifecycle

```python
# Authentication happens automatically on first API call
client = FolioClient(folio_url="...", tenant="...", username="...", password="...")

# First call triggers authentication
users = client.folio_get("/users", "users")  # Authenticates here

# Subsequent calls use stored token
groups = client.folio_get("/groups", "usergroups")  # Uses token

# Token refresh happens automatically when needed
more_users = client.folio_get("/users", "users")  # May refresh token
```

## Security Best Practices

### Environment Variables

Store credentials in environment variables, not in code:

```bash
# .env file or environment
export FOLIO_URL="https://your-folio-instance.com"
export FOLIO_TENANT="your_tenant"
export FOLIO_USERNAME="your_username"
export FOLIO_PASSWORD="your_password"
```

```python
import os
from folioclient import FolioClient

client = FolioClient(
    folio_url=os.getenv("FOLIO_URL"),
    tenant=os.getenv("FOLIO_TENANT"),
    username=os.getenv("FOLIO_USERNAME"),
    password=os.getenv("FOLIO_PASSWORD")
)
```

### Configuration Files

For development, you can use configuration files:

```yaml
# config.yml
folio:
  url: "https://folio-dev.example.com"
  tenant: "diku"
  username: "diku_admin"
  password: "admin"
```

```python
import yaml
from folioclient import FolioClient

with open("config.yml") as f:
    config = yaml.safe_load(f)

client = FolioClient(**config["folio"])
```

## Permission Requirements

Your FOLIO user account needs appropriate capabilities (Eureka FOLIO) or permissions (Okapi FOLIO) for the operations you want to perform:

**Read Operations**
: View permissions for relevant modules (users, inventory, etc.)

**Write Operations**
: Create, edit, or delete permissions for relevant modules

**Administrative Operations**
: Administrative permissions may be required for some endpoints

## Common Authentication Issues

### Invalid Credentials

```python
import httpx

try:
    client = FolioClient(...)
    users = client.folio_get("/users", "users")
except httpx.HTTPStatusError as e:
    if e.response.status_code == 401:
        print("Authentication failed - check credentials")
    elif e.response.status_code == 403:
        print("Access denied - check permissions")
```
```{note}
`FolioClient` provides a [set of custom exceptions](./api/exceptions.md) that are raised when an HTTP error occurs that are more granular than those provide by httpx. However, each is derived from a parent `httpx` exception. For example, `folioclient.FolioAuthenticationError` is raised when an `httpx.HTTPStatusError` occurs with a `401` status, while a `folioclient.FolioPermissionError` is raised for a `403`.
```
### Network Issues

```python
import httpx

try:
    client = FolioClient(...)
    users = client.folio_get("/users", "users")
except httpx.ConnectError:
    print("Cannot connect to FOLIO instance")
except httpx.TimeoutException:
    print("Request timed out")
```

### Token Expiration

FolioClient handles token expiration automatically, but you can catch related errors:

```python
from folioclient.exceptions import FolioClientException

try:
    # Long-running operation
    for user in client.folio_get_all("/users", "users"):
        process_user(user)
except FolioClientException as e:
    print(f"Authentication error: {e}")
```

## Advanced Authentication

### Session Persistence

FolioClient maintains authentication across the client lifecycle:

```python
# Authentication persists across multiple operations
client = FolioClient(...)

# All these operations use the same authenticated session
users = client.folio_get("/users", "users")
groups = client.folio_get("/groups", "usergroups")
items = client.folio_get("/inventory/items", "items")

# Clean up when done
client.close()
```
Once a `client` is closed, it cannot be re-used to connect to FOLIO.

### Context Manager

Use context managers for automatic cleanup:

```python
# Recommended pattern
with FolioClient(folio_url="...", tenant="...", username="...", password="...") as client:
    users = client.folio_get("/users", "users")
    # Client automatically closed and cleaned up
```

## Async Authentication

Authentication works the same way with async operations:

```python
import asyncio
from folioclient import FolioClient

async def main():
    client = FolioClient(...)
    
    try:
        # Authentication happens on first async call
        users = await client.folio_get_async("/users", "users")
        
        # Subsequent calls use stored token
        groups = await client.folio_get_async("/groups", "usergroups")
        
    finally:
        await client.close()

asyncio.run(main())
```

## Troubleshooting

### Enable Debug Logging

```python
import logging

# Enable debug logging to see authentication details
logging.basicConfig(level=logging.DEBUG)

client = FolioClient(...)
users = client.folio_get("/users", "users")
```

### Verify Tenant ID

Make sure your tenant ID is correct - it's case-sensitive and must match exactly
