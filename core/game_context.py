from socials.social_state import StartOfGameSocial, EndOfGameSocial


class GameContext:
    """
    Centralized context for game-related data and shared resources.
    """

    def __init__(self, config, bluesky_client, nosocial=False):
        self.config = config
        self.bluesky_client = bluesky_client
        self.nosocial = nosocial

        # Attributes Below are Not Passed-In at Initialization Time
        self.game = None
        self.game_id = None
        self.game_state = None
        self.preferred_team_name = None
        self.preferred_team_abbreviation = None
        self.other_team_name = None
        self.preferred_team_id = None
        self.preferred_homeaway = None
        self.preferred_score = 0
        self.other_score = 0
        self.combined_roster = None
        self.gametime_rosters_set = False
        self.game_hashtag = None
        self.preferred_team_hashtag = None
        self.season_id = None
        self.last_sort_order = 0
        self.parsed_event_ids = []
        self.all_goals = []
        self.events = []

        # Social Media Related Trackers
        self.preview_socials = StartOfGameSocial()
        self.final_socials = EndOfGameSocial()
