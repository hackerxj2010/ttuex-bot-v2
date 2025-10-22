import asyncio
import random
import logging
from functools import wraps

logger = logging.getLogger(__name__)

def async_retry(max_attempts=3, base_delay=1.0, factor=2.0):
    """
    A decorator to retry an async function if it raises an exception.

    Args:
        max_attempts: The maximum number of attempts.
        base_delay: The initial delay between retries in seconds.
        factor: The factor by which to multiply the delay for each subsequent retry.
    """
    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            delay = base_delay
            for attempt in range(1, max_attempts + 1):
                try:
                    return await fn(*args, **kwargs)
                except Exception as e:
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
