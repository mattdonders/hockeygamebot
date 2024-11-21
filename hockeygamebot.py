import argparse
import logging
from datetime import datetime, timedelta
import time

import requests

import core.rosters as rosters
import core.schedule as schedule
import utils.others as otherutils
from core.play_by_play import parse_play_by_play_with_names
from core.preview import format_future_game_post, format_season_series_post, sleep_until_game_start
from core.live import parse_live_game
from socials.bluesky import BlueskyClient
from utils.config import load_config
from utils.team_abbreviations import TEAM_ABBREVIATIONS
from utils.team_details import TEAM_DETAILS


class GameContext:
    """
    Centralized context for game-related data and shared resources.
    """

    def __init__(self, config, bluesky_client, nosocial=False):
        self.config = config
        self.bluesky_client = bluesky_client
        self.nosocial = nosocial
        self.game_id = None
        self.preferred_team_name = None
        self.preferred_team_abbreviation = None
        self.other_team_name = None
        self.preferred_team_id = None
        self.preferred_homeaway = None
        self.combined_roster = None
        self.game_hashtag = None
        self.preferred_team_hashtag = None
        self.season_id = None
        self.last_sort_order = 0
        self.parsed_event_ids = []
        self.all_goals = []


def handle_is_game_today(game, target_date, team_abbreviation, season_id, context):
    """
    Handle logic when there is a game today.
    """
    logging.info(f"Game found today ({target_date}):")
    logging.info(
        f"  {game['awayTeam']['placeName']['default']} ({game['awayTeam']['abbrev']}) "
        f"@ {game['homeTeam']['placeName']['default']} ({game['homeTeam']['abbrev']})"
    )
    logging.info(f"  Venue: {game['venue']['default']}")
    logging.info(f"  Start Time (UTC): {game['startTimeUTC']}")

    # Set hashtags and game context
    home_team = game["homeTeam"]["abbrev"]
    away_team = game["awayTeam"]["abbrev"]
    context.preferred_team_hashtag = TEAM_DETAILS[team_abbreviation]["hashtag"]
    context.game_hashtag = f"#{away_team}vs{home_team}"

    # Get Game ID & Store It
    game_id = game["id"]
    context.game_id = game_id

    # Load Combined Rosters into Game Context
    context.combined_roster = rosters.load_combined_roster(game, team_abbreviation, season_id)

    # Determine preferred team role and extract associated details
    is_home_team = game["homeTeam"]["abbrev"] == team_abbreviation
    context.preferred_team_id = game["homeTeam"]["id"] if is_home_team else game["awayTeam"]["id"]
    context.preferred_homeaway = "home" if is_home_team else "away"

    # Extract team abbreviations
    preferred_team_abbreviation = game["homeTeam"]["abbrev"] if is_home_team else game["awayTeam"]["abbrev"]
    other_team_abbreviation = game["awayTeam"]["abbrev"] if is_home_team else game["homeTeam"]["abbrev"]

    # Use TEAM_DETAILS to get full team names
    context.preferred_team_name = TEAM_DETAILS[preferred_team_abbreviation]["full_name"]
    context.other_team_name = TEAM_DETAILS[other_team_abbreviation]["full_name"]

    # DEBUG Log the GameContext
    logging.debug(f"Full Game Context: {vars(context)}")

    # If we enter this function on the day of a game (before the game starts), gameState = "FUT"
    # We should send preview posts & then sleep until game time.
    if game["gameState"] == "FUT":
        logging.info("Handling future (FUT) game state.")

        # Generate and post the game time preview
        game_time_post = format_future_game_post(game, context)
        bsky_gametime = context.bluesky_client.post(game_time_post)
        logging.info(vars(bsky_gametime))
        logging.info("Posted game time preview.")

        # Fetch the team schedule and calculate the season series
        team_schedule = schedule.fetch_schedule(team_abbreviation, season_id)
        home_team = game["homeTeam"]["abbrev"]
        away_team = game["awayTeam"]["abbrev"]
        opposing_team = away_team if home_team == team_abbreviation else home_team

        # Generate and post the season series preview
        season_series_post = format_season_series_post(
            team_schedule, team_abbreviation, opposing_team, context
        )
        bsky_seasonseries = context.bluesky_client.post(
            season_series_post, reply_root=bsky_gametime, reply_post=bsky_gametime
        )
        logging.info("Posted season series preview.")

        # Sleep until the game starts
        start_time = game["startTimeUTC"]
        sleep_until_game_start(start_time)

        # POLL Until Game Goes Live
        while True:
            updated_game_state = schedule.fetch_game_state(game_id)  # Implement this API call
            if updated_game_state == "LIVE":
                logging.info("Game state is now LIVE. Transitioning to live parsing.")
                parse_live_game(game_id, context)
                return
            elif updated_game_state == "OFF":
                logging.warning("Game transitioned to OFF without going LIVE. Exiting.")
                return
            else:
                logging.info("Game still in FUT state. Sleeping for 30 seconds.")
                time.sleep(30)

    if game["gameState"] == "LIVE":
        logging.info("Game Context: %s", vars(context))
        logging.info("Handling live (LIVE) game state.")

        # Get Game-Time Rosters and Combine w/ Pre-Game Rosters
        game_time_rosters = rosters.load_game_rosters(context)
        final_combined_rosters = {**context.combined_roster, **game_time_rosters}
        context.combined_roster = final_combined_rosters

        # Parse Live Game Data
        parse_live_game(game_id, context)
        return

    # If we enter this function from a date in the future & gameState = "OFF"
    # Parse everything once & exit.
    # TODO: "trigger" end of game functions before exiting
    if game["gameState"] == "OFF":
        logging.info("Game state is OFF. Fetching play-by-play data and parsing it once.")

        # Extract game ID and build the play-by-play URL
        game_id = game["id"]
        play_by_play_url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play"
        logging.info(f"Fetching play-by-play data from {play_by_play_url}")

        # Fetch play-by-play data
        response = requests.get(play_by_play_url)
        if response.status_code == 200:
            play_by_play_data = response.json()
            logging.info("Play-by-play data successfully fetched. Parsing events.")
            events = play_by_play_data.get("plays", [])
            parse_play_by_play_with_names(events, context)
        else:
            logging.error(f"Failed to fetch play-by-play data. Status code: {response.status_code}")

        # Exit the function after parsing
        return


