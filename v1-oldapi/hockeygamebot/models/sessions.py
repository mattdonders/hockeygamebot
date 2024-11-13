import requests


class SessionFactory:
    def __init__(self):
        self.session = None

    def get(self):
        if self.session is None:
            self.session = requests.session()
        return self.session
