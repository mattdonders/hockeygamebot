import logging
from core.events.goal import GoalEvent
from core.events.penalty import PenaltyEvent
from core.events.faceoff import FaceoffEvent
from core.events.stoppage import StoppageEvent
from core.events.period_end import PeriodEndEvent


class EventFactory:
    """
    A factory to create event objects based on their type.
    """

    @staticmethod
    def create_event(event_data, context):
        # Get & Add Event ID to Master List of Parsed Events
        event_id = event_data.get("eventId")
        if event_id:
            context.parsed_event_ids.append(event_id)

        event_type = event_data.get("typeDescKey", "UnsupportedEvent")
        sort_order = event_data.get("sortOrder", "N/A")

        # Mapping of event types to their corresponding classes
        event_mapping = {
            "goal": GoalEvent,
            "penalty": PenaltyEvent,
            "faceoff": FaceoffEvent,
            "stoppage": StoppageEvent,
            "period-end": PeriodEndEvent,
        }

        # Get the event class based on the type
        event_class = event_mapping.get(event_type)

        if event_class:
            # Log the creation of the event
            logging.info(f"Creating event of type: {event_class} / Sort Order: {sort_order}")
            return event_class(event_data, context)

        # Log unsupported or unknown event types
        logging.warning(f"Unsupported or unknown event type: {event_type} / Sort Order: {sort_order}")
        return None
