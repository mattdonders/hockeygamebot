"""
Functions pertaining to the NHL schedule (via API).
"""

import logging
import random

from hockeygamebot.nhlapi import api


def get_content_feed(game_id, milestones=False):
    """Queries the NHL Content Feed API to get media items (photos, videos, etc)

    Args:
        game_id (int) - The unique identifier of the Game.
        milestones (bool) - Returns only the milestones section

    Returns:
        response - JSON object of live feed results
    """

    logging.info("Content Feed requested (milestones: %s)!", milestones)
    api_endpoint = f"game/{game_id}/content"
    response = api.nhl_api(api_endpoint).json()

    # Calculate milestones if argument is True
    # response = response if not milestones else response["media"]["milestones"]["items"]
    response = response if not milestones else response["highlights"]["scoreboard"]["items"]
    return response


def search_milestones_for_id(milestones, event_id):
    """Searches the milestones list for an item that matches the statsEventID passed in.

    Args:
        event_id (int): NHL Game Event ID

    Returns:
        event_exists (bool): Does the event exist
        highlight (dict): Dictionary of the highlight itself
        nhl_video_url (string): URL pointing to the NHL Video Highlight of the event
    """
    # If mile
    if not milestones:
        return False, None, None

    str_event_id = str(event_id)
    stats_event_dict = {"type": "statsEventId", "value": str_event_id, "displayName": str_event_id}

    # Iterate over "Milestones" & Check for Our Event ID
    # When Found, Break out of the Loop & Continue Processing
    event = None

    for i in milestones:
        has_our_event = [x for x in i["keywords"] if x == stats_event_dict]
        if has_our_event:
            event = i
            break

    # event = next(filter(lambda obj: obj.get("statsEventId") == str(event_id), milestones), None)

    if not event:
        return False, None, None

    try:
        # highlight = event.get("highlight")
        highlight = event
        video_id = highlight.get("id")

        if not video_id:
            logging.warning(
                "The highlight for %s exists, but there is no Video ID - try again next loop.",
                event_id,
            )
            return False, None, None

        nhl_video_url = f"https://www.nhl.com/video/c-{video_id}?tcid=tw_video_content_id"

        playbacks = highlight.get("playbacks")
        nhl_mp4_url = next(x["url"] for x in playbacks if x["name"] == "FLASH_1800K_896x504")
        return True, highlight, nhl_video_url, nhl_mp4_url
    except AttributeError:
        logging.error("Error getting video ID and / or NHL Video URL.")
        return False, None, None


def get_game_recap(content_feed):
    """Searches the content feed for the game recap.

    Args:
        content_feed (dict): NHL Content Feed

    Returns:
        recap (dict): Dictionary of the full recap event
        nhl_video_url (string): URL pointing to the NHL Video Recap
    """

    epg = content_feed["media"]["epg"]
    recap = next(x for x in epg if x["title"] == "Recap")

    video_id = recap["items"][0]["id"]
    nhl_video_url = f"https://www.nhl.com/video/c-{video_id}?tcid=tw_video_content_id"

    return recap, nhl_video_url


def get_condensed_game(content_feed):
    """Searches the content feed for the condensed game / extended highlights.

    Args:
        content_feed (dict): NHL Content Feed

    Returns:
        recap (dict): Dictionary of the full recap event
        nhl_video_url (string): URL pointing to the NHL Video Condensed Game
    """

    epg = content_feed["media"]["epg"]
    condensed = next(x for x in epg if x["title"] == "Extended Highlights")

    video_id = condensed["items"][0]["id"]
    nhl_video_url = f"https://www.nhl.com/video/c-{video_id}?tcid=tw_video_content_id"

    return condensed, nhl_video_url
