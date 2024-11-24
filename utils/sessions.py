import requests


class SessionFactory:
    """
    A reusable factory for creating and managing a single `requests` session.

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
        """
        Initializes the SessionFactory with no active session.
        """
        self.session = None

    def get(self) -> requests.Session:
        """
        Retrieves the managed `requests.Session` instance.

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
