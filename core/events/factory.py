import json
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

                # Instantiate Empty Event Image
                event_img = None

                # Let parse() return either:
                # - message (str / False / None), or
                # - (image_path, message)
                parse_result = event_object.parse()
                event_message = None

                if isinstance(parse_result, tuple) and len(parse_result) == 2:
                    event_img, event_message = parse_result
                else:
                    event_message = parse_result

                if event_message is None:
                    if event_class is GenericEvent:
                        logger.info(
                            "GenericEvent: no message for %s (ID: %s, SortOrder: %s).",
                            event_type,
                            event_id,
                            sort_order,
                        )
                        return None
                    else:
                        logger.error(
                            "Error creating %s event (type: %s) for ID: %s / SortOrder: %s — parse() returned None.",
                            event_class.__name__,
                            event_type,
                            event_id,
                            sort_order,
                        )
                        try:
                            preview = json.dumps(event_data, default=str)
                            logger.error("Event payload preview (first 800 chars): %s", preview[:800])
                        except Exception:
                            logger.error("Failed to serialize event_data for logging.")
                        return None

                if event_message is not False:
                    event_class.cache.add(event_object)

                    # Send Message (on new object creation only)
                    # Define the event types where add_score should be False
                    disable_add_score_events = (GoalEvent, PeriodEndEvent)
                    add_score = not isinstance(event_object, disable_add_score_events)

                    # Always pass media; post_message handles media=None just fine
                    event_object.post_message(
                        event_message,
                        add_score=add_score,
                        media=event_img,
                    )

                    # For GoalEvents, we want to Check & Add Highlight Clip (even on event creation)
                    if event_class == GoalEvent:
                        logger.info("New GoalEvent creation - checking for highlights.")
                        event_object: GoalEvent  # IDE Typing Hint
                        event_object.check_and_add_highlight(event_data)
                        event_object.check_and_add_gif(context)
                else:
                    # No social output by design (e.g. GenericEvent)
                    logger.info(
                        "%s created with no social message (type: %s, ID: %s, SortOrder: %s).",
                        event_class.__name__,
                        event_type,
                        event_id,
                        sort_order,
                    )
            except Exception as error:
                logger.error(
                    "Error creating %s event (type: %s) for ID: %s / SortOrder: %s.",
                    event_class.__name__,
                    event_type,
                    event_id,
                    sort_order,
                )
                logger.error("Exception: %r", error)
                try:
                    preview = json.dumps(event_data, default=str)
                    logger.error("Event payload preview (first 800 chars): %s", preview[:800])
                except Exception:
                    logger.error("Failed to serialize event_data for logging.")
                logger.error("Traceback:\n%s", traceback.format_exc())
                return

        if sort_order < 9000:
            context.last_sort_order = sort_order
        else:
            logger.warning("Not setting GameContext sort order to %s - invalid value.", sort_order)
