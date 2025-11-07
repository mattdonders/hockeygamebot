import argparse
import http.server
import logging
import os
import socketserver
import sys
import threading
import time
import warnings
from datetime import datetime, timedelta
from pathlib import Path

from matplotlib import font_manager

import utils.others as otherutils
from core import charts, final, preview, rosters, schedule
from core.charts import teamstats_chart
from core.integrations import nst
from core.live import parse_live_game
from core.models.game_context import GameContext
from core.models.team import Team
from definitions import RESOURCES_DIR
from socials.publisher import SocialPublisher
from utils.config import load_config
from utils.team_details import TEAM_DETAILS

warnings.filterwarnings(
    "ignore",
    message="The 'default' attribute.*`Field\\(\\)`",
    category=UserWarning,
)


class SilentHTTPHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress all HTTP logs


def start_dashboard_server(port=8000, max_retries=5):
    """Start the dashboard web server with error recovery and port file.

    Creates .dashboard_port file containing:
    - Port number
    - Local IP address
    - Dashboard URLs

    Args:
        port: Initial port to try (will increment if in use)
        max_retries: Maximum number of restart attempts

    """
    import errno
    import socket

    # Use pathlib.Path to get the script directory
    os.chdir(Path(__file__).resolve().parent)
    Handler = SilentHTTPHandler

    retry_count = 0
    current_port = port

    while retry_count < max_retries:
        try:
            # Try to bind to the port
            with socketserver.TCPServer(("0.0.0.0", current_port), Handler) as httpd:
                logging.info(
                    f"Dashboard server running at http://0.0.0.0:{current_port}/dashboard.html"
                )

                # Write port file for easy reference
                try:
                    # Get local IP address
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s.connect(("8.8.8.8", 80))
                    local_ip = s.getsockname()[0]
                    s.close()

                    # Write port and IP to file
                    with Path(".dashboard_port").open("w") as f:
                        f.write(f"{current_port}\n")
                        f.write(f"{local_ip}\n")
                        f.write(f"http://localhost:{current_port}/dashboard.html\n")
                        f.write(f"http://{local_ip}:{current_port}/dashboard.html\n")

                    logging.info("Dashboard info written to .dashboard_port")
                    logging.info(
                        f"Network access: http://{local_ip}:{current_port}/dashboard.html"
                    )
                except Exception as e:
                    logging.warning(f"Could not write dashboard port file: {e}")

                # If we had to use a different port, warn user
                if current_port != port:
                    logging.warning(
                        f"Original port {port} unavailable, using {current_port}"
                    )

                # Start serving (this blocks)
                httpd.serve_forever()

        except OSError as e:
            if e.errno == errno.EADDRINUSE:
                # Port is already in use, try next port
                logging.warning(
                    f"Port {current_port} is in use, trying {current_port + 1}"
                )
                current_port += 1
                retry_count += 1
                continue
            # Other OS error, log and retry after delay
            logging.error(f"Dashboard server error: {e}", exc_info=True)
            retry_count += 1
            if retry_count < max_retries:
                import time

                time.sleep(10)
            continue

        except Exception as e:
            # Unexpected error, log and retry
            logging.error(f"Dashboard server crashed: {e}", exc_info=True)
            retry_count += 1
            if retry_count < max_retries:
                logging.info(
                    f"Restarting dashboard server (attempt {retry_count}/{max_retries})..."
                )
                import time

                time.sleep(10)
            continue

    # If we get here, all retries failed
    logging.critical(f"Dashboard server failed to start after {max_retries} attempts")
    logging.critical("Bot will continue running but dashboard will be unavailable")


