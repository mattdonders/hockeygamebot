import logging

from .base import Cache, Event

logger = logging.getLogger(__name__)


class FaceoffEvent(Event):
    cache = Cache(__name__)

    def parse(self):
        winning_player_name = self.details.get("winningPlayerName")
        losing_player_name = self.details.get("losingPlayerName")

        if self.time_in_period == "00:00":
            # 'Force Fail' on missing data
            if not (winning_player_name and losing_player_name):
                logger.warning("Faceoff data not fully available - force fail & will retry next loop.")
                return False

            return (
                f"{winning_player_name} wins the opening faceoff of the {self.period_number_ordinal} "
                f"period against {losing_player_name}."
            )
        return False
