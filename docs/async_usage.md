# Asynchronous Usage

FolioClient provides full async/await support for high-performance applications. This is especially useful when making many concurrent API calls or when integrating with async frameworks.

## Basic Async Operations

All synchronous methods have async counterparts:

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

    try:
        # Async API calls
        users = await client.folio_get_async("/users", "users")
        groups = await client.folio_get_async("/groups", "usergroups")
        
        print(f"Found {len(users)} users and {len(groups)} groups")
        
    finally:
        await client.close()

asyncio.run(main())
```

## Async Method Reference

| Sync Method | Async Equivalent |
|-------------|------------------|
| `folio_get()` | `folio_get_async()` |
| `folio_post()` | `folio_post_async()` |
| `folio_put()` | `folio_put_async()` |
| `folio_delete()` | `folio_delete_async()` |
| `folio_get_all()` | `folio_get_all_async()` |

## Async Pagination

Process large datasets asynchronously:

```python
async def process_all_users():
    client = FolioClient(...)
    
    try:
        # Async iteration over all users
        async for user in client.folio_get_all_async("/users", "users"):
            print(f"Processing user: {user['username']}")
            
            # Perform async operations on each user
            await process_user_data(user)
            
    finally:
        await client.close()

asyncio.run(process_all_users())
```

## Concurrent Operations

Make multiple API calls concurrently for better performance:

```python
import asyncio
from folioclient import FolioClient

async def fetch_multiple_resources():
    client = FolioClient(...)
    
    try:
        # Run multiple requests concurrently
        users_task = client.folio_get_async("/users", "users")
        groups_task = client.folio_get_async("/groups", "usergroups")
        locations_task = client.folio_get_async("/locations", "locations")
        
        # Wait for all to complete
        users, groups, locations = await asyncio.gather(
            users_task,
            groups_task, 
            locations_task
        )
        
        print(f"Loaded {len(users)} users, {len(groups)} groups, {len(locations)} locations")
        
    finally:
        await client.close()

asyncio.run(fetch_multiple_resources())
```

## Batch Processing

Process data in batches with controlled concurrency:

```python
import asyncio
from asyncio import Semaphore

async def process_users_in_batches():
    client = FolioClient(...)
    semaphore = Semaphore(10)  # Limit to 10 concurrent operations
    
    async def process_user_with_limit(user):
        async with semaphore:
            # Process one user with concurrency limit
            return await process_user_details(client, user)
    
    try:
        # Get all users
        users = await client.folio_get_async("/users", "users")
        
        # Process in batches with concurrency control
        tasks = [process_user_with_limit(user) for user in users]
        results = await asyncio.gather(*tasks)
        
        print(f"Processed {len(results)} users")
        
    finally:
        await client.close()

async def process_user_details(client, user):
    # Fetch additional details for each user
    user_id = user['id']
    loans = await client.folio_get_async(
        "/circulation/loans", 
        "loans", 
        query=f"userId=={user_id}"
    )
    return {'user': user, 'loan_count': len(loans)}

asyncio.run(process_users_in_batches())
```

## Error Handling in Async Code

FolioClient's automatic retry logic works seamlessly with async operations:

```python
import asyncio
import os
import httpx
from folioclient import FolioClient
from folioclient.exceptions import FolioClientClosed

async def robust_async_operations():
    # Configure retries for async operations
    os.environ['FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES'] = '3'
    os.environ['FOLIOCLIENT_MAX_AUTH_ERROR_RETRIES'] = '2'
    
    client = FolioClient(...)
    
    try:
        # Async operations get automatic retry behavior
        tasks = []
        
        for endpoint in ["/users", "/groups", "/locations"]:
            task = safe_fetch(client, endpoint)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"Task {i} failed: {result}")
            else:
                print(f"Task {i} succeeded: {len(result)} items")
                
    finally:
        await client.close()

async def safe_fetch(client, endpoint):
    try:
        # This call includes automatic retry logic for:
        # - Server errors (502, 503, 504)
        # - Connection errors  
        # - Auth errors (403) with re-authentication
        return await client.folio_get_async(endpoint, endpoint.split('/')[-1])
    except httpx.HTTPStatusError as e:
        print(f"HTTP error on {endpoint}: {e.response.status_code}")
        raise
    except FolioClientClosed:
        print(f"Client closed during {endpoint} request")
        raise
    except Exception as e:
        print(f"Unexpected error on {endpoint}: {e}")
        raise

