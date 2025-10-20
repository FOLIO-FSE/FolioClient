# Performance

FolioClient is designed for high performance, but there are several strategies you can use to optimize your applications further.

## JSON Processing Optimization

### Experimental orjson Support

Install FolioClient with experimental orjson support for significantly faster JSON processing:

```bash
pip install folioclient[orjson]
```

```{note}
`orjson`-based JSON handling is experimental and may have compatibility issues in some environments. Test thoroughly before using in production.
```
This may provide 2-5x performance improvements for JSON-heavy operations:

```python
from folioclient import FolioClient

# orjson is used automatically when available
client = FolioClient(...)

# Large JSON responses are processed much faster with orjson
large_dataset = client.folio_get("/inventory/items", "items", limit=1000)
```

:::{note}
For most operations with a FOLIO system, the performance bottleneck will be sending or receiving results, not deserializing JSON data. This means that the real-world impact of using `orjson` optimizations may not be noticeable in most circumstances.
:::

## Connection and Request Optimization

### Connection Pooling

FolioClient uses httpx with automatic connection pooling:

```python
# Connection pooling happens automatically when you invoke FolioClient as a context manager
with FolioClient(...) as client:

    # Multiple requests reuse connections
    for i in range(100):
        users = client.folio_get("/users", "users", limit=10, offset=i*10)
```

### Timeout Configuration

FolioClient provides granular timeout control for different aspects of HTTP connections. You can configure timeouts using environment variables, constructor parameters, or httpx.Timeout objects.

#### Environment Variables

Configure timeouts globally using these environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `FOLIOCLIENT_CONNECT_TIMEOUT` | `None` | Connection timeout in seconds (unlimited by default) |
| `FOLIOCLIENT_READ_TIMEOUT` | `None` | Read timeout in seconds (unlimited by default) |
| `FOLIOCLIENT_WRITE_TIMEOUT` | `None` | Write timeout in seconds (unlimited by default) |
| `FOLIOCLIENT_POOL_TIMEOUT` | `None` | Connection pool timeout in seconds (unlimited by default) |

#### Legacy Timeout Support

For backward compatibility, the legacy `FOLIOCLIENT_HTTP_TIMEOUT` variable is still supported. When set, it applies the same timeout value to all timeout types:

```bash
# Legacy: applies 60 seconds to all timeout types
export FOLIOCLIENT_HTTP_TIMEOUT=60

# Modern: granular control
export FOLIOCLIENT_CONNECT_TIMEOUT=15
export FOLIOCLIENT_READ_TIMEOUT=180
export FOLIOCLIENT_WRITE_TIMEOUT=30
export FOLIOCLIENT_POOL_TIMEOUT=10
```

#### Programmatic Configuration

Pass timeout configuration directly to the FolioClient constructor:

```python
from folioclient import FolioClient
import httpx

# No timeout parameter - uses environment variables if set
client = FolioClient(
    "https://folio.example.com",
    "tenant_id",
    "username", 
    "password"
    # Will use FOLIOCLIENT_*_TIMEOUT environment variables
)

# Explicit timeout=None - ignores all environment variables
client = FolioClient(
    "https://folio.example.com",
    "tenant_id",
    "username", 
    "password",
    timeout=None  # Forces unlimited timeout, ignores environment
)

# Single timeout value (applies to all timeout types)
client = FolioClient(
    "https://folio.example.com",
    "tenant_id",
    "username", 
    "password",
    timeout=60.0
)

# Granular timeout dictionary
client = FolioClient(
    "https://folio.example.com",
    "tenant_id", 
    "username",
    "password",
    timeout={
        "connect": 15.0,
        "read": 180.0,
        "write": 30.0,
        "pool": 10.0
    }
)

# httpx.Timeout object (for maximum control)
timeout_obj = httpx.Timeout(
    connect=15.0,
    read=180.0, 
    write=30.0,
    pool=10.0
)
client = FolioClient(
    "https://folio.example.com",
    "tenant_id",
    "username", 
    "password", 
    timeout=timeout_obj
)
```

#### Important Timeout Behavior

There's an important distinction between not specifying the `timeout` parameter and explicitly setting it to `None`:

