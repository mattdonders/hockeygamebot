# core/events/period_start.py
import logging

from .base import Cache, Event

logger = logging.getLogger(__name__)


class PeriodStartEvent(Event):
    """
    Treat the start of the 1st period as a 'game has started' event.

    - Only posts for:
        period == 1 AND time_in_period == "00:00"
    - Uses event_type='game_start' so X routing
      respects your DEFAULT_X_EVENT_ALLOWLIST.
    """

    cache = Cache(__name__)
    ogical_event_type = "game_start"

    def parse(self):
        # Only trigger at the start of the 1st period
        if self.period_number != 1 or self.time_in_period != "00:00":
            return False

        ctx = self.context

        home = ctx.home_team.short_name
        away = ctx.away_team.short_name
        venue = ctx.venue  # Guaranteed per your design

        social_string = f"{away} vs {home} is underway at {venue}! 🏒"

        return social_string
