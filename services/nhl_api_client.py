# services/nhl_api_client.py

import requests


class NHLAPIClient:
    API_WEB_BASEURL = "https://api-web.nhle.com"
    NHLE_BASEURL = "https://api.nhle.com"

    def __init__(self):
        self.session = requests.Session()

    def get_club_schedule_season_now(self, team_abbr):
        """Fetches the club schedule season data for the given team abbreviation."""
        endpoint = f"/v1/club-schedule-season/{team_abbr}/now"
        url = self.API_WEB_BASEURL + endpoint

        response = self.session.get(url)
        response.raise_for_status()
        data = response.json()
        return data

    def get_team_data(self):
        """Fetches team data from the NHL API."""
        url = f"{self.NHLE_BASEURL}/stats/rest/en/team"
        response = self.session.get(url)
        response.raise_for_status()
        data = response.json()
        return data
