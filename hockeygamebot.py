# pylint: disable=wrong-import-position


import argparse
import json
import logging
import os
import random
import sys
import threading
import time
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import requests
from matplotlib import font_manager

import core.preview as preview
import core.rosters as rosters
import core.schedule as schedule
import utils.others as otherutils
from core import charts, final
from core.charts import teamstats_chart
from core.events.event_cache import GameCache
from core.events.goal import GoalEvent
from core.integrations import injuries, nst
from core.live import parse_live_game
from core.milestones import MilestoneService
from core.models.game_context import GameContext
from core.models.team import Team
from definitions import RESOURCES_DIR
from socials.platforms import NON_X_PLATFORMS
from socials.publisher import SocialPublisher
from socials.utils import normalize_post_refs, write_milestones_index
from socials.x_rate_limiter import XRateLimiter
from utils.config import load_config
from utils.others import normalize_venue_name
from utils.status_monitor import StatusMonitor
from utils.team_details import TEAM_DETAILS

logger = logging.getLogger("hockeygamebot")
warnings.filterwarnings(
    "ignore",
    message="The 'default' attribute.*`Field\\(\\)`",
    category=UserWarning,
)


def _handle_pregame_state(context: GameContext):
    """
    Handle all pre-game (FUT / PRE) behavior:

      - unified pre-game post (core_sent)
      - milestones pre-game post (milestones_sent)
      - officials / referees pre-game post (officials_sent)
      - sleep logic via preview_sleep_calculator
    """
    logger.info("Handling a preview game state: %s", context.game_state)

    cache = getattr(context, "cache", None)

    if not context.preview_socials.core_sent:
        logger.info("Unified pre-game post not yet sent; generating content.")

        chart_path = None
        try:
            right_rail_data = schedule.fetch_rightrail(context.game_id)
            teamstats_data = right_rail_data.get("teamSeasonStats")
            if teamstats_data:
                chart_path = teamstats_chart(context, teamstats_data, ingame=False)
                logger.info("Generated pre-game team stats chart at %s", chart_path)
            else:
                logger.info("No teamSeasonStats in right rail; skipping chart.")
        except Exception as e:
            logger.exception("Failed to generate pre-game team stats chart: %s", e)

        try:
            # Use X-style pre-game copy as the unified pre-game message
            pregame_message = preview.format_pregame_post(context.game, context)
        except Exception as e:
            logger.exception(
                "Failed to format unified pre-game message with format_pregame_post; "
                "falling back to format_future_game_post: %s",
                e,
            )
            pregame_message = preview.format_future_game_post(context.game, context)

        try:
            results = context.social.post_and_seed(
                message=pregame_message,
                media=chart_path,
                platforms="enabled",  # all enabled platforms, including X
                event_type="pregame",
                state=context.preview_socials,
            )

            # Mark the unified pre-game post as sent
            context.preview_socials.core_sent = True

            if cache is not None:
                cache.mark_pregame_sent("core", results)
                cache.save()

            logger.info("Posted unified pre-game post with chart (if available).")
        except Exception as e:
            logger.exception("Failed to post unified pre-game preview: %s", e)

    # --- Officials remain a separate, non-X threaded reply ---
    if not context.preview_socials.officials_sent:
        try:
            officials_post = preview.generate_referees_post(context)
            if officials_post:
                context.social.reply(
                    message=officials_post,
                    platforms=NON_X_PLATFORMS,
                    state=context.preview_socials,
                )
                context.preview_socials.officials_sent = True

                if cache is not None:
                    cache.mark_pregame_sent("officials")
                    cache.save()

                logger.info("Posted officials preview (threaded).")
            else:
                logger.info("No officials info available; skipping.")
        except Exception as e:
            logger.exception("Failed to post officials preview: %s", e)

    # --- Milestone Watch / Preview Post ---
    if context.milestone_service is not None and not context.preview_socials.milestones_sent:
        try:
            milestone_msg = preview.generate_pregame_milestones_post(context)

            if milestone_msg:
                # We only enter here if milestones EXIST
                results = context.social.reply(
                    message=milestone_msg,
                    platforms="enabled",  # all enabled platforms, including X
                    state=context.preview_socials,
                )

                post_refs = normalize_post_refs(results)

                # Only write the JSON index if we actually have published posts
                if post_refs:
                    write_milestones_index(context, milestone_msg, post_refs)
                    logger.info(
                        "Posted pre-game milestone preview for %d hits.",
                        len(context.preview_socials.milestone_hits),
                    )
                else:
                    logger.warning(
                        "Milestone preview posted but returned no PostRefs — skipping milestone index write."
                    )

            else:
                # No milestones at all → do not write index file
                logger.info("No milestones for this game — marking milestones_sent=True and moving on.")

            # Set flag regardless to avoid repeated attempts
            context.preview_socials.milestones_sent = True

            if cache is not None:
                cache.mark_pregame_sent("milestones")
                cache.save()

        except Exception:
            logger.exception("Failed to post pre-game milestone preview.")

    # --- Sleep until closer to game time ---
    if hasattr(context, "monitor"):
        context.monitor.set_status("SLEEPING")
    preview.preview_sleep_calculator(context)


