import logging

from utils.others import get_player_name
from utils.team_details import get_team_name_by_id

from .base import Cache, Event


class PenaltyEvent(Event):
    cache = Cache(__name__)

    def penalty_type_fixer(self, original_type):
        """A function that converts some poorly named penalty types."""
        secondarty_types = {
            "interference-goalkeeper": "goalie interference",
            "delaying-game-puck-over-glass": "delay of game (puck over glass)",
            # "delaying game - puck over glass": "delay of game (puck over glass)",
            # "interference - goalkeeper": "goalie interference",
            # "missing key [pd_151]": "delay of game (unsuccessful challenge)",
            # "hi-sticking": "high sticking",
        }
        return secondarty_types.get(original_type, original_type)

    def parse(self):
        penalty_name = self.penalty_type_fixer(self.details.get("descKey", "unknown penalty"))
        penalty_duration = self.details.get("duration", 0)
        committed_by = get_player_name(self.details.get("committedByPlayerId"), self.context.combined_roster)
        drawn_by = get_player_name(self.details.get("drawnByPlayerId"), self.context.combined_roster)
        served_by = get_player_name(self.details.get("servedByPlayerId"), self.context.combined_roster)
        penalty_team = get_team_name_by_id(self.details.get("eventOwnerTeamId"))

        # 'Force Fail' on missing data
        if penalty_name == "minor":
            logging.warning("Penalty data not fully available - force fail & will retry next loop.")
            return False

        # Start constructing the penalty string
        if penalty_name == "bench":
            penalty_string = (
                f"Penalty: The {penalty_team} take a bench minor ({penalty_duration} minutes). "
                f"The penalty will be served by: {served_by}."
            )
        elif penalty_name == "delaying-game-unsuccessful-challenge":
            penalty_string = (
                f"Penalty: The {penalty_team} take a bench minor for an unsuccessful challenge ({penalty_duration} minutes). "
                f"The penalty will be served by: {served_by}."
            )
        else:
            penalty_string = f"Penalty: {committed_by} is called for {penalty_name} ({penalty_duration} minutes)."

            # Add drawn by information if it exists
            if drawn_by:
                penalty_string += f"\nPenalty drawn by: {drawn_by}."

        return penalty_string
