"""FolioClient is a Python client for interacting with API in FOLIO.

It provides methods for making standard HTTP requests, handling
authentication, and managing sessions. It can also interact with
GitHub to fetch the latest versions of API schemas for FOLIO modules.
"""

import importlib.metadata

from folioclient.exceptions import (
    # Base exceptions
    FolioError,
    FolioClientClosed,
    # Connection errors
    FolioConnectionError,
    FolioSystemUnavailableError,
    FolioTimeoutError,
    FolioProtocolError,
    FolioNetworkError,
    # HTTP errors
    FolioHTTPError,
    # 4xx client errors
    FolioClientError,
    FolioBadRequestError,
    FolioAuthenticationError,
    FolioPermissionError,
    FolioResourceNotFoundError,
    FolioDataConflictError,
    FolioValidationError,
    FolioRateLimitError,
    # 5xx server errors
    FolioServerError,
    FolioInternalServerError,
    FolioBadGatewayError,
    FolioServiceUnavailableError,
    FolioGatewayTimeoutError,
)
from folioclient.FolioClient import FolioClient
from folioclient._httpx import FolioAuth, FolioConnectionParameters

__version__ = importlib.metadata.version("folioclient")
__all__ = [
    # Core client
    "FolioClient",
    # FOLIO Auth Components
    "FolioAuth",
    "FolioConnectionParameters",
    # Base exceptions
    "FolioError",
    # Client closed
    "FolioClientClosed",
    # Connection errors
    "FolioConnectionError",
    "FolioSystemUnavailableError",
    "FolioTimeoutError",
    "FolioProtocolError",
    "FolioNetworkError",
    # HTTP errors
    "FolioHTTPError",
    # 4xx client errors
    "FolioClientError",
    "FolioBadRequestError",
    "FolioAuthenticationError",
    "FolioPermissionError",
    "FolioResourceNotFoundError",
    "FolioDataConflictError",
    "FolioValidationError",
    "FolioRateLimitError",
    # 5xx server errors
    "FolioServerError",
    "FolioInternalServerError",
    "FolioBadGatewayError",
    "FolioServiceUnavailableError",
    "FolioGatewayTimeoutError",
]
