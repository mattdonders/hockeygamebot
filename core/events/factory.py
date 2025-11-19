import logging
import traceback

import utils.others as otherutils
from core.events.base import Event
from core.events.faceoff import FaceoffEvent
from core.events.game_end import GameEndEvent
from core.events.generic import GenericEvent
from core.events.goal import GoalEvent
from core.events.penalty import PenaltyEvent
from core.events.period_end import PeriodEndEvent
from core.events.shootout import ShootoutEvent
from core.events.stoppage import StoppageEvent

logger = logging.getLogger(__name__)


class EventFactory:
    """
    A factory to create event objects based on their type.
    """

    @staticmethod
    def create_event(event_data, context, new_plays):
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
        logger.debug("Existing Event Object: %s", event_object)

        # Check for scoring changes and NHL Video IDs on GoalEvents
        # We also use the new_plays variable to only check for scoring changes on no new events
        if event_class == GoalEvent and event_object is not None and not new_plays:
            event_object: GoalEvent  # Type Hinting for IDE

            # Scoring Changes Checked Here
            event_object.check_scoring_changes(event_data)

            # Check for Highlight URLs
            if not event_object.highlight_clip_url:
                event_object.check_and_add_highlight(event_data)

            # Check for Goal GIFs
            # The GIF flag check is done inside the check_and_add_gif method & returns
            # TODO: Apply this logic (check inside function) to highlights as well
            event_object.check_and_add_gif(context)

        if not event_object:
            # Initialize empty event image
            event_img = None

            # Add Name Fields for Each ID Field in Event Details
            details = event_data.get("details", {})
            details = otherutils.replace_ids_with_names(details, context.combined_roster)
            event_data["details"] = details

            try:
                logger.info(
                    "Creating %s event (type: %s) for ID: %s / SortOrder: %s.",
                    event_class.__name__,
                    event_type,
                    event_id,
                    sort_order,
                )

                event_object = event_class(event_data, context)

                # CHANGE: Parse now returns None for failed to create objects
                # We can "force fail (via False)" events that are missing some data (maybe via retry)
                events_returning_image = PeriodEndEvent
                if isinstance(event_object, events_returning_image):
                    event_img, event_message = event_object.parse()
                else:
                    event_message = event_object.parse()

                if event_message is not False:
                    event_class.cache.add(event_object)

                    # Send Message (on new object creation only)
                    # Define the event types where add_score should be False
                    disable_add_score_events = (GoalEvent, PeriodEndEvent)
                    add_score = not isinstance(event_object, disable_add_score_events)

                    # Post message with the determined add_score value
                    if event_img:
                        event_object.post_message(event_message, add_score=add_score, media=event_img)
                    else:
                        event_object.post_message(event_message, add_score=add_score)

                    # For GoalEvents, we want to Check & Add Highlight Clip (even on event creation)
                    if event_class == GoalEvent:
                        logger.info("New GoalEvent creation - checking for highlights.")
                        event_object: GoalEvent  # IDE Typing Hint
                        event_object.check_and_add_highlight(event_data)
                        event_object.check_and_add_gif(context)
                else:
                    logger.warning(
                        "Unable to create / parse %s event (type: %s) for ID: %s / SortOrder: %s.",
                        event_class.__name__,
                        event_type,
                        event_id,
                        sort_order,
                    )
                    logger.warning(event_data)
            except Exception as error:
                logger.error(
                    "Error creating %s event (type: %s) for ID: %s / SortOrder: %s.",
                    event_class.__name__,
                    event_type,
                    event_id,
                    sort_order,
                )
                # logger.error(response)
                logger.error(error)
                logger.error(traceback.format_exc())
                return

        if sort_order < 9000:
            context.last_sort_order = sort_order
        else:
            logger.warning("Not setting GameContext sort order to %s - invalid value.", sort_order)