def handle_was_game_yesterday(game, yesterday, context):
    """
    Handle logic when there was a game yesterday.
    """
    logging.info(f"Game found yesterday ({yesterday}):")
    logging.info(
        f"  {game['awayTeam']['placeName']['default']} ({game['awayTeam']['abbrev']}) "
        f"@ {game['homeTeam']['placeName']['default']} ({game['homeTeam']['abbrev']})"
    )
    logging.info(f"  Venue: {game['venue']['default']}")
    logging.info(f"  Start Time (UTC): {game['startTimeUTC']}")
    context.bluesky_client.post("Game Summary Placeholder Message")
    # Log placeholder action for yesterday's game
    logging.debug("No play-by-play parsing performed for yesterday's game.")


def main():

    # fmt: off
    parser = argparse.ArgumentParser(description="Check NHL games for a specific date.")
    parser.add_argument("--config", type=str, default="config.yaml", help="Path to the configuration file (default: config.yaml).")
    parser.add_argument("--date", type=str, help="Date to check for a game (format: YYYY-MM-DD). Defaults to today's date.")
    parser.add_argument("--nosocial", action="store_true", help="Print messages instead of posting to socials.")
    parser.add_argument("--console", action="store_true", help="Write logs to console instead of a file.")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging.")
    parser.add_argument("--debugsocial", action="store_true", help="Uses 'debug' accounts to test socials.")
    args = parser.parse_args()
    # fmt: on

    # Load configuration
    config = load_config(args.config)

    # Setup logging & log startup info
    otherutils.setup_logging(config, console=args.console, debug=args.debug)
    otherutils.log_startup_info(args, config)

    team_name = config.get("default", {}).get("team_name", "New Jersey Devils")
    team_abbreviation = TEAM_ABBREVIATIONS.get(team_name)
    if not team_abbreviation:
        logging.error(f"Team abbreviation for '{team_name}' not found in mapping dictionary.")
        raise Exception(f"Team abbreviation for '{team_name}' not found in mapping dictionary.")

    # Initialize Bluesky Client
    bluesky_environment = "debug" if args.debugsocial else "prod"
    bluesky_account = config["bluesky"][bluesky_environment]["account"]
    bluesky_password = config["bluesky"][bluesky_environment]["password"]
    bluesky_client = BlueskyClient(account=bluesky_account, password=bluesky_password, nosocial=args.nosocial)
    bluesky_client.login()
    logging.info(f"Bluesky client initialized for environment: {bluesky_environment}.")

    # Create the GameContext
    context = GameContext(config=config, bluesky_client=bluesky_client, nosocial=args.nosocial)
    context.preferred_team_abbreviation = team_abbreviation

    # Fetch season ID
    season_id = schedule.fetch_season_id(team_abbreviation)
    context.season_id = season_id

    # Determine dates to check
    target_date = args.date if args.date else datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        # Fetch schedule
        team_schedule = schedule.fetch_schedule(team_abbreviation, season_id)
        logging.info(f"Fetched schedule for {team_name}.")

        # Check for a game on the target date
        game_today, _ = schedule.is_game_on_date(team_schedule, target_date)
        if game_today:
            handle_is_game_today(game_today, target_date, team_abbreviation, season_id, context)
            return

        # Check for a game yesterday
        game_yesterday, _ = schedule.is_game_on_date(team_schedule, yesterday)
        if game_yesterday:
            handle_was_game_yesterday(game_yesterday, yesterday, context)
            return

        # No games found
        logging.info(f"No games found for {team_name} on {target_date} or {yesterday}.")

    except Exception as e:
        logging.error(f"Error occurred: {e}", exc_info=True)


if __name__ == "__main__":
    main()
