# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## v1.1.0

### Removed
- Dropped support for Python 3.10; the minimum supported version is now Python 3.11.

### Fixed
- `FolioClient.fetch_github_schema` now rewrites `raml-util` references with any number of leading `../` segments (e.g. `../../../raml-util/...` in folio-org/acq-models) and no longer corrupts text that already contains the absolute raml-util URL.
- `get_from_github` / `get_latest_from_github` returned non-deterministic results for large schema trees (e.g. acq-models `composite_purchase_order.json`): a relative `$ref` could resolve to the content of an unrelated file. Root cause is a bug in jsonref 1.1.0 (`replace_refs(..., proxies=False)`): `_walk_refs` memoizes by `id()` while replacing proxies, the replaced proxies are freed immediately, and their ids get reused by later nodes, which then receive the earlier node's result. Dereferencing now uses a small internal resolver (`folioclient._schema_refs.dereference`) instead of jsonref.

### Changed
- Widened the `uv_build` build requirement to `>=0.9.3,<0.14.0` and removed the deprecated MIT license classifier (the PEP 639 `license = "MIT"` field is already set).
- Schema dereferencing no longer uses jsonref. Behavior differences: results are plain nested `dict`/`list` objects (not jsonref proxies); each document is fetched once and every `$ref` is resolved against the URL of the document containing it; sibling keys next to a `$ref` (e.g. `description`) are now merged over the referenced schema (previously dropped); circular refs are left as `{"$ref": "<absolute URL>"}` markers instead of producing self-referential objects; load failures propagate as the original `httpx` exceptions instead of `jsonref.JsonRefError`.
- Existing live mod-inventory-storage schema tests now force full `$ref` resolution instead of only checking for top-level `properties`.

### Added
- Python 3.15 is now tested in CI and listed in the package classifiers.
- Network tests (`integration` marker) that fully dereference acq-models schemas via the submodule SHA pinned by mod-orders, and the latest-release inventory (instance, holdings, item) and user schemas, to detect upstream changes that break schema resolution.


## v1.0.16

### Fixed
- `module_versions` entitlements fallback now returns the full module list: it pages through all of the tenant's applications with `folio_get_all` (500 per request) and includes `uiModules`, so restricted users get the same list as the proxy endpoint. Fixes [#151](https://github.com/FOLIO-FSE/FolioClient/issues/151).

## v1.0.15

### Fixed
- Logout on async context-manager exit no longer fails in an ECS context.

## v1.0.14

