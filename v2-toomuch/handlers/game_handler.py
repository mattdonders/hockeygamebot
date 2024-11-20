import logging
import time
from datetime import datetime

import pytz

from utils import utils


# from models.game_state import GameState, GameStateCode    # TBD


class GameHandler:
    def __init__(self, nhl_service, content_preparer, social_media_service):
        self.nhl_service = nhl_service
        self.content_preparer = content_preparer
        self.social_media_service = social_media_service

        self.teams_data = self.nhl_service.get_team_full_names()

    def handle_game_today(self, game_info):
        # Create a Game object from game_info
        game = self.nhl_service.create_game_from_info(game_info)
        print(vars(game))
        # Start the game loop
        self.start_game_loop(game)

    def calculate_sleep_until_game_start(self, game):
        # Get current time and game start time in UTC
        now_utc = datetime.utcnow()
        game_start_time_utc = datetime.strptime(game.start_time_utc, "%Y-%m-%dT%H:%M:%SZ")

        # Calculate the time difference in seconds
        time_diff = (game_start_time_utc - now_utc).total_seconds()
        sleep_time = max(time_diff, 0)  # Ensure sleep time is non-negative
        return sleep_time

    def start_game_loop(self, game):
        """Main game loop to track game state and perform actions accordingly."""
        logging.info("Starting main game loop now!")
        while True:
            if game.game_state == "FUT":
                self.handle_preview_state(game)
            elif game.game_state == "LIVE":
                self.handle_live_state(game)
            elif game.game_state == "OFF":
                self.handle_final_state(game)
                break  # Exit the loop after handling the final state
            else:
                logging.warning(f"Unhandled game state: {game.game_state}")
                time.sleep(60)  # Sleep before checking again

    def send_pregame_message(self, game):
        # Get the full team names
        away_team_name = game.away_team_name
        home_team_name = game.home_team_name

        venue = game.game_info.get("venue")
        if isinstance(venue, dict):
            venue_name = venue.get("default", "Unknown Venue")
        else:
            venue_name = venue

        # Convert startTimeUTC to US/Eastern time
        start_time_eastern = utils.convert_time_to_eastern(game.start_time_utc)
        start_time_formatted = start_time_eastern.strftime("%I:%M %p")
        start_time_noampm = start_time_eastern.strftime("%I:%M")

        # Determine if the game is today, tomorrow, or the day name
        now_eastern = datetime.now(pytz.timezone("US/Eastern"))
        days_diff = (start_time_eastern.date() - now_eastern.date()).days
        if days_diff == 0:
            day_text = "today"
        elif days_diff == 1:
            day_text = "tomorrow"
        else:
            day_text = start_time_eastern.strftime("%A")

        # Get the broadcast data
        us_networks = self.nhl_service.get_us_broadcast_networks(game.game_info)
        broadcast_channel = ", ".join(us_networks) if us_networks else "Unavailable"
        clock_emoji = utils.clock_emoji(start_time_noampm)

        # Prepare the content
        content = (
            f"Tune in {day_text} when the {away_team_name} take on the {home_team_name} at {venue_name}.\n\n"
            f"{clock_emoji} {start_time_formatted}\n"
            f"📺 {broadcast_channel}\n"
            f"#️⃣ #{game.game_hashtag}"
        )

        self.social_media_service.post_update(content)

    def handle_preview_state(self, game):
        # Send pre-game message
        self.send_pregame_message(game)

        # Calculate time to sleep until game start
        sleep_time = self.calculate_sleep_until_game_start(game)
        logging.info(f"Sleeping for {sleep_time} seconds until game start.")
        time.sleep(sleep_time)

        # After sleeping, proceed to check game state again
        logging.info("Waking up. Checking game state.")
        # Game state will be checked in the main loop

    def handle_pregame_updates(self, game):
        # Send core pre-game content once
        if not game.preview_socials.core_sent:
            content = self.content_preparer.prepare_pregame_content(game)
            self.social_media_service.post_update(content)
            game.preview_socials.core_sent = True

        # Send other pre-game updates periodically
        sleep_time, last_sleep_before_live = self.content_preparer.calculate_pregame_sleep_time(game)
        if last_sleep_before_live:
            # Adjust sleep time if needed and get starting lineup
            sleep_time = max(sleep_time - 300, 0)
            time.sleep(sleep_time)
            self.handle_starting_lineup(game)
        else:
            time.sleep(sleep_time)

    def handle_starting_lineup(self, game):
        # Fetch and post starting lineup
        content = self.content_preparer.prepare_starting_lineup_content(game)
        self.social_media_service.post_update(content)
        game.preview_socials.starters_sent = True

    def handle_live_state(self, game):
        # Implement live game updates
        pass  # Placeholder for live game handling

    def handle_final_state(self, game):
        # Implement post-game updates
        content = self.content_preparer.prepare_postgame_content(game)
        self.social_media_service.post_update(content)
        logging.info("Game has ended. Exiting game loop.")

    def handle_game_yesterday(self, game_info):
        content = self.content_preparer.prepare_postgame_content(game_info)
        self.social_media_service.post_update(content)
