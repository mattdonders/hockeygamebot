import time
from functools import wraps

import requests


def retry(max_attempts=3, backoff_seconds=1):
    """Decorator for retrying network requests with exponential backoff.

    Args:
        max_attempts (int): Maximum number of retry attempts
        backoff_seconds (int): Base time to wait between retries

    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempts = 0
            while attempts < max_attempts:
                try:
                    return func(*args, **kwargs)
                except (requests.RequestException, ConnectionError):
                    attempts += 1
                    if attempts == max_attempts:
                        raise
                    wait_time = backoff_seconds * (2**attempts)
                    time.sleep(wait_time)
            return None

        return wrapper

    return decorator


class SessionFactory:
    """A reusable factory for creating and managing a single `requests` session.

    The `SessionFactory` class ensures consistent behavior by maintaining a single
    `requests.Session` instance across multiple HTTP requests. This improves performance
    and allows shared configuration such as headers, cookies, or connection pooling.

    Attributes:
        session (requests.Session): The `requests.Session` instance managed by the factory.

    Methods:
        get():
            Returns the existing `requests.Session` instance or creates a new one if none exists.

    """

    def __init__(self):
        """Initializes the SessionFactory with no active session."""
        self.session = None

    def get(self) -> requests.Session:
        """Retrieves the managed `requests.Session` instance.

        If a session does not already exist, a new `requests.Session` instance is created
        and returned. Subsequent calls will return the same session instance.

        Returns:
            requests.Session: The managed `requests.Session` instance.

        Example Usage:
            session_factory = SessionFactory()
            session = session_factory.get()
            response = session.get("https://api.example.com/data")

        """
        if self.session is None:
            self.session = requests.session()
        return self.session

    @retry()
    def request_with_retry(self, method, url, **kwargs):
        """Makes a request with built-in retry mechanism

        Args:
            method (str): HTTP method (get, post, etc.)
            url (str): Request URL
            **kwargs: Additional request parameters

        Returns:
            requests.Response: Response from the request

        """
        session = self.get()
        return getattr(session, method)(url, **kwargs)
