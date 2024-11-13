# -*- coding: utf-8 -*-

"""
This module contains all functions pertaining to a game in Preview State.
"""

import logging
import sys
import time
import os

from hockeygamebot.core import images
from hockeygamebot.definitions import IMAGES_PATH
from hockeygamebot.helpers import utils
from hockeygamebot.models.game import Game
from hockeygamebot.models.gamestate import GameState
from hockeygamebot.models.gametype import GameType
from hockeygamebot.nhlapi import api, livefeed, schedule, thirdparty
from hockeygamebot.social import socialhandler


def generate_game_preview(game: Game):
    """Generates and sends the game preview to social media.

    This function runs when the game is in Preview State and it is not yet
    game time. Should only run once at the morning scheduled time.

    Args:
        game: Game Object

    Returns:
        sleep_time: Seconds to sleep until next action
    """

    logging.info("Generating Game Preview images & social media posts.")
    logging.info("Game Date: Local - %s, UTC - %s", game.game_time_local, game.date_time)

    # Load our Config
    # config = utils.load_config()
    # preview_sleep_time = config["script"]["preview_sleep_time"]
    # preview_sleep_mins = preview_sleep_time / 60

    # Get the preferred team, other teams & homeaway from the Game object
    pref_team, other_team = game.get_preferred_team()
    # pref_team_homeaway = game.preferred_team.home_away

    # Get Team Hashtags
    pref_hashtag = utils.team_hashtag(pref_team.team_name, game.game_type)
    other_hashtag = utils.team_hashtag(other_team.team_name, game.game_type)

    # Generate the propert clock emoji for the game time
    clock_emoji = utils.clock_emoji(game.game_time_local)

    # If the game is a playoff game, our preview text changes slightly
    if GameType(game.game_type) == GameType.PLAYOFFS:
        playoff_info = schedule.get_playoff_info(pref_team.team_id, game.season)
        Game.playoff_info = playoff_info

        round_number = playoff_info["round"]["number"]

        matchup_teams = playoff_info["matchupTeams"]
        pref_playoff_info = [x for x in matchup_teams if x["team"]["name"] == pref_team.team_name][0]
        pref_playoff_series = pref_playoff_info["seriesRecord"]
        pref_playoff_wins = pref_playoff_series["wins"]
        pref_playoff_losses = pref_playoff_series["losses"]
        pref_team.playoff_series_record = f"W: {pref_playoff_wins} | L: {pref_playoff_losses}"

        other_playoff_info = [x for x in matchup_teams if x["team"]["name"] == other_team.team_name][0]
        other_playoff_series = other_playoff_info["seriesRecord"]
        other_playoff_wins = other_playoff_series["wins"]
        other_playoff_losses = other_playoff_series["losses"]
        other_team.playoff_series_record = f"W: {other_playoff_wins} | L: {other_playoff_losses}"

        preview_text_teams = (
            f"Tune in {game.game_time_of_day} for Round #{round_number} / Game #{game.game_id_playoff_game} when the "
            f"{pref_team.team_name} take on the {other_team.team_name} at {game.venue}."
        )
    else:
        preview_text_teams = (
            f"Tune in {game.game_time_of_day} when the {pref_team.team_name} "
            f"take on the {other_team.team_name} at {game.venue}."
        )

    # Generate clock, channel & hashtag emoji text preview
    preview_text_emojis = (
        f"{clock_emoji} {game.game_time_local}\n"
        f"\U0001F4FA {pref_team.tv_channel}\n"
        f"\U00000023\U0000FE0F\U000020E3 {game.game_hashtag}"
    )

    # Generate final preview tweet text
    preview_tweet_text = f"{preview_text_teams}\n\n{preview_text_emojis}"
    game.preview_socials.core_msg = preview_tweet_text

    # Generate pre-game image
    pregame_image = images.pregame_image(game)
    img_filename = os.path.join(IMAGES_PATH, "temp", f"Pregame-{game.game_id}.png")
    pregame_image.save(img_filename)

    # Send preview tweet w/ pre-game image to social media handler
    social_dict = socialhandler.send(msg=preview_tweet_text, media=img_filename, force_send=True)
    game.pregame_lasttweet = social_dict["twitter"]

    # Generate Season Series Data
    season_series = schedule.season_series(game.game_id, pref_team, other_team)
    season_series_string = season_series[0]

    if season_series_string is None:
        # If this is the first game of the season, we can set the 'last_season' flag to enable the
        # season series function to check last year's season series between the two teams.
        logging.info(
            "First game of the season - re-run the season series function with the last_season flag."
        )

        season_series = schedule.season_series(game.game_id, pref_team, other_team, last_season=True)

        season_series_string = season_series[0]
        season_series_string = (
            f"This is the first meeting of the season between the "
            f"{pref_team.short_name} & the {other_team.short_name}.\n\n"
            f"LAST SEASON STATS\n{season_series_string}"
        )

        # season_series_tweet_text = (
        #     f"This is the first meeting of the season between the "
        #     f"{pref_team.short_name} & the {other_team.short_name}. "
        #     f"Last season's stats -"
        #     f"\n\n{season_series_string}\n{points_leader_str}\n{toi_leader_str}"
        #     f"\n\n{pref_hashtag} {other_hashtag} {game.game_hashtag}"
        # )

    # Extract strings from returned list / tuple
    points_leader_str = season_series[1]
    toi_leader_str = season_series[2]

    if game.game_type == "P":
        # season_series_str = season_series_str.replace("season series", "regular season series")
        season_series_string = f"Regular Season Stats -\n\n{season_series_string}"

    season_series_tweet_text = (
        f"{season_series_string}\n{points_leader_str}\n{toi_leader_str}"
        f"\n\n{pref_hashtag} {other_hashtag} {game.game_hashtag}"
    )

    game.preview_socials.season_series_msg = season_series_tweet_text

    # logging.info(preview_tweet_text)
    # logging.info(season_series_tweet_text)
    discord_color = images.discord_color(game.preferred_team.team_name)
    social_dict = socialhandler.send(
        msg=season_series_tweet_text,
        reply=game.pregame_lasttweet,
        force_send=True,
        discord_title="PREVIEW: Season Series",
        discord_color=discord_color,
    )

    game.pregame_lasttweet = social_dict["twitter"]

    game.preview_socials.core_sent = True
    game.preview_socials.season_series_sent = True


