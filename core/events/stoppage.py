from .base import Cache, Event


class StoppageEvent(Event):
    cache = Cache(__name__)

    def parse(self):
        secondary_reason = self.details.get("secondaryReason")
        if secondary_reason == "tv-timeout":
            return f"Game Stoppage: TV Timeout at {self.time_remaining} in the {self.period_number_ordinal} period."
        elif secondary_reason == "video-review":
            return f"Game Stoppage: The previous play is under video review."
        return None