asyncio.run(robust_async_operations())
```

### Async Retry Benefits

The retry system provides special benefits for async operations:

- **Non-blocking retries** - Other coroutines continue running during retry delays
- **Concurrent retry isolation** - Each async operation retries independently
- **Shared connection pooling** - Retries reuse connection pools efficiently
- **Graceful degradation** - Failed operations don't block successful ones

```python
async def concurrent_with_retries():
    client = FolioClient(...)
    
    # Configure fast retries for development
    os.environ['FOLIOCLIENT_SERVER_ERROR_RETRY_DELAY'] = '1.0'
    
    # Multiple concurrent operations, each with independent retry logic
    async def fetch_data(endpoint, key):
        # Each call gets its own retry behavior
        return await client.folio_get_async(endpoint, key)
    
    # All operations run concurrently, retries don't block each other
    users, groups, locations = await asyncio.gather(
        fetch_data("/users", "users"),
        fetch_data("/groups", "usergroups"), 
        fetch_data("/locations", "locations")
    )
    
    return users, groups, locations
```

## Context Managers with Async

Use async context managers for proper resource cleanup:

```python
async def using_async_context_manager():
    # Note: FolioClient doesn't support async context managers yet,
    # but you can create your own wrapper
    
    class AsyncFolioClient:
        def __init__(self, **kwargs):
            self.client = FolioClient(**kwargs)
        
        async def __aenter__(self):
            return self.client
        
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            await self.client.close()
    
    # Usage
    async with AsyncFolioClient(folio_url="...", tenant="...", 
                                username="...", password="...") as client:
        users = await client.folio_get_async("/users", "users")
        # Client automatically closed
```

## Integration with Web Frameworks

### FastAPI Integration

```python
from fastapi import FastAPI, HTTPException
from folioclient import FolioClient
import httpx

app = FastAPI()

# Global client instance (in production, use dependency injection)
folio_client = FolioClient(...)

@app.get("/api/users")
async def get_users(limit: int = 100):
    try:
        users = await folio_client.folio_get_async(
            "/users", "users", limit=limit
        )
        return {"users": users, "count": len(users)}
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code, 
            detail=f"FOLIO API error: {e}"
        )

@app.on_event("shutdown")
async def shutdown():
    await folio_client.close()
```

### Aiohttp Integration

```python
from aiohttp import web
from folioclient import FolioClient

async def get_users(request):
    client = request.app['folio_client']
    
    try:
        users = await client.folio_get_async("/users", "users")
        return web.json_response({"users": users})
    except Exception as e:
        return web.json_response(
            {"error": str(e)}, 
            status=500
        )

async def create_app():
    app = web.Application()
    
    # Initialize FolioClient
    app['folio_client'] = FolioClient(...)
    
    # Add routes
    app.router.add_get('/users', get_users)
    
    return app

async def cleanup(app):
    await app['folio_client'].close()

if __name__ == '__main__':
    app = create_app()
    app.on_cleanup.append(cleanup)
    web.run_app(app, host='localhost', port=8080)
```

## Performance Considerations

### Async Best Practices

1. **Use semaphores** to limit concurrency and avoid overwhelming FOLIO
2. **Batch operations** when possible
3. **Handle exceptions** at appropriate levels
4. **Always close clients** when done
5. **Use connection pooling** for multiple clients

```python
# Good async pattern
async def efficient_processing():
    semaphore = asyncio.Semaphore(5)  # Limit concurrent requests
    client = FolioClient(...)
    
    async def process_with_limit(item):
        async with semaphore:
            return await process_item(client, item)
    
    try:
        items = await client.folio_get_async("/items", "items")
        tasks = [process_with_limit(item) for item in items[:100]]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successful = [r for r in results if not isinstance(r, Exception)]
        failed = [r for r in results if isinstance(r, Exception)]
        
        print(f"Processed: {len(successful)}, Failed: {len(failed)}")
        
    finally:
        await client.close()
```

## Testing Async Code

Use pytest-asyncio for testing async functionality:

```python
import pytest
from unittest.mock import AsyncMock, patch
from folioclient import FolioClient

@pytest.mark.asyncio
async def test_async_folio_get():
    with patch.object(FolioClient, 'folio_get_async', new_callable=AsyncMock) as mock_get:
        mock_get.return_value = [{"id": "1", "username": "test"}]
        
        client = FolioClient(...)
        users = await client.folio_get_async("/users", "users")
        
        assert len(users) == 1
        assert users[0]["username"] == "test"
        mock_get.assert_called_once_with("/users", "users")
```

## Debugging Async Issues

Enable asyncio debug mode during development:

```python
import asyncio
import logging

# Enable asyncio debug mode
asyncio.get_event_loop().set_debug(True)

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Your async code here
async def debug_example():
    client = FolioClient(...)
    try:
        users = await client.folio_get_async("/users", "users")
    finally:
        await client.close()

asyncio.run(debug_example())
```