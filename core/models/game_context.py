from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar, Dict, Optional

import pytz

from core.milestones import MilestoneService
from core.models.clock import Clock
from core.models.team import Team
from socials.bluesky import BlueskyClient
from socials.publisher import SocialPublisher
from socials.social_state import EndOfGameSocial, StartOfGameSocial
from socials.types import PostRef


class GameContext:
    """
    Centralized context for managing NHL game-related data and shared resources.

    The `GameContext` class serves as the primary hub for tracking and managing the state
    of an NHL game, including team details, game configuration, rosters, and social media
    interactions. It facilitates communication between different parts of the application
    and ensures that game-related data is consistently managed and accessible.

    Attributes:
        config (dict): Configuration settings loaded from a YAML file, including team preferences
            and API credentials.
        bluesky_client: An instance of the Bluesky API client for posting social media updates.
        nosocial (bool): A flag to disable social media posting for debugging purposes.

    Game Details:
        game (dict): The raw game data from the NHL API.
        game_id (str): Unique identifier for the game (e.g., "2023020356").
        game_type (str): <TBD>
        game_shortid (str): Abbreviated game ID for easier logging or debugging.
        game_state (str): Current state of the game (e.g., "LIVE", "FUT", "OFF").
        season_id (str): Identifier for the NHL season in which the game is played.
        clock (Clock): An instance of the `Clock` class for managing game time.

    Team Details:
        preferred_team (Team): The user's preferred NHL team.
        other_team (Team): The opposing team in the game.
        home_team (Team): The home team in the game.
        away_team (Team): The away team in the game.
        preferred_homeaway (str): Indicates whether the preferred team is playing as "home" or "away".

    Roster Details:
        combined_roster (dict): A combined roster of both teams for the game.
        gametime_rosters_set (bool): Indicates whether rosters have been finalized at game time.

    Social Media Details:
        game_hashtag (str): The primary hashtag for the game, used in social media posts.
        preferred_team_hashtag (str): Hashtag associated with the preferred team.

    Event Tracking:
        last_sort_order (int): Tracks the last event's sort order for real-time event parsing.
        all_goals (list): List of all goals recorded during the game.
        events (list): A collection of parsed game events.
        live_loop_counter (int): A way to keep track of the number of live loops we've done.

    Social Media Trackers:
        preview_socials (StartOfGameSocial): Tracks the state of social posts before the game starts.
        final_socials (EndOfGameSocial): Tracks the state of social posts after the game ends.

    Methods:
        __init__: Initializes the `GameContext` with configuration and shared resources.
    """

    # Track the "current" / active context (one per process)
    _active: ClassVar["GameContext | None"] = None

    def __init__(self, config: dict, social: SocialPublisher, nosocial: bool = False, debugsocial: bool = False):
        self.config = config
        self.social = social  # unified SocialPublisher (Bluesky+Threads)
        self.bluesky_client = social  # back-compat shim for old call sites
        self.nosocial: bool = nosocial
        self.debugsocial: bool = debugsocial

        self.cache = None  # type: ignore  # set per game after IDs/teams are known

        # Attributes Below are Not Passed-In at Initialization Time
        self.game = None
        self.game_id = None
        self.game_type = None
        self.game_shortid = None
        self.game_state = None
        self.season_id = None
        self.game_time = None
        self.game_time_local = None
        self.game_time_local_str = None
        self.venue = None
        self.clock: Clock = Clock()

        self.period_descriptor: dict | None = None
        self.display_period: int | None = None

        self.preferred_team: Team = None
        self.other_team: Team = None
        self.home_team: Team = None
        self.away_team: Team = None

        self.preferred_homeaway = None

        self.combined_roster = None
        self.preferred_roster = None
        self.other_roster = None
        self.gametime_rosters_set = False
        self.game_hashtag = None
        self.preferred_team_hashtag = None

        self.last_sort_order = 0
        self.all_goals = []
        self.events = []

        self.live_loop_counter = 0

        # Social Media Related Trackers
        self.preview_socials = StartOfGameSocial()
        self.final_socials = EndOfGameSocial()

        self.milestone_service: Optional[MilestoneService] = None

    # -------------------------
    # Helpers
    # -------------------------
    @staticmethod
    def make_post_ref(res: Optional[Dict[str, Any]]) -> Optional[PostRef]:
        """
        Normalize a publisher result dict (from Bluesky/Threads/etc.) into PostRef.
        Expected keys (best-effort, optional in input):
          - platform: str
          - id: str (Threads published/creation id; Bluesky URI)
          - uri: str (Bluesky)
          - cid: str (Bluesky)
          - published: bool
        """
        if not res:
            return None

        platform = str(res.get("platform", "unknown"))
        canonical_id = res.get("id") or res.get("uri") or res.get("published_id") or res.get("container_id") or ""

        return PostRef(
            platform=platform,
            id=str(canonical_id),
            uri=res.get("uri"),
            cid=res.get("cid"),
            published=bool(res.get("published", True)),
            raw=res,
        )

    @property
    def game_time_of_day(self):
        """Returns the time of the day of the game (later today or tonight)."""
        game_date_hour = self.game_time_local.strftime("%H")
        return "tonight" if int(game_date_hour) > 17 else "later today"

    @property
    def game_time_countdown(self):
        """Returns a countdown (in seconds) to the game start time."""
        now = datetime.now().astimezone(pytz.timezone(self.preferred_team.timezone))
        countdown = (self.game_time_local - now).total_seconds()
        return 0 if countdown < 0 else countdown

        # ---------- Active context helpers ----------

    @classmethod
    def set_active(cls, context: "GameContext") -> None:
        cls._active = context

    @classmethod
    def get_active(cls) -> "GameContext":
        if cls._active is None:
            raise RuntimeError("No active GameContext has been set")
        return cls._active
