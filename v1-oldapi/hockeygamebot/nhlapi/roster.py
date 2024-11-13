"""
Functions pertaining to the NHL Roster (via API).
"""
import logging

from hockeygamebot.nhlapi import livefeed, api
from hockeygamebot.helpers import arguments, utils
from hockeygamebot.models.sessions import SessionFactory


def gameday_roster_update(game):
    """ Gets the gameday rosters from the live feed endpoint.
        This is needed because in some instances a player is not included
        on the /teams/{id}/roster page for some reason.

    Args:
        game: Current Game object

    Returns:
        None
    """

    args = arguments.get_arguments()

    home_team = game.home_team
    away_team = game.away_team

    logging.info("Getting gameday rosters from Live Feed endpoint.")

    try:
        gameday_roster = livefeed.get_livefeed(game.game_id)
        all_players = gameday_roster.get("gameData").get("players")
        for player_id, player in all_players.items():
            try:
                team = player.get("currentTeam").get("name")
                if team == home_team.team_name:
                    home_team.gameday_roster[player_id] = player
                else:
                    away_team.gameday_roster[player_id] = player
            except Exception as e:
                logging.error("%s doesn't have a team - skipping.", player["fullName"])
    except Exception as e:
        logging.error("Unable to get all players.")
        logging.error(e)


def player_attr_by_id(roster, player_id, attribute):
    """Returns the attribute of a player given a roaster and a player_id.

    Args:
        roster (dict): Team roster (returned from API)
        player_id (str): Player unique identifier (IDXXXXXXX)
        attribute (str): Attribute from roster dictionary.

    Returns:
        string: Attribute of the person requested.
    """
    new_player_id = player_id.replace("ID", "")
    for roster_item in roster:
        person_id = str(roster_item["person"]["id"])
        person_attr = roster_item["person"][attribute]
        if person_id == new_player_id:
            return person_attr


def nonroster_player_attr_by_id(player_id, attribute):
    """Returns the attribute of a non-roster player via the NHL People API.

    Args:
        player_id (str): Player unique identifier (IDXXXXXXX)
        attribute (str): Attribute from roster dictionary.

    Returns:
        string: Attribute of the person requested.
    """
    api_player_url = f"/people/{player_id}"
    api_player = api.nhl_api(api_player_url).json()
    player_attr = api_player["people"][0][attribute]
    return player_attr
