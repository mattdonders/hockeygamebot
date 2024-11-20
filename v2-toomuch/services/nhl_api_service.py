# services/nhl_api_service.py

from datetime import timedelta
import logging
from configuration import config
from models.game import Game
from services.nhl_api_client import NHLAPIClient
from utils import utils


class NHLAPIService:
    def __init__(self):
        self.api_client = NHLAPIClient()

    def get_next_game(self, team_abbr):
        """Finds the next game for the given team abbreviation where gameState is 'FUT'."""
        data = self.api_client.get_club_schedule_season_now(team_abbr)
        games = data.get("games", [])
        for game in games:
            if game.get("gameState") == "FUT":
                return game
        return None

    def get_last_game(self, team_abbr):
        """Finds the last game for the given team abbreviation where gameState is 'FINAL'."""
        data = self.api_client.get_club_schedule_season_now(team_abbr)
        games = data.get("games", [])
        for game in reversed(games):
            if game.get("gameState") == "FINAL":
                return game
        return None

    def is_game_today(self, team_abbr, date):
        logging.info("Checking if there is a game for date: %s", date)
        next_game = self.get_next_game(team_abbr)
        if next_game:
            start_time_utc = next_game.get("gameDate")
            start_time_eastern = utils.convert_time_to_eastern(start_time_utc)
            days_diff = (start_time_eastern.date() - date.date()).days
            print(days_diff)
            if days_diff == 0:
                return True, next_game
        return False, None

    def was_game_yesterday(self, team_id, date):
        # Check if there was a game yesterday
        yesterday = date - timedelta(days=1)
        date_str = yesterday.strftime("%Y-%m-%d")
        schedule = self.api_client.get_schedule(team_id, date_str, date_str)
        games = schedule.get("dates", [])
        if games:
            game_info = games[0]["games"][0]
            return True, game_info
        return False, None

    def get_team_full_names(self):
        """Creates a mapping of team IDs to full team names and abbreviations."""
        data = self.api_client.get_team_data()
        team_mapping = {}
        teams = data.get("data", [])
        for team in teams:
            team_id = team.get("id")
            full_name = team.get("fullName")
            abbreviation = team.get("triCode")
            team_mapping[team_id] = {
                "full_name": full_name,
                "abbreviation": abbreviation,
                "team_id": team_id,
            }
        return team_mapping

    def create_game_from_info(self, game_info):
        game_id = game_info.get("id")
        start_time_utc = game_info.get("startTimeUTC")
        game = Game(game_id=game_id, start_time_utc=start_time_utc)
        logging.info(vars(game))

        # Initialize additional attributes
        team_names = self.get_team_full_names()
        home_team_id = game_info.get("homeTeam", {}).get("id")
        game.home_team_name = team_names[home_team_id].get("full_name")
        away_team_id = game_info.get("awayTeam", {}).get("id")
        game.away_team_name = team_names[away_team_id].get("full_name")

        # You can also initialize the initial game state
        status = game_info.get("status", {})
        game.game_state = game_info.get("gameState")

        # Shove Game Info into Game Object
        game.game_info = game_info

        game.game_hashtag = config["default"].get("team_hashtag")

        # Calculate the initial game time countdown
        game.calculate_time_until_game_start()

        return game

    def get_us_broadcast_networks(self, game_data):
        """Extracts US broadcast networks from the game data."""
        tv_broadcasts = game_data.get("tvBroadcasts", [])
        us_networks = []
        for broadcast in tv_broadcasts:
            if broadcast.get("countryCode") == "US":
                us_networks.append(broadcast.get("network"))
        return us_networks