def game_preview_others(game: Game):
    """Other game preview information (excluding our core game preview).
        This includes things like goalies, lines, referees, etc.

    This function runs when the game is in Preview State and it is not yet
    game time. Runs every xxx minutes (configured in config.yaml file).

    Args:
        game: Game Object

    Returns:
        sleep_time: Seconds to sleep until next action
    """
    # All of the below functions containg information from non-NHL API sites
    # Each one is wrapped in a try / except just in case.

    # Load our Config
    config = utils.load_config()
    preview_sleep_time = config["script"]["preview_sleep_time"]
    preview_sleep_mins = preview_sleep_time / 60

    # Get the preferred team, other teams & homeaway from the Game object
    pref_team, other_team = game.get_preferred_team()
    pref_team_homeaway = game.preferred_team.home_away

    # Get Team Hashtags
    pref_hashtag = utils.team_hashtag(pref_team.team_name, game.game_type)
    other_hashtag = utils.team_hashtag(other_team.team_name, game.game_type)

    # Process the pre-game information for the starting goalies
    if not game.preview_socials.goalies_pref_sent or not game.preview_socials.goalies_other_sent:
        logging.info("One of the two goalies is not yet confirmed - getting their info now.")
        # goalies_confirmed_values = ("Confirmed", "Likely", "Unconfirmed")
        goalies_confirmed_values = ("Confirmed", "Likely")
        try:
            df_date = game.custom_game_date("%m-%d-%Y")
            goalies_df = thirdparty.dailyfaceoff_goalies(pref_team, other_team, pref_team_homeaway, df_date)
            logging.info(goalies_df)

            goalie_confirm_pref = bool(goalies_df.get("pref").get("confirm") in goalies_confirmed_values)
            goalie_confirm_other = bool(goalies_df.get("other").get("confirm") in goalies_confirmed_values)

            logging.info("Goalie Confirmed PREF : %s", goalie_confirm_pref)
            logging.info("Goalie Confirmed OTHER : %s", goalie_confirm_other)

            if goalie_confirm_pref and not game.preview_socials.goalies_pref_sent:
                try:
                    goalie_pref = goalies_df.get("pref")
                    goalie_pref_name = goalie_pref.get("name")
                    goalie_pref_confirm = goalie_pref.get("confirm")
                    goalie_pref_season = goalie_pref.get("season")
                    if goalie_pref_season == "-- W-L | GAA | SV% | SO":
                        goalie_pref_season = "None (Season Debut)"
                    goalie_hr_pref = thirdparty.hockeyref_goalie_against_team(
                        goalie_pref_name, game.other_team.team_name
                    )
                    logging.info("Hockey Reference Goalie PREF : %s", goalie_hr_pref)

                    pref_goalie_tweet_text = (
                        f"{goalie_pref_confirm} goalie for the {pref_team.short_name} -\n"
                        f"(via @DailyFaceoff)\n\n{goalie_pref_name}\n"
                        f"Season Stats: {goalie_pref_season}\n"
                        f"Career (vs. {other_team.short_name}): {goalie_hr_pref}\n\n"
                        f"{pref_hashtag} {game.game_hashtag}"
                    )
                    discord_color = images.discord_color(game.preferred_team.team_name)
                    social_dict = socialhandler.send(
                        msg=pref_goalie_tweet_text,
                        reply=game.pregame_lasttweet,
                        force_send=True,
                        discord_title="PREVIEW: Goalie Start",
                        discord_color=discord_color,
                    )
                    game.pregame_lasttweet = social_dict["twitter"]
                    game.preview_socials.goalies_pref_sent = True

                except Exception as e:
                    logging.error(
                        "Exception getting PREFERRED Hockey Reference splits - try again next loop."
                    )
                    logging.error(e)
            else:
                logging.info("Preferred goalie not yet confirmed - try again next loop.")

            if goalie_confirm_other and not game.preview_socials.goalies_other_sent:
                try:
                    goalie_other = goalies_df.get("other")
                    goalie_other_name = goalie_other.get("name")
                    goalie_other_confirm = goalie_other.get("confirm")
                    goalie_other_season = goalie_other.get("season")
                    if goalie_other_season == "-- W-L | GAA | SV% | SO":
                        goalie_other_season = "None (Season Debut)"
                    goalie_hr_other = thirdparty.hockeyref_goalie_against_team(
                        goalie_other_name, game.preferred_team.team_name
                    )
                    logging.info("Hockey Reference Goalie OTHER : %s", goalie_hr_other)

                    other_goalie_tweet_text = (
                        f"{goalie_other_confirm} goalie for the {other_team.short_name} -\n"
                        f"(via @DailyFaceoff)\n\n{goalie_other_name}\n"
                        f"Season Stats: {goalie_other_season}\n"
                        f"Career (vs. {pref_team.short_name}): {goalie_hr_other}\n\n"
                        f"{other_hashtag} {game.game_hashtag}"
                    )

                    discord_color = images.discord_color(game.preferred_team.team_name)
                    social_dict = socialhandler.send(
                        msg=other_goalie_tweet_text,
                        reply=game.pregame_lasttweet,
                        force_send=True,
                        discord_title="PREVIEW: Goalie Start",
                        discord_color=discord_color,
                    )

                    game.pregame_lasttweet = social_dict["twitter"]
                    game.preview_socials.goalies_other_sent = True

                except Exception as e:
                    logging.error("Exception getting OTHER Hockey Reference splits - try again next loop.")
                    logging.error(e)
            else:
                logging.info("Other goalie not yet confirmed - try again next loop.")

        except Exception as e:
            logging.error("Exception getting Daily Faceoff goalies - try again next loop.")
            logging.error(e)

    # Process the pre-game information for the game officials
    if not game.preview_socials.officials_sent:
        try:
            officials = thirdparty.scouting_the_refs(game, pref_team)
            logging.info(officials)

            officials_confirmed = officials.get("confirmed")

            if officials_confirmed:
                officials_tweet_text = f"The officials (via @ScoutingTheRefs) for {game.game_hashtag} are -\n"
                for key, attrs in officials.items():
                    if key == "confirmed":
                        continue
                    officials_tweet_text = f"{officials_tweet_text}\n\n{key.title()}:"
                    for official in attrs:
                        official_name = official.get("name")
                        official_season = official.get("seasongames")
                        official_career = official.get("careergames")
                        official_games = official.get("totalgames", 0)
                        official_penalty_game = official.get("penaltygame")
                        if official_penalty_game:
                            official_detail = (
                                f"{official_name} (Games: {official_games} | P/GM: {official_penalty_game})"
                            )
                            # official_detail = f"{official_name} (Gms: {official_season} / {official_career} | P/GM: {official_penalty_game})"
                        else:
                            official_detail = f"{official_name} (Games: {official_games})"
                            # official_detail = f"{official_name} (Games: {official_season} / {official_career})"
                        officials_tweet_text = f"{officials_tweet_text}\n- {official_detail}"

                social_dict = socialhandler.send(
                    msg=officials_tweet_text, reply=game.pregame_lasttweet, force_send=True
                )

                game.pregame_lasttweet = social_dict["twitter"]
                game.preview_socials.officials_sent = True
            else:
                logging.info("Officials not yet confirmed - try again next loop.")

        except Exception as e:
            logging.error("Exception getting Scouting the Refs information - try again next loop.")
            logging.error(e)

    # Process the pre-game information for the preferred team lines
    if not game.preview_socials.pref_lines_sent or game.preview_socials.check_for_changed_lines("preferred"):
        try:
            pref_lines = thirdparty.dailyfaceoff_lines(game, pref_team)
            if not pref_lines.get("confirmed"):
                raise AttributeError("Preferred team lines are not yet confirmed yet - try again next loop.")

            fwd_string = pref_lines.get("fwd_string")
            def_string = pref_lines.get("def_string")

            lines_tweet_text = (
                f"Lines for the {pref_hashtag} -\n"
                f"(via @DailyFaceoff)\n\n"
                f"Forwards:\n{fwd_string}\n\n"
                f"Defense:\n{def_string}"
            )

            # If we have not sent the lines out at all, force send them
            if not game.preview_socials.pref_lines_sent:
                social_dict = socialhandler.send(
                    msg=lines_tweet_text, reply=game.pregame_lasttweet, force_send=True
                )
                game.pregame_lasttweet = social_dict["twitter"]
                game.preview_socials.pref_lines_msg = lines_tweet_text
                game.preview_socials.pref_lines_sent = True
            else:
                lines_changed, lines_tweet_text = game.preview_socials.did_lines_change(
                    "preferred", lines_tweet_text
                )
                if lines_changed:
                    social_dict = socialhandler.send(
                        msg=lines_tweet_text, reply=game.pregame_lasttweet, force_send=True
                    )
                    game.pregame_lasttweet = social_dict["twitter"]
                    game.preview_socials.pref_lines_msg = lines_tweet_text
                    game.preview_socials.pref_lines_resent = True
                else:
                    logging.info("The preferred team lines have not changed - check again in an hour.")

        except AttributeError as e:
            logging.info(e)
        except Exception as e:
            logging.error("Exception getting Daily Faceoff lines information - try again next loop.")
            logging.error(e)

    # Process the pre-game information for the preferred team lines
    if not game.preview_socials.other_lines_sent or game.preview_socials.check_for_changed_lines("other"):
        try:
            other_lines = thirdparty.dailyfaceoff_lines(game, other_team)
            if not other_lines.get("confirmed"):
                raise AttributeError("Other team lines are not yet confirmed yet - try again next loop.")

            fwd_string = other_lines.get("fwd_string")
            def_string = other_lines.get("def_string")

            lines_tweet_text = (
                f"Lines for the {other_hashtag} -\n"
                f"(via @DailyFaceoff)\n\n"
                f"Forwards:\n{fwd_string}\n\n"
                f"Defense:\n{def_string}"
            )

            # If we have not sent the lines out at all, force send them
            if not game.preview_socials.other_lines_sent:
                social_dict = socialhandler.send(
                    msg=lines_tweet_text, reply=game.pregame_lasttweet, force_send=True
                )
                game.pregame_lasttweet = social_dict["twitter"]
                game.preview_socials.other_lines_msg = lines_tweet_text
                game.preview_socials.other_lines_sent = True
            else:
                lines_changed, lines_tweet_text = game.preview_socials.did_lines_change(
                    "other", lines_tweet_text
                )
                if lines_changed:
                    social_dict = socialhandler.send(
                        msg=lines_tweet_text, reply=game.pregame_lasttweet, force_send=True
                    )
                    game.pregame_lasttweet = social_dict["twitter"]
                    game.preview_socials.other_lines_msg = lines_tweet_text
                    game.preview_socials.other_lines_resent = True
                else:
                    logging.info("The preferred team lines have not changed - check again in an hour.")

        except AttributeError as e:
            logging.info(e)
        except Exception as e:
            logging.error("Exception getting Daily Faceoff lines information - try again next loop.")
            logging.error(e)

    # Check if all pre-game tweets are sent
    # And return time to sleep
    all_pregametweets = all(value is True for value in game.pregametweets.values())

    if not all_pregametweets and game.game_time_countdown > preview_sleep_time:
        logging.info(
            "Game State is Preview & all pre-game tweets are not sent. " "Sleep for 30 minutes & check again."
        )
        return preview_sleep_time, False
    elif not all_pregametweets and game.game_time_countdown < preview_sleep_time:
        logging.warning(
            "Game State is Preview & all pre-game tweets are not sent. "
            "Less than %s minutes until game time so we skip these today."
            "If needed, we try to get lines at the end of the game for advanced stats.",
            preview_sleep_mins,
        )
        return game.game_time_countdown, True
    else:
        logging.info(
            "Game State is Preview & all tweets are sent. Sleep for %s seconds until game time.",
            game.game_time_countdown,
        )

        # We need to subtract 5-minutes from this
        return game.game_time_countdown, True


