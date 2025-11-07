"""Retry decorator with exponential backoff for API calls.

Usage:
    from utils.retry import retry

    @retry(max_attempts=3, delay=2.0, exceptions=(requests.RequestException,))
    def fetch_data():
        response = requests.get('https://api.example.com')
        response.raise_for_status()
        return response.json()
"""

import contextlib
import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    logger_name: str | None = None,
) -> Callable:
    """Decorator to retry a function with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts (default: 3)
        delay: Initial delay between retries in seconds (default: 1.0)
        backoff: Multiplier for delay on each retry (default: 2.0)
        exceptions: Tuple of exception types to catch (default: all exceptions)
        logger_name: Optional logger name for custom logging

    Returns:
        Decorated function that retries on failure

    Example:
        @retry(max_attempts=3, delay=2.0, exceptions=(requests.RequestException,))
        def fetch_nhl_data():
            response = requests.get('https://api-web.nhle.com/...')
            response.raise_for_status()
            return response.json()

    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Use custom logger if provided
            log = logging.getLogger(logger_name) if logger_name else logger

            attempt = 0
            current_delay = delay
            last_exception = None

            while attempt < max_attempts:
                try:
                    return func(*args, **kwargs)

                except exceptions as e:
                    attempt += 1
                    last_exception = e

                    if attempt >= max_attempts:
                        log.error(
                            f"Function {func.__name__} failed after {max_attempts} attempts. Last error: {e}",
                        )
                        raise

                    log.warning(
                        f"Attempt {attempt}/{max_attempts} failed for {func.__name__}: {e}. "
                        f"Retrying in {current_delay:.1f}s...",
                    )

                    time.sleep(current_delay)
                    current_delay *= backoff

            # Should never reach here, but just in case
            if last_exception:
                raise last_exception
            return None

        return wrapper

    return decorator


def retry_with_fallback(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    fallback_value: Any = None,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable:
    """Retry decorator that returns a fallback value instead of raising on failure.

    Args:
        max_attempts: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff: Multiplier for delay on each retry
        fallback_value: Value to return if all attempts fail
        exceptions: Tuple of exception types to catch

    Returns:
        Decorated function that returns fallback_value on failure

    Example:
        @retry_with_fallback(max_attempts=2, fallback_value=[])
        def fetch_optional_data():
            # This will return [] if it fails after 2 attempts
            response = requests.get('https://api.example.com/optional-endpoint')
            return response.json()

    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            attempt = 0
            current_delay = delay

            while attempt < max_attempts:
                try:
                    return func(*args, **kwargs)

                except exceptions as e:
                    attempt += 1

                    if attempt >= max_attempts:
                        logger.error(
                            f"Function {func.__name__} failed after {max_attempts} attempts. "
                            f"Returning fallback value. Last error: {e}",
                        )
                        return fallback_value

                    logger.warning(
                        f"Attempt {attempt}/{max_attempts} failed for {func.__name__}: {e}. "
                        f"Retrying in {current_delay:.1f}s...",
                    )

                    time.sleep(current_delay)
                    current_delay *= backoff

            return fallback_value

        return wrapper

    return decorator


# Example usage in schedule.py:
if __name__ == "__main__":
    import requests

    # Example 1: Retry with raising on failure
    @retry(max_attempts=3, delay=1.0, exceptions=(requests.RequestException,))
    def fetch_schedule(team_abbrev: str, season_id: str):
        """Fetch team schedule with automatic retry."""
        url = f"https://api-web.nhle.com/v1/club-schedule-season/{team_abbrev}/{season_id}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()

    # Example 2: Retry with fallback value
    @retry_with_fallback(max_attempts=2, fallback_value={})
    def fetch_optional_stats():
        """Fetch optional stats, return empty dict on failure."""
        response = requests.get("https://api.example.com/stats", timeout=5)
        response.raise_for_status()
        return response.json()

    # Test the decorator
    with contextlib.suppress(requests.RequestException):
        result = fetch_schedule("NJD", "20232024")
