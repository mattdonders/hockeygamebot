import logging
import time
import requests

from core.play_by_play import parse_play_by_play_with_names


def parse_live_game(game_id, context):
    """
    Continuously parse live game events.
    """
    play_by_play_url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play"

    while True:
        response = requests.get(play_by_play_url)
        if response.status_code == 200:
            play_by_play_data = response.json()
            events = play_by_play_data.get("plays", [])
            logging.info("Number of *TOTAL* Events Retrieved from PBP: %s", len(events))

            goal_events = [event for event in events if event["typeDescKey"] == "goal"]
            logging.info("Number of *GOAL* Events Retrieved from PBP: %s", len(goal_events))

            logging.info("Filtering for Events After Sort Order: %s", context.last_sort_order)
            last_sort_order = context.last_sort_order
            new_events = [event for event in events if event["sortOrder"] > last_sort_order]
            num_new_events = len(new_events)
            logging.info("Number of *NEW* Events Retrieved from PBP: %s", num_new_events)

            # TODO: This prevents goals from being re-parsed by the standard parser.
            # TODO: We will re-parse goals separately & do scoring changes & highlight links.
            logging.info("Filtering for Events Based on Event ID.")
            parsed_event_ids = context.parsed_event_ids
            new_events = [event for event in new_events if event["eventId"] not in parsed_event_ids]
            num_new_events = len(new_events)
            logging.info("Number of *NEW* Events Retrieved from PBP: %s", num_new_events)

            if num_new_events > 0:
                parse_play_by_play_with_names(new_events, context)

                new_events_last_sort_order = new_events[-1]["sortOrder"]
                logging.info("Updating Game Context Sort Order: %s", new_events_last_sort_order)
                context.last_sort_order = new_events_last_sort_order

            # Check game state
            game_state = play_by_play_data.get("gameState", "LIVE")
            if game_state == "OFF":
                logging.info("Game has ended. Exiting live game parsing.")
                break

        else:
            logging.error(f"Failed to fetch live play-by-play data. Status code: {response.status_code}")
            break

        logging.info("Sleeping for 30s waiting for new events.")
        time.sleep(30)  # Poll every 30 seconds
