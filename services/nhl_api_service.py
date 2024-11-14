# services/nhl_api_service.py

from services.nhl_api_client import NHLAPIClient


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

    def get_team_full_names(self):
        """Creates a mapping of team IDs to full team names and abbreviations."""
        data = self.api_client.get_team_data()
        team_mapping = {}
        teams = data.get("data", [])
        for team in teams:
            team_id = team.get("id")
            full_name = team.get("fullName")
            abbreviation = team.get("triCode")
            team_mapping[team_id] = {"full_name": full_name, "abbreviation": abbreviation}
        return team_mapping

    def get_us_broadcast_networks(self, game_data):
        """Extracts US broadcast networks from the game data."""
        tv_broadcasts = game_data.get("tvBroadcasts", [])
        us_networks = []
        for broadcast in tv_broadcasts:
            if broadcast.get("countryCode") == "US":
                us_networks.append(broadcast.get("network"))
        return us_networks
