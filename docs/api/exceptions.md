# Exceptions

```{eval-rst}
.. automodule:: folioclient.exceptions
   :members:
   :undoc-members:
   :show-inheritance:
```

## Usage Examples

### Basic Exception Handling

```python
from folioclient import FolioClient
from folioclient.exceptions import FolioClientClosed, FolioClientException
import httpx

client = FolioClient(...)

try:
    users = client.folio_get("/users", "users")
except httpx.HTTPStatusError as e:
    print(f"HTTP error: {e.response.status_code}")
except FolioClientClosed:
    print("Client has been closed")
except FolioClientException as e:
    print(f"FolioClient error: {e}")
```

### Async Exception Handling

```python
import asyncio
from folioclient import FolioClient
from folioclient.exceptions import FolioClientClosed

async def handle_errors():
    client = FolioClient(...)
    
    try:
        users = await client.folio_get_async("/users", "users")
    except FolioClientClosed:
        print("Client was closed during operation")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        await client.close()

asyncio.run(handle_errors())
```