### Changed
- `folio_get_all_async` now behaves like `folio_get_all` (see [#148](https://github.com/FOLIO-FSE/FolioClient/issues/148)).
- Type annotations use modern `X | Y` union syntax.

## v1.0.13

### Added
- Custom HTTP headers on requests: `folio_get`/`put`/`post`/`delete`, their async variants, and the pagination helpers accept a `headers` dict that is merged with the client's default auth headers. Documented in the README and quickstart.

## v1.0.12

### Fixed
- Token expiration parsing now works on Python 3.10 (FOLIO's trailing-`Z` timestamps are parsed with `dateutil` instead of `datetime.fromisoformat`).
- Async authentication is serialized with a per-event-loop `asyncio.Lock`. The previous `threading.RLock` provided no mutual exclusion between coroutines, so N concurrent flows produced N logins.
- A 401 is now treated as authoritative: the client re-authenticates unless another caller has already replaced the token, instead of only when the token looked locally expired.
- The 401 retry reads the response body before raising.
- 403 retries are now effective: multipart uploads are replayable and a short delay is added before retrying. FOLIO's Keycloak integration frequently translates transient backend errors into 403s. The delay is documented.

## v1.0.11

### Added
- Cached property for service points. Fixes [#142](https://github.com/FOLIO-FSE/FolioClient/issues/142).

## v1.0.10

### Fixed
- The authentication response is read before a 403 exception is raised.

## v1.0.9

### Changed
- Improved type hints for decorators and exceptions using overloads for better compatibility.

## v1.0.8

### Fixed
- `FolioAuth` handles transient 403 Forbidden responses with retry logic; a repeated 403 on retry no longer raises a custom exception.

### Added
- `bugfest-next` integration-test configuration.

## v1.0.7

### Fixed
- Schema fallback for the mod-inventory-storage schema path changes in v30.0.0 and later.

## v1.0.6

### Fixed
- Connection-error exception translation was handled incorrectly.

## v1.0.5

### Fixed
- Logout failed for ECS tenants; the tenant ID is now reset on logout.

## v1.0.4

### Changed
- `folio_post` / `folio_put` helpers accept a `dict` or `str` payload; `prepare_payload` raises a clear error for other types.
- More debug logging in `FolioAuth` (tenant ID setting and authentication flows).

### Fixed
- `should_retry_auth_error` checks that the response attribute exists before reading the status code, along with other retry-decorator fixes.

## v1.0.3

### Added
- Docstrings for the `tenant_id` and `refresh_token` properties.
- Python 3 trove classifier.

## v1.0.2.post1

### Changed
- Documentation and packaging only: docs requirements updates and a stable docs branch workflow for Read the Docs.

## v1.0.2

### Changed
- Added package classifiers and updated build-system requirements.
- Renamed the logout exception handler to a private method.

## v1.0.1

### Changed
- `FolioAuth` is now created in `FolioClient.login()` instead of `__init__`, so tests can patch `login()` and supply a mock `FolioAuth` rather than mocking the whole class.

## v1.0.0

### Added
- Comprehensive Sphinx documentation
- Full async/await support for all FOLIO HTTP operations
- Intelligent pagination with ID-based optimization
- Experimental orjson support for improved JSON performance
- Type hints throughout the codebase
- Context manager support for automatic cleanup
- Better handling of cached properties in an ECS context [#74](https://github.com/FOLIO-FSE/FolioClient/issues/74)
- Custom exceptions for FolioClient

### Changed
- Refactored core logic to eliminate code duplication
- Improved error handling and custom exceptions
- Enhanced authentication flow with automatic token refresh and cookie-based authentication
- Switched from a custom auth flow handler to use an `httpx.Auth` subclass for authentication and token management
- Consolidated folio_get_all and folio_get_all_by_id_offset based on query

### Deprecated
- `http_timeout` property - Returns httpx.Timeout object instead of original parameter value
- `okapi_url` property - Use `gateway_url` instead
- `okapi_headers` property - Use `folio_headers` instead
- `okapi_token` property - Use `access_token` instead
- `folio_token_expires` property - Use `access_token_expires` instead
- `ssl_verify` parameter - Will be removed in future release

### Fixed
- Authentication token management across sync/async operations
- Pagination edge cases with large datasets

### Security
- Improved credential handling and token security

## ⚠️ Backwards-Incompatible Changes and Deprecations (v1.0.0)

FolioClient v1.0.0 introduces several breaking changes to modernize the library and improve reliability. Please review this section carefully before upgrading.

### Python Version Requirements
- **Minimum Python version raised to 3.10**
- Dropped support for Python 3.8 and 3.9
- **Rationale**: Enables modern type hints, async improvements, and pattern matching

### FOLIO version support
- Dropped support for pre-Quesnelia releases of FOLIO (FolioClient no longer supports `/authn/login` endpoint for authentication)

### Timeout Parameter Behavior
- **Breaking change in `timeout` parameter handling**
- **Old behavior**: `timeout=None` and no timeout parameter were treated identically
- **New behavior**: 
  - No `timeout` parameter: Uses environment variable configuration (HTTPX_TIMEOUT, TIMEOUT_CONFIG)
  - `timeout=None`: Explicitly disables all timeouts, ignoring environment variables
  - `timeout=value`: Uses provided value with environment variable fallbacks for unspecified components
- **Migration**: 
  - If you want no timeout: explicitly pass `timeout=None` or don't set environment variables
  - If you want environment defaults: omit the timeout parameter entirely
  - If you want custom timeout: pass your timeout configuration as before, or pass a dictionary of timeout keyword arguments or an `httpx.Timeout` instance

### Property Return Type Changes

#### `http_timeout` Property (DEPRECATED)
- **Breaking change**: Now returns `httpx.Timeout` object instead of original parameter value
- **Old behavior**: Returned the original timeout parameter (float, dict, or None)
- **New behavior**: Returns processed `httpx.Timeout` object or None
- **Impact**: Code using this property with non-httpx libraries may break
- **Migration**: 
  - **Deprecated**: This property will be removed in a future release
  - For cross-library compatibility, store the original timeout value separately
  - Use FolioClient's built-in HTTP methods instead of external libraries when possible

#### Deprecated Property Names
Multiple properties have been renamed for clarity and consistency:

| Deprecated Property | New Property | Breaking Change |
|-------------------|--------------|-----------------|
| `okapi_url` | `gateway_url` | No - backward compatible |
| `okapi_headers` | `folio_headers` | No - backward compatible |
| `okapi_token` | `access_token` | No - backward compatible |
| `okapi_token_expires` | `access_token_expires` | No - backward compatible |

**Migration**: Update code to use new property names. Old names still work but emit deprecation warnings.

### Removed Methods
- **`get_random_objects` method** - This method has been removed
- **Rationale**: Method was not widely used and did not align with modern API design principles
- **Migration**: Replace with appropriate `folio_get` or `folio_get_all` calls with specific queries

### Authentication Flow Changes
- **Enhanced token lifecycle management** Tokens now renew at one minute before expiry and this offset is no longer configurable via environment variable
- **Cookie-based authentication** for better session handling [#73](https://github.com/FOLIO-FSE/FolioClient/issues/73)
- **Impact**: Custom authentication code may need updates
- **Migration**: While this change is largely transparent to the end-user of FolioClient, the one notable change is that you no longer need to pass the `headers=okapi_headers` to any `httpx.Client` or `httpx.AsyncClient` objects created using the `FolioClient.get_folio_http_client` and `FolioClient.get_folio_http_client_async` methods. They are instantiated with built-in authentication.

### Exception Hierarchy
- **New FOLIO-specific exception types**:
  - `FolioAuthenticationError` (401 errors)
  - `FolioPermissionError` (403 errors)  
  - `FolioResourceNotFoundError` (404 errors)
  - `FolioValidationError` (422 errors)
  - `FolioInternalServerError` (500 errors)
  - And more...
- **Migration**: Update exception handling to catch specific FOLIO exception types, but existing `httpx.HTTPStatusError` and `httpx.ConnectError` handling should continue to function normally, though message bodies may change

### Environment Variable Changes
- **New timeout configuration variables**: 
  - `FOLIOCLIENT_CONNECT_TIMEOUT` - Connection timeout in seconds
  - `FOLIOCLIENT_READ_TIMEOUT` - Read timeout in seconds
  - `FOLIOCLIENT_WRITE_TIMEOUT` - Write timeout in seconds
  - `FOLIOCLIENT_POOL_TIMEOUT` - Connection pool timeout in seconds
  - Existing `FOLIOCLIENT_HTTP_TIMEOUT` still supported for backward compatibility
- **Migration**: Existing `FOLIOCLIENT_HTTP_TIMEOUT` configurations continue to work

### Type Safety Improvements
- **Enhanced type hints** throughout the codebase
- **Stricter type checking** for parameters and return values
- **Impact**: MyPy and other type checkers may report new issues
- **Migration**: Update type annotations in your code to match new signatures

### Async Operation Changes
- **All FOLIO HTTP operations now have async counterparts**
- **Context manager support** for both sync and async operations
- **Migration**: 
  - Sync operations: No changes required
  - New async operations: Use `async with` and `await` as appropriate

## Migration Checklist

1. **Update Python version** to 3.10 or higher
2. **Update timeout handling**:
   - Replace `timeout=None` with explicit `timeout=None` if you want no timeout
   - Remove `timeout` parameter if you want environment defaults
3. **Update property names**:
   - `okapi_url` → `gateway_url`
   - `okapi_headers` → `folio_headers`  
   - `okapi_token` → `access_token`
   - `okapi_token_expires` → `access_token_expires`
4. **Remove usage of `http_timeout` property** if used with non-httpx libraries
5. **Replace removed methods**:
   - `get_random_objects` → Use `folio_get` or `folio_get_all` with specific queries
   - `folio_get_all_by_id_offset` has been consolidated with `folio_get_all` and behavior is invoked whenever `query=` contains `sortBy id`
6. **Update exception handling** to catch specific FOLIO exception types
7. **Test thoroughly** in your environment before deploying

For questions about migration, please open an issue on GitHub or join us at [\#fse_folio_migration_tools](https://open-libr-foundation.slack.com/archives/C01HRQKSLL8) on the [OLF Slack](https://open-libr-foundation.slack.com/).

\[Older Releases\]

## v0.60.0 (07/11/2023)
## What's Changed
* Fix GitHub testing configuration by @bltravis in https://github.com/FOLIO-FSE/FolioClient/pull/26
* Fixes Better Support fetching YAML Schemas for OpenAPI modules #30 by @bltravis in https://github.com/FOLIO-FSE/FolioClient/pull/31
* Updated FolioClient to use dynamic properties for api token values by @bltravis in https://github.com/FOLIO-FSE/FolioClient/pull/28
* Fixes #32 by @bltravis in https://github.com/FOLIO-FSE/FolioClient/pull/33


**Full Changelog**: [https://github.com/FOLIO-FSE/FolioClient/compare/v_0501...v_0600](https://github.com/FOLIO-FSE/FolioClient/compare/v_0501...v_0600)

## v_0501 (13/08/2023)
## What's Changed
* Add optional parameter to pass ssl verification parameters to httpx. Fixes #20 by @bltravis in https://github.com/FOLIO-FSE/FolioClient/pull/21
* Refactor how query parameters are handled for FolioClient.folio_get_all and FolioClient.folio_get by @bltravis in https://github.com/FOLIO-FSE/FolioClient/pull/22
* Bumped version to 0.50.1 and added author. by @bltravis in https://github.com/FOLIO-FSE/FolioClient/pull/24


**Full Changelog**: [https://github.com/FOLIO-FSE/FolioClient/compare/v_050...v_0501](https://github.com/FOLIO-FSE/FolioClient/compare/v_050...v_0501)

## v_050 (16/05/2023)
- [**closed**] Remove poetry.lock from repo [#17](https://github.com/FOLIO-FSE/FolioClient/issues/17)
- [**closed**] Swap out requests for an async-compatible library [#16](https://github.com/FOLIO-FSE/FolioClient/issues/16)


## v_043 (16/02/2023)
*No changelog for this release.*


## Forty two! (28/09/2022)
Added missing Github authentication

## Fortyone! (31/05/2022)
bad tag.

## Thirty nine! (23/03/2022)
- Support YAML files to be  fetched via "get latest from github"

## Thirty eight! (10/02/2022)


## Thirty seven! (04/02/2022)
Same as 36..

## Thirty six! (04/02/2022)
Added optional page size to folio_get_all #

## Thirty five! (09/11/2021)


## Thirty four! (09/11/2021)


## Thirty tree! (08/11/2021)


## Thirty two! (08/11/2021)


## Thirty one! (08/11/2021)
Minor adjustments to validate everything works after transfer

## Thirtieth! (22/02/2021)


## twentyninth (21/10/2020)


## Twentyeight! (21/09/2020)
This change might brake code, since it move from returning lists to yielding . 

## twentyseventh! (24/06/2020)


## Twentysixth (24/06/2020)


## twentyfifth (05/06/2020)


## Twentyfourth (31/05/2020)


## Twentythird! (07/05/2020)


## twentysecond! (07/05/2020)


## twentyfirst (05/05/2020)


## Twentieth (05/05/2020)


## nineteenth (15/04/2020)


## eighteenth (07/04/2020)


## seventeenth! (21/02/2020)


## Sixteenth! (21/02/2020)
