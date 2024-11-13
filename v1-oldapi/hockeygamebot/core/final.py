# -*- coding: utf-8 -*-

"""
This module contains all functions pertaining to a game in a Final State.
"""

import logging
import os
from datetime import datetime, timedelta

import dateutil.tz
from dateutil.parser import parse

from hockeygamebot.definitions import IMAGES_PATH
from hockeygamebot.models.game import Game
from hockeygamebot.nhlapi import schedule, thirdparty
from hockeygamebot.social import socialhandler
from hockeygamebot.core import images


def final_score(livefeed: dict, game: Game):
    """Takes the livefeed response from the NHL API and sets the status & key of this attribute
        in the EndOfGame socials class.

    Args:
        livefeed: Live Feed API response
        game: Game Object

    Returns:
        None: Sets a status & message in EndOfGame object
        # bool: if the function runs & sends to social succesfully
    """
    logging.info("Starting the core Final Score work now.")
    if game.final_socials.final_score_sent:
        logging.debug("Final score social already sent - skip this iteration!")
        return

    # Get all nested dictionaries frmo the livefeed response
    all_plays = livefeed["liveData"]["plays"]["allPlays"]
    boxscore = livefeed["liveData"]["boxscore"]
    linescore = livefeed["liveData"]["linescore"]

    linescore_period = linescore["currentPeriod"]
    linescore_teams = linescore["teams"]
    linescore_pref = linescore_teams[game.preferred_team.home_away]
    linescore_other = linescore_teams[game.other_team.home_away]

    pref_home_text = "on the road" if game.preferred_team.home_away == "away" else "at home"
    score_pref = linescore_pref["goals"]
    score_other = linescore_other["goals"]

    # Everytime there is a shootout, when the GAME_END event is posted,
    # the score of the game is still tied - fix this by checking the SO scores.
    if linescore_period == 5 and (score_pref == score_other):
        logging.info("A shootout caused the final score to be tied - checke the shootoutInfo key")
        shootout_info = linescore["shootoutInfo"]
        logging.info("Shootout Info: %s", shootout_info)
        pref_so_goals = shootout_info[game.preferred_team.home_away]["scores"]
        other_so_goals = shootout_info[game.other_team.home_away]["scores"]
        if pref_so_goals > other_so_goals:
            logging.info("Preferred Team scored more shootout goals, increment score by 1.")
            score_pref = score_pref + 1
        else:
            logging.info("Other Team scored more shootout goals, increment score by 1.")
            score_other = score_other + 1

        # Set Team Objects New Score
        game.preferred_team.score = score_pref
        game.other_team.score = score_other

    if score_pref > score_other:
        final_score_text = (
            f"{game.preferred_team.short_name} win {pref_home_text} over the "
            f"{game.other_team.short_name} by a score of {score_pref} to "
            f"{score_other}! 🚨🚨🚨"
        )
    else:
        final_score_text = (
            f"{game.preferred_team.short_name} lose {pref_home_text} to the "
            f"{game.other_team.short_name} by a score of {score_pref} to "
            f"{score_other}! 👎🏻👎🏻👎🏻"
        )

    # Using the NHL Schedule API, get the next game which goes at the bottom of this core tweet
    try:
        next_game = schedule.get_next_game(game.local_datetime, game.preferred_team.team_id)

        # Caclulate the game in the team's local time zone
        tz_id = dateutil.tz.gettz(game.preferred_team.tz_id)
        tz_offset = tz_id.utcoffset(datetime.now(tz_id))
        next_game_date = next_game["gameDate"]
        next_game_dt = parse(next_game_date)
        next_game_dt_local = next_game_dt + tz_offset
        next_game_string = datetime.strftime(next_game_dt_local, "%A %B %d @ %I:%M%p")

        # Get next game's opponent
        next_game_teams = next_game["teams"]

        next_game_home = next_game_teams["home"]
        next_game_home_id = next_game_home["team"]["id"]
        next_game_home_name = next_game_home["team"]["name"]

        next_game_away = next_game_teams["away"]
        next_game_away_name = next_game_away["team"]["name"]

        if next_game_home_id == game.preferred_team.team_id:
            next_opponent = next_game_away_name
        else:
            next_opponent = next_game_home_name

        next_game_venue = next_game["venue"]["name"]
        next_game_text = f"Next Game: {next_game_string} vs. {next_opponent} (at {next_game_venue})!"
    except Exception as e:
        logging.warning("Error getting next game via the schedule endpoint.")
        logging.error(e)
        next_game_text = ""

    final_image = images.stats_image(game=game, game_end=True, boxscore=boxscore)
    img_filename = os.path.join(IMAGES_PATH, "temp", f"Final-{game.game_id}.png")
    final_image.save(img_filename)

    final_score_msg = f"{final_score_text}\n\n{next_game_text}"
    # socialhandler.send(final_score_msg)
    socialhandler.send(msg=final_score_msg, media=img_filename)

    # Set the final score message & status in the EndOfGame Social object
    game.final_socials.final_score_msg = final_score_msg
    game.final_socials.final_score_sent = True


