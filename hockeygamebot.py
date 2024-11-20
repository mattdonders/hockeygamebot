import argparse
from datetime import datetime, timedelta

import requests

import core.rosters as rosters
import core.schedule as schedule
from core.play_by_play import parse_play_by_play_with_names
from socials.bluesky import BlueskyClient
from utils.config import load_config
from utils.team_abbreviations import TEAM_ABBREVIATIONS


class GameContext:
    """
    Centralized context for game-related data and shared resources.
    """

    def __init__(self, bluesky_client):
        self.bluesky_client = bluesky_client
        self.preferred_team_name = None
        self.other_team_name = None
        self.preferred_team_id = None
        self.preferred_homeaway = None
        self.combined_roster = None


def handle_is_game_today(game, target_date, team_abbreviation, season_id, context):
    """
    Handle logic when there is a game today.
    """
    print(f"Game found today ({target_date}):")
    print(
        f"  {game['awayTeam']['placeName']['default']} ({game['awayTeam']['abbrev']}) "
        f"@ {game['homeTeam']['placeName']['default']} ({game['homeTeam']['abbrev']})"
    )
    print(f"  Venue: {game['venue']['default']}")
    print(f"  Start Time (UTC): {game['startTimeUTC']}")

    # Determine preferred team role
    context.preferred_team_id = (
        game["homeTeam"]["id"] if game["homeTeam"]["abbrev"] == team_abbreviation else game["awayTeam"]["id"]
    )
    context.preferred_homeaway = "home" if game["homeTeam"]["abbrev"] == team_abbreviation else "away"

    # Extract team names
    context.preferred_team_name = (
        game["homeTeam"]["placeName"]["default"]
        if context.preferred_homeaway == "home"
        else game["awayTeam"]["placeName"]["default"]
    )
    context.other_team_name = (
        game["awayTeam"]["placeName"]["default"]
        if context.preferred_homeaway == "home"
        else game["homeTeam"]["placeName"]["default"]
    )

    # Load combined roster for both teams
    context.combined_roster = rosters.load_combined_roster(game, team_abbreviation, season_id)

    # Parse play-by-play only for today's game if game_state is OFF
    if game["gameState"] == "OFF":
        game_id = game["id"]
        play_by_play_url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play"
        response = requests.get(play_by_play_url)
        if response.status_code == 200:
            play_by_play_data = response.json()
            parse_play_by_play_with_names(play_by_play_data, context)


def handle_was_game_yesterday(game, yesterday, context):
    """
    Handle logic when there was a game yesterday.
    """
    print(f"Game found yesterday ({yesterday}):")
    print(
        f"  {game['awayTeam']['placeName']['default']} ({game['awayTeam']['abbrev']}) "
        f"@ {game['homeTeam']['placeName']['default']} ({game['homeTeam']['abbrev']})"
    )
    print(f"  Venue: {game['venue']['default']}")
    print(f"  Start Time (UTC): {game['startTimeUTC']}")
    # Example of using the Bluesky client in this handler
    context.bluesky_client.post_message("Game Summary Placeholder Message")
    # Do not parse play-by-play for yesterday's game


def main():
    parser = argparse.ArgumentParser(description="Check NHL games for a specific date.")
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Path to the configuration file (default: config.yaml).",
    )
    parser.add_argument(
        "--date", type=str, help="Date to check for a game (format: YYYY-MM-DD). Defaults to today's date."
    )
    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)
    team_name = config.get("default", {}).get("team_name", "New Jersey Devils")
    team_abbreviation = TEAM_ABBREVIATIONS.get(team_name)
    if not team_abbreviation:
        raise Exception(f"Team abbreviation for '{team_name}' not found in mapping dictionary.")

    # Initialize Bluesky Client
    bluesky_environment = "debug"
    bluesky_account = config["bluesky"][bluesky_environment]["account"]
    bluesky_password = config["bluesky"][bluesky_environment]["password"]
    bluesky_client = BlueskyClient(bluesky_account, bluesky_password)
    bluesky_client.login()

    # Create the GameContext
    context = GameContext(bluesky_client)

    # Fetch season ID
    season_id = schedule.fetch_season_id(team_abbreviation)

    # Determine dates to check
    target_date = args.date if args.date else datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        # Fetch schedule
        team_schedule = schedule.fetch_schedule(team_abbreviation)

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
        print(f"No games found for {team_name} on {target_date} or {yesterday}.")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
