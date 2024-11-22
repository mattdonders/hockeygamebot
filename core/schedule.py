import requests
import logging


def fetch_season_id(team_abbreviation: str):
    """
    Fetch the current season ID from the schedule API.
    """
    url = f"https://api-web.nhle.com/v1/club-schedule-season/{team_abbreviation}/now"
    logging.info(f"Fetching season ID from URL: {url}")

    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        season_id = data.get("currentSeason")
        logging.info(f"Fetched current season ID: {season_id}")
        return season_id
    else:
        logging.error(f"Failed to fetch season ID. Status Code: {response.status_code}")
        raise Exception(f"Failed to fetch season ID. Status Code: {response.status_code}")


def fetch_schedule(team_abbreviation: str, season_id: str):
    """
    Fetch the schedule for the specified team and season.
    """
    url = f"https://api-web.nhle.com/v1/club-schedule-season/{team_abbreviation}/{season_id}"
    logging.debug(f"Fetching schedule from URL: {url}")
    response = requests.get(url)
    if response.status_code == 200:
        logging.info(f"Fetched schedule for team: {team_abbreviation}, season: {season_id}")
        return response.json()
    else:
        raise Exception(f"Failed to fetch schedule. Status Code: {response.status_code}")


def fetch_playbyplay(game_id: str):
    """
    Fetch the play by play for the current game.
    """

    url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play"
    logging.info(f"Fetching play-by-play data from {url}")

    # Fetch play-by-play data
    response = requests.get(url)
    if response.status_code == 200:
        play_by_play_data = response.json()
        return play_by_play_data
    else:
        raise Exception(f"Failed to fetch play by play data. Status Code: {response.status_code}")


def is_game_on_date(schedule: dict, target_date: str):
    """
    Check if there is a game on the specified date and return the game details and ID.
    """
    logging.debug(f"Checking for games on date: {target_date}")
    games = schedule.get("games", [])
    for game in games:
        if game["gameDate"] == target_date:
            game_id = game.get("id")
            logging.info(f"Game found on {target_date}: Game ID {game_id}")
            logging.info(f"Play-by-Play URL: https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play")
            return game, game_id

    logging.info(f"No game found on {target_date}.")
    return None, None


def fetch_game_state(game_id):
    url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play"
    response = requests.get(url)
    if response.status_code == 200:
        game_data = response.json()
        return game_data.get("gameState", "UNKNOWN")
    else:
        logging.error(
            f"Failed to fetch game state for game ID {game_id}. Status code: {response.status_code}"
        )
        return "ERROR"
