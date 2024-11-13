"""
This module contains functions related to gathering video links
from YouTube (useful for recap or condensed game links).
"""

from youtube_search import YoutubeSearch


def search_youtube(search_term, num_results):
    """ Searches YouTube for a specified search term
        and returns a set number of results.

    Args:
        search_term: The string to search on YouTube

    Returns:
        results: A dictionary of YouTube video details
    """

    results = YoutubeSearch(search_term, max_results=num_results)
    results_dict = results.to_dict()

    return results_dict


def youtube_condensed(away_team, home_team):
    """ Searches YouTube for the condensed game / extended highlights of a game.

    Args:
        away_team: Name of the away team
        home_team: Name of the home team

    Returns:
        result: Search result with full YouTube link added.
    """

    search_term = f"NHL Highlights | {away_team} @ {home_team}"
    results = search_youtube(search_term, 1)
    result = results[0]

    # Add the full YouTube link to the return dictionary
    link = result["link"]
    yt_link = f"https://youtube.com{link}"
    result["yt_link"] = yt_link
    return result
