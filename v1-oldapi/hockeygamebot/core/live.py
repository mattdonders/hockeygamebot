# -*- coding: utf-8 -*-

"""
This module contains all functions pertaining to a game in Live State.
"""

import logging
import time

from hockeygamebot.core import common
from hockeygamebot.helpers import arguments, utils
from hockeygamebot.models import gameevent
from hockeygamebot.models.game import Game
from hockeygamebot.models.gameevent import GoalEvent
from hockeygamebot.nhlapi import nst
from hockeygamebot.social import socialhandler


def live_loop(livefeed: dict, game: Game):
    """The master live-game loop. All logic spawns from here.

    Args:
        livefeed: Live Feed API response
        game: Game Object

    Returns:
        None
    """
    config = utils.load_config()

    # Load all plays, the next event ID & new plays into lists
    # current_event_idx = livefeed.get("liveData").get("currentPlay").get("about").get("eventIdx")
    all_plays = livefeed.get("liveData").get("plays").get("allPlays")

    # Subset all_plays by last_event_idx to shorten the loop
    next_event_idx = game.last_event_idx + 1
    new_plays_list = all_plays[next_event_idx:]

    if not new_plays_list:
        new_plays = bool(new_plays_list)
        logging.info(
            "No new plays detected. This game event loop will catch any missed events & "
            "and also check for any scoring changes on existing goals."
        )
    elif len(new_plays_list) < 10:
        new_plays = bool(new_plays_list)
        new_plays_shortlist = list()
        for play in new_plays_list:
            event_type = play["result"]["eventTypeId"]
            event_idx = play["about"]["eventIdx"]
            event_kv = f"{event_idx}: {event_type}"
            new_plays_shortlist.append(event_kv)
        logging.info(
            "%s new event(s) detected - looping through them now: %s",
            len(new_plays_list),
            new_plays_shortlist,
        )
    else:
        new_plays = bool(new_plays_list)
        logging.info("%s new event(s) detected - looping through them now.", len(new_plays_list))

    # We pass in the entire all_plays list into our event_factory in case we missed an event
    # it will be created because it doesn't exist in the Cache.
    for play in all_plays:
        gameevent.event_factory(game=game, play=play, livefeed=livefeed, new_plays=new_plays)

    # Check if any goals were removed
    try:
        for goal in game.all_goals[:]:
            was_goal_removed = goal.was_goal_removed(all_plays)
            if was_goal_removed:
                pref_team = game.preferred_team.team_name
                goals_list = game.pref_goals if goal.event_team == pref_team else game.other_goals

                # Remove the Goal from all lists, caches & then finallydelete the object
                game.all_goals.remove(goal)
                goals_list.remove(goal)
                goal.cache.remove(goal)
                del goal
    except Exception as e:
        logging.error("Encounted an exception trying to detect if a goal is no longer in the livefeed.")
        logging.error(e)


def intermission_loop(game: Game):
    """The live-game intermission loop. Things to do during an intermission

    Args:
        game: Game Object

    Returns:
        live_sleep_time: The amount to sleep until our next check.
    """

    args = arguments.get_arguments()
    config = utils.load_config()

    # If we are in intermission, check if NST is ready for charts.
    # Incorporating the check into this loop will be sure we obey the 60s sleep rule.
    # We use the currentPeriod as the key to lookup if the charts
    # have been sent for the current period's intermission
    nst_chart_period_sent = game.nst_charts.charts_by_period.get(game.period.current)
    if not nst_chart_period_sent:
        logging.info("NST Charts not yet sent - check if it's ready for us to scrape.")
        nst_ready = nst.is_nst_ready(game.preferred_team.short_name) if not args.date else True
        if nst_ready:
            try:
                list_of_charts = nst.generate_all_charts(game=game)
                # Chart at Position 0 is the Overview Chart & 1-4 are the existing charts
                overview_chart = list_of_charts["overview"]
                team_charts = list_of_charts["barcharts"]
                shift_chart = list_of_charts["shift"]
                heatmap_charts = list_of_charts["heatmaps"]

                last_chart_socials = None

                if overview_chart:
                    overview_chart_msg = (
                        f"Team Overview stat percentages - 5v5 (SVA) after the "
                        f"{game.period.current_ordinal} period (via @NatStatTrick)."
                    )

                    last_chart_socials = socialhandler.send(
                        overview_chart_msg, media=overview_chart, game_hashtag=True
                    )

                if team_charts:
                    charts_msg = (
                        f"Individual, on-ice, forward lines & defensive pairs after the "
                        f"{game.period.current_ordinal} period (via @NatStatTrick)."
                    )
                    last_chart_socials = socialhandler.send(
                        charts_msg, media=team_charts, game_hashtag=True, reply=last_chart_socials["twitter"]
                    )

                if heatmap_charts:
                    charts_msg = (
                        f"Linemate & Opposition Data (TOI, CF% and xGF%) after the "
                        f"{game.period.current_ordinal} period (via @NatStatTrick)."
                    )
                    last_chart_socials = socialhandler.send(
                        charts_msg,
                        media=heatmap_charts,
                        game_hashtag=True,
                        reply=last_chart_socials["twitter"],
                    )

                if shift_chart:
                    charts_msg = (
                        f"Shift length breakdown after the "
                        f"{game.period.current_ordinal} period (via @NatStatTrick)."
                    )
                    last_chart_socials = socialhandler.send(
                        charts_msg, media=shift_chart, game_hashtag=True, reply=last_chart_socials["twitter"]
                    )

                game.nst_charts.charts_by_period[game.period.current] = True

            except Exception as e:
                logging.error("Error creating Natural Stat Trick charts (%s) - sleep for a bit longer.", e)

    # Check if our shotmap was RT'd & if not try to search for it and send it out
    shotmap_retweet_sent = game.period.shotmap_retweet
    if not shotmap_retweet_sent and config["socials"]["twitter"]:
        game.period.shotmap_retweet = common.search_send_shotmap(game=game)

    # Calculate proper sleep time based on intermission status
    if game.period.intermission_remaining > config["script"]["intermission_sleep_time"]:
        live_sleep_time = config["script"]["intermission_sleep_time"]
        logging.info(
            "Sleeping for configured intermission time (%ss).",
            config["script"]["intermission_sleep_time"],
        )
    else:
        # Adds a MAX function here to avoid sleeping 0s between calls
        live_sleep_time = max(game.period.intermission_remaining, 5)
        logging.info("Sleeping for remaining intermission time (%ss).", game.period.intermission_remaining)

    return live_sleep_time


def minute_remaining_check(game: Game):
    """A function to check if there is approximately a minute remaining in the period."""

    if game.period.time_remaining == "END":
        game.period.current_oneminute_sent = True
        return

    period_remain_ss = utils.from_mmss(game.period.time_remaining)
    if 50 <= period_remain_ss <= 65:
        msg = f"One minute remaining in the {game.period.current_ordinal} period."
        socialhandler.send(msg=msg, game_hashtag=True)
        game.period.current_oneminute_sent = True
    elif period_remain_ss < 50:
        # Force the property to true if the period is below 50s
        game.period.current_oneminute_sent = True