- **No `timeout` parameter**: Uses environment variables (`FOLIOCLIENT_*_TIMEOUT`) or defaults
- **`timeout=None`**: Explicitly ignores all environment variables and sets timeout to "unlimited"
- **`timeout=<value>`**: Uses the specified value to construct a httpx.Timeout object

#### Timeout Types Explained

- **Connect Timeout**: Maximum time to wait for establishing a connection
- **Read Timeout**: Maximum time to wait for receiving data from the server  
- **Write Timeout**: Maximum time to wait for sending data to the server
- **Pool Timeout**: Maximum time to wait for a connection from the connection pool

#### Timeout Tuning Guidelines

**For fast, reliable networks and high-performance FOLIO environments:**
```bash
export FOLIOCLIENT_CONNECT_TIMEOUT=10
export FOLIOCLIENT_READ_TIMEOUT=120
export FOLIOCLIENT_WRITE_TIMEOUT=15
export FOLIOCLIENT_POOL_TIMEOUT=5
```

**For slow or unreliable networks:**
```bash
export FOLIOCLIENT_CONNECT_TIMEOUT=60
export FOLIOCLIENT_READ_TIMEOUT=600
export FOLIOCLIENT_WRITE_TIMEOUT=60  
export FOLIOCLIENT_POOL_TIMEOUT=30
```

**For large data operations:**
```bash
export FOLIOCLIENT_READ_TIMEOUT=1800  # 30 minutes
export FOLIOCLIENT_WRITE_TIMEOUT=1800
```

#### Configuration Priority

Timeout configuration follows this priority order:

1. **Constructor `timeout` parameter** (highest priority)
   - `httpx.Timeout` object: Uses as-is, completely overrides environment variables
   - `float/int`: Uses as single timeout for all types, overrides environment variables  
   - `dict`: **Merges with environment variables** - dict values override environment, missing dict keys filled from environment
   - `timeout=None`: Ignores all environment variables sets timeout to unlimited for all operations
2. **Environment variables** (used when no `timeout` parameter provided, and merged with dict timeout argument)
   - `FOLIOCLIENT_HTTP_TIMEOUT` provides the default timeout value for all types
   - Granular variables (`FOLIOCLIENT_*_TIMEOUT`) override specific timeout types
   - Both can be used together (granular settings override the legacy default)

#### Default Timeout Behavior

The default timeout behavior maintains backward compatibility with the original requests-based implementation:

- **All timeouts**: `None` (unlimited) by default
- **Environment variable fallback**: When environment variables are set, those values are used
- **Legacy compatibility**: `FOLIOCLIENT_HTTP_TIMEOUT` applies the same timeout to all timeout types

**No timeouts by default** means:
- Better compatibility with legacy FOLIO environments
- No unexpected timeout errors for long-running operations
- Consistent behavior with the original `requests`-based functionality

To enable granular timeouts, set environment variables:
```bash
export FOLIOCLIENT_CONNECT_TIMEOUT=30
export FOLIOCLIENT_READ_TIMEOUT=300  # 5 minutes
export FOLIOCLIENT_WRITE_TIMEOUT=30
export FOLIOCLIENT_POOL_TIMEOUT=10
```

## Async Performance

### Concurrent Operations

Use async for concurrent API calls:

```python
import asyncio
import time

async def concurrent_requests():
    client = FolioClient(...)
    
    start_time = time.time()
    
    # Sequential requests (slow)
    users = await client.folio_get_async("/users", "users")
    groups = await client.folio_get_async("/groups", "usergroups") 
    locations = await client.folio_get_async("/locations", "locations")
    
    sequential_time = time.time() - start_time
    print(f"Sequential: {sequential_time:.2f}s")
    
    start_time = time.time()
    
    # Concurrent requests (fast)
    users, groups, locations = await asyncio.gather(
        client.folio_get_async("/users", "users"),
        client.folio_get_async("/groups", "usergroups"),
        client.folio_get_async("/locations", "locations")
    )
    
    concurrent_time = time.time() - start_time
    print(f"Concurrent: {concurrent_time:.2f}s")
    print(f"Speedup: {sequential_time/concurrent_time:.1f}x")
```

### Controlled Concurrency

Limit concurrency to avoid overwhelming FOLIO:

