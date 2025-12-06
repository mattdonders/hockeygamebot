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
    event_type = "game_start"  # <-- important for X allowlist

    def parse(self):
        # Only care about the very start of the first period
        if self.period_number != 1 or self.time_in_period != "00:00":
            return False

        # Build a simple "game underway" message.
        # You can tune these attribute names once we line it
        # up with your GameContext, but this is the idea.
        ctx = self.context

        # Try to build a nice matchup label.
        matchup = getattr(ctx, "matchup_label", None)
        if not matchup:
            home = getattr(ctx, "home_team_name", None)
            away = getattr(ctx, "away_team_name", None)
            if home and away:
                matchup = f"{away} vs {home}"
            else:
                matchup = "Tonight's game"

        venue = getattr(ctx, "venue_name", None) or getattr(ctx, "arena_name", None)

        if venue:
            social_string = f"{matchup} is underway at {venue}! 🏒"
        else:
            social_string = f"{matchup} is underway! 🏒"

        return social_string
