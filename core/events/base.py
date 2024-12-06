import logging
from core.models.game_context import GameContext
from utils.others import ordinal


class Cache:
    """
    A generic cache for storing and managing objects by type.

    This class provides functionality to store and retrieve objects,
    manage pending entries requiring additional processing, and define
    a cache duration for time-sensitive operations.

    Attributes:
        contains (object): The type of objects this cache holds.
        duration (int): The duration (in seconds) the cache entries are considered valid. Defaults to 60.
        entries (dict): A dictionary of cached entries, keyed by unique identifiers (e.g., event IDs).
        pending (dict): A dictionary of pending entries, keyed by unique identifiers, waiting for further data.

    Methods:
        add(entry): Adds an object to the main cache.
        add_pending(entry): Adds an object to the pending cache, with a default retry count of 0.
        get(id): Retrieves an object from the main cache by its identifier or returns `None` if not found.
        get_pending(id): Retrieves an object from the pending cache by its identifier or returns `None` if not found.
        remove(entry): Removes an object from the main cache by its unique identifier.

    Example:
        event_cache = Cache(Event, duration=120)
        event_cache.add(event)
        retrieved_event = event_cache.get(event.event_id)
    """

    def __init__(self, object_type: object, duration: int = 60):
        self.contains = object_type
        self.duration = duration
        self.entries = {}
        self.pending = {}

    def add(self, entry: object):
        """Adds an object to this Cache."""
        self.entries[entry.event_id] = entry

    def add_pending(self, entry: object):
        """Adds a pending object to the cache (waiting for missing data)."""
        self.pending[entry.event_id] = {"entry": entry, "tries": 0}

    def get(self, id: int):
        """Gets an entry from the cache / checks if exists via None return."""
        entry = self.entries.get(id)
        return entry

    def get_pending(self, id: int):
        """Gets an entry from the pending cache / checks if exists via None return."""
        entry = self.pending.get(id)
        return entry

    def remove(self, entry: object):
        """Removes an entry from its Object cache."""
        del self.entries[entry.event_id]


class Event:
    """
    Represents an individual event with parsed data and associated context.

    This class encapsulates event-specific data, provides methods for parsing and posting messages,
    and integrates with social platforms such as Bluesky.

    Attributes:
        event_data (dict): The raw event data retrieved from the API or source.
        event_id (int): The unique identifier for the event.
        event_type (str): A description of the event type (e.g., "goal", "penalty", "faceoff").
        period_number (int): The period number in which the event occurred (e.g., 1, 2, 3).
        period_number_ordinal (str): The period number formatted as an ordinal (e.g., "1st", "2nd").
        time_in_period (str): The timestamp within the period when the event occurred (e.g., "12:34").
        time_remaining (str): The time remaining in the period when the event occurred (e.g., "07:26").
        sort_order (int): A numerical value representing the order of events for sorting purposes.
        details (dict): Additional event-specific details, such as scoring player, shot type, etc.
        context (object): The shared context object, holding game state and configuration.
        bsky_root (object): The root Bluesky post object for a thread associated with the event.
        bsky_parent (object): The parent Bluesky post object in a thread for the event.
        add_hashtags (bool): A flag indicating whether hashtags should be appended to messages.

    Methods:
        parse(): Parses the raw event data for additional processing (stub for subclassing or further extension).
        post_message(message): Posts a formatted message to Bluesky, appending hashtags if enabled.

    Example:
        event = Event(event_data, context)
        event.parse()
        event.post_message("Goal scored by Player X!")
    """

    pending = Cache(__name__)

    def __init__(self, event_data, context: GameContext):
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
        # self.add_hashtags = True

        self.context.events.append(self)

    def parse(self):
        pass

    def post_message(
        self,
        message,
        link=None,
        add_hashtags=True,
        add_score=True,
        bsky_parent=None,
        bsky_root=None,
        media=None,
    ):
        """
        Post the parsed message to the appropriate channel, if applicable.
        """

        # Force Hashtags Off for Debugging
        add_hashtags = False if self.context.debugsocial else add_hashtags

        if message:
            # Calculate Footer String
            footer_parts = []

            if add_hashtags:
                footer_parts.append(self.context.preferred_team.hashtag)

            if add_score:
                pref_team = self.context.preferred_team
                other_team = self.context.other_team
                pref_score = f"{pref_team.abbreviation}: {pref_team.score}"
                other_score = f"{other_team.abbreviation}: {other_team.score}"
                footer_parts.append(f"{pref_score} / {other_score}")

            if footer_parts:
                footer_string = " | ".join(footer_parts)
                message += f"\n\n{footer_string}"

            # Post Message to Bluesky
            bsky_post = self.context.bluesky_client.post(
                message, link=link, reply_parent=bsky_parent, reply_root=bsky_root, media=media
            )

            # Add BlueSky post object to event object
            # If there is no root object, set the post as the root
            self.bsky_parent = bsky_post
            self.bsky_root = bsky_post if not self.bsky_root else self.bsky_root