def _handle_live_state(context: GameContext):
    logger.debug("Game Context: %s", vars(context))
    logger.info("Handling a LIVE game state: %s", context.game_state)

    # Set status to RUNNING when actively processing game
    if hasattr(context, "monitor"):
        context.monitor.set_status("RUNNING")

    if not context.gametime_rosters_set:
        # Get Game-Time Rosters and Combine w/ Pre-Game Rosters
        logger.info("Getting game-time rosters and adding them to existing combined rosters.")
        game_time_rosters = rosters.load_game_rosters(context)
        final_combined_rosters = {
            **context.combined_roster,
            **game_time_rosters,
        }
        context.combined_roster = final_combined_rosters
        context.gametime_rosters_set = True

    # Parse Live Game Data
    parse_live_game(context)

    if context.clock.in_intermission:
        intermission_sleep_time = context.clock.seconds_remaining
        logger.info(
            "Game is in intermission - sleep for the remaining time (%ss).",
            intermission_sleep_time,
        )
        if hasattr(context, "monitor"):
            context.monitor.set_status("SLEEPING")
        time.sleep(intermission_sleep_time)
    else:
        live_sleep_time = context.config["script"]["live_sleep_time"]
        logger.info("Sleeping for configured live game time (%ss).", live_sleep_time)

        # Now increment the counter sleep for the calculated time above
        context.live_loop_counter += 1
        time.sleep(live_sleep_time)


