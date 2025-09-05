"""FolioClient is a Python client for interacting with API in FOLIO.

It provides methods for making standard HTTP requests, handling
authentication, and managing sessions. It can also interact with
GitHub to fetch the latest versions of API schemas for FOLIO modules.
"""

import importlib.metadata

from folioclient.exceptions import FolioClientClosed
from folioclient.FolioClient import FolioClient

__version__ = importlib.metadata.version("folioclient")
__all__ = ["FolioClient", "FolioClientClosed"]