```python
import asyncio
from asyncio import Semaphore

async def controlled_concurrency():
    client = FolioClient(...)
    semaphore = Semaphore(5)  # Max 5 concurrent requests
    
    async def fetch_with_limit(endpoint, key):
        async with semaphore:
            return await client.folio_get_async(endpoint, key)
    
    # Process many requests with controlled concurrency
    endpoints = [
        ("/users", "users"),
        ("/groups", "usergroups"),
        ("/locations", "locations"),
        ("/service-points", "servicepoints"),
        ("/material-types", "mtypes"),
    ]
    
    tasks = [fetch_with_limit(ep, key) for ep, key in endpoints]
    results = await asyncio.gather(*tasks)
    
    print(f"Fetched {len(results)} datasets with controlled concurrency")
```

## Pagination Performance

### Batch Size Optimization

Choose optimal batch sizes for your use case:

```python
import time

def benchmark_batch_sizes():
    client = FolioClient(...)
    
    batch_sizes = [10, 50, 100, 500, 1000]
    
    for batch_size in batch_sizes:
        start_time = time.time()
        count = 0
        
        for user in client.folio_get_all("/users", "users", limit=batch_size):
            count += 1
            if count >= 1000:  # Process 1000 users for benchmark
                break
        
        elapsed = time.time() - start_time
        print(f"Batch size {batch_size}: {elapsed:.2f}s ({count/elapsed:.1f} users/sec)")
```

### ID-Based Pagination

Use ID-sorted queries for optimal pagination performance, particularly for large record sets (100s of thousands or millions of records):

```python
# Slower: offset-based pagination
for user in client.folio_get_all("/users", "users"):
    process_user(user)

# Faster: ID-based pagination (automatic when sorted by id)
query = "active==true sortBy id"
for user in client.folio_get_all("/users", "users", query=query):
    process_user(user)
```

## Error Handling Performance

### Built-in Retry System

FolioClient includes modern retry logic powered by [tenacity](https://tenacity.readthedocs.io/) that's optimized for performance:

```python
import os
from folioclient import FolioClient

# Configure optimal retry settings for your environment
os.environ['FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES'] = '3'
os.environ['FOLIOCLIENT_SERVER_ERROR_RETRY_DELAY'] = '2.0'
os.environ['FOLIOCLIENT_SERVER_ERROR_MAX_WAIT'] = '30'

client = FolioClient(...)

# All client methods automatically include retry logic
users = client.folio_get("/users", "users")  # Retries on 502, 503, 504
```

### Performance Benefits

The built-in retry system provides:

- **Zero overhead when no errors occur** - No performance penalty for successful requests
- **Efficient backoff** - Exponential backoff prevents overwhelming servers
- **Configurable limits** - Prevent runaway retry loops
- **Automatic jitter** - Prevents thundering herd problems
- **Async-aware** - Works seamlessly with async operations

For detailed retry configuration, see the [Retry Configuration Guide](retry_configuration.md).

## Best Practices Summary

1. **Use orjson experimentally** for JSON-heavy applications (deserialization-only)
2. **Implement async** for concurrent operations
3. **Choose appropriate batch sizes** (start with 50-100 for most cases)
4. **Use ID-based pagination** when possible (sort by id)
5. **Implement caching** for frequently accessed data
6. **Handle errors gracefully** with retries
7. **Process data streaming** for large datasets
8. **Control concurrency** to avoid overwhelming FOLIO
9. **Clean up resources** properly with context managers

```python
# Performance-optimized example
import asyncio
from asyncio import Semaphore

async def optimized_processing():
    # Use experimental orjson if available
    async with FolioClient(...) as client:
        # Control concurrency
        semaphore = Semaphore(3)
       
        async def process_user_batch(users):
            async with semaphore:
                for user in users:
                    await process_user_async(user)
       
        # Use ID-based pagination with optimal batch size
        query = "active==true sortBy id"
        batch = []
        batch_size = 100
        
        async for user in client.folio_get_all_async(
            "/users", "users", query=query, limit=batch_size
        ):
            batch.append(user)
            
            if len(batch) >= batch_size:
                await process_user_batch(batch)
                batch = []
        
        # Process remaining users
        if batch:
            await process_user_batch(batch)

asyncio.run(optimized_processing())
```
