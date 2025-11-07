from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pytz
from socials.bluesky import BlueskyClient

from core.models.clock import Clock
from core.models.team import Team
from socials.social_state import EndOfGameSocial, StartOfGameSocial


@dataclass
class GameContext:
    """Centralized context for managing NHL game-related data and shared resources.

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

    # Configuration and Client
    config: dict[str, Any]
    bluesky_client: BlueskyClient
    nosocial: bool = False
    debugsocial: bool = False

    # Game Details
    game: dict | None = None
    game_id: str | None = None
    game_type: str | None = None
    game_shortid: str | None = None
    game_state: str | None = None
    season_id: str | None = None
    game_time: datetime | None = None
    game_time_local: datetime | None = None
    game_time_local_str: str | None = None
    venue: str | None = None
    clock: Clock = field(default_factory=Clock)

    # Team Details
    preferred_team: Team | None = None
    other_team: Team | None = None
    home_team: Team | None = None
    away_team: Team | None = None
    preferred_homeaway: str | None = None

    # Roster and Hashtag Details
    combined_roster: dict | None = None
    gametime_rosters_set: bool = False
    game_hashtag: str | None = None
    preferred_team_hashtag: str | None = None

    # Event Tracking
    last_sort_order: int = 0
    all_goals: list = field(default_factory=list)
    events: list = field(default_factory=list)
    live_loop_counter: int = 0

    # Social Media Trackers
    preview_socials: StartOfGameSocial = field(default_factory=StartOfGameSocial)
    final_socials: EndOfGameSocial = field(default_factory=EndOfGameSocial)

    @property
    def game_time_of_day(self) -> str:
        """Returns the time of the day of the game (later today or tonight)."""
        if not self.game_time_local:
            return ""
        game_date_hour = self.game_time_local.strftime("%H")
        return "tonight" if int(game_date_hour) > 17 else "later today"

    @property
    def game_time_countdown(self) -> float:
        """Returns a countdown (in seconds) to the game start time."""
        if not self.game_time_local or not self.preferred_team:
            return 0
        now = datetime.now().astimezone(pytz.timezone(self.preferred_team.timezone))
        countdown = (self.game_time_local - now).total_seconds()
        return max(0, countdown)
