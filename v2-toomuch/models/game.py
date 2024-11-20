# models/game.py


from datetime import datetime, timezone


class Game:
    def __init__(self, game_id, start_time_utc):
        self.game_id = game_id
        self.start_time_utc = start_time_utc
        self.game_info = None
        self.game_state = None
        self.game_state_code = None
        self.last_sort_order = 0  # Initialize to 0
        self.away_team_name = None
        self.home_team_name = None
        self.game_hashtag = None
        self.game_time_countdown = None  # Time until game starts in seconds

    def update_game(self, livefeed_data):
        # Update game state and other attributes based on livefeed data
        self.game_state = livefeed_data.get("gameState")
        self.game_state_code = livefeed_data.get("gameStateCode")
        # Update additional attributes as needed
        # For example, update the game time countdown
        # self.game_time_countdown = ... (calculate based on current time and start time)

    def calculate_time_until_game_start(self):
        # Convert start_time_utc to datetime object
        game_start_time = datetime.strptime(self.start_time_utc, "%Y-%m-%dT%H:%M:%SZ")
        game_start_time = game_start_time.replace(tzinfo=timezone.utc)

        # Get current UTC time
        now_utc = datetime.now(timezone.utc)

        # Calculate time difference in seconds
        time_diff = (game_start_time - now_utc).total_seconds()
        self.game_time_countdown = max(time_diff, 0)  # Ensure non-negative value
