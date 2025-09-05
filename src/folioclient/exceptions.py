"""
Custom exceptions for the folioclient package.
"""


class FolioClientClosed(Exception):
    """
    Raised when an operation is attempted on a closed FolioClient.
    """

    def __init__(self, message: str = "The FolioClient is closed") -> None:
        super().__init__(message)
