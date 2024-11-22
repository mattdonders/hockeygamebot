from .base import Cache, Event


class FaceoffEvent(Event):
    cache = Cache(__name__)

    def parse(self):
        winning_player_name = self.details.get("winningPlayerName")
        losing_player_name = self.details.get("losingPlayerName")

        if self.time_in_period == "00:00":
            return (
                f"{winning_player_name} wins the opening faceoff of the {self.period_number_ordinal} "
                f"period against {losing_player_name}."
            )
        return None
