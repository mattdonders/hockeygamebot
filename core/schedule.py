import requests


def fetch_season_id(team_abbreviation: str):
    """
    Fetch the current season ID from the schedule API.
    """
    url = f"https://api-web.nhle.com/v1/club-schedule-season/{team_abbreviation}/now"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data.get("currentSeason")
    else:
        raise Exception(f"Failed to fetch season ID. Status Code: {response.status_code}")


def fetch_schedule(team_abbreviation: str):
    """
    Fetch the schedule for the specified team.
    """
    url = f"https://api-web.nhle.com/v1/club-schedule-season/{team_abbreviation}/now"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Failed to fetch schedule. Status Code: {response.status_code}")


def is_game_on_date(schedule: dict, target_date: str):
    """
    Check if there is a game on the specified date and return the game details and ID.
    """
    games = schedule.get("games", [])
    for game in games:
        if game["gameDate"] == target_date:
            game_id = game.get("id")
            print(f"Play-by-Play URL: https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play")
            return game, game_id
    return None, None
