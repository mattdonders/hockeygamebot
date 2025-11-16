import logging
import time

import requests

from core import schedule
from core.events.factory import EventFactory
from core.models.game_context import GameContext
from core.play_by_play import parse_play_by_play_with_names
from utils.others import safe_remove

logger = logging.getLogger(__name__)


def process_removed_goal(goal, context):
    """Remove a goal from all relevant lists and caches."""
    pref_team = context.preferred_team.team_name
    goals_list = context.pref_goals if goal.event_team == pref_team else context.other_goals

    logger.info(f"Removing goal by {goal.event_team}. Event ID: {goal.event_id}")

    # Safely remove the goal from all relevant collections
    safe_remove(goal, context.all_goals)
    safe_remove(goal, goals_list)
    safe_remove(goal, goal.cache)

    # Delete the goal object if needed
    del goal


def detect_removed_goals(context, all_plays):
    """
    Detect and handle goals that are no longer in the live feed.
    Iterates through all goals, checks their status using `was_goal_removed`,
    and removes them if necessary.
    """
    try:
        # Iterate over a copy of the list to avoid modification issues
        for goal in context.all_goals[:]:
            # Check if the goal has been removed
            if goal.was_goal_removed(all_plays):
                logger.info("Goal removed: Event ID %s", goal.event_id)
                process_removed_goal(goal, context)
            else:
                logger.debug(
                    "Goal still valid or pending removal: Event ID %s (Counter: %d)",
                    goal.event_id,
                    goal.event_removal_counter,
                )
    except Exception as e:
        # Log any unexpected exceptions
        logger.error("Encountered an exception while detecting removed goals.")
        logger.exception(e)


def parse_live_game(context: GameContext):
    """
    Parse live game events via Event Factory.
    Restart-safe:
      - Non-goal events are skipped if already processed (via context.cache).
      - Goal events are always re-evaluated each loop (for highlight/score updates).
    """

    play_by_play_data = schedule.fetch_playbyplay(context.game_id)
    all_events = play_by_play_data.get("plays", [])

    logger.debug("Number of *TOTAL* Events Retrieved from PBP: %s", len(all_events))
    logger.info("%s total event(s) detected in PBP - checking for new events.", len(all_events))

    goal_events = [event for event in all_events if event.get("typeDescKey") == "goal"]
    logger.debug("Number of *GOAL* Events Retrieved from PBP: %s", len(goal_events))

    # Be defensive about types
    last_sort_order = int(getattr(context, "last_sort_order", 0) or 0)
    new_events = [e for e in all_events if int(e.get("sortOrder", 0)) > last_sort_order]
    num_new_events = len(new_events)
    new_plays = num_new_events != 0

    # ✅ Correct message based on new_plays
    if not new_plays:
        logger.info(
            "No new plays detected. This loop will catch any missed events "
            "and also check for scoring changes on existing goals."
        )
    else:
        logger.info("%s new event(s) detected - looping through them now.", num_new_events)

    # We pass the entire list into the factory so missed events can still be created.
    # BUT we gate non-goals with the persistent cache to avoid duplicates across restarts.
    skipped_non_goals = 0
    processed_events = 0

    for event in all_events:
        event_type = event.get("typeDescKey")
        is_goal = event_type == "goal"

        # Persistent cache gating for non-goal events
        ev_id = event.get("eventId")
        if not is_goal and getattr(context, "cache", None) and ev_id is not None:
            if context.cache.has_seen(ev_id):
                skipped_non_goals += 1

                logger.debug("🔍 Skipping cached non-goal: eventType=%s / eventId=%s (restart-safe)", event_type, ev_id)
                # Already processed in a previous run/loop; skip creating it again
                continue

        # Increment Processed Event Count
        processed_events += 1

        # Dispatch to factory (goal events re-evaluate every loop)
        EventFactory.create_event(event, context, new_plays)

        # Update last_sort_order fast-gate (ignore weird sentinel values if any)
        try:
            sort_order = int(event.get("sortOrder", 0))
        except Exception:
            sort_order = 0

        if sort_order > last_sort_order and sort_order < 9000:
            context.last_sort_order = sort_order
            last_sort_order = sort_order  # keep local in sync

        # Mark non-goal events as processed in the persistent cache
        if not is_goal and getattr(context, "cache", None) and ev_id is not None:
            context.cache.mark_seen(ev_id, sort_order)
            # Persist immediately or based on config
            flush_every = int(context.config.get("script", {}).get("cache_flush_every_events", 1))
            if flush_every == 1:
                context.cache.save()

    # If batching, persist once at end
    if getattr(context, "cache", None):
        flush_every = int(context.config.get("script", {}).get("cache_flush_every_events", 1))
        if flush_every > 1:
            context.cache.save()

    if processed_events or skipped_non_goals:
        logger.info(
            "Live parse summary: %s event(s) processed, %s cached non-goal event(s) skipped (restart-safe).",
            processed_events,
            skipped_non_goals,
        )

    # After event creation is completed, let's check for deleted goals (usually for challenges)
    # detect_removed_goals(context, all_events)
