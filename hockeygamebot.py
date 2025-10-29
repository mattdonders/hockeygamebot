import argparse
import logging
from datetime import datetime, timedelta
import os
import sys
import time

from matplotlib import font_manager, rcParams
import requests

from core import final
from core import charts
from core.charts import intermission_chart, teamstats_chart
from core.integrations import nst
from core.models.team import Team
import core.rosters as rosters
import core.schedule as schedule
from definitions import RESOURCES_DIR
import utils.others as otherutils
from core.play_by_play import parse_play_by_play_with_names
import core.preview as preview
from core.live import parse_live_game
from socials.bluesky import BlueskyClient
from utils.config import load_config
from utils.team_details import TEAM_DETAILS
from core.models.game_context import GameContext


def start_game_loop(context: GameContext):
    """
    Manages the main game loop for real-time updates.

    This function handles various game states, including pre-game, live and post-game.
    It processes live events, manages game intermissions, posts
    updates to social platforms, and transitions to post-game logic.

    Args:
        context (GameContext): The shared context containing game details, configuration,
            and state management.
    """
    # ------------------------------------------------------------------------------
    # START THE MAIN LOOP
    # ------------------------------------------------------------------------------

    while True:
        # Every loop, update game state so the logic below works for switching between them
        updated_game_state = schedule.fetch_game_state(context.game_id)
        context.game_state = updated_game_state

        clock_data = schedule.fetch_clock(context.game_id)
        context.clock.update(clock_data)

        # If we enter this function on the day of a game (before the game starts), gameState = "FUT"
        # We should send preview posts & then sleep until game time.
        if context.game_state in ["PRE", "FUT"]:
            logging.info("Handling a preview game state: %s", context.game_state)

            # Generate and post the game time preview
            if not context.preview_socials.core_sent:
                game_time_post = preview.format_future_game_post(context.game, context)
                bsky_gametime = context.bluesky_client.post(game_time_post)
                context.preview_socials.core_sent = True
                if bsky_gametime:
                    logging.debug(vars(bsky_gametime))
                    context.preview_socials.bluesky_root = bsky_gametime
                    context.preview_socials.bluesky_parent = bsky_gametime
                logging.info("Posted game time preview.")

            # Generate and post the season series preview
            if not context.preview_socials.season_series_sent:
                # Fetch the team schedule and calculate the season series
                team_schedule = schedule.fetch_schedule(
                    context.preferred_team.abbreviation, context.season_id
                )
                home_team = context.game["homeTeam"]["abbrev"]
                away_team = context.game["awayTeam"]["abbrev"]
                opposing_team = away_team if home_team == context.preferred_team.abbreviation else home_team

                season_series_post = preview.format_season_series_post(
                    team_schedule, context.preferred_team.abbreviation, opposing_team, context
                )
                bsky_seasonseries = context.bluesky_client.post(
                    season_series_post, reply_root=bsky_gametime, reply_parent=bsky_gametime
                )
                context.preview_socials.season_series_sent = True
                if bsky_seasonseries:
                    logging.debug(vars(bsky_seasonseries))
                    context.preview_socials.bluesky_parent = bsky_seasonseries
                logging.info("Posted season series preview.")

            if not context.preview_socials.team_stats_sent:
                right_rail_data = schedule.fetch_rightrail(context.game_id)
                teamstats_data = right_rail_data.get("teamSeasonStats")
                teamstats_chart_path = teamstats_chart(context, teamstats_data, ingame=False)
                teamstats_msg = f"Pre-Game team stats for {context.game_time_of_day}'s game."
                if teamstats_chart_path:
                    bsky_teamstats = context.bluesky_client.post(
                        message=teamstats_msg,
                        media=teamstats_chart_path,
                        reply_parent=context.preview_socials.bluesky_parent,
                        reply_root=context.preview_socials.bluesky_root,
                    )
                    context.preview_socials.team_stats_sent = True
                    if bsky_teamstats:
                        logging.debug(vars(bsky_teamstats))
                        context.preview_socials.bluesky_parent = bsky_teamstats
                    logging.info("Posted pre-game team stats chart.")

            # Get Referees from "Right Rail" of Gamecenter Page
            if not context.preview_socials.officials_sent:
                officials_post = preview.generate_referees_post(context)
                if officials_post:
                    bsky_officials = context.bluesky_client.post(
                        officials_post,
                        reply_parent=context.preview_socials.bluesky_parent,
                        reply_root=context.preview_socials.bluesky_root,
                    )
                    context.preview_socials.officials_sent = True
                    if bsky_officials:
                        logging.debug(vars(bsky_officials))
                        context.preview_socials.bluesky_parent = bsky_officials
                    logging.info("Posted season series preview.")

            # Use our auto-sleep calculator now
            preview.preview_sleep_calculator(context)

        elif context.game_state in ["PRE", "LIVE", "CRIT"]:
            logging.debug("Game Context: %s", vars(context))
            logging.info("Handling a LIVE game state: %s", context.game_state)

            if not context.gametime_rosters_set:
                # Get Game-Time Rosters and Combine w/ Pre-Game Rosters
                logging.info("Getting game-time rosters and adding them to existing combined rosters.")
                game_time_rosters = rosters.load_game_rosters(context)
                final_combined_rosters = {**context.combined_roster, **game_time_rosters}
                context.combined_roster = final_combined_rosters
                context.gametime_rosters_set = True

            # Parse Live Game Data
            parse_live_game(context)

            if context.clock.in_intermission:
                intermission_sleep_time = context.clock.seconds_remaining
                logging.info(
                    "Game is in intermission - sleep for the remaining time (%ss).", intermission_sleep_time
                )
                time.sleep(intermission_sleep_time)
            else:
                live_sleep_time = context.config["script"]["live_sleep_time"]
                logging.info("Sleeping for configured live game time (%ss).", live_sleep_time)

                # Now increment the counter sleep for the calculated time above
                context.live_loop_counter += 1
                time.sleep(live_sleep_time)

        elif context.game_state in ["OFF", "FINAL"]:
            logging.info(
                "Game is now over and / or 'Official' - run end of game functions with increased sleep time."
            )

            # If (for some reason) the bot was started after the end of the game
            # We need to re-run the live loop once to parse all of the events
            if not context.events:
                logging.info("Bot started after game ended, pass livefeed into event factory to fill events.")

                if not context.gametime_rosters_set:
                    # Get Game-Time Rosters and Combine w/ Pre-Game Rosters
                    logging.info("Getting game-time rosters and adding them to existing combined rosters.")
                    game_time_rosters = rosters.load_game_rosters(context)
                    final_combined_rosters = {**context.combined_roster, **game_time_rosters}
                    context.combined_roster = final_combined_rosters
                    context.gametime_rosters_set = True

                # Extract game ID and build the play-by-play URL
                game_id = context.game_id
                # play_by_play_data = schedule.fetch_playbyplay(game_id)
                # events = play_by_play_data.get("plays", [])

                # Parse Live Game Data
                parse_live_game(context)

            if not context.final_socials.final_score_sent:
                final_score_post = final.final_score(context)
                bsky_finalscore = context.bluesky_client.post(final_score_post)
                context.final_socials.final_score_sent = True
                if bsky_finalscore:
                    logging.debug(vars(bsky_finalscore))
                    context.final_socials.bluesky_root = bsky_finalscore
                    context.final_socials.bluesky_parent = bsky_finalscore

            if not context.final_socials.three_stars_sent:
                three_stars_post = final.three_stars(context)
                bsky_threestars = context.bluesky_client.post(three_stars_post)
                context.final_socials.three_stars_sent = True
                if bsky_threestars:
                    logging.debug(vars(bsky_threestars))
                    context.final_socials.bluesky_parent = bsky_threestars

            if not context.final_socials.team_stats_sent:
                right_rail_data = schedule.fetch_rightrail(context.game_id)
                team_stats_data = right_rail_data.get("teamGameStats")
                if team_stats_data:
                    chart_path = charts.teamstats_chart(context, team_stats_data, ingame=True)
                    chart_message = "Team Game Stats"

            end_game_loop(context)
        else:
            print(context.game_state)
            sys.exit()


