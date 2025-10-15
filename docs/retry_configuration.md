# Retry Configuration

FolioClient includes comprehensive retry logic powered by the [tenacity](https://tenacity.readthedocs.io/) library, along with granular timeout configuration for optimal HTTP client behavior. This modern retry system provides robust error handling with exponential backoff and extensive configuration options.

## Overview

The retry system automatically handles:

- **Server errors** (502, 503, 504) and connection errors
- **Authorization errors** (403) with automatic re-authentication
- **Remote protocol errors** with HTTP client recreation
- **Exponential backoff** to avoid overwhelming servers
- **Configurable limits** to prevent infinite retry loops

## Quick Start

By default, **no retries are performed** - you must opt-in by setting environment variables:

```bash
# Enable basic server error retries
export FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES=3

# Enable auth error retries  
export FOLIOCLIENT_MAX_AUTH_ERROR_RETRIES=2

# Your script will now automatically retry on transient errors
python your_folio_script.py
```

## Environment Variables

### Server Error Retries

Configure retry behavior for server errors (502, 503, 504) and connection issues:

| Variable | Default | Description |
|----------|---------|-------------|
| `FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES` | `0` | Maximum number of retry attempts (0 = no retries) |
| `FOLIOCLIENT_SERVER_ERROR_RETRY_DELAY` | `10.0` | Initial delay in seconds before first retry |
| `FOLIOCLIENT_SERVER_ERROR_RETRY_FACTOR` | `3.0` | Exponential backoff multiplier |
| `FOLIOCLIENT_SERVER_ERROR_MAX_WAIT` | `unlimited` | Maximum wait time between retries |

#### Max Wait Configuration

The `FOLIOCLIENT_SERVER_ERROR_MAX_WAIT` variable supports:

- **Number** (e.g., `"60"`): Maximum wait time in seconds
- **"unlimited"**, **"inf"**, or **"none"**: No maximum (default)
- **Unset**: Same as unlimited (maintains backward compatibility)

```bash
# Cap wait times at 2 minutes
export FOLIOCLIENT_SERVER_ERROR_MAX_WAIT=120

# No cap on wait times (can grow very large)
export FOLIOCLIENT_SERVER_ERROR_MAX_WAIT=unlimited
```

### Auth Error Retries

Configure retry behavior for authorization errors (403):

| Variable | Default | Description |
|----------|---------|-------------|
| `FOLIOCLIENT_MAX_AUTH_ERROR_RETRIES` | `0` | Maximum number of retry attempts (0 = no retries) |
| `FOLIOCLIENT_AUTH_ERROR_RETRY_DELAY` | `10.0` | Initial delay in seconds before first retry |
| `FOLIOCLIENT_AUTH_ERROR_RETRY_FACTOR` | `3.0` | Exponential backoff multiplier |
| `FOLIOCLIENT_AUTH_ERROR_MAX_WAIT` | `60.0` | Maximum wait time between retries |

**Note**: Auth errors include automatic re-authentication before retry attempts.

### Legacy Variables

For backward compatibility, these legacy environment variables are also supported:

| Legacy Variable | Modern Equivalent |
|----------------|-------------------|
| `SERVER_ERROR_RETRIES_MAX` | `FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES` |
| `SERVER_ERROR_RETRY_DELAY` | `FOLIOCLIENT_SERVER_ERROR_RETRY_DELAY` |
| `SERVER_ERROR_RETRY_FACTOR` | `FOLIOCLIENT_SERVER_ERROR_RETRY_FACTOR` |
| `AUTH_ERROR_RETRIES_MAX` | `FOLIOCLIENT_MAX_AUTH_ERROR_RETRIES` |
| `AUTH_ERROR_RETRY_DELAY` | `FOLIOCLIENT_AUTH_ERROR_RETRY_DELAY` |
| `AUTH_ERROR_RETRY_FACTOR` | `FOLIOCLIENT_AUTH_ERROR_RETRY_FACTOR` |

## Configuration Examples

### Conservative Configuration

Suitable for most production environments:

```bash
# Moderate retries with reasonable limits
export FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES=3
export FOLIOCLIENT_SERVER_ERROR_RETRY_DELAY=5.0
export FOLIOCLIENT_SERVER_ERROR_MAX_WAIT=60

export FOLIOCLIENT_MAX_AUTH_ERROR_RETRIES=2  
export FOLIOCLIENT_AUTH_ERROR_RETRY_DELAY=5.0
export FOLIOCLIENT_AUTH_ERROR_MAX_WAIT=30
```

This creates retry timing like:
- Attempt 1: Immediate
- Attempt 2: 5s delay  
- Attempt 3: 15s delay
- Attempt 4: 45s delay (capped at 60s for server errors)

### Aggressive Configuration

For environments with frequent transient issues:

```bash
# More retries with faster initial response
export FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES=5
export FOLIOCLIENT_SERVER_ERROR_RETRY_DELAY=2.0
export FOLIOCLIENT_SERVER_ERROR_RETRY_FACTOR=2.0
export FOLIOCLIENT_SERVER_ERROR_MAX_WAIT=120

export FOLIOCLIENT_MAX_AUTH_ERROR_RETRIES=3
export FOLIOCLIENT_AUTH_ERROR_RETRY_DELAY=2.0
export FOLIOCLIENT_AUTH_ERROR_RETRY_FACTOR=2.0
```

### Development Configuration

Fast feedback for development environments:

```bash
# Quick retries for rapid development
export FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES=2
export FOLIOCLIENT_SERVER_ERROR_RETRY_DELAY=1.0
export FOLIOCLIENT_SERVER_ERROR_RETRY_FACTOR=2.0
export FOLIOCLIENT_SERVER_ERROR_MAX_WAIT=10

export FOLIOCLIENT_MAX_AUTH_ERROR_RETRIES=1
export FOLIOCLIENT_AUTH_ERROR_RETRY_DELAY=1.0
```

## Retry Timing Calculation

The exponential backoff formula is:

```
delay = retry_delay * (retry_factor ^ attempt_number)
actual_delay = min(delay, max_wait)
```

### Example Timing

With default settings (`FOLIOCLIENT_SERVER_ERROR_RETRY_DELAY=10`, `FOLIOCLIENT_SERVER_ERROR_RETRY_FACTOR=3`, `FOLIOCLIENT_SERVER_ERROR_MAX_WAIT=unlimited`):

| Attempt | Calculation | Delay |
|---------|-------------|-------|
| 1 | Immediate | 0s |
| 2 | 10 * 3^0 | 10s |
| 3 | 10 * 3^1 | 30s |
| 4 | 10 * 3^2 | 90s |
| 5 | 10 * 3^3 | 270s |

With `FOLIOCLIENT_SERVER_ERROR_MAX_WAIT=60`:

| Attempt | Calculation | Capped Delay |
|---------|-------------|--------------|
| 1 | Immediate | 0s |
| 2 | 10 * 3^0 | 10s |
| 3 | 10 * 3^1 | 30s |
| 4 | 10 * 3^2 = 90s | 60s (capped) |
| 5 | 10 * 3^3 = 270s | 60s (capped) |

## Advanced Usage

### Programmatic Configuration

While environment variables are the primary configuration method, you can also configure retries programmatically:

```python
import os
from folioclient import FolioClient

# Set configuration before creating client
os.environ['FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES'] = '3'
os.environ['FOLIOCLIENT_SERVER_ERROR_MAX_WAIT'] = '60'

client = FolioClient(...)

# All client methods now use the configured retry behavior
users = client.folio_get("/users", "users")
```

### Monitoring Retries

The retry system includes comprehensive logging. Enable INFO level logging to see retry attempts:

```python
import logging

# Enable retry logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('folioclient.decorators')

# Now you'll see retry attempts in your logs
client = FolioClient(...)
users = client.folio_get("/users", "users")
```

Example log output:
```
INFO:folioclient.decorators:Retrying folio_get in 10.0 seconds...
INFO:folioclient.decorators:Retrying folio_get in 30.0 seconds...
```

## Best Practices

### Production Environments

1. **Start conservative**: Begin with 2-3 retries and moderate delays
2. **Monitor and adjust**: Use logging to understand retry patterns
3. **Set reasonable limits**: Always configure `FOLIOCLIENT_*_MAX_WAIT` to prevent very long delays
4. **Consider downstream impact**: More retries means more load on FOLIO servers

### Development Environments

1. **Faster feedback**: Use shorter delays and fewer retries
2. **Enable logging**: Monitor retry behavior during development
3. **Test edge cases**: Verify retry behavior under various failure conditions

### Network-Specific Tuning

- **Slow networks**: Increase `FOLIOCLIENT_*_RETRY_DELAY` and `FOLIOCLIENT_*_MAX_WAIT`
- **Fast networks**: Decrease `FOLIOCLIENT_*_RETRY_DELAY` values for quicker recovery
- **Unreliable networks**: Increase `FOLIOCLIENT_MAX_*_ERROR_RETRIES` but set reasonable `FOLIOCLIENT_*_MAX_WAIT`
- **Stable networks**: Minimal retries may be sufficient

## Advanced Usage

### Custom Methods with Retry Protection

If you're subclassing FolioClient and adding custom methods, you can use the same retry decorators that protect the built-in methods. This is useful for complex operations that combine multiple FOLIO API calls, but you can't use the built-in `folio_*` http methods (eg. you're working with a PATCH api endpoint, or you just want greater control over the request).

**Important Notes:**
- Decorators must be imported from `folioclient.decorators`
- Use the same decorator order  for consistent behavior
- The `@use_client_session` decorator is required for HTTP operations
- Your methods should follow the same patterns as built-in FolioClient methods
- All retry configuration (environment variables) applies to your custom methods too

**Handling Partial Success:**
When using retry decorators with multi-step operations, be aware that server errors can result in partial success (e.g., user created but response lost). For simpler cases, consider breaking complex operations into smaller, idempotent methods.

**Decorator Functions:**
- `@folio_retry_on_server_error`: Retries on 502, 503, 504 errors and connection issues
- `@folio_retry_on_auth_error`: Retries on 403 errors with automatic re-authentication  
- `@handle_remote_protocol_error`: Handles connection protocol errors
- `@use_client_session`: Required for HTTP operations that want to use the instance-level `httpx.Client` or `AsyncClient` objects, if available (the decorator will create a temporary client if one does not exist or is closed)
- `@folio_errors`: Translates httpx exceptions into FOLIO-specific exceptions

:::{attention}
The `handle_remote_protocol_error`, `use_client_session`, and `use_client_session_with_generator` decorators can only be applied to methods of FolioClient or a subclass, as they assume that `self` is a FolioClient instance. 
:::


## Troubleshooting

### Common Issues

**Issue**: Retries not happening
- **Check**: Verify environment variables are set
- **Check**: Confirm error types match retry conditions (502, 503, 504 for server errors)

**Issue**: Retries taking too long
- **Solution**: Set `FOLIOCLIENT_*_MAX_WAIT` to cap delays
- **Solution**: Reduce `FOLIOCLIENT_*_RETRY_FACTOR` for slower growth

**Issue**: Too many retries
- **Solution**: Reduce `FOLIOCLIENT_MAX_*_ERROR_RETRIES`
- **Solution**: Check for systemic issues causing repeated failures

### Debugging

Enable debug logging to see detailed retry information:

```python
import logging
logging.getLogger('tenacity').setLevel(logging.DEBUG)
logging.getLogger('folioclient.decorators').setLevel(logging.DEBUG)
```

This will show:
- Retry attempt details
- Backoff calculations  
- Success/failure outcomes
- Total retry duration

## Migration from Custom Retry Logic

If you were previously using custom retry logic, the new system provides:

- **Better performance**: Tenacity is optimized and well-tested
- **More features**: Jitter, advanced backoff strategies, comprehensive logging
- **Easier configuration**: Environment variables instead of code changes  
- **Consistency**: Same retry behavior across all FolioClient methods

To migrate:
1. Remove custom retry code
2. Set appropriate environment variables
3. Test with your typical workloads
4. Adjust configuration as needed