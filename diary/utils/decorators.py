import time
import logging
from functools import wraps
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)

def retry_on_failure(max_retries=3, delay=1, backoff=2, exceptions=(RequestException,)):
    """
    Retry decorator with exponential backoff for API calls

    Parameters:
    - max_retries: Maximum number of retry attempts
    - delay: Initial delay between retries in seconds
    - backoff: Multiplier for the delay with each retry
    - exceptions: Tuple of exceptions to catch and retry

    Usage:
    @retry_on_failure(max_retries=3, delay=1, backoff=2)
    def call_api():
        # API call that might fail
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            mtries, mdelay = max_retries, delay
            while mtries > 0:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    msg = f"{func.__name__} failed. Retrying in {mdelay}s. Error: {str(e)}"
                    logger.warning(msg)

                    mtries -= 1
                    if mtries == 0:
                        logger.error(f"All retries failed for {func.__name__}: {str(e)}")
                        raise

                    time.sleep(mdelay)
                    mdelay *= backoff
        return wrapper
    return decorator
