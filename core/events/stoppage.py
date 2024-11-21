from .base import Event


class StoppageEvent(Event):
    def parse(self):
        secondary_reason = self.details.get("secondaryReason")
        if secondary_reason == "tv-timeout":
            return f"Game Stoppage: TV Timeout at {self.time_remaining} in the {self.period_number} period."
        elif secondary_reason == "video-review":
            return f"Game Stoppage: The previous play is under video review."
        return None
