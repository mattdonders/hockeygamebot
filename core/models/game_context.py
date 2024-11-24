from core.models.clock import Clock
from core.models.team import Team
from socials.social_state import StartOfGameSocial, EndOfGameSocial


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

    Social Media Trackers:
        preview_socials (StartOfGameSocial): Tracks the state of social posts before the game starts.
        final_socials (EndOfGameSocial): Tracks the state of social posts after the game ends.

    Methods:
        __init__: Initializes the `GameContext` with configuration and shared resources.
    """

    def __init__(self, config, bluesky_client, nosocial=False):
        self.config = config
        self.bluesky_client = bluesky_client
        self.nosocial = nosocial

        # Attributes Below are Not Passed-In at Initialization Time
        self.game = None
        self.game_id = None
        self.game_type = None
        self.game_shortid = None
        self.game_state = None
        self.season_id = None
        self.clock: Clock = Clock()

        self.preferred_team: Team = None
        self.other_team: Team = None
        self.home_team: Team = None
        self.away_team: Team = None

        self.preferred_homeaway = None

        self.combined_roster = None
        self.gametime_rosters_set = False
        self.game_hashtag = None
        self.preferred_team_hashtag = None

        self.last_sort_order = 0
        self.all_goals = []
        self.events = []

        # Social Media Related Trackers
        self.preview_socials = StartOfGameSocial()
        self.final_socials = EndOfGameSocial()
