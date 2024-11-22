import logging
from utils.others import ordinal


class Event:
    def __init__(self, event_data, context):
        self.event_data = event_data
        self.event_id = event_data.get("eventId")
        self.event_type = event_data.get("typeDescKey", "unknown")
        self.period_number = event_data.get("periodDescriptor", {}).get("number", 0)
        self.period_number_ordinal = ordinal(self.period_number)
        self.time_in_period = event_data.get("timeInPeriod", "00:00")
        self.time_remaining = event_data.get("timeRemaining", "00:00")
        self.sort_order = event_data.get("sortOrder", 0)
        self.details = event_data.get("details", {})
        self.context = context
        self.bsky_root = None
        self.bsky_parent = None
        self.add_hashtags = True

        self.context.events.append(self)

    def parse(self):
        pass

    def post_message(self):
        """
        Post the parsed message to the appropriate channel, if applicable.
        """
        message = self.parse()
        if message:
            if self.add_hashtags:
                message += f"\n\n{self.context.preferred_team_hashtag} | {self.context.game_hashtag}"

            # Post Message to Bluesky
            bsky_post = self.context.bluesky_client.post(message)

            # Add BlueSky post object to event object
            # If there is no root object, set the post as the root
            self.bsky_parent = bsky_post
            self.bsky_root = bsky_post if not self.bsky_root else self.bsky_root


class Cache:
    """A cache that holds Events by type."""

    def __init__(self, object_type: object, duration: int = 60):
        self.contains = object_type
        self.duration = duration
        self.entries = {}

    def add(self, entry: object):
        """Adds an object to this Cache."""
        self.entries[entry.event_id] = entry

    def get(self, id: int):
        """Gets an entry from the cache / checks if exists via None return."""
        entry = self.entries.get(id)
        return entry

    def remove(self, entry: object):
        """Removes an entry from its Object cache."""
        del self.entries[entry.event_id]