def end_game_loop(context: GameContext):
    """
    Finalizes the game loop and logs the end of the game.

    This function logs the final game summary, including scores, timestamps, and any
    final details. It is the logical endpoint for the script.

    Args:
        context (GameContext): The shared context containing game details, configuration,
            and state management.
    """

    logging.info("#" * 80)
    logging.info("End of the '%s' Hockey Game Bot game.", context.preferred_team.full_name)
    logging.info(
        "Final Score: %s: %s / %s: %s",
        context.preferred_team.full_name,
        context.preferred_team.score,
        context.other_team.full_name,
        context.other_team.score,
    )
    logging.info("TIME: %s", datetime.now())
    logging.info("%s\n", "#" * 80)
    sys.exit()


def handle_is_game_today(game, target_date, preferred_team, season_id, context: GameContext):
    """
    Handles pre-game setup and initialization for games occurring today.

    This function sets up team objects, rosters, hashtags, and game metadata in the
    context. It prepares the application for real-time updates during the game.

    Args:
        game (dict): The dictionary containing details of today's game.
        target_date (str): The date of the game (format: YYYY-MM-DD).
        preferred_team (Team): The user's preferred team object.
        season_id (int): The current NHL season identifier.
        context (GameContext): The shared context containing game details, configuration,
            and state management.
    """

    logging.info(f"Game found today ({target_date}):")
    logging.info(
        f"  {game['awayTeam']['placeName']['default']} ({game['awayTeam']['abbrev']}) "
        f"@ {game['homeTeam']['placeName']['default']} ({game['homeTeam']['abbrev']})"
    )
    logging.info(f"  Venue: {game['venue']['default']}")
    logging.info(f"  Start Time (UTC): {game['startTimeUTC']}")

    # Setup Other Team Object & Other Related Team Functions
    is_preferred_home = game["homeTeam"]["abbrev"] == preferred_team.abbreviation
    other_team_abbreviation = game["awayTeam"]["abbrev"] if is_preferred_home else game["homeTeam"]["abbrev"]
    other_team_name = TEAM_DETAILS[other_team_abbreviation]["full_name"]
    other_team = Team(other_team_name)

    # Add All Teams to GameContext
    context.preferred_team = preferred_team
    context.other_team = other_team
    context.home_team = preferred_team if is_preferred_home else other_team
    context.away_team = other_team if is_preferred_home else preferred_team
    context.preferred_homeaway = "home" if is_preferred_home else "away"

    # Set hashtags into game context
    context.game_hashtag = f"#{context.away_team.abbreviation}vs{context.home_team.abbreviation}"

    # Get Game ID / Type & Store it in the GameContext
    game_id = game["id"]
    game_type = game["gameType"]
    context.game_id = game_id
    context.game_type = game_type
    context.game_shortid = str(game_id)[-4:]

    # Set Game Time & Game Time (in local TZ)
    context.game_time = game["startTimeUTC"]
    game_time_local = otherutils.convert_utc_to_localteam_dt(
        context.game_time, context.preferred_team.timezone
    )
    game_time_local_str = otherutils.convert_utc_to_localteam(
        context.game_time, context.preferred_team.timezone
    )
    context.game_time_local = game_time_local
    context.game_time_local_str = game_time_local_str

    # Get Game Information & Store it in the GameContext
    game_state = game["gameState"]
    context.game_state = game_state
    context.venue = game["venue"]["default"]

    # Load Combined Rosters into Game Context
    context.combined_roster = rosters.load_combined_roster(game, preferred_team, other_team, season_id)

    # DEBUG Log the GameContext
    logging.debug(f"Full Game Context: {vars(context)}")

    # Pre-Game Setup is Completed
    # Start Game Loop by passing in GameContext
    start_game_loop(context)