def _handle_postgame_state(context: GameContext):
    # Set Constants for Stay-Away to Send Highlights and GOAL GIFs / MP4s
    PENDING_GOAL_RETRIES = 4
    PENDING_GOAL_SLEEP = 20  # seconds

    logger.info("Game is now over and / or 'Official' - run end of game functions with increased sleep time.")

    # Set status to RUNNING for final game processing
    if hasattr(context, "monitor"):
        context.monitor.set_status("RUNNING")

    # If (for some reason) the bot was started after the end of the game
    # We need to re-run the live loop once to parse all of the events
    if not context.events:
        logger.info("Bot started after game ended, pass livefeed into event factory to fill events.")

        if not context.gametime_rosters_set:
            # Get Game-Time Rosters and Combine w/ Pre-Game Rosters
            logger.info("Getting game-time rosters and adding them to existing combined rosters.")
            game_time_rosters = rosters.load_game_rosters(context)
            final_combined_rosters = {
                **context.combined_roster,
                **game_time_rosters,
            }
            context.combined_roster = final_combined_rosters
            context.gametime_rosters_set = True

        # Extract game ID and build the play-by-play URL
        game_id = context.game_id
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
        all_content_posted = True

        logger.info(f"Final content check - attempt {final_attempt}/{max_final_attempts}")

        # 1. Post Final Score (should always be ready)
        if not context.final_socials.final_score_sent:
            try:
                final_score_post = final.final_score(context)
                if final_score_post:  # Validate not None
                    results = context.social.post_and_seed(
                        message=final_score_post,
                        platforms="enabled",  # Bsky + Threads + X
                        event_type="final_summary",  # uses X allowlist
                        state=context.final_socials,
                    )
                    context.final_socials.final_score_sent = True
                    logger.info("Posted and seeded final score thread roots.")
                else:
                    logger.warning("Final score post returned None")
            except Exception as e:
                logger.error(f"Error posting final score: {e}", exc_info=True)
                if hasattr(context, "monitor"):
                    context.monitor.record_error(f"Final score post failed: {e}")

        # 2. Post Three Stars (may not be ready immediately)
        if not context.final_socials.three_stars_sent:
            try:
                three_stars_post = final.three_stars(context)
                if three_stars_post:
                    res = context.social.reply(
                        message=three_stars_post,
                        platforms="enabled",  # Bsky + Threads + X
                        event_type="three_stars",  # uses X allowlist
                        state=context.final_socials,  # uses seeded roots/parents
                    )
                    context.final_socials.three_stars_sent = True
                    logger.info("Posted three stars reply successfully.")
                else:
                    logger.info("⏳ Three stars not available yet, will retry")
                    all_content_posted = False
            except Exception as e:
                logger.error(f"Error posting three stars: {e}", exc_info=True)
                if hasattr(context, "monitor"):
                    context.monitor.record_error(f"Three stars post failed: {e}")

        # 3. Post Team Stats Chart
        if not context.final_socials.team_stats_sent:
            try:
                right_rail_data = schedule.fetch_rightrail(context.game_id)
                team_stats_data = right_rail_data.get("teamGameStats")
                if team_stats_data:
                    chart_path = charts.teamstats_chart(context, team_stats_data, ingame=True)
                    if chart_path:  # ✅ Validate chart was created
                        chart_message = f"Final team stats for tonight's game.\n\n{context.preferred_team.hashtag} | {context.game_hashtag}"
                        res = context.social.reply(
                            message=chart_message,
                            media=chart_path,
                            platforms="enabled",  # Bsky + Threads + X
                            event_type="final_summary",  # uses X allowlist
                            state=context.final_socials,  # auto-picks the current parent
                        )
                        context.final_socials.team_stats_sent = True
                        logger.info("Posted team stats chart reply successfully.")
                    else:
                        logger.warning("Team stats chart returned None")
                else:
                    logger.warning("Team stats data not available")
            except Exception as e:
                logger.error(f"Error posting team stats: {e}", exc_info=True)
                if hasattr(context, "monitor"):
                    context.monitor.record_error(f"Team stats post failed: {e}")

            # 4. Calculate Any Goalie Milestones
            if context.milestone_service is not None:
                winning_goalie_id, was_shutout = final.infer_goalie_result_from_boxscore(context)

                if winning_goalie_id is not None:
                    try:
                        goalie_hits = context.milestone_service.handle_postgame_goalie_milestones(
                            goalie_id=winning_goalie_id,
                            won=True,
                            got_shutout=was_shutout,
                        )
                    except Exception:
                        logger.exception("Error applying goalie post-game milestones")
                        goalie_hits = []

                    if goalie_hits:
                        logging.info("Goalie Hits: %s", goalie_hits)
                        # However you're storing final milestones for social posts:
                        if hasattr(context, "final_socials"):
                            context.final_socials.milestone_hits.extend(goalie_hits)

                    # Persist updated wins/shutouts
                    try:
                        context.milestone_service.flush_snapshot_cache()
                    except Exception:
                        logger.exception("Failed to flush milestone snapshot cache after goalie milestones.")

            # 5. Post post-game milestones (goals + goalie wins/shutouts)
            if (
                context.milestone_service is not None
                and context.final_socials is not None
                and context.final_socials.milestone_hits  # <- non-empty
            ):
                milestone_msg = final.generate_final_milestones_post(context)

                if milestone_msg:
                    context.social.post(
                        message=milestone_msg,
                        platforms="enabled",  # Milestones should go to all socials
                        state=context.final_socials,
                    )
                    # If you want a sent-flag:
                    context.final_socials.milestones_sent = True  # optional new bool on EndOfGameSocial

        # Check if all required content has been posted
        if (
            context.final_socials.final_score_sent
            and context.final_socials.three_stars_sent
            and context.final_socials.team_stats_sent
        ):
            logger.info("⏳ Running a few intervals to wait for any pending GIFs!")
            wait_for_goal_gifs(context)

            logger.info("🎉 All final content posted successfully!")
            end_game_loop(context)
            return  # Exit the function

        # If not all content posted and we have attempts remaining, sleep and retry
        if final_attempt < max_final_attempts:
            if hasattr(context, "monitor"):
                context.monitor.set_status("SLEEPING")
            logger.info(f"Waiting {final_sleep_time}s before next final content check...")
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
        logger.warning(f"⚠️  Max final attempts reached. Missing content: {', '.join(missing_content)}")
        if hasattr(context, "monitor"):
            context.monitor.record_error(f"Incomplete final content: {', '.join(missing_content)}")

    end_game_loop(context)


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
    # HYDRATE PRE-GAME SOCIAL STATE FROM CACHE (ONCE)
    # ------------------------------------------------------------------------------
    cache = getattr(context, "cache", None)
    if cache is not None and hasattr(context, "preview_socials"):
        mapping = [
            ("core", "core_sent"),
            ("officials", "officials_sent"),
            ("milestones", "milestones_sent"),
        ]
        for kind, attr in mapping:
            if hasattr(context.preview_socials, attr) and cache.is_pregame_sent(kind):
                setattr(context.preview_socials, attr, True)

        roots = cache.get_pregame_root_refs()
        if roots:
            logger.info("Restoring pre-game thread roots from cache: %s", roots)
            context.social.restore_roots_from_cache(roots, state=context.preview_socials)

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

        # If we enter this function on the day of a game (before the game starts), gameState = "FUT"
        # We should send preview posts & then sleep until game time.
        if context.game_state in ["PRE", "FUT"]:
            _handle_pregame_state(context)

        elif context.game_state in ["LIVE", "CRIT"]:
            _handle_live_state(context)

        elif context.game_state in ["OFF", "FINAL"]:
            _handle_postgame_state(context)

        else:
            logger.error(f"Unknown game state: {context.game_state}")
            print(context.game_state)
            sys.exit()


