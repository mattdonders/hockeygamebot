from .base import Cache, Event


class ShootoutEvent(Event):
    cache = Cache(__name__)

    def parse(self):
        """Parse a goal event and return a formatted message."""
