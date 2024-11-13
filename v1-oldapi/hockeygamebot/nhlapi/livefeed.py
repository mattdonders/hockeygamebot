"""
Functions pertaining to the NHL schedule (via API).
"""

import logging
import random

from hockeygamebot.nhlapi import api


def get_livefeed(game_id):
    """Queries the NHL Live Feed API to determine if there is a game today.

    Args:
        game_id (int) - The unique identifier of the Game.

    Returns:
        response - JSON object of live feed results
    """
    randomnum = random.randint(1000, 9999)
    logging.info("Live Feed requested (random cache - %s)!", randomnum)
    api_endpoint = f"game/{game_id}/feed/live?{randomnum}"
    response = api.nhl_api(api_endpoint).json()
    return response
