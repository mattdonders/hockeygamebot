import logging
import time
import requests

from core import schedule
from core.events.factory import EventFactory
from core.game_context import GameContext
from core.play_by_play import parse_play_by_play_with_names


def parse_live_game(context: GameContext):
    """
    Parse live game events via Event Factory.
    """

    play_by_play_data = schedule.fetch_playbyplay(context.game_id)
    all_events = play_by_play_data.get("plays", [])

    logging.debug("Number of *TOTAL* Events Retrieved from PBP: %s", len(all_events))

    goal_events = [event for event in all_events if event["typeDescKey"] == "goal"]
    logging.debug("Number of *GOAL* Events Retrieved from PBP: %s", len(goal_events))

    last_sort_order = context.last_sort_order
    new_events = [event for event in all_events if event["sortOrder"] > last_sort_order]
    num_new_events = len(new_events)
    logging.info("Number of *NEW* Events Retrieved from PBP: %s", num_new_events)

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
        EventFactory.create_event(event, context)
