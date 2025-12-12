import json
import logging
import os
from datetime import datetime, timedelta

from definitions import ROSTERS_DIR
from utils.http import get_json

logger = logging.getLogger(__name__)


def load_roster(team_abbreviation: str, season_id: int):
    """
    Load the roster for the specified team and season.
    Check for local file before fetching from the API.
    If the local file exists but is older than 24 hours, fetch a new roster.
    """
    file_path = ROSTERS_DIR / f"{team_abbreviation}-roster.json"

    # Check if the local file exists
    if os.path.exists(file_path):
        # Check file's last modification time
        last_modified_time = datetime.fromtimestamp(os.path.getmtime(file_path))
        current_time = datetime.now()
        time_difference = current_time - last_modified_time

        if time_difference <= timedelta(hours=24):
            # File is up-to-date, load it
            with open(file_path, "r") as file:
                logger.info(f"Loaded roster for {team_abbreviation} from local file.")
                return json.load(file)
        else:
            # File is outdated, log and update
            logger.info(
                f"Roster file for {team_abbreviation} is outdated (last updated: {last_modified_time}). "
                "Fetching a new roster from the API."
            )

    # Fetch from the API if the file doesn't exist or is outdated
    url = f"https://api-web.nhle.com/v1/roster/{team_abbreviation}/{season_id}"
    roster_data = get_json(url, key="roster")

    # Save to local file for future use
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w") as file:
        json.dump(roster_data, file)
        logger.info(f"Saved updated roster for {team_abbreviation} to {file_path}.")

    return roster_data


def load_game_rosters(context):
    logger.info("Getting rosterSpots from Game Center feed.")
    game_id = context.game_id
    url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play"
    try:
        pbp_data = get_json(url, key="roster")
    except Exception as e:
        logger.error(f"Failed to fetch roster for game {game_id}: {e}")
        return {}

    if pbp_data:
        roster_spots = pbp_data.get("rosterSpots")

        roster = {
            # Note: Assuming this remains valid for the data structure
            player["playerId"]: f"{player['firstName']['default']} {player['lastName']['default']}"
            for player in roster_spots
        }

        return roster

    return {}


def get_opposing_team_abbreviation(game, team_abbreviation):
    """
    Determine the opposing team's abbreviation based on the game data.
    """
    if game["awayTeam"]["abbrev"] == team_abbreviation:
        return game["homeTeam"]["abbrev"]
    return game["awayTeam"]["abbrev"]


def flatten_roster(roster_data):
    """
    Flatten roster data from 'forwards', 'defensemen', and 'goalies' sections into a single list.
    Extract the 'default' key for each player's firstName and lastName.
    """
    all_players = roster_data.get("forwards", []) + roster_data.get("defensemen", []) + roster_data.get("goalies", [])
    return {player["id"]: f"{player['firstName']['default']} {player['lastName']['default']}" for player in all_players}


def load_combined_roster(game, preferred_team, other_team, season_id):
    """
    Load and combine the rosters for both teams involved in the game.
    """
    preferred_team_roster_data = load_roster(preferred_team.abbreviation, season_id)
    other_team_roster_data = load_roster(other_team.abbreviation, season_id)

    # Flatten and combine rosters
    combined_roster = {
        **flatten_roster(preferred_team_roster_data),
        **flatten_roster(other_team_roster_data),
    }

    # print(combined_roster)

    return combined_roster


def get_preferred_roster(preferred_team, season_id):
    """
    Load the roster for the preferred team involved in the game.
    """
    preferred_team_roster_data = load_roster(preferred_team.abbreviation, season_id)

    # Flatten roster
    preferred_roster = flatten_roster(preferred_team_roster_data)

    return preferred_roster


def load_team_rosters(preferred_team, other_team, season_id):
    """
    Load rosters for both the preferred and other teams, and combine them.
    """
    pref_data = load_roster(preferred_team.abbreviation, season_id)
    other_data = load_roster(other_team.abbreviation, season_id)

    preferred_roster = flatten_roster(pref_data)
    other_roster = flatten_roster(other_data)

    combined_roster = {**preferred_roster, **other_roster}
    return preferred_roster, other_roster, combined_roster
