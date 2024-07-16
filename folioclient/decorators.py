"""This module contains decorators for the FolioClient package."""

import logging
import os
import time
from functools import wraps

import httpx


def retry_on_server_error(func):
    """Retry a function if a temporary server error is encountered.

    Args:
        func: The function to be retried.

    Returns:
        The decorated function.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        retry_factor = float(os.environ.get("FOLIOCLIENT_SERVER_ERROR_RETRY_FACTOR", "3"))
        max_retries = int(os.environ.get("FOLIOCLIENT_MAX_SERVER_ERROR_RETRIES", "0"))
        retry_delay = int(os.environ.get("FOLIOCLIENT_SERVER_ERROR_RETRY_DELAY", "10"))
        for retry in range(max_retries + 1):
            try:
                return func(*args, **kwargs)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in [502, 503, 504]:
                    if retry == max_retries:
                        logging.exception(
                            f'Server error requesting new auth token: "{exc.response}"'
                            "Maximum number of retries reached, giving up."
                        )
                        raise
                    logging.info(
                        f"FOLIOCLIENT: Server error requesting new auth token:"
                        f' "{exc.response}". Retrying again in {retry_delay} seconds. '
                        f"Retry {retry + 1}/{max_retries}"
                    )
                    time.sleep(retry_delay)
                    retry_delay *= retry_factor
                else:
                    raise

    return wrapper
