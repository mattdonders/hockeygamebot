import os
import json
import requests


def load_roster(team_abbreviation: str, season_id: int):
    """
    Load the roster for the specified team and season.
    Check for local file before fetching from the API.
    """
    file_path = f"resources/{team_abbreviation}-roster.json"

    # Load from local file if it exists
    if os.path.exists(file_path):
        with open(file_path, "r") as file:
            print(f"Loaded roster for {team_abbreviation} from local file.")
            return json.load(file)

    # Otherwise, fetch from the API
    url = f"https://api-web.nhle.com/v1/roster/{team_abbreviation}/{season_id}"
    response = requests.get(url)
    if response.status_code == 200:
        roster = response.json()

        # Save to local file for future use
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w") as file:
            json.dump(roster, file)
            print(f"Saved roster for {team_abbreviation} to {file_path}.")

        return roster
    else:
        raise Exception(
            f"Failed to fetch roster for {team_abbreviation}. Status Code: {response.status_code}"
        )


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


def load_combined_roster(game, team_abbreviation, season_id):
    """
    Load and combine the rosters for both teams involved in the game.
    """
    opposing_team_abbreviation = get_opposing_team_abbreviation(game, team_abbreviation)

    primary_team_roster_data = load_roster(team_abbreviation, season_id)
    opposing_team_roster_data = load_roster(opposing_team_abbreviation, season_id)

    # Flatten and combine rosters
    combined_roster = {
        **flatten_roster(primary_team_roster_data),
        **flatten_roster(opposing_team_roster_data),
    }

    # print(combined_roster)

    return combined_roster
