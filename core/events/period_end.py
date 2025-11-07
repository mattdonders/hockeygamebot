from core import charts, schedule

from .base import Cache, Event


class PeriodEndEvent(Event):
    """Event for when a period ends."""

    cache = Cache(__name__)

    def parse(self):
        """Parse the period-end event and return a formatted message."""
        period_number = self.period_number
        period_type = self.event_data.get("periodDescriptor", {}).get("periodType", "unknown")
        period_ordinal = f"{period_number}{'th' if 10 <= period_number % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(period_number % 10, 'th')}"

        if period_type == "REG":
            message = f"The {period_ordinal} period has ended."
        elif period_type == "OT":
            message = "Overtime has ended."
        elif period_type == "SO":
            message = "The shootout has ended."
        else:
            message = f"The {period_ordinal} period of type '{period_type}' has ended."

        message += (
            f"\n\n"
            f"{self.context.preferred_team.full_name}: {self.context.preferred_team.score}\n"
            f"{self.context.other_team.full_name}: {self.context.other_team.score}"
        )

        right_rail_data = schedule.fetch_rightrail(self.context.game_id)
        team_stats_data = right_rail_data.get("teamGameStats")
        chart_path = charts.teamstats_chart(self.context, team_stats_data, ingame=True) if team_stats_data else None

        return chart_path, message
