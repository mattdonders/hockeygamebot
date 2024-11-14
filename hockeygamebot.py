# hockeygamebot.py

import logging
import time
from datetime import datetime, timedelta
import pytz

from services.nhl_api_service import NHLAPIService
from services.social_media_service import SocialMediaService
from configuration import config
from utils import utils, arguments


class HockeyGameBotApp:
    def __init__(self):
        # Load configuration
        self.config = config

        # Parse command-line arguments
        self.args = arguments.get_arguments()

        # Set up logging
        utils.setup_logging(self.config, self.args)

        # Initialize services
        self.nhl_service = NHLAPIService()
        social_env = "prod" if not self.args.debugsocial else "debug"
        self.social_media_service = SocialMediaService(
            self.config, env=social_env, nosocial=self.args.nosocial
        )

        # Initialize variables
        self.team_name = None
        self.team_abbr = None
        self.team_hashtag = None
        self.next_game = None

    def run(self):
        # Log initial information
        self.log_startup_info()

        # Set up the game
        self.setup_game()

        # Prepare content
        content = self.prepare_content()

        # Post to social media
        self.post_update(content)

    def log_startup_info(self):
        logging.info("#" * 80)
        logging.info("New instance of the Hockey Game Bot started.")
        if self.args.docker:
            logging.info("Running in a Docker container - environment variables parsed.")
        logging.info("TIME: %s", datetime.now())
        logging.info(
            "ARGS - nosocial: %s, console: %s, teamoverride: %s",
            self.args.nosocial,
            self.args.console,
            self.args.team,
        )
        logging.info(
            "ARGS - debug: %s, debugsocial: %s, overridelines: %s",
            self.args.debug,
            self.args.debugsocial,
            self.args.overridelines,
        )
        logging.info(
            "ARGS - date: %s, split: %s, localdata: %s", self.args.date, self.args.split, self.args.localdata
        )
        logging.info(
            "SOCIAL - bluesky: %s, threads: %s",
            self.config["socials"]["bluesky"],
            self.config["socials"]["threads"],
        )
        logging.info("%s\n", "#" * 80)

    def setup_game(self):
        # Determine the team abbreviation and hashtag
        self.team_name = self.args.team if self.args.team else self.config["default"]["team_name"]
        self.team_abbr = self.config["default"].get("team_abbr", "NJD")
        self.team_hashtag = self.config["default"].get("team_hashtag", self.team_abbr)

        # Fetch the next game
        self.next_game = self.nhl_service.get_next_game(self.team_abbr)
        if not self.next_game:
            logging.info("No upcoming games found. Exiting.")
            exit()

    def prepare_content(self):
        # Fetch team full names
        team_data = self.nhl_service.get_team_full_names()

        # Get the away and home team IDs
        away_team_id = self.next_game.get("awayTeam", {}).get("id")
        home_team_id = self.next_game.get("homeTeam", {}).get("id")

        # Get the full team names
        away_team_info = team_data.get(away_team_id, {})
        away_team_name = away_team_info.get("full_name", "Unknown Team")
        away_team_abbr = away_team_info.get("abbreviation", "UNK")

        home_team_info = team_data.get(home_team_id, {})
        home_team_name = home_team_info.get("full_name", "Unknown Team")
        home_team_abbr = home_team_info.get("abbreviation", "UNK")

        venue = self.next_game.get("venue")
        if isinstance(venue, dict):
            venue_name = venue.get("default", "Unknown Venue")
        else:
            venue_name = venue

        start_time_utc = self.next_game.get("startTimeUTC")

        # Convert startTimeUTC to US/Eastern time
        start_time_eastern = self.convert_time_to_eastern(start_time_utc)
        start_time_formatted = start_time_eastern.strftime("%I:%M %p")

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
        us_networks = self.nhl_service.get_us_broadcast_networks(self.next_game)
        broadcast_channel = ", ".join(us_networks) if us_networks else "Unavailable"

        # Prepare the content
        content = (
            f"Tune in {day_text} when the {away_team_name} take on the {home_team_name} at {venue_name}.\n\n"
            f"🕢 {start_time_formatted}\n"
            f"📺 {broadcast_channel}\n"
            f"#️⃣ #{self.team_hashtag}"
        )

        return content

    def convert_time_to_eastern(self, utc_time_str):
        """Converts UTC time string to US/Eastern timezone."""
        utc_time = datetime.strptime(utc_time_str, "%Y-%m-%dT%H:%M:%SZ")
        utc_time = utc_time.replace(tzinfo=pytz.utc)
        eastern = pytz.timezone("US/Eastern")
        eastern_time = utc_time.astimezone(eastern)
        return eastern_time

    def post_update(self, content):
        # Post the content to social media
        self.social_media_service.post_update(content)

    def end_game_loop(self):
        logging.info("Game has ended.")
        # Perform any necessary cleanup


if __name__ == "__main__":
    app = HockeyGameBotApp()
    app.run()
