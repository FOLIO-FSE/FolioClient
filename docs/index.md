# FolioClient Documentation

[![PyPI Version](https://img.shields.io/pypi/v/folioclient.svg)](https://pypi.org/project/folioclient/)
[![Python Versions](https://img.shields.io/pypi/pyversions/folioclient.svg)](https://pypi.org/project/folioclient/)
[![License](https://img.shields.io/github/license/FOLIO-FSE/FolioClient.svg)](https://github.com/FOLIO-FSE/FolioClient/blob/master/LICENSE)

FolioClient is a Python library for interacting with FOLIO Library Systems Platform APIs. 
It provides both synchronous and asynchronous interfaces for making API calls, handling 
authentication, pagination, and data processing.

## Key Features

* **Dual Interface**: Both sync and async support for all operations
* **Smart Pagination**: Automatic handling of large datasets with optimized ID-based pagination
* **Authentication Management**: Automatic token handling and refresh
* **Intelligent Retry Logic**: Modern tenacity-based exponential backoff with configurable limits
* **Performance Optimized**: Experimental orjson support for faster JSON processing
* **Type Safe**: Full type hints for better IDE support and code reliability
* **FOLIO Native**: Built specifically for FOLIO's API patterns and conventions

## Getting Started

### Installation

```bash
pip install folioclient

# For experimental performance improvements
pip install folioclient[orjson]
```

### Basic Usage

```python
from folioclient import FolioClient

# Initialize the client
client = FolioClient(
    folio_url="https://your-folio-instance.com",
    tenant="your_tenant",
    username="your_username",
    password="your_password"
)

# Fetch data
users = client.folio_get("/users", "users")
print(f"Found {len(users)} users")

# With query filtering
active_users = client.folio_get(
    "/users", 
    "users", 
    query="active==true"
)

# Process all records with pagination
for user in client.folio_get_all("/users", "users"):
    print(f"Processing user: {user['username']}")

client.close() # Close the client (or use a context manager)
```

### Async Usage

```python
import asyncio
from folioclient import FolioClient

async def main():
    client = FolioClient(
        folio_url="https://your-folio-instance.com",
        tenant="your_tenant", 
        username="your_username",
        password="your_password"
    )

    # Async operations
    users = await client.folio_get_async("/users", "users")
    
    # Process all records asynchronously
    async for user in client.folio_get_all_async("/users", "users"):
        print(f"Processing user: {user['username']}")
    
    await client.close()

asyncio.run(main())
```

```{toctree}
:maxdepth: 2
:titlesonly:
:hidden:

installation
quickstart
authentication
api/folioclient
api/exceptions
pagination
async_usage
performance
retry_configuration
contributing
changelog
```

## Indices and tables

* {ref}`genindex`
* {ref}`modindex`
* {ref}`search`