def wait_for_goal_gifs(context: GameContext):
    PENDING_GOAL_RETRIES = 4
    PENDING_GOAL_SLEEP = 20

    for attempt in range(PENDING_GOAL_RETRIES):
        all_events = getattr(context, "events", []) or []

        pending_goals = [
            e
            for e in all_events
            if isinstance(e, GoalEvent)
            and getattr(e, "is_preferred", False)
            and not getattr(e, "goal_gif_generated", False)
        ]

        if not pending_goals:
            logger.info("All preferred goal GIFs are now generated or skipped.")
            return

        logger.info(
            "Pending GIF attempt %d/%d — %d preferred goals still missing GIFs.",
            attempt + 1,
            PENDING_GOAL_RETRIES,
            len(pending_goals),
        )

        for goal in pending_goals:
            try:
                goal.check_and_add_gif(context)
            except Exception as e:
                logger.exception(
                    "Error while retrying GIF for GoalEvent[%s]: %s",
                    getattr(goal, "event_id", "unknown"),
                    e,
                )

        if attempt < PENDING_GOAL_RETRIES - 1:
            logger.info("Sleeping %ss before next GIF retry attempt...", PENDING_GOAL_SLEEP)
            time.sleep(PENDING_GOAL_SLEEP)

    logger.warning("Some preferred goal GIFs are still pending after maximum retries.")


