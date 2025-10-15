# Pagination

FOLIO APIs return paginated results for large datasets. FolioClient provides intelligent pagination handling that optimizes performance based on the query type and data characteristics.

## Understanding FOLIO Pagination

FOLIO uses two pagination strategies:

1. **Offset-based pagination**: Traditional page-based approach
2. **ID-based pagination**: More efficient for large result sets

FolioClient automatically chooses the best strategy based on your query.

## Basic Pagination

### Manual Pagination

For fine-grained control, use manual pagination:

```python
from folioclient import FolioClient

client = FolioClient(...)

# Get first page
users = client.folio_get("/users", "users", limit=10, offset=0)
print(f"Page 1: {len(users)} users")

# Get second page  
users = client.folio_get("/users", "users", limit=10, offset=10)
print(f"Page 2: {len(users)} users")

# Continue until no more results
offset = 0
limit = 10

while True:
    users = client.folio_get("/users", "users", limit=limit, offset=offset)
    if not users:
        break
        
    print(f"Processing {len(users)} users at offset {offset}")
    
    for user in users:
        process_user(user)
        
    offset += len(users)
```

### Automatic Pagination

Use `folio_get_all()` for automatic, efficient pagination over large datasets:

```python
# Process all users automatically
for user in client.folio_get_all("/users", "users"):
    print(f"Processing: {user['username']}")

# With query filtering
for active_user in client.folio_get_all("/users", "users", query="active==true"):
    print(f"Active user: {active_user['username']}")
```
```{attention}
Endpoints that do not support paging using `offset` and `limit` are not currently supported by `folio_get_all`.
```
## Pagination Strategies

### Offset-Based Pagination

Traditional pagination using offset and limit:

```python
# Manual offset-based pagination
limit = 100
offset = 0
all_users = []

while limit == 100:
    batch = client.folio_get("/users", "users", limit=limit, offset=offset)
        
    all_users.extend(batch)
    offset += len(batch)
    limit = len(batch)
    print(f"Loaded {len(all_users)} total users")
```
```{attention}
Offset-based pagination is fine for querying most record types in FOLIO. However, if you are going to query a large dataset (eg. Instances, Holdings, or Items), you will experience increasing slowdowns and resource contention with each offset/page of records retrieved. For such large sets, using [id-based pagination](#id-based-pagination) will provide more reliable performance.
```

### ID-Based Pagination

More efficient for large datasets when sorted by ID:

```python
# FolioClient automatically uses ID-based pagination when appropriate
# This happens when your query is sorted by 'id'

query = "active==true sortBy id"
for user in client.folio_get_all("/users", "users", query=query):
    print(f"User ID: {user['id']}")
```

The client detects ID-sorted queries and automatically switches to ID-based pagination for better performance.

## Advanced Pagination Options

### Custom Batch Sizes

Control pagination batch size for optimal performance:

```python
# Small batches for memory-constrained environments
for user in client.folio_get_all("/users", "users", limit=10):
    process_user(user)

# Large batches for better throughput
for user in client.folio_get_all("/users", "users", limit=1000):
    process_user(user)

# Default batch size is 10, which works well for most cases
```

### Query-Specific Pagination

Different queries may benefit from different approaches:

```python
# For ID-sorted queries, FolioClient uses optimized ID-based pagination
id_sorted_query = "metadata.createdDate>2024-01-01 sortBy id"
for user in client.folio_get_all("/users", "users", query=id_sorted_query):
    print(f"User created: {user['metadata']['createdDate']}")

# For other sorts, it uses offset-based pagination
name_sorted_query = "active==true sortBy personal.lastName"
for user in client.folio_get_all("/users", "users", query=name_sorted_query):
    print(f"User: {user['personal']['lastName']}")
```

## Async Pagination

There is an async versions of `folio_get_all`: `folio_get_all_async`:

```python
import asyncio

async def process_all_users_async():
    async with FolioClient(...):    
        try:
           async for user in client.folio_get_all_async("/users", "users"):
               print(f"Processing: {user['username']}")
               await process_user_async(user)
        except (FolioConnectionError, FolioHTTPError) as e:
            print(
                f"Error retrieving {e.request.url}", getattr(getattr(e, "response"), "text", e)
            )

asyncio.run(process_all_users_async())
```

## Performance Optimization

### Choosing Batch Size

Optimal batch size depends on several factors:

```python
# Small records, network is fast -> larger batches
for item in client.folio_get_all("/items", "items", limit=1000):
    process_small_item(item)

# Large records, limited memory -> smaller batches  
for user in client.folio_get_all("/users", "users", limit=25):
    process_large_user_record(user)

# For most use cases, the default (100) works well
for record in client.folio_get_all("/endpoint", "key"):
    process_record(record)
```

### Monitoring Progress

Track pagination progress for long-running operations:

```python
import time

def process_with_progress():
    client = FolioClient(...)
    
    start_time = time.time()
    processed = 0
    
    for user in client.folio_get_all("/users", "users", limit=100):
        process_user(user)
        processed += 1
        
        # Progress report every 1000 records
        if processed % 1000 == 0:
            elapsed = time.time() - start_time
            rate = processed / elapsed
            print(f"Processed {processed} users ({rate:.1f} users/sec)")
```

## Error Handling in Pagination

Handle errors gracefully during pagination:

```python
import httpx
from folioclient.exceptions import FolioClientException

def robust_pagination():
    client = FolioClient(...)
    
    processed = 0
    errors = 0
    
    try:
        for user in client.folio_get_all("/users", "users"):
            try:
                process_user(user)
                processed += 1
            except Exception as e:
                print(f"Error processing user {user.get('id', 'unknown')}: {e}")
                errors += 1
                
    except httpx.HTTPStatusError as e:
        print(f"HTTP error during pagination: {e.response.status_code}")
    except FolioClientException as e:
        print(f"FolioClient error: {e}")
    
    print(f"Processed: {processed}, Errors: {errors}")
```

## Working with Filtered Results

### Pagination with CQL Queries

```python
# Filter and paginate efficiently
query = "active==true and personal.lastName=Smith*"

for user in client.folio_get_all("/users", "users", query=query):
    print(f"Active Smith: {user['personal']['lastName']}")

# Complex queries with sorting for optimal pagination
complex_query = """
active==true and 
metadata.createdDate>2024-01-01 
sortBy id
"""

for user in client.folio_get_all("/users", "users", query=complex_query):
    print(f"Recent user: {user['username']}")
```

### Counting Results

Get total count before processing:

```python
# Get total count first
total_count = client.folio_get("/users", "totalRecords", limit=0)
print(f"Total users: {total_count}")
```

```{note}
`limit=0` is the idiomatic way to get an accurate record count from most modules in FOLIO. Some Spring-based modules may throw an error with limit=0, so you will need to experiment
```

## Best Practices

1. **Use appropriate batch sizes** - Start with default (100) and adjust based on performance
2. **Implement progress monitoring** for long-running operations  
3. **Handle errors gracefully** - Don't let one bad record stop the entire process
4. **Consider memory usage** - Use streaming for very large datasets
5. **Use async for concurrency** - When processing multiple datasets
