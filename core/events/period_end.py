import logging

from core import charts, schedule
from utils.game_type_constants import GAME_TYPE_REGULAR_SEASON

from .base import Cache, Event

logger = logging.getLogger(__name__)


class PeriodEndEvent(Event):
    """
    Event for when a period ends.
    """

    cache = Cache(__name__)
    logical_event_type = "period_summary"

    def parse(self):
        """
        Parse the period-end event and return a formatted message.
        """
        period_number = self.period_number
        period_type = self.event_data.get("periodDescriptor", {}).get("periodType", "unknown")
        period_ordinal = f"{period_number}{'th' if 10 <= period_number % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(period_number % 10, 'th')}"

        # ---------------------------------------------------------
        # NEW: Skip late-period summaries in regular-season games
        # - Period 3: end of regulation
        # - Period 4: end of OT
        # The GameEnd charts will follow shortly and cover this.
        # ---------------------------------------------------------
        game_type = getattr(self.context, "game_type", None)
        if game_type == GAME_TYPE_REGULAR_SEASON and period_number in (3, 4):
            # Returning None tells the factory "no social message for this event"
            logger.info(
                "Skipping PeriodEndEvent summary for period %s in regular-season game; "
                "final GameEnd charts will cover this.",
                period_number,
            )
            return None
        # ---------------------------------------------------------

        if period_type == "REG":
            message = f"The {period_ordinal} period has ended."
        elif period_type == "OT":
            message = f"Overtime has ended."
        elif period_type == "SO":
            message = f"The shootout has ended."
        else:
            message = f"The {period_ordinal} period of type '{period_type}' has ended."

        message += (
            f"\n\n"
            f"{self.context.preferred_team.full_name}: {self.context.preferred_team.score}\n"
            f"{self.context.other_team.full_name}: {self.context.other_team.score}"
        )

        right_rail_data = schedule.fetch_rightrail(self.context.game_id)
        team_stats_data = right_rail_data.get("teamGameStats")
        if team_stats_data:
            chart_path = charts.teamstats_chart(
                self.context, team_stats_data, ingame=True, period_label_short=self.period_label_short
            )
        else:
            chart_path = None

        return chart_path, message
