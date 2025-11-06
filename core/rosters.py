import json
import logging
import os
from datetime import datetime, timedelta

import requests


def load_roster(team_abbreviation: str, season_id: int):
    """
    Load the roster for the specified team and season.
    Check for local file before fetching from the API.
    If the local file exists but is older than 24 hours, fetch a new roster.
    """
    file_path = f"resources/{team_abbreviation}-roster.json"

    # Check if the local file exists
    if os.path.exists(file_path):
        # Check file's last modification time
        last_modified_time = datetime.fromtimestamp(os.path.getmtime(file_path))
        current_time = datetime.now()
        time_difference = current_time - last_modified_time

        if time_difference <= timedelta(hours=24):
            # File is up-to-date, load it
            with open(file_path) as file:
                logging.info(f"Loaded roster for {team_abbreviation} from local file.")
                return json.load(file)
        else:
            # File is outdated, log and update
            logging.info(
                f"Roster file for {team_abbreviation} is outdated (last updated: {last_modified_time}). "
                "Fetching a new roster from the API."
            )

    # Fetch from the API if the file doesn't exist or is outdated
    url = f"https://api-web.nhle.com/v1/roster/{team_abbreviation}/{season_id}"
    response = requests.get(url)
    if response.status_code == 200:
        roster = response.json()

        # Save to local file for future use
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w") as file:
            json.dump(roster, file)
            logging.info(f"Saved updated roster for {team_abbreviation} to {file_path}.")

        return roster
    error_message = f"Failed to fetch roster for {team_abbreviation}. Status Code: {response.status_code}"
    logging.error(error_message)
    raise Exception(error_message)


def load_game_rosters(context):
    logging.info("Getting rosterSpots from Game Center feed.")
    game_id = context.game_id
    url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play"
    response = requests.get(url)
    if response.status_code == 200:
        pbp_data = response.json()
        roster_spots = pbp_data.get("rosterSpots")

        roster = {
            player["playerId"]: f"{player['firstName']['default']} {player['lastName']['default']}"
            for player in roster_spots
        }

        return roster


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
    all_players = (
        roster_data.get("forwards", []) + roster_data.get("defensemen", []) + roster_data.get("goalies", [])
    )
    return {
        player["id"]: f"{player['firstName']['default']} {player['lastName']['default']}"
        for player in all_players
    }


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