def handle_was_game_yesterday(game, yesterday, context: GameContext):
    """
    Handles logic for games that occurred yesterday.

    Posts a summary message and logs placeholder actions for past games without
    parsing play-by-play events.

    Args:
        game (dict): The dictionary containing details of yesterday's game.
        yesterday (str): The date of yesterday (format: YYYY-MM-DD).
        context (GameContext): The shared context containing game details, configuration,
            and state management.
    """

    # Log placeholder action for yesterday's game
    logging.debug("No play-by-play parsing performed for yesterday's game.")

    # Setup Other Team Object & Other Related Team Functions
    is_preferred_home = game["homeTeam"]["abbrev"] == context.preferred_team.abbreviation
    other_team_abbreviation = game["awayTeam"]["abbrev"] if is_preferred_home else game["homeTeam"]["abbrev"]
    other_team_name = TEAM_DETAILS[other_team_abbreviation]["full_name"]
    other_team = Team(other_team_name)
    context.other_team = other_team

    context.home_team = context.preferred_team if is_preferred_home else other_team
    context.away_team = other_team if is_preferred_home else context.preferred_team

    # Add Game ID to Context (For Consistency)
    game_id = game["id"]
    context.game_id = game_id

    # Get Final Score & Setup the "Result String"
    pref_score = game["homeTeam"]["score"] if is_preferred_home else game["awayTeam"]["score"]
    other_score = game["awayTeam"]["score"] if is_preferred_home else game["homeTeam"]["score"]
    game_result_str = "defeat" if pref_score > other_score else "lose to"

    # Re-Assign Team Names for Easier Use
    pref_team_name = context.preferred_team.full_name
    other_team_name = context.other_team.full_name

    logging.info(f"Game found yesterday ({yesterday}):")
    logging.info(
        f"  {game['awayTeam']['placeName']['default']} ({game['awayTeam']['abbrev']}) "
        f"@ {game['homeTeam']['placeName']['default']} ({game['homeTeam']['abbrev']})"
    )
    logging.info(f"  Venue: {game['venue']['default']}")
    logging.info(f"  Start Time (UTC): {game['startTimeUTC']}")
    logging.info(
        f"  Final Score - {context.preferred_team.abbreviation}: {pref_score} / {context.other_team.abbreviation}: {other_score}"
    )

    logging.info("Getting Game Recap & Description")
    game_stories = schedule.fetch_stories(context.game_id)
    right_rail = schedule.fetch_rightrail(context.game_id)
    # print(game_stories)
    # Game Headline w/ Recap & Game Summary w/ Condensed Game
    game_headline = game_stories["items"][0]["headline"]
    game_headline = f"{game_headline}." if not game_headline.endswith(".") else game_headline

    if "--" in game_stories["items"][0]["summary"]:
        game_summary = game_stories["items"][0]["summary"].split("--")[1].strip()
    else:
        game_summary = game_stories["items"][0]["summary"]

    game_videos = right_rail["gameVideo"]
    game_video_prefix = (
        f"{context.away_team.abbreviation.lower()}-at-{context.home_team.abbreviation.lower()}"
    )
    game_recap_video_slug = game_videos["threeMinRecap"]
    game_recap_url = f"https://www.nhl.com/video/{game_video_prefix}-recap-{game_recap_video_slug}"
    game_condensed_video_slug = game_videos["condensedGame"]
    game_condensed_url = (
        f"https://www.nhl.com/video/{game_video_prefix}-condensed-game-{game_condensed_video_slug}"
    )

    game_recap_msg = f"{game_headline}\n\nGame Recap: {game_recap_url}"
    game_condensed_msg = f"{game_summary}\n\nCondensed Game: {game_condensed_url}"

    bsky_recap = context.bluesky_client.post(game_recap_msg, link=game_recap_url)
    bsky_condensed = context.bluesky_client.post(
        game_condensed_msg, link=game_condensed_url, reply_parent=bsky_recap, reply_root=bsky_recap
    )

    logging.info("Generating Season & L10 Team Stat Charts from Natural Stat Trick.")
    team_season_msg = (
        f"Updated season overview & last 10 game stats after the {pref_team_name} "
        f"{game_result_str} the {other_team_name} by a score of {pref_score} to {other_score}."
        f"\n\n{context.preferred_team.hashtag}"
    )
    team_season_fig = nst.generate_team_season_charts(pref_team_name, "sva")
    team_season_fig_last10 = nst.generate_team_season_charts(pref_team_name, "sva", lastgames=10)
    team_season_fig_all = nst.generate_team_season_charts(pref_team_name, "all")
    team_season_fig_last10_all = nst.generate_team_season_charts(pref_team_name, "all", lastgames=10)
    team_season_charts = [
        team_season_fig,
        team_season_fig_last10,
        team_season_fig_all,
        team_season_fig_last10_all,
    ]

    bsky_seasonimg = context.bluesky_client.post(team_season_msg, media=team_season_charts)


