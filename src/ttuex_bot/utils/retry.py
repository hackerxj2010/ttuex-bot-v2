import asyncio
import random
import logging
from functools import wraps
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

class PermanentError(Exception):
    """Exception that should NOT be retried as it indicates a permanent issue."""
    pass

class TemporaryError(Exception):
    """Exception that should be retried as it indicates a temporary issue."""
    pass

def should_retry_exception(exc: Exception) -> bool:
    """
    Determine if an exception should trigger a retry or not.
    
    Returns True for temporary errors that can be retried.
    Returns False for permanent errors that should not be retried.
    """
    # Permanent errors - don't retry
    if isinstance(exc, PermanentError):
        return False
    
    # Playwright timeout errors are typically temporary
    if isinstance(exc, PlaywrightTimeoutError):
        return True
    
    # Common temporary errors that we should retry
    error_messages = [
        "net::ERR_",  # Network errors
        "timeout", 
        "load failed",
        "navigation failed",
        "page crashed",
        "connection refused",
        "connection reset",
        "host is unreachable",
        "was closed",  # WebSocket or connection closed
        "failed to fetch",
        "network error",
    ]
    
    exc_str = str(exc).lower()
    if any(msg in exc_str for msg in error_messages):
        return True
    
    # Check for common temporary Playwright errors
    if hasattr(exc, '__class__') and 'timeout' in exc.__class__.__name__.lower():
        return True
    
    # By default, assume most errors are temporary and should be retried
    # (This is conservative - it's better to retry a permanent error once or twice
    # than to fail quickly on a temporary error)
    return True

def async_retry(max_attempts=3, base_delay=1.0, factor=2.0, permanent_errors=None):
    """
    A decorator to retry an async function if it raises a temporary exception.

    Args:
        max_attempts: The maximum number of attempts.
        base_delay: The initial delay between retries in seconds.
        factor: The factor by which to multiply the delay for each subsequent retry.
        permanent_errors: List of specific exception types that should not be retried.
    """
    if permanent_errors is None:
        permanent_errors = []
        
    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            delay = base_delay
            for attempt in range(1, max_attempts + 1):
                try:
                    return await fn(*args, **kwargs)
                except Exception as e:
                    # Check if this is a permanent error that should not be retried
                    if not should_retry_exception(e):
                        logger.error(
                            f"Permanent error in '{fn.__name__}', not retrying: {e}. "
                            f"Failed after {attempt} attempt(s)."
                        )
                        raise
                    
                    # Check if it's one of the explicitly configured permanent errors
                    if any(isinstance(e, err_type) for err_type in permanent_errors):
                        logger.error(
                            f"Explicitly configured permanent error in '{fn.__name__}', not retrying: {e}. "
                            f"Failed after {attempt} attempt(s)."
                        )
                        raise
                    
                    if attempt == max_attempts:
                        logger.error(f"Function '{fn.__name__}' failed after {max_attempts} attempts.")
                        raise
                    
                    logger.warning(
                        f"Attempt {attempt}/{max_attempts} for '{fn.__name__}' failed: {e}. "
                        f"Retrying in {delay:.2f} seconds..."
                    )
                    await asyncio.sleep(delay + random.random() * 0.1)
                    delay *= factor
        return wrapper
    return decorator
