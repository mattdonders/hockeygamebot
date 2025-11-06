import logging

from core import schedule
from core.events.factory import EventFactory
from core.models.game_context import GameContext
from utils.others import safe_remove


def process_removed_goal(goal, context):
    """Remove a goal from all relevant lists and caches."""
    pref_team = context.preferred_team.team_name
    goals_list = context.pref_goals if goal.event_team == pref_team else context.other_goals

    logging.info(f"Removing goal by {goal.event_team}. Event ID: {goal.event_id}")

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
                logging.info("Goal removed: Event ID %s", goal.event_id)
                process_removed_goal(goal, context)
            else:
                logging.debug(
                    "Goal still valid or pending removal: Event ID %s (Counter: %d)",
                    goal.event_id,
                    goal.event_removal_counter,
                )
    except Exception as e:
        # Log any unexpected exceptions
        logging.error("Encountered an exception while detecting removed goals.")
        logging.exception(e)


def parse_live_game(context: GameContext):
    """
    Parse live game events via Event Factory.
    """

    play_by_play_data = schedule.fetch_playbyplay(context.game_id)
    all_events = play_by_play_data.get("plays", [])

    logging.debug("Number of *TOTAL* Events Retrieved from PBP: %s", len(all_events))
    logging.info("%s total event(s) detected in PBP - checking for new events.", len(all_events))

    goal_events = [event for event in all_events if event.get("typeDescKey") == "goal"]
    logging.debug("Number of *GOAL* Events Retrieved from PBP: %s", len(goal_events))

    last_sort_order = context.last_sort_order
    new_events = [event for event in all_events if event["sortOrder"] > last_sort_order]
    num_new_events = len(new_events)
    new_plays = num_new_events != 0
    #  logging.info("Number of *NEW* Events Retrieved from PBP: %s", num_new_events)

    if num_new_events == 0:
        logging.info(
            "No new plays detected. This game event loop will catch any missed events & "
            "and also check for any scoring changes on existing goals."
        )
    else:
        logging.info("%s new event(s) detected - looping through them now.", num_new_events)

    # We pass in the entire all_plays list into our event_factory in case we missed an event
    # it will be created because it doesn't exist in the Cache.
    for event in all_events:
        EventFactory.create_event(event, context, new_plays)

    # After event creation is completed, let's check for deleted goals (usually for challenges)
    # detect_removed_goals(context, all_events)
