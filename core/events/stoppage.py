import logging

from .base import Cache, Event

logger = logging.getLogger(__name__)


class StoppageEvent(Event):
    cache = Cache(__name__)

    def parse(self):
        secondary_reason = self.details.get("secondaryReason")

        # TV timeout
        if secondary_reason == "tv-timeout":
            return (
                f"Game stoppage: TV timeout with {self.time_remaining} remaining "
                f"in the {self.period_number_ordinal} period."
            )

        # Coach’s challenge / video review
        if secondary_reason == "video-review":
            return (
                "Game stoppage: The previous play is under video review "
                f"({self.time_remaining} remaining in the {self.period_number_ordinal} period)."
            )

        # All other stoppages: no social output by design
        logger.info(
            "StoppageEvent[%s]: no social message for secondaryReason=%r " "at %s in %s.",
            getattr(self, "event_id", "unknown"),
            secondary_reason,
            getattr(self, "time_remaining", "?"),
            getattr(self, "period_number_ordinal", "?"),
        )
        return False
