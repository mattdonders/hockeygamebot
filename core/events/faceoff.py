from .base import Event


class FaceoffEvent(Event):
    def parse(self):
        if self.time_in_period == "00:00":
            return f"The opening faceoff for period {self.period_number} is underway!"
        return None