def main():
    """
    Entry point for the NHL game-checking script.

    This function parses command-line arguments, initializes configuration and logging,
    sets up the preferred team and Bluesky client, fetches the game schedule, and
    determines whether there are games today or yesterday. It invokes the appropriate
    handling functions for these scenarios.
    """

    # fmt: off
    parser = argparse.ArgumentParser(description="Check NHL games for a specific date.")
    parser.add_argument("--config", type=str, default="config.yaml", help="Path to the configuration file (default: config.yaml).")
    parser.add_argument("--date", type=str, help="Date to check for a game (format: YYYY-MM-DD). Defaults to today's date.")
    parser.add_argument("--nosocial", action="store_true", help="Print messages instead of posting to socials.")
    parser.add_argument("--console", action="store_true", help="Write logs to console instead of a file.")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging.")
    parser.add_argument("--debugsocial", action="store_true", help="Uses 'debug' accounts to test socials.")
    args = parser.parse_args()
    # fmt: on

    # Load configuration
    config = load_config(args.config)

    # Setup logging & log startup info
    otherutils.setup_logging(config, console=args.console, debug=args.debug)
    otherutils.log_startup_info(args, config)

    team_name = config.get("default", {}).get("team_name", "New Jersey Devils")
    preferred_team = Team(team_name)

    # Initialize Bluesky Client
    bluesky_environment = "debug" if args.debugsocial else "prod"
    bluesky_account = config["bluesky"][bluesky_environment]["account"]
    bluesky_password = config["bluesky"][bluesky_environment]["password"]
    bluesky_client = BlueskyClient(account=bluesky_account, password=bluesky_password, nosocial=args.nosocial)
    bluesky_client.login()
    logging.info(f"Bluesky client initialized for environment: {bluesky_environment}.")

    # Load Custom Fonts for Charts
    inter_font_path = os.path.join(RESOURCES_DIR, "Inter-Regular.ttf")
    inter_font = font_manager.FontProperties(fname=inter_font_path)
    # rcParams["font.family"] = inter_font.get_name()

    # Create the GameContext
    context = GameContext(
        config=config, bluesky_client=bluesky_client, nosocial=args.nosocial, debugsocial=args.debugsocial
    )

    # Add Preferred Team to GameContext
    context.preferred_team = preferred_team

    # Fetch season ID
    season_id = schedule.fetch_season_id(preferred_team.abbreviation)
    context.season_id = season_id

    # Determine dates to check
    target_date = args.date if args.date else datetime.now().strftime("%Y-%m-%d")
    target_date_dt = datetime.strptime(target_date, "%Y-%m-%d")
    yesterday = (target_date_dt - timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        # Fetch schedule
        team_schedule = schedule.fetch_schedule(preferred_team.abbreviation, season_id)
        logging.info(f"Fetched schedule for {team_name}.")

        # Check for a game on the target date
        game_today, _ = schedule.is_game_on_date(team_schedule, target_date)
        if game_today:
            context.game = game_today
            handle_is_game_today(game_today, target_date, preferred_team, season_id, context)
            return

        # Check for a game yesterday
        game_yesterday, _ = schedule.is_game_on_date(team_schedule, yesterday)
        if game_yesterday:
            handle_was_game_yesterday(game_yesterday, yesterday, context)
            return

        # No games found
        logging.info(f"No games found for {team_name} on {target_date} or {yesterday}.")

    except Exception as e:
        logging.error(f"Error occurred: {e}", exc_info=True)


if __name__ == "__main__":
    main()
