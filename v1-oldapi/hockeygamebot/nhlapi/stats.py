"""
This module contains the any stats related functions from the NHL API for players or teams.
"""

import logging
import requests

import pandas as pd

from hockeygamebot.helpers import utils

# Load configuration file in global scope
urls = utils.load_urls()


def get_player_career_stats(player_id):
    """Returns the career stats of an NHL player by their given player ID.

    Args:
        player_id: A 7-digit NHL player id.

    Returns:
        career_stats: A dictionary of a players career stats
    """
    try:
        PERSON_API = "{api}/people/{id}?expand=person.stats&stats=careerRegularSeason".format(
            api=urls["endpoints"]["nhl_endpoint"], id=player_id
        )
        response = requests.get(PERSON_API).json()
        person = response.get("people")[0]
        position = person.get("primaryPosition")["code"]
        stats = person.get("stats")[0].get("splits")[0].get("stat")
        return stats
    except IndexError as e:
        logging.error("For some reason, %s doesn't have regular season stats. (%s)", player_id, e)
        return {"assists": 0, "points": 0, "goals": 0}


def get_goalie_career_stats(player_id):
    """The NHL API doesn't contain points stats for goalie, use Natural Stat Trick for stat retrieval."""

    try:
        NST_BASE = urls["endpoints"]["nst"]
        GOALIE_NST_API = f"{NST_BASE}/playerreport.php?stype=2&sit=all&playerid={player_id}"
        response = requests.get(GOALIE_NST_API)

        df = pd.read_html(response.content)[0]
        df = df.append(df.sum(numeric_only=True), ignore_index=True)
    except:
        pass
