# fmt: off
TEAM_DETAILS = {
    "NJD": {"full_name": "New Jersey Devils", "hashtag": "#NJDevils", "timezone": "America/New_York", "team_id": 1},
    "CAR": {"full_name": "Carolina Hurricanes", "hashtag": "#LetsGoCanes", "timezone": "America/New_York", "team_id": 12},
    "WSH": {"full_name": "Washington Capitals", "hashtag": "#ALLCAPS", "timezone": "America/New_York", "team_id": 15},
    "NYI": {"full_name": "New York Islanders", "hashtag": "#Isles", "timezone": "America/New_York", "team_id": 2},
    "TBL": {"full_name": "Tampa Bay Lightning", "hashtag": "#GoBolts", "timezone": "America/New_York", "team_id": 14},
    "NYR": {"full_name": "New York Rangers", "hashtag": "#NYR", "timezone": "America/New_York", "team_id": 3},
    "PHI": {"full_name": "Philadelphia Flyers", "hashtag": "#FueledByPhilly", "timezone": "America/New_York", "team_id": 4},
    "PIT": {"full_name": "Pittsburgh Penguins", "hashtag": "#LetsGoPens", "timezone": "America/New_York", "team_id": 5},
    "BOS": {"full_name": "Boston Bruins", "hashtag": "#NHLBruins", "timezone": "America/New_York", "team_id": 6},
    "BUF": {"full_name": "Buffalo Sabres", "hashtag": "#LetsGoBuffalo", "timezone": "America/New_York", "team_id": 7},
    "TOR": {"full_name": "Toronto Maple Leafs", "hashtag": "#LeafsForever", "timezone": "America/Toronto", "team_id": 10},
    "MTL": {"full_name": "Montreal Canadiens", "hashtag": "#GoHabsGo", "timezone": "America/Toronto", "team_id": 8},
    "OTT": {"full_name": "Ottawa Senators", "hashtag": "#GoSensGo", "timezone": "America/Toronto", "team_id": 9},
    "FLA": {"full_name": "Florida Panthers", "hashtag": "#TimeToHunt", "timezone": "America/New_York", "team_id": 13},
    "DET": {"full_name": "Detroit Red Wings", "hashtag": "#LGRW", "timezone": "America/Detroit", "team_id": 17},
    "CBJ": {"full_name": "Columbus Blue Jackets", "hashtag": "#CBJ", "timezone": "America/New_York", "team_id": 29},
    "CHI": {"full_name": "Chicago Blackhawks", "hashtag": "#Blackhawks", "timezone": "America/Chicago", "team_id": 16},
    "STL": {"full_name": "St. Louis Blues", "hashtag": "#stlblues", "timezone": "America/Chicago", "team_id": 19},
    "NSH": {"full_name": "Nashville Predators", "hashtag": "#Preds", "timezone": "America/Chicago", "team_id": 18},
    "DAL": {"full_name": "Dallas Stars", "hashtag": "#TexasHockey", "timezone": "America/Chicago", "team_id": 25},
    "COL": {"full_name": "Colorado Avalanche", "hashtag": "#GoAvsGo", "timezone": "America/Denver", "team_id": 21},
    "WPG": {"full_name": "Winnipeg Jets", "hashtag": "#GoJetsGo", "timezone": "America/Winnipeg", "team_id": 52},
    "MIN": {"full_name": "Minnesota Wild", "hashtag": "#mnwild", "timezone": "America/Chicago", "team_id": 30},
    "VAN": {"full_name": "Vancouver Canucks", "hashtag": "#Canucks", "timezone": "America/Vancouver", "team_id": 23},
    "EDM": {"full_name": "Edmonton Oilers", "hashtag": "#LetsGoOilers", "timezone": "America/Edmonton", "team_id": 22},
    "CGY": {"full_name": "Calgary Flames", "hashtag": "#Flames", "timezone": "America/Edmonton", "team_id": 20},
    "LAK": {"full_name": "Los Angeles Kings", "hashtag": "#GoKingsGo", "timezone": "America/Los_Angeles", "team_id": 26},
    "ANA": {"full_name": "Anaheim Ducks", "hashtag": "#FlyTogether", "timezone": "America/Los_Angeles", "team_id": 24},
    "SJS": {"full_name": "San Jose Sharks", "hashtag": "#SJSharks", "timezone": "America/Los_Angeles", "team_id": 28},
    "SEA": {"full_name": "Seattle Kraken", "hashtag": "#SeaKraken", "timezone": "America/Los_Angeles", "team_id": 55},
    "VGK": {"full_name": "Vegas Golden Knights", "hashtag": "#VegasBorn", "timezone": "America/Los_Angeles", "team_id": 54},
}

# fmt: on


def get_team_name_by_id(team_id):
    """
    Get the team name based on the team_id.

    Args:
        team_id (int): The NHL team ID.

    Returns:
        str: The full name of the team, or None if not found.
    """
    for team_abbr, details in TEAM_DETAILS.items():
        if details.get("team_id") == team_id:
            return details.get("full_name")
    return None