def three_stars(livefeed: dict, game: Game):
    """Takes the livefeed response from the NHL API and sets the status & key of the three-stars
        attribute in the EndOfGame socials class.

    Args:
        livefeed: Live Feed API response
        game: Game Object

    Returns:
        None: Sets a status & message in EndOfGame object
        # bool: if the function runs & sends to social succesfully
    """
    if game.final_socials.three_stars_sent:
        logging.debug("Three stars social already sent - skip this loop!")
        return

    logging.info("Checking for the 3-stars of the game.")

    all_players = livefeed["gameData"]["players"]
    decisions = livefeed["liveData"]["decisions"]

    try:
        first_star_id = f"ID{decisions['firstStar']['id']}"
        first_star_name = decisions["firstStar"]["fullName"]
        first_star_tricode = all_players[first_star_id]["currentTeam"]["triCode"]
        first_star_full = f"{first_star_name} ({first_star_tricode})"

        second_star_id = f"ID{decisions['secondStar']['id']}"
        second_star_name = decisions["secondStar"]["fullName"]
        second_star_tricode = all_players[second_star_id]["currentTeam"]["triCode"]
        second_star_full = f"{second_star_name} ({second_star_tricode})"

        third_star_id = f"ID{decisions['thirdStar']['id']}"
        third_star_name = decisions["thirdStar"]["fullName"]
        third_star_tricode = all_players[third_star_id]["currentTeam"]["triCode"]
        third_star_full = f"{third_star_name} ({third_star_tricode})"

        stars_text = f"⭐️: {first_star_full}\n⭐️⭐️: {second_star_full}\n⭐️⭐️⭐️: {third_star_full}"
        three_stars_msg = f"The three stars for the game are - \n{stars_text}"

    except KeyError:
        logging.info("3-stars have not yet posted - try again in next iteration.")
        return

    discord_color = images.discord_color(game.preferred_team.team_name)
    socialhandler.send(three_stars_msg, discord_title="FINAL: Three Stars", discord_color=discord_color)

    # Set the final score message & status in the EndOfGame Social object
    game.final_socials.three_stars_msg = three_stars_msg
    game.final_socials.three_stars_sent = True


def hockeystatcards(game: Game):
    """Uses the Hockey Stat Cards API to retrieve gamescores for the current game.
        Generates an image based on those values & sends the socials.

    Args:
        game (Game): Current Game object.

    Returns:
        None
    """

    game_scores = thirdparty.hockeystatcard_gamescores(game=game)
    if not game_scores:
        logging.warning("Could not get game scores, exiting.")
        return False

    home_gs = game_scores[0]
    away_gs = game_scores[1]

    hsc_charts = images.hockeystatcards_charts(game=game, home_gs=home_gs, away_gs=away_gs)

    hsc_social_text = (
        f"{game.preferred_team.short_name} & {game.other_team.short_name} Game Score leaderboard."
        f"\n\n(via @hockeystatcards @NatStatTrick @domluszczyszyn)"
    )

    socialhandler.send(msg=hsc_social_text, media=hsc_charts)

    # Set the end of game social attributes
    game.final_socials.hsc_msg = hsc_social_text
    game.final_socials.hsc_sent = True
