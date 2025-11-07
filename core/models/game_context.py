from datetime import datetime
from typing import Any, Literal

import pytz

from core.models.clock import Clock
from core.models.team import Team, Teams
from socials.publisher import SocialPublisher
from socials.social_state import EndOfGameSocial, StartOfGameSocial
from utils.status_monitor import StatusMonitor


class GameContext:
    """Centralized context for managing NHL game-related data and shared resources.

    The `GameContext` class acts as the primary hub for tracking and managing the state
    of an NHL game, including configuration data, team assignments, live-game updates,
    social media integration, and event history. It ensures that all modules share a
    consistent and authoritative view of the current game.

    Attributes:
        # Core Configuration
        config (dict): Configuration settings loaded from a YAML file, including team preferences
            and API credentials.
        social (SocialPublisher): Unified social publisher for Bluesky/Threads.
        bluesky_client (SocialPublisher): Backward-compatible alias for the same SocialPublisher.
        nosocial (bool): If True, disables all outbound social media posting.
        debugsocial (bool): If True, enables debug-mode logging for social posting without publishing.

        # Game Metadata
        game (dict | None): Raw game data fetched from the NHL API.
        game_id (str): Unique identifier for the current game (e.g., "2023020356").
        season_id (str): Identifier for the active NHL season.
        game_type (str | None): Type of game (e.g., regular, preseason, postseason).
        game_shortid (str | None): Abbreviated or simplified game identifier for logs.
        game_state (str | None): Current state of the game (e.g., "LIVE", "FUT", "OFF").
        game_time (datetime | None): Official start time of the game in UTC.
        game_time_local (datetime | None): Localized version of `game_time`.
        game_time_local_str (str | None): String representation of the local start time.
        venue (str | None): Venue name where the game is played.

        # Season Metadata
        clock (Clock): Instance of the `Clock` class for time tracking within periods.

        # Team Metadata
        teams (Teams): Wrapper object containing preferred, other, home, and away teams.
        preferred_team (Team): The user's preferred NHL team.
        other_team (Team): The opponent.
        home_team (Team): The home team.
        away_team (Team): The away team.
        preferred_homeaway (Literal["home", "away"] | None): Indicates whether the preferred team
            is home or away.
        teams_ready (bool): Returns True if all teams are initialized.

        # Roster Data
        combined_roster (dict | None): Combined player data from both teams.
        gametime_rosters_set (bool): Whether the final game-time rosters are locked.

        # Social Media Metadata
        game_hashtag (str | None): Primary hashtag for the game (e.g., "#NJDvsNYR").
        preferred_team_hashtag (str | None): Hashtag associated with the preferred team.

        # Event Tracking
        last_sort_order (int): Sort order of the most recently processed event.
        all_goals (list): History of all goal events parsed during the game.
        events (list): Complete collection of parsed in-game events.
        live_loop_counter (int): Number of polling loops executed during live-game parsing.

        # Monitoring
        monitor (StatusMonitor): Tracks status JSON updates and runtime conditions.

        # Social Media State
        preview_socials (StartOfGameSocial): State tracking for pre-game social posts.
        final_socials (EndOfGameSocial): State tracking for post-game social posts.

        # Hidden Internal Fields (private)
        _game_id (str | None): Backing field for the public `game_id` property.
        _season_id (str | None): Backing field for the public `season_id` property.
        _teams (Teams | None): Backing field for the public `teams` property.

    Methods:
        __init__(config, social, nosocial=False, debugsocial=False):
            Initializes the GameContext with configuration and shared resources.

        set_game_ids(game_id: str, season_id: str) -> None:
            Assigns both game and season identifiers at once.

        set_teams(preferred: Team, other: Team, preferred_homeaway: Literal["home", "away"]) -> None:
            Sets all team references (preferred, other, home, away) in one step.

        format_scoreline() -> str:
            Returns a formatted score string for display or social posts.

        game_time_countdown() -> float:
            Returns the number of seconds until game start, or 0 if already started or invalid.

        teams_ready -> bool:
            Returns True if all four team objects are initialized.

    """

    # ---------- Backing fields (intentional optionals) ----------
    _game_id: str | None = None
    _season_id: str | None = None
    _teams: Teams | None = None

    # Non-team metadata set later during setup
    preferred_homeaway: Literal["home", "away"] | None = None  # convenience flag

    # ---------- Public init inputs ----------
    def __init__(self, config: dict, social: SocialPublisher, nosocial: bool = False, debugsocial: bool = False):
        # Config + socials
        self.config = config
        self.social = social  # unified SocialPublisher (Bluesky/Threads)
        self.bluesky_client = social  # back-compat alias for older callsites
        self.nosocial: bool = nosocial
        self.debugsocial: bool = debugsocial

        # Game meta (lazy-filled)
        self.game: dict | None = None
        self.game_type: str | None = None
        self.game_shortid: str | None = None
        self.game_state: str | None = None
        self.game_time: datetime | None = None
        self.game_time_local: datetime | None = None
        self.game_time_local_str: str | None = None
        self.venue: str | None = None

        # Season meta (lazy-filled via setter)
        # _season_id backing field above

        # Clock
        self.clock: Clock = Clock()

        # Rosters
        self.combined_roster: dict[str, Any] = {}
        self.gametime_rosters_set: bool = False

        # Social bits
        self.game_hashtag: str | None = None
        self.preferred_team_hashtag: str | None = None

        # Event tracking
        self.last_sort_order: int = 0
        self.all_goals: list = []
        self.events: list = []
        self.live_loop_counter: int = 0

        # Status monitor (declare + initialize so Pylance knows it exists)
        self.monitor: StatusMonitor = StatusMonitor()

        # Back-compat social state trackers
        self.preview_socials = StartOfGameSocial()
        self.final_socials = EndOfGameSocial()

    # ---------- Non-optional public properties (raise if unset) ----------
    @property
    def game_id(self) -> str:
        if self._game_id is None:
            raise RuntimeError("GameContext.game_id is not set")
        return self._game_id

    @property
    def season_id(self) -> str:
        if self._season_id is None:
            raise RuntimeError("GameContext.season_id is not set")
        return self._season_id

    @property
    def teams(self) -> Teams:
        if self._teams is None:
            raise RuntimeError("GameContext.teams is not set")
        return self._teams

    # ---------- Setters (simple helpers, no separate @property setters needed) ----------
    def set_game_ids(self, game_id: str, season_id: str) -> None:
        self._game_id = game_id
        self._season_id = season_id

    def set_teams(self, preferred: Team, other: Team, preferred_homeaway: Literal["home", "away"]) -> None:
        self.preferred_homeaway = preferred_homeaway
        if preferred_homeaway == "home":
            self._teams = Teams(preferred=preferred, other=other, home=preferred, away=other)
        else:
            self._teams = Teams(preferred=preferred, other=other, home=other, away=preferred)

    # ---------- Back-compat properties so existing code keeps working ----------
    @property
    def preferred_team(self) -> Team:
        return self.teams.preferred

    @property
    def other_team(self) -> Team:
        return self.teams.other

    @property
    def home_team(self) -> Team:
        return self.teams.home

    @property
    def away_team(self) -> Team:
        return self.teams.away

    @property
    def teams_ready(self) -> bool:
        return self._teams is not None

    # ---- Other / Optional Helpers ----
    def game_time_of_day(self) -> str:
        """Returns 'tonight' or 'later today' based on local hour."""
        if not self.game_time_local:
            return "later today"
        hour = int(self.game_time_local.strftime("%H"))
        return "tonight" if hour > 17 else "later today"

    def game_time_countdown(self) -> float:
        """Seconds until game start; 0 if missing or in the past."""
        if not (self.game_time_local and self._teams and getattr(self.preferred_team, "timezone", None)):
            return 0
        now = datetime.now().astimezone(pytz.timezone(self.preferred_team.timezone))
        delta = (self.game_time_local - now).total_seconds()
        return max(delta, 0)