def get_starters(game: Game):
    """Uses the NHL Roster Report to get the starting lineup."""

    def get_players_name(score_rpt_row):
        """Very specific function to only return the player's last name from the roster report."""
        player_name = score_rpt_row.find_all("td")[2].text
        return " ".join(player_name.replace(" (A)", "").replace(" (C)", "").title().split()[1:])

    while not game.preview_socials.starters_sent:
        livefeed_resp = livefeed.get_livefeed(game.game_id)
        game.update_game(livefeed_resp)
        if game.game_state == GameState.LIVE.value:
            logging.info("Game state switched to live - forget about the starters.")
            return

        roster_endpoint = f"/{game.season}/RO{game.game_id_html}.HTM"
        r = api.nhl_score_rpt(roster_endpoint)

        if not r:
            logging.warning("Roster report is not available, something is wrong.")
            return

        try:
            soup = thirdparty.bs4_parse(r.content)
            team_headings = soup.find("td", class_="teamHeading + border").find_parent("tr")
            data = team_headings.find_next("tr")

            rosters = data.find("tr").find_all("td", recursive=False)
            roster = rosters[0] if game.preferred_team.home_away == "away" else rosters[1]

            players = [x for x in roster.find_all("tr")]

            starters = list()
            for pos in [("L", "R", "C"), "D", "G"]:
                pos_all = [x for x in players if x.find_all("td")[1].text in pos]
                pos_start = [get_players_name(x) for x in pos_all if "bold" in x.find_all("td")[0]["class"]]
                pos_start_str = " - ".join(pos_start)
                starters.append(pos_start_str)
        except Exception as e:
            logging.error(
                "Something happened while trying to get the starters - sleep for 20s & try again. %s",
                e,
            )
            time.sleep(20)
            continue

        if not starters:
            logging.info("Starters not yet avialble from the roster report - sleep & try again.")
            time.sleep(20)
            continue

        starters_string = "\n".join(starters)
        starters_msg = (
            f"{utils.team_hashtag(game.preferred_team.team_name)} Starters:" f"\n\n{starters_string}"
        )
        socialhandler.send(starters_msg, force_send=True, game_hashtag=True)
        game.preview_socials.starters_msg = starters_msg
        game.preview_socials.starters_sent = True
