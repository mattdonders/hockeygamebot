import logging
import utils.others as otherutils
from core.events import EventFactory


def replace_ids_with_names(details, roster):
    """
    Replace fields ending with 'Id' in the details dictionary with their corresponding 'Name' fields,
    excluding fields ending in 'TeamId'.
    """
    for key, value in list(details.items()):  # Use list() to avoid runtime modification issues
        if key.endswith("Id") and not key.endswith("TeamId") and isinstance(value, int):
            player_name = roster.get(value, "Unknown Player")
            details[key.replace("Id", "Name")] = player_name
    return details


def parse_play_by_play_with_names(events, context):
    """
    Parse play-by-play data, dynamically replace player IDs with names,
    and process events using the EventFactory.
    """

    parsed_events = []

    for event in events:
        # event_type = event.get("typeDescKey", "unknown")
        details = event.get("details", {})

        # Replace player IDs with names dynamically
        details = replace_ids_with_names(details, context.combined_roster)
        logging.debug(f"Event details after replacing IDs with names: {details}")

        # Create an event object using the factory
        parsed_event = EventFactory.create_event(event, context)

        if parsed_event:
            parsed_events.append(parsed_event)

            try:
                parsed_event.post_message()
                # message = parsed_event.parse()
                # if message:
                #     context.bluesky_client.post(message)
            except Exception as e:
                logging.error(f"Error processing event: {e}", exc_info=True)

    # logging.info(f"Parsed {len(parsed_events)} events successfully.")
