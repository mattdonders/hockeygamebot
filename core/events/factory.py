import logging
import traceback
from core.events.base import Event
from core.events.game_end import GameEndEvent
from core.events.goal import GoalEvent
from core.events.penalty import PenaltyEvent
from core.events.faceoff import FaceoffEvent
from core.events.shootout import ShootoutEvent
from core.events.stoppage import StoppageEvent
from core.events.period_end import PeriodEndEvent
from core.events.generic import GenericEvent
import utils.others as otherutils


class EventFactory:
    """
    A factory to create event objects based on their type.
    """

    @staticmethod
    def create_event(event_data, context):
        # Get & Add Event ID to Master List of Parsed Events
        event_id = event_data.get("eventId")

        # Pull out necessary fields for other parsing logic
        event_type = event_data.get("typeDescKey", "UnsupportedEvent")
        sort_order = event_data.get("sortOrder", "N/A")
        period_type = event_data.get("periodDescriptor", {}).get("periodType")

        # Mapping of event types to their corresponding classes
        event_mapping = {
            "goal": GoalEvent,
            "penalty": PenaltyEvent,
            "faceoff": FaceoffEvent,
            "stoppage": StoppageEvent,
            "period-end": PeriodEndEvent,
            "game-end": GameEndEvent,
        }

        # Get the event class based on the type
        event_class = event_mapping.get(event_type, GenericEvent)

        # Re-classify shootout events as such
        shootout = bool(period_type == "SO" and event_class != GameEndEvent)
        event_class = ShootoutEvent if shootout else event_class

        # Check whether this event is in our Cache
        event_object = event_class.cache.get(event_id)
        logging.debug("Existing Event Object: %s", event_object)

        if not event_object:
            # Add Name Fields for Each ID Field in Event Details
            details = event_data.get("details", {})
            details = otherutils.replace_ids_with_names(details, context.combined_roster)
            event_data["details"] = details

            try:
                logging.info(
                    "Creating %s event (type: %s) for ID: %s / SortOrder: %s.",
                    event_class.__name__,
                    event_type,
                    event_id,
                    sort_order,
                )

                event_object = event_class(event_data, context)

                # CHANGE: Parse now returns None for failed to create objects
                # We can "force fail (via False)" events that are missing some data (maybe via retry)
                event_message = event_object.parse()

                if event_message is not False:
                    event_class.cache.add(event_object)

                    # Send Message (on new object creation only)
                    event_object.post_message(event_message)
                else:
                    logging.warning(
                        "Unable to create / parse %s event (type: %s) for ID: %s / SortOrder: %s.",
                        event_class.__name__,
                        event_type,
                        event_id,
                        sort_order,
                    )
                    logging.warning(event_data)
            except Exception as error:
                logging.error(
                    "Error creating %s event (type: %s) for ID: %s / SortOrder: %s.",
                    event_class.__name__,
                    event_type,
                    event_id,
                    sort_order,
                )
                # logging.error(response)
                logging.error(error)
                logging.error(traceback.format_exc())
                return

        if sort_order < 9000:
            context.last_sort_order = sort_order
        else:
            logging.warning("Not setting GameContext sort order to %s - invalid value.", sort_order)
