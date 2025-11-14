import logging

from core.events.base import Cache, Event

logger = logging.getLogger(__name__)

class GenericEvent(Event):
    cache = Cache(__name__)

    def parse(self):
        """
        Generic parsing logic for events not explicitly mapped.
        """
        # logger.info(f"Received unmapped event: {self.event_type} at sort order {self.sort_order}.")
        return None  # No message to post by default