def start_game_loop(context: GameContext):
    """Manages the main game loop for real-time updates.

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

        # Update monitoring dashboard with current game state
        if hasattr(context, "monitor"):
            context.monitor.update_game_state(context)

        # Type-Narrowing Game Context
        game = context.game
        if game is None:
            # pick your behavior: early return/continue, or raise to hit the outer try/except
            raise RuntimeError("No game data set on context.")

        # If we enter this function on the day of a game (before the game starts), gameState = "FUT"
        # We should send preview posts & then sleep until game time.
        if context.game_state in ["PRE", "FUT"]:
            logging.info("Handling a preview game state: %s", context.game_state)

            # Generate and post the game time preview
            if not context.preview_socials.core_sent:
                game_time_post = preview.format_future_game_post(context.game, context)
                try:
                    # Handles posting + seeding thread roots automatically
                    context.social.post_and_seed(
                        message=game_time_post,
                        platforms="enabled",
                        state=context.preview_socials,
                        message=game_time_post,
                        platforms="enabled",
                        state=context.preview_socials,
                    )
                    context.preview_socials.core_sent = True
                    logging.info("Posted and seeded pre-game thread roots.")
                except Exception as e:
                    logging.exception("Failed to post preview: %s", e)

            if not context.preview_socials.season_series_sent:
                try:
                    team_schedule = schedule.fetch_schedule(context.preferred_team.abbreviation, context.season_id)
                    home_team = game["homeTeam"]["abbrev"]
                    away_team = game["awayTeam"]["abbrev"]
                    opposing_team = away_team if home_team == context.preferred_team.abbreviation else home_team

                    season_series_post = preview.format_season_series_post(
                        team_schedule,
                        context.preferred_team.abbreviation,
                        opposing_team,
                        context,
                    )

                    # Reply into the existing pre-game thread on all enabled platforms
                    context.social.reply(
                        message=season_series_post,
                        platforms="enabled",
                        state=context.preview_socials,  # keeps roots/parents advancing
                    )

                    context.preview_socials.season_series_sent = True
                    logging.info("Posted season series preview (threaded).")
                except Exception as e:
                    logging.exception("Failed to post season series preview: %s", e)

            # Post pre-game team stats chart (reply under the same thread)
            if (
                not context.preview_socials.team_stats_sent
                and context.preview_socials.core_sent
            ):
                try:
                    right_rail_data = schedule.fetch_rightrail(context.game_id)
                    teamstats_data = right_rail_data.get("teamSeasonStats")
                    chart_path = teamstats_chart(context, teamstats_data, ingame=False)

                    if chart_path:
                        msg = f"Pre-game team stats for {context.game_time_of_day}'s game."
                        context.social.reply(
                            message=msg,
                            media=chart_path,
                            platforms="enabled",
                            alt_text="Pre-game team stats comparison",
                            state=context.preview_socials,
                        )
                        context.preview_socials.team_stats_sent = True
                        logging.info("Posted pre-game team stats chart (threaded).")
                    else:
                        logging.info("No team stats chart produced; skipping.")
                except Exception as e:
                    logging.exception("Failed to post pre-game team stats chart: %s", e)

            # Post officials (reply under the same thread)
            if not context.preview_socials.officials_sent:
                try:
                    officials_post = preview.generate_referees_post(context)
                    if officials_post:
                        context.social.reply(
                            message=officials_post,
                            platforms="enabled",
                            state=context.preview_socials,  # keeps roots/parents advancing
                        )
                        context.preview_socials.officials_sent = True
                        logging.info("Posted officials preview (threaded).")
                    else:
                        logging.info("No officials info available; skipping.")
                except Exception as e:
                    logging.exception("Failed to post officials preview: %s", e)

            # Use our auto-sleep calculator now
            if hasattr(context, "monitor"):
                context.monitor.set_status("SLEEPING")
            preview.preview_sleep_calculator(context)

        elif context.game_state in ["PRE", "LIVE", "CRIT"]:
            logging.debug("Game Context: %s", vars(context))
            logging.info("Handling a LIVE game state: %s", context.game_state)

            # Set status to RUNNING when actively processing game
            if hasattr(context, "monitor"):
                context.monitor.set_status("RUNNING")

            if not context.gametime_rosters_set:
                # Get Game-Time Rosters and Combine w/ Pre-Game Rosters
                logging.info("Getting game-time rosters and adding them to existing combined rosters.")
                game_time_rosters = rosters.load_game_rosters(context) or {}
                final_combined_rosters = {**context.combined_roster, **game_time_rosters}
                context.combined_roster = final_combined_rosters
                context.gametime_rosters_set = True

            # Parse Live Game Data
            parse_live_game(context)

            if context.clock.in_intermission:
                intermission_sleep_time = context.clock.seconds_remaining
                logging.info("Game is in intermission - sleep for the remaining time (%ss).", intermission_sleep_time)
                if hasattr(context, "monitor"):
                    context.monitor.set_status("SLEEPING")
                time.sleep(intermission_sleep_time)
            else:
                live_sleep_time = context.config["script"]["live_sleep_time"]
                logging.info(
                    "Sleeping for configured live game time (%ss).", live_sleep_time
                )

                # Now increment the counter sleep for the calculated time above
                context.live_loop_counter += 1
                time.sleep(live_sleep_time)

        elif context.game_state in ["OFF", "FINAL"]:
            logging.info("Game is now over and / or 'Official' - run end of game functions with increased sleep time.")

            # Set status to RUNNING for final game processing
            if hasattr(context, "monitor"):
                context.monitor.set_status("RUNNING")

            # If (for some reason) the bot was started after the end of the game
            # We need to re-run the live loop once to parse all of the events
            if not context.events:
                logging.info(
                    "Bot started after game ended, pass livefeed into event factory to fill events."
                )

                if not context.gametime_rosters_set:
                    # Get Game-Time Rosters and Combine w/ Pre-Game Rosters
                    logging.info("Getting game-time rosters and adding them to existing combined rosters.")
                    game_time_rosters = rosters.load_game_rosters(context) or {}
                    final_combined_rosters = {**context.combined_roster, **game_time_rosters}
                    context.combined_roster = final_combined_rosters
                    context.gametime_rosters_set = True

                # Extract game ID and build the play-by-play URL
                # play_by_play_data = schedule.fetch_playbyplay(game_id)
                # events = play_by_play_data.get("plays", [])

                # Parse Live Game Data
                parse_live_game(context)

            # Retry loop for final content (three stars may not be available immediately)
            max_final_attempts = 10  # Check up to 10 times
            final_attempt = 0
            final_sleep_time = 30  # Wait 30 seconds between attempts

            while final_attempt < max_final_attempts:
                final_attempt += 1

                logging.info(
                    f"Final content check - attempt {final_attempt}/{max_final_attempts}"
                )

                # 1. Post Final Score (should always be ready)
                if not context.final_socials.final_score_sent:
                    try:
                        final_score_post = final.final_score(context)
                        if final_score_post:  # Validate not None
                            context.social.post_and_seed(
                                message=final_score_post,
                                platforms="enabled",
                                state=context.final_socials,
                            )
                            context.final_socials.final_score_sent = True
                            logging.info("Posted and seeded final score thread roots.")
                        else:
                            logging.warning("Final score post returned None")
                    except Exception as e:
                        logging.error(f"Error posting final score: {e}", exc_info=True)
                        if hasattr(context, "monitor"):
                            context.monitor.record_error(
                                f"Final score post failed: {e}"
                            )

                # 2. Post Three Stars (may not be ready immediately)
                if not context.final_socials.three_stars_sent:
                    try:
                        three_stars_post = final.three_stars(context)
                        if three_stars_post:
                            context.social.reply(
                                message=three_stars_post,
                                platforms="enabled",
                                state=context.final_socials,  # uses seeded roots/parents
                            )
                            context.final_socials.three_stars_sent = True
                            logging.info("Posted three stars reply successfully.")
                        else:
                            logging.info("⏳ Three stars not available yet, will retry")
                    except Exception as e:
                        logging.error(f"Error posting three stars: {e}", exc_info=True)
                        if hasattr(context, "monitor"):
                            context.monitor.record_error(
                                f"Three stars post failed: {e}"
                            )

                # 3. Post Team Stats Chart
                if not context.final_socials.team_stats_sent:
                    try:
                        right_rail_data = schedule.fetch_rightrail(context.game_id)
                        team_stats_data = right_rail_data.get("teamGameStats")
                        if team_stats_data:
                            chart_path = charts.teamstats_chart(
                                context, team_stats_data, ingame=True
                            )
                            if chart_path:  # ✅ Validate chart was created
                                chart_message = (
                                    f"Final team stats for tonight's game.\n\n"
                                    f"{context.preferred_team.hashtag} | {context.game_hashtag}"
                                )
                                context.social.reply(
                                    message=chart_message,
                                    media=chart_path,
                                    platforms="enabled",
                                    state=context.final_socials,  # auto-picks the current parent
                                )
                                context.final_socials.team_stats_sent = True
                                logging.info(
                                    "Posted team stats chart reply successfully."
                                )
                            else:
                                logging.warning("Team stats chart returned None")
                        else:
                            logging.warning("Team stats data not available")
                    except Exception as e:
                        logging.error(f"Error posting team stats: {e}", exc_info=True)
                        if hasattr(context, "monitor"):
                            context.monitor.record_error(f"Team stats post failed: {e}")

                # Check if all required content has been posted
                if (
                    context.final_socials.final_score_sent
                    and context.final_socials.three_stars_sent
                    and context.final_socials.team_stats_sent
                ):
                    logging.info("🎉 All final content posted successfully!")
                    end_game_loop(context)
                    return  # Exit the function

                # If not all content posted and we have attempts remaining, sleep and retry
                if final_attempt < max_final_attempts:
                    if hasattr(context, "monitor"):
                        context.monitor.set_status("SLEEPING")
                    logging.info(
                        f"Waiting {final_sleep_time}s before next final content check..."
                    )
                    time.sleep(final_sleep_time)
                    if hasattr(context, "monitor"):
                        context.monitor.set_status("RUNNING")

            # If we exhausted all attempts, log what's missing and exit anyway
            missing_content = []
            if not context.final_socials.final_score_sent:
                missing_content.append("final score")
            if not context.final_socials.three_stars_sent:
                missing_content.append("three stars")
            if not context.final_socials.team_stats_sent:
                missing_content.append("team stats")

            if missing_content:
                logging.warning(f"⚠️  Max final attempts reached. Missing content: {', '.join(missing_content)}")
                if hasattr(context, "monitor"):
                    context.monitor.record_error(
                        f"Incomplete final content: {', '.join(missing_content)}"
                    )

            end_game_loop(context)

        else:
            logging.error(f"Unknown game state: {context.game_state}")
            sys.exit()


def end_game_loop(context: GameContext):
    """Finalizes the game loop and logs the end of the game.

    This function logs the final game summary, including scores, timestamps, and any
    final details. It is the logical endpoint for the script.

    Args:
        context (GameContext): The shared context containing game details, configuration,
            and state management.

    """
    logging.info("#" * 80)
    logging.info(
        "End of the '%s' Hockey Game Bot game.", context.preferred_team.full_name
    )
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
    """Handles pre-game setup and initialization for games occurring today.

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
        f"@ {game['homeTeam']['placeName']['default']} ({game['homeTeam']['abbrev']})",
    )
    logging.info(f"  Venue: {game['venue']['default']}")
    logging.info(f"  Start Time (UTC): {game['startTimeUTC']}")

    # Setup Other Team Object & Other Related Team Functions
    is_preferred_home = game["homeTeam"]["abbrev"] == preferred_team.abbreviation
    other_team_abbreviation = (
        game["awayTeam"]["abbrev"] if is_preferred_home else game["homeTeam"]["abbrev"]
    )
    other_team_name = TEAM_DETAILS[other_team_abbreviation]["full_name"]
    other_team = Team(other_team_name)

    # Add All Teams to GameContext
    context.set_teams(
        preferred=preferred_team,
        other=other_team,
        preferred_homeaway="home" if is_preferred_home else "away",
    )

    # Set hashtags into game context
    context.game_hashtag = (
        f"#{context.away_team.abbreviation}vs{context.home_team.abbreviation}"
    )

    # Get Game ID / Type & Store it in the GameContext
    game_id = game["id"]
    game_type = game["gameType"]
    context.set_game_ids(game_id=game_id, season_id=season_id)
    context.game_type = game_type
    context.game_shortid = str(game_id)[-4:]

    # Set Game Time & Game Time (in local TZ)
    context.game_time = game["startTimeUTC"]
    game_time_local = otherutils.convert_utc_to_localteam_dt(context.game_time, context.preferred_team.timezone)
    game_time_local_str = otherutils.convert_utc_to_localteam(context.game_time, context.preferred_team.timezone)
    context.game_time_local = game_time_local
    context.game_time_local_str = game_time_local_str

    # Get Game Information & Store it in the GameContext
    game_state = game["gameState"]
    context.game_state = game_state
    context.venue = game["venue"]["default"]

    # Load Combined Rosters into Game Context
    context.combined_roster = rosters.load_combined_roster(
        game, preferred_team, other_team, season_id
    )

    # DEBUG Log the GameContext
    logging.debug(f"Full Game Context: {vars(context)}")

    # Pre-Game Setup is Completed
    # Start Game Loop by passing in GameContext
    start_game_loop(context)