def end_game_loop(context: GameContext):
    """
    Finalizes the game loop and logs the end of the game.

    This function logs the final game summary, including scores, timestamps, and any
    final details. It is the logical endpoint for the script.

    Args:
        context (GameContext): The shared context containing game details, configuration,
            and state management.
    """

    logger.info("#" * 80)
    logger.info("End of the '%s' Hockey Game Bot game.", context.preferred_team.full_name)
    logger.info(
        "Final Score: %s: %s / %s: %s",
        context.preferred_team.full_name,
        context.preferred_team.score,
        context.other_team.full_name,
        context.other_team.score,
    )
    logger.info("TIME: %s", datetime.now())
    logger.info("%s\n", "#" * 80)
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

    logger.info(f"Game found today ({target_date}):")
    logger.info(
        f"  {game['awayTeam']['placeName']['default']} ({game['awayTeam']['abbrev']}) "
        f"@ {game['homeTeam']['placeName']['default']} ({game['homeTeam']['abbrev']})"
    )
    logger.info(f"  Venue: {game['venue']['default']}")
    logger.info(f"  Start Time (UTC): {game['startTimeUTC']}")

    # Since there is a game today, we want to now create our status / cache file
    # This is used to cache events AND to manage live bots for the Game Bot Dashboard
    # Initialize per-game StatusMonitor now that we know there is a game today.
    team_slug = preferred_team.abbreviation.lower()  # e.g. "njd", "pit"
    status_path = Path(f"status_{team_slug}.json")

    monitor = StatusMonitor(status_path)
    context.monitor = monitor

    # Attach the monitor to SocialPublisher & schedule module
    if hasattr(context, "social") and context.social is not None:
        context.social.monitor = monitor
    schedule.set_monitor(monitor)

    # Optional: mark as STARTING
    monitor.set_status("STARTING")

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

    # Generate Team Slug (for File Name Separation)
    file_team_slug = context.preferred_team.abbreviation

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
    game_time_local = otherutils.convert_utc_to_localteam_dt(context.game_time, context.preferred_team.timezone)
    game_time_local_str = otherutils.convert_utc_to_localteam(context.game_time, context.preferred_team.timezone)
    context.game_time_local = game_time_local
    context.game_time_local_str = game_time_local_str

    # Get Game Information & Store it in the GameContext
    game_state = game["gameState"]
    context.game_state = game_state

    # Set (& Normalize Venue Name)
    venue = game["venue"]["default"]
    context.venue = normalize_venue_name(venue)

    # Load Combined Rosters into Game Context
    preferred_roster, other_roster, combined_roster = rosters.load_team_rosters(preferred_team, other_team, season_id)
    context.combined_roster = combined_roster
    context.preferred_roster = preferred_roster
    context.other_roster = other_roster

    cache_dir = context.config.get("script", {}).get("cache_dir", "./data/cache")
    cache_dir_path = Path(cache_dir)
    season_dir = cache_dir_path / str(season_id)
    season_dir.mkdir(parents=True, exist_ok=True)

    # Fetch injury info for the preferred team (season-ending year)
    # season_id in your code is likely like "20252026" -> we need 2026
    season_end_year = int(str(season_id)[-4:])

    try:
        injury_records = injuries.get_team_injuries_from_hockey_reference(
            preferred_team.abbreviation,
            season_end_year,
            cache_root=season_dir,
        )
        injured_names = injuries.build_injured_name_set(injury_records)
        logger.info(
            "Injuries: Hockey-Reference reports %d injured players for %s",
            len(injury_records),
            preferred_team.abbreviation,
        )
    except Exception:
        logger.exception("Injuries: failed to fetch/parse Hockey-Reference injuries")
        injury_records = []
        injured_names = set()

    # Cache the Injury Set in Context for Later Use
    context.injured_players = injured_names

    for injury in injury_records:
        logger.info(f"{injury}")

    # Per-game milestone snapshot cache
    milestone_cache_path = season_dir / f"{game_id}_{file_team_slug}-milestones.json"
    logger.info("Milestone snapshot cache path: %s", milestone_cache_path)

    # Extract player IDs from preferred roster for milestone checks
    player_ids = list(preferred_roster.keys())

    # Initialize MilestoneService and preload roster
    # This will be used during live game parsing to check for milestones on goals/assists
    try:
        thresholds = context.config.get("milestones", {})
        milestone_session = requests.Session()

        context.milestone_service = MilestoneService(
            thresholds=thresholds,
            session=milestone_session,
            snapshot_cache_path=milestone_cache_path,
        )

        # Preload snapshots for everyone on the combined roster.
        # This will be cheap on re-runs because it uses the per-game cache.
        context.milestone_service.preload_for_roster(player_ids)

        # Debug logging of baselines (what you're already doing)
        context.milestone_service.log_roster_baselines(
            player_ids,
            player_name_resolver=lambda pid: context.preferred_roster.get(pid, str(pid)),
        )

        # Compute pregame milestones (games-played *hits* + stat *watches*)
        milestones_gp, milestones_watches = context.milestone_service.get_pregame_milestones_for_roster(
            player_ids,
            player_name_resolver=lambda pid: context.preferred_roster.get(pid, str(pid)),
        )

        # Filter out Injury Players (by Name) so we don't generate milestone previews for them
        def is_injured(pid: int) -> bool:
            # Out preferred_roster maps {player_id: "Full Name"}
            name = context.preferred_roster.get(pid, "")
            name_norm = name.lower().strip()
            logging.info("Checking if player is injured: %s (ID: %s)", name_norm, pid)
            return name_norm in injured_names

        filtered_milestones_gp = []
        for ms in milestones_gp:
            if is_injured(ms.player_id):
                logger.info(
                    "Skipping milestone HIT for injured player: %s (%s)",
                    context.preferred_roster.get(ms.player_id, str(ms.player_id)),
                    ms.label,
                )
                continue
            filtered_milestones_gp.append(ms)

        filtered_milestones_watches = []
        for watch in milestones_watches:
            if is_injured(watch.player_id):
                logger.info(
                    "Skipping milestone WATCH for injured player: %s (%s)",
                    context.preferred_roster.get(watch.player_id, str(watch.player_id)),
                    watch.label,
                )
                continue
            filtered_milestones_watches.append(watch)

        # Clip Max Watches by our Threshold
        max_watches = thresholds.get("max_watches", 3)
        milestones_watches = sorted(milestones_watches, key=lambda w: w.remaining)[:max_watches]

        # Save on the social state for later formatting
        context.preview_socials.milestone_hits = filtered_milestones_gp
        context.preview_socials.milestone_watches = filtered_milestones_watches

        for ms in filtered_milestones_gp:
            logging.info("%s", str(ms))

        for ms in filtered_milestones_watches:
            logging.info("%s", str(ms))

        # Persist any new snapshots fetched for this game
        context.milestone_service.flush_snapshot_cache()

        logger.info(
            "MilestoneService initialized and roster preloaded for %d players.",
            len(player_ids),
        )
    except Exception:
        logger.exception("Failed to initialize or preload MilestoneService; milestones will be disabled for this game.")
        context.milestone_service = None

    finally:
        # Always try to flush snapshots if we created the service at all
        if context.milestone_service is not None:
            try:
                context.milestone_service.flush_snapshot_cache()
            except Exception:
                logger.exception("Failed to flush milestone snapshot cache.")

    # Initialize restart-safe cache
    cache_dir = context.config.get("script", {}).get("cache_dir", "./data/cache")
    context.cache = GameCache(
        root_dir=cache_dir,
        season_id=str(season_id),
        game_id=str(game_id),
        team_abbrev=context.preferred_team.abbreviation,
    )
    context.cache.load()

    # DEBUG Log the GameContext
    logger.debug(f"Full Game Context: {vars(context)}")

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
    logger.debug("No play-by-play parsing performed for yesterday's game.")

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

    logger.info(f"Game found yesterday ({yesterday}):")
    logger.info(
        f"  {game['awayTeam']['placeName']['default']} ({game['awayTeam']['abbrev']}) "
        f"@ {game['homeTeam']['placeName']['default']} ({game['homeTeam']['abbrev']})"
    )
    logger.info(f"  Venue: {game['venue']['default']}")
    logger.info(f"  Start Time (UTC): {game['startTimeUTC']}")
    logger.info(
        f"  Final Score - {context.preferred_team.abbreviation}: {pref_score} / {context.other_team.abbreviation}: {other_score}"
    )

    logger.info("Getting Game Recap & Description")
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
    game_video_prefix = f"{context.away_team.abbreviation.lower()}-at-{context.home_team.abbreviation.lower()}"
    game_recap_video_slug = game_videos["threeMinRecap"]
    game_recap_url = f"https://www.nhl.com/video/{game_video_prefix}-recap-{game_recap_video_slug}"
    game_condensed_video_slug = game_videos["condensedGame"]
    game_condensed_url = f"https://www.nhl.com/video/{game_video_prefix}-condensed-game-{game_condensed_video_slug}"

    game_recap_msg = f"{game_headline}\n\nGame Recap: {game_recap_url}"
    game_condensed_msg = f"{game_summary}\n\nCondensed Game: {game_condensed_url}"

    try:
        # TBD: Removed threading from Game Recap / Condensed posts for now
        context.social.post(message=game_recap_msg, platforms=NON_X_PLATFORMS)
        context.social.post(message=game_condensed_msg, platforms=NON_X_PLATFORMS)
        logger.info("Posted Game Recap & Condensed Game Videos to non-X platforms.")
    except Exception as e:
        logger.exception("Failed to post recap/condensed game to non-X platforms: %s", e)

    logger.info("Generating Season & L10 Team Stat Charts from Natural Stat Trick.")
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

    try:
        context.social.post(
            message=team_season_msg,
            media=team_season_charts,  # list[str]; Bluesky multi-image, Threads mini-thread
            platforms=NON_X_PLATFORMS,
        )
        logger.info("Posted season charts successfully.")
    except Exception as e:
        logger.exception("Failed to post season charts: %s", e)

    # X / Twitter: Single Combined Post w/ Charts & Recap Link
    game_recap_msg = f"{game_headline}\n\nGame Recap: {game_recap_url}"
    game_condensed_msg = f"{game_summary}\n\nCondensed Game: {game_condensed_url}"

    # X/Twitter: single combined message (headline + stats context + recap link)
    x_lead_emoji = "🚨" if pref_score > other_score else "😞"
    x_combined_msg = (
        f"{x_lead_emoji} {game_headline}\n\n"  # <-- headline + double line break
        f"Updated season overview & last 10 game stats after the "
        f"{pref_team_name} {game_result_str} the {other_team_name} by a score of "
        f"{pref_score} to {other_score}."
        f"\n\nGame Recap: {game_recap_url}"  # <-- recap link
        f"\n\n{context.preferred_team.hashtag}"  # <-- hashtag on its own line
    )

    try:
        context.social.post(
            message=x_combined_msg,
            media=team_season_charts,  # X will render them in a 2x2 grid
            platforms=["x"],
        )
        logger.info("Posted combined recap + charts post to X.")
    except Exception as e:
        logger.exception("Failed to post combined recap + charts to X: %s", e)


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
    parser.add_argument("--config", type=str, default="config/config.yaml", help="Path to the configuration file (default: config.yaml).")
    parser.add_argument("--date", type=str, help="Date to check for a game (format: YYYY-MM-DD). Defaults to today's date.")
    parser.add_argument("--nosocial", action="store_true", help="Print messages instead of posting to socials.")
    parser.add_argument("--dry-run", dest="nosocial", action="store_true", help="Alias for --nosocial (no posting).")
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
    # bluesky_environment = "debug" if args.debugsocial else "prod"
    # bluesky_account = config["bluesky"][bluesky_environment]["account"]
    # bluesky_password = config["bluesky"][bluesky_environment]["password"]
    # bluesky_client = BlueskyClient(account=bluesky_account, password=bluesky_password, nosocial=args.nosocial)
    # bluesky_client.login()
    # logger.info(f"Bluesky client initialized for environment: {bluesky_environment}.")

    # Initialize unified Social Publisher (handles Bluesky + Threads)
    # Resolve social mode with clear precedence and no CLI override:
    # 1) ENV (HOCKEYBOT_MODE=prod|debug)
    # 2) YAML (script.mode: prod|debug)
    # 3) default: prod

    env_mode_raw = os.getenv("HOCKEYBOT_MODE", "")
    env_mode = env_mode_raw.strip().lower() if env_mode_raw else ""

    script_cfg = config.get("script", {}) or {}
    yaml_mode_raw = script_cfg.get("post_mode")
    if yaml_mode_raw is None:
        yaml_mode_raw = script_cfg.get("mode", "prod")  # legacy
        logger.warning("Config 'script.mode' is deprecated; use 'script.post_mode'.")
    config_mode = str(yaml_mode_raw).strip().lower()

    # Transitional: if the old flag is still present, warn that it's ignored.
    try:
        if getattr(args, "debugsocial", False):
            logger.warning("Flag --debugsocial is set but ignored. Social mode no longer supports CLI debug override.")
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

    logger.info(
        "Social mode resolved -> %s [from: ENV=%r, YAML=%r]",
        social_mode,
        env_mode or None,
        config_mode or None,
    )

    # --- NEW: resolve nosocial with CLI override ---
    yaml_nosocial = bool(config.get("script", {}).get("nosocial", False))
    cli_nosocial = bool(getattr(args, "nosocial", False))  # True only if flag provided
    effective_nosocial = True if cli_nosocial else yaml_nosocial

    # Build XRateLimiter (if X/Twitter is enabled) and pass it to the publisher
    cache_dir = Path(config.get("script", {}).get("cache_dir", "./data/cache"))
    socials_cfg = config.get("socials", {}) or {}
    x_rate_limiter = None
    if socials_cfg.get("x") or socials_cfg.get("twitter"):
        x_rate_limiter = XRateLimiter(
            team_slug=preferred_team.abbreviation.lower(),
            base_cache_dir=cache_dir,
        )

    # Instantiate publisher; let it read script.nosocial from the YAML
    publisher = SocialPublisher(
        config=config, mode=social_mode, nosocial=effective_nosocial, monitor=None, x_rate_limiter=x_rate_limiter
    )

    # Only log in when we might post
    if not publisher.nosocial:
        publisher.login_all()

    # Log exactly what the publisher is using
    logger.info(
        "SocialPublisher initialized (mode=%s, nosocial=%s) [cli_nosocial=%s, yaml_nosocial=%s]",
        social_mode,
        publisher.nosocial,  # authoritative value used internally
        cli_nosocial,
        yaml_nosocial,
    )

    # Load Custom Fonts for Charts
    inter_font_path = os.path.join(RESOURCES_DIR, "Inter-Regular.ttf")
    inter_font = font_manager.FontProperties(fname=inter_font_path)
    # rcParams["font.family"] = inter_font.get_name()

    # Create the GameContext
    context = GameContext(
        config=config,
        social=publisher,
        nosocial=publisher.nosocial,
        debugsocial=debug_social_flag,
    )

    # Set Active (Global) Game Context
    GameContext.set_active(context)

    # Add Preferred Team to GameContext
    context.preferred_team = preferred_team

    # Stagger startup for multi-scaling of bot to avoid API calls on the same second
    initial_delay = random.uniform(0, 20)
    logger.info("Initial startup delay for this process: %.1fs", initial_delay)
    time.sleep(initial_delay)

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
        logger.info(f"Fetched schedule for {team_name}.")

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
        logger.info(f"No games found for {team_name} on {target_date} or {yesterday}.")

    except Exception as e:
        logger.error(f"Error occurred: {e}", exc_info=True)
        if hasattr(context, "monitor"):
            context.monitor.record_error(str(e))
            context.monitor.set_status("ERROR")

    finally:
        # Shutdown monitor gracefully
        if "context" in locals() and hasattr(context, "monitor"):
            context.monitor.shutdown()


if __name__ == "__main__":
    main()
