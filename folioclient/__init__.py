import importlib.metadata

from folioclient.FolioClient import FolioClient
from folioclient.exceptions import FolioClientClosed

__version__ = importlib.metadata.version("folioclient")
__all__ = ["FolioClient", "FolioClientClosed"]
