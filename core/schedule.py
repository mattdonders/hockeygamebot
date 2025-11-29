import logging

import requests

from utils.http import get_json
from utils.retry import retry

logger = logging.getLogger(__name__)
# Module-level monitor for tracking API calls
_monitor = None


def set_monitor(monitor):
    """Set the module-level monitor for API call tracking."""
    global _monitor
    _monitor = monitor


def _make_api_call(url: str, timeout: int = 10):
    """
    Make an API call with optional monitoring.

    Args:
        url: The URL to fetch
        timeout: Request timeout in seconds

    Returns:
        Response object
    """
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()

        # Track successful API call
        if _monitor:
            _monitor.record_api_call(success=True)

        return response
    except Exception:
        # Track failed API call
        if _monitor:
            _monitor.record_api_call(success=False)
        raise


def _make_api_json(url: str, key: str = "default", timeout: int = 10):
    """
    Make a JSON API call through the robust HTTP client, with monitoring hooks.

    Args:
        url: URL to fetch
        key: limiter key for rate control (e.g. 'play_by_play')
        timeout: per-request timeout in seconds
    Returns:
        Parsed JSON dict
    """
    try:
        data = get_json(url, key=key, timeout=timeout)
        if _monitor:
            _monitor.record_api_call(success=True)
        return data
    except Exception:
        if _monitor:
            _monitor.record_api_call(success=False)
        raise


@retry(max_attempts=3, delay=2.0, exceptions=(requests.RequestException,))
def fetch_season_id(team_abbreviation: str):
    """
    Fetch the current season ID from the schedule API.
    """
    url = f"https://api-web.nhle.com/v1/club-schedule-season/{team_abbreviation}/now"
    logger.info(f"Fetching season ID from URL: {url}")

    response = _make_api_call(url, timeout=10)

    data = response.json()
    season_id = data.get("currentSeason")
    logger.info(f"Fetched current season ID: {season_id}")
    return season_id


@retry(max_attempts=3, delay=2.0, exceptions=(requests.RequestException,))
def fetch_schedule(team_abbreviation: str, season_id: str):
    """
    Fetch the schedule for the specified team and season.
    """
    url = f"https://api-web.nhle.com/v1/club-schedule-season/{team_abbreviation}/{season_id}"
    logger.debug(f"Fetching schedule from URL: {url}")

    response = _make_api_call(url, timeout=10)

    logger.info(f"Fetched schedule for team: {team_abbreviation}, season: {season_id}")
    return response.json()


def fetch_playbyplay(game_id: str):
    """
    Fetch the play-by-play for the current game with built-in rate limiting
    and 429/5xx resilience.
    """
    url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play"
    logger.info("Fetching play-by-play data from %s", url)

    # use key="play_by_play" so the limiter applies proper pacing
    return _make_api_json(url, key="play_by_play", timeout=10)


@retry(max_attempts=3, delay=2.0, exceptions=(requests.RequestException,))
def fetch_boxscore(game_id: str):
    """
    Fetch the boxscore for the given game from the new NHL API.

    This is used for things like determining the winning goalie and
    whether they earned a shutout.
    """
    url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/boxscore"
    logger.info("Fetching boxscore data from %s", url)

    # use key="boxscore" so the limiter can treat this separately
    return _make_api_json(url, key="boxscore", timeout=10)


@retry(max_attempts=3, delay=2.0, exceptions=(requests.RequestException,))
def fetch_landing(game_id: str):
    """
    Fetch the landing page data for the current game.
    """
    url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/landing"
    logger.info(f"Fetching GameCenter landing page data from {url}")

    response = _make_api_call(url, timeout=10)

    return response.json()


@retry(max_attempts=3, delay=2.0, exceptions=(requests.RequestException,))
def fetch_stories(game_id: str):
    """
    Fetch the post-game stories data (used for video highlights the next day).
    """
    url = f"https://forge-dapi.d3.nhle.com/v2/content/en-us/stories?tags.slug=gameid-{game_id}&tags.slug=game-recap&context.slug=nhl"
    logger.info(f"Fetching Stories data from {url}")

    response = _make_api_call(url, timeout=10)

    return response.json()


@retry(max_attempts=3, delay=2.0, exceptions=(requests.RequestException,))
def fetch_rightrail(game_id: str):
    """
    Fetch the right rail for the current game from GameCenter.
    This is useful because it has quick access to team stats.
    """
    url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/right-rail"
    logger.info(f"Fetching GameCenter right-rail page data from {url}")

    response = _make_api_call(url, timeout=10)

    return response.json()


def is_game_on_date(schedule: dict, target_date: str):
    """
    Check if there is a game on the specified date and return the game details and ID.
    """
    logger.info(f"Checking for games on (target) date: {target_date}")
    games = schedule.get("games", [])

    for game in games:
        if game["gameDate"] == target_date:
            game_id = game.get("id")
            logger.info(f"Game found on {target_date} / Game ID {game_id}")
            logger.info(f"Play-by-Play URL: https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play")
            return game, game_id

    logger.info(f"No game found on {target_date}.")
    return None, None


def fetch_next_game(schedule: dict):
    """
    Once a game is over, we can use this function to get the next game in 'FUT' state.
    """
    games = schedule.get("games", [])

    for game in games:
        if game["gameState"] == "FUT":
            game_id = game.get("id")
            game_date = game.get("gameDate")
            logger.info(f"Next game found on {game_date} / Game ID {game_id}")
            return game

    # TODO - implement logic for playoffs / next season / etc
    logger.info("No next game found in this season.")
    return None, None


def fetch_game_state(game_id: str):
    """
    Fetch the current game state for a specific game.

    Returns:
        str: Game state (e.g., 'LIVE', 'FUT', 'FINAL', 'OFF') or 'UNKNOWN' if not found
    """
    url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play"
    game_data = _make_api_json(url, key="play_by_play", timeout=10)
    return game_data.get("gameState", "UNKNOWN")


def fetch_clock(game_id: str):
    """
    Fetch the current game clock data for a specific game.

    Returns:
        dict: Clock data including time remaining, period, intermission status, etc.
    """
    url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play"
    game_data = _make_api_json(url, key="play_by_play", timeout=10)
    return game_data.get("clock", {})
