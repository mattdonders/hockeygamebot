import logging
from typing import List, Optional, Union

from core.events.text_utils import period_label, period_label_playoffs
from core.models.game_context import GameContext
from utils.others import ordinal

logger = logging.getLogger(__name__)

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

    # -------------------------------------------------
    # Period labeling helpers
    # -------------------------------------------------
    @property
    def is_playoffs(self) -> bool:
        """
        Whether the current game is a playoff game.

        TODO: Replace this stub once playoff logic is implemented.
        e.g., set via `context.is_playoffs` or `context.game_type`
        when reading from the NHL schedule API.
        """
        return False

    def _period_label(self, *, short: bool) -> str:
        """
        Internal helper that selects the correct label
        function depending on playoff state.
        """
        event_dict = getattr(self, "event_data", {}) or {}

        if self.is_playoffs:
            return period_label_playoffs(event_dict, short=short)
        return period_label(event_dict, short=short)

    @property
    def period_label(self) -> str:
        """Long form: 'the 2nd period', 'overtime', or 'the shootout'."""
        return self._period_label(short=False)

    @property
    def period_label_short(self) -> str:
        """Short form: '2nd', 'OT', or 'SO'."""
        return self._period_label(short=True)

    def post_message(
        self,
        message: str,
        link: Optional[str] = None,
        add_hashtags: bool = True,
        add_score: bool = True,
        media: Optional[Union[str, List[str]]] = None,
        alt_text: str = "",
    ) -> None:
        """
        Fire-and-forget post for regular events (no threading).
        Supports text-only, single image (str), or multi-image (list[str]).
        Delegates to the unified SocialPublisher (Bluesky/Threads parity).
        Never raises; logs exceptions via context.logger if available.
        """

        # If parse() returned None or an empty string, there is nothing to post.
        if not message or not str(message).strip():
            # This can happen for GenericEvent and other “silent” events.
            logger.debug(
                "post_message: no text for %s (event_id=%s, type=%s) — skipping.",
                self.__class__.__name__,
                getattr(self, "event_id", None),
                getattr(self, "event_type", None),
            )
            return

        # Respect debugsocial for hashtags
        add_hashtags = False if getattr(self.context, "debugsocial", False) else add_hashtags

        # Footer (hashtags + score)
        footer_parts: List[str] = []
        if add_hashtags:
            try:
                hashtag = getattr(self.context.preferred_team, "hashtag", "")
                if hashtag:
                    footer_parts.append(hashtag)
            except Exception:
                pass

        if add_score:
            try:
                pref = self.context.preferred_team
                other = self.context.other_team
                footer_parts.append(f"{pref.abbreviation}: {pref.score} / {other.abbreviation}: {other.score}")
            except Exception:
                pass

        text = str(message)
        if footer_parts:
            text += "\n\n" + " | ".join(footer_parts)
        if link:
            text += f"\n\n{link}"

        # Fan out to Bluesky + Threads (Publisher handles platform quirks + multi-image)
        try:
            self.context.social.post(
                message=text,
                media=media,
                alt_text=alt_text or "",
                platforms="enabled",
            )
        except Exception as e:
            # Never crash event parsing
            logger.exception("Social post failed: %s", e)

    def post_message_old(
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
                message,
                link=link,
                reply_parent=bsky_parent,
                reply_root=bsky_root,
                media=media,
            )

            # Add BlueSky post object to event object
            # If there is no root object, set the post as the root
            self.bsky_parent = bsky_post
            self.bsky_root = bsky_post if not self.bsky_root else self.bsky_root
