# utils/logging_session.py

import logging
import requests


class LoggingSession(requests.Session):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)

    def request(self, method, url, **kwargs):
        self.logger.info(f"Making {method} request to URL: {url}")
        if "params" in kwargs:
            self.logger.debug(f"With params: {kwargs['params']}")
        if "data" in kwargs:
            self.logger.debug(f"With data: {kwargs['data']}")
        if "json" in kwargs:
            self.logger.debug(f"With json: {kwargs['json']}")
        if "headers" in kwargs:
            self.logger.debug(f"With headers: {kwargs['headers']}")

        response = super().request(method, url, **kwargs)

        self.logger.debug(f"Received response: {response.status_code}")
        return response