def handle_was_game_yesterday(game, yesterday, preferred_team: Team, context: GameContext):
    """Handles logic for games that occurred yesterday.

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
    is_preferred_home = game["homeTeam"]["abbrev"] == preferred_team.abbreviation
    other_team_abbreviation = game["awayTeam"]["abbrev"] if is_preferred_home else game["homeTeam"]["abbrev"]
    other_team_name = TEAM_DETAILS[other_team_abbreviation]["full_name"]
    other_team = Team(other_team_name)

    context.set_teams(
        preferred=preferred_team,
        other=other_team,
        preferred_homeaway="home" if is_preferred_home else "away",
    )

    # Add Game ID to Context (For Consistency)
    context.set_game_ids(game_id=game["id"], season_id=game["season"])

    # Get Final Score & Setup the "Result String"
    pref_score = (
        game["homeTeam"]["score"] if is_preferred_home else game["awayTeam"]["score"]
    )
    other_score = (
        game["awayTeam"]["score"] if is_preferred_home else game["homeTeam"]["score"]
    )
    game_result_str = "defeat" if pref_score > other_score else "lose to"

    # Re-Assign Team Names for Easier Use
    pref_team_name = context.preferred_team.full_name
    other_team_name = context.other_team.full_name

    logging.info(f"Game found yesterday ({yesterday}):")
    logging.info(
        f"  {game['awayTeam']['placeName']['default']} ({game['awayTeam']['abbrev']}) "
        f"@ {game['homeTeam']['placeName']['default']} ({game['homeTeam']['abbrev']})",
    )
    logging.info(f"  Venue: {game['venue']['default']}")
    logging.info(f"  Start Time (UTC): {game['startTimeUTC']}")
    logging.info(
        "  Final Score - %s: %s / %s: %s",
        context.preferred_team.abbreviation,
        pref_score,
        context.other_team.abbreviation,
        other_score,
    )

    logging.info("Getting Game Recap & Description")
    game_stories = schedule.fetch_stories(context.game_id)
    right_rail = schedule.fetch_rightrail(context.game_id)
    # print(game_stories)
    # Game Headline w/ Recap & Game Summary w/ Condensed Game
    game_headline = game_stories["items"][0]["headline"]
    game_headline = (
        f"{game_headline}." if not game_headline.endswith(".") else game_headline
    )

    if "--" in game_stories["items"][0]["summary"]:
        game_summary = game_stories["items"][0]["summary"].split("--")[1].strip()
    else:
        game_summary = game_stories["items"][0]["summary"]

    game_videos = right_rail["gameVideo"]
    game_video_prefix = f"{context.away_team.abbreviation.lower()}-at-{context.home_team.abbreviation.lower()}"
    game_recap_video_slug = game_videos["threeMinRecap"]
    game_recap_url = (
        f"https://www.nhl.com/video/{game_video_prefix}-recap-{game_recap_video_slug}"
    )
    game_condensed_video_slug = game_videos["condensedGame"]
    game_condensed_url = f"https://www.nhl.com/video/{game_video_prefix}-condensed-game-{game_condensed_video_slug}"

    game_recap_msg = f"{game_headline}\n\nGame Recap: {game_recap_url}"
    game_condensed_msg = f"{game_summary}\n\nCondensed Game: {game_condensed_url}"

    try:
        # TBD: Removed threading from Game Recap / Condensed posts for now
        context.social.post(message=game_recap_msg, platforms="enabled")
        context.social.post(message=game_condensed_msg, platforms="enabled")
        logging.info("Posted Game Recap & Condensed Game Videos to Socials.")
    except Exception as e:
        logging.exception("Failed to post recap/condensed game: %s", e)

    logging.info("Generating Season & L10 Team Stat Charts from Natural Stat Trick.")
    team_season_msg = (
        f"Updated season overview & last 10 game stats after the {pref_team_name} "
        f"{game_result_str} the {other_team_name} by a score of {pref_score} to {other_score}."
        f"\n\n{context.preferred_team.hashtag}"
    )
    team_season_fig = nst.generate_team_season_charts(pref_team_name, "sva")
    team_season_fig_last10 = nst.generate_team_season_charts(
        pref_team_name, "sva", lastgames=10
    )
    team_season_fig_all = nst.generate_team_season_charts(pref_team_name, "all")
    team_season_fig_last10_all = nst.generate_team_season_charts(
        pref_team_name, "all", lastgames=10
    )
    team_season_charts = [
        team_season_fig,
        team_season_fig_last10,
        team_season_fig_all,
        team_season_fig_last10_all,
    ]

    try:
        context.social.post(
            message=team_season_msg,
            media=team_season_charts,  # list[str]; Bluesky multi-image, Threads mini-thread
            platforms="enabled",
        )
        logging.info("Posted season charts successfully.")
    except Exception as e:
        logging.exception("Failed to post season charts: %s", e)


def main():
    """Entry point for the NHL game-checking script.

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

    # Start dashboard server in background
    dashboard_thread = threading.Thread(
        target=start_dashboard_server, args=(8000,), daemon=True
    )
    dashboard_thread.start()
    logging.info("Dashboard server started in background")

    team_name = config.get("default", {}).get("team_name", "New Jersey Devils")
    preferred_team = Team(team_name)

    # Initialize Bluesky Client
    # bluesky_environment = "debug" if args.debugsocial else "prod"
    # bluesky_account = config["bluesky"][bluesky_environment]["account"]
    # bluesky_password = config["bluesky"][bluesky_environment]["password"]
    # bluesky_client = BlueskyClient(account=bluesky_account, password=bluesky_password, nosocial=args.nosocial)
    # bluesky_client.login()
    # logging.info(f"Bluesky client initialized for environment: {bluesky_environment}.")

    # Initialize unified Social Publisher (handles Bluesky + Threads)
    # Resolve social mode with clear precedence and no CLI override:
    # 1) ENV (HOCKEYBOT_MODE=prod|debug)
    # 2) YAML (script.mode: prod|debug)
    # 3) default: prod

    env_mode_raw = os.getenv("HOCKEYBOT_MODE", "")
    env_mode = env_mode_raw.strip().lower() if env_mode_raw else ""

    yaml_mode_raw = config.get("script", {}).get("mode", "prod")
    config_mode = str(yaml_mode_raw).strip().lower()

    # Transitional: if the old flag is still present, warn that it's ignored.
    try:
        if getattr(args, "debugsocial", False):
            logging.warning("Flag --debugsocial is set but ignored. Social mode no longer supports CLI debug override.")
    except NameError:
        # args may not exist in some contexts; ignore.
        pass

    if env_mode in {"prod", "debug"}:
        social_mode = env_mode
    elif config_mode in {"prod", "debug"}:
        social_mode = config_mode
    else:
        social_mode = "prod"

    debug_social_flag = social_mode == "debug"

    logging.info(
        "Social mode resolved -> %s [from: ENV=%r, YAML=%r]",
        social_mode,
        env_mode or None,
        config_mode or None,
    )

    # Instantiate publisher; let it read script.nosocial from the YAML
    publisher = SocialPublisher(config=config, mode=social_mode)
    publisher.login_all()  # safe no-op for Threads

    # Log exactly what the publisher is using
    yaml_nosocial = bool(config.get("script", {}).get("nosocial", False))
    logging.info(
        "SocialPublisher initialized (mode=%s, nosocial=%s) [yaml_nosocial=%s]",
        social_mode,
        publisher.nosocial,  # authoritative
        yaml_nosocial,  # helpful for debugging config vs runtime
    )
    # Load Custom Fonts for Charts
    inter_font_path = str(Path(RESOURCES_DIR) / "Inter-Regular.ttf")
    inter_font = font_manager.FontProperties(fname=inter_font_path)
    # rcParams["font.family"] = inter_font.get_name()
    # rcParams["font.family"] = inter_font.get_name()

    # Create the GameContext
    context = GameContext(
        config=config,
        social=publisher,
        nosocial=publisher.nosocial,
        debugsocial=debug_social_flag,
    )

    # Attach the Monitor to BlueSky Client & Schedule Modules
    # bluesky_client.monitor = monitor
    publisher.monitor = context.monitor
    schedule.set_monitor(context.monitor)

    # Add Preferred Team to GameContext
    # context.preferred_team = preferred_team

    # Fetch season ID
    season_id = schedule.fetch_season_id(preferred_team.abbreviation)
    # context.season_id = season_id

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
            handle_is_game_today(
                game_today, target_date, preferred_team, season_id, context
            )
            return

        # Check for a game yesterday
        game_yesterday, _ = schedule.is_game_on_date(team_schedule, yesterday)
        if game_yesterday:
            handle_was_game_yesterday(game_yesterday, yesterday, preferred_team, context)
            return

        # No games found
        logging.info(f"No games found for {team_name} on {target_date} or {yesterday}.")

    except Exception as e:
        logging.error(f"Error occurred: {e}", exc_info=True)
        if hasattr(context, "monitor"):
            context.monitor.record_error(str(e))
            context.monitor.set_status("ERROR")

    finally:
        # Shutdown monitor gracefully
        if "context" in locals() and hasattr(context, "monitor"):
            context.monitor.shutdown()


if __name__ == "__main__":
    main()
