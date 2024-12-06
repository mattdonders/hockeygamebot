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


def fetch_landing(game_id: str):
    """
    Fetch the play by play for the current game.
    """

    url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/landing"
    logging.info(f"Fetching GameCenter landing page data from {url}")

    # Fetch play-by-play data
    response = requests.get(url)
    if response.status_code == 200:
        landing_data = response.json()
        return landing_data
    else:
        raise Exception(f"Failed to fetch GameCenter landing data. Status Code: {response.status_code}")


def fetch_stories(game_id: str):
    """
    Fetch the post-game stories data (used for video highlights the next day.)
    """

    url = f"https://forge-dapi.d3.nhle.com/v2/content/en-us/stories?tags.slug=gameid-{game_id}&tags.slug=game-recap&context.slug=nhl"
    logging.info(f"Fetching Stories data data from {url}")

    # Fetch play-by-play data
    response = requests.get(url)
    if response.status_code == 200:
        landing_data = response.json()
        return landing_data
    else:
        raise Exception(f"Failed to fetch Stories Page data. Status Code: {response.status_code}")


def fetch_rightrail(game_id: str):
    """
    Fetch the right rail for the current game from GameCenter.
    This is useful because it has quick access to team stats.
    """

    url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/right-rail"
    logging.info(f"Fetching GameCenter right-rail page data from {url}")

    # Fetch play-by-play data
    response = requests.get(url)
    if response.status_code == 200:
        right_rail_data = response.json()
        return right_rail_data
    else:
        raise Exception(f"Failed to fetch GameCenter right-rail data. Status Code: {response.status_code}")


def is_game_on_date(schedule: dict, target_date: str):
    """
    Check if there is a game on the specified date and return the game details and ID.
    """
    logging.info(f"Checking for games on (target) date: {target_date}")
    games = schedule.get("games", [])
    for game in games:
        if game["gameDate"] == target_date:
            game_id = game.get("id")
            logging.info(f"Game found on {target_date} /  Game ID {game_id}")
            logging.info(f"Play-by-Play URL: https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play")
            return game, game_id

    logging.info(f"No game found on {target_date}.")
    return None, None


def fetch_next_game(schedule: dict):
    """Once a game is over, we can use this function to get the next game in 'FUT' state."""
    games = schedule.get("games", [])
    for game in games:
        if game["gameState"] == "FUT":
            game_id = game.get("id")
            game_date = game.get("gameDate")
            logging.info(f"Next game found on {game_date} / Game ID {game_id}")
            return game

    # TODO - implement logic for playoffs / next season / etc
    logging.info(f"No next game found on this season.")
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


def fetch_clock(game_id):
    url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play"
    response = requests.get(url)
    if response.status_code == 200:
        game_data = response.json()
        clock_data = game_data.get("clock", {})
        return clock_data
    else:
        logging.error(
            f"Failed to fetch game state for game ID {game_id}. Status code: {response.status_code}"
        )
        return "ERROR"
