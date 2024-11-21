from .base import Event
from utils.others import get_player_name
from utils.team_details import get_team_name_by_id


class PenaltyEvent(Event):
    def parse(self):
        penalty_name = self.details.get("descKey", "unknown penalty")
        penalty_duration = self.details.get("duration", 0)
        committed_by = get_player_name(self.details.get("committedByPlayerId"), self.context.combined_roster)
        drawn_by = get_player_name(self.details.get("drawnByPlayerId"), self.context.combined_roster)
        served_by = get_player_name(self.details.get("servedByPlayerId"), self.context.combined_roster)
        penalty_team = get_team_name_by_id(self.details.get("eventOwnerTeamId"))

        if penalty_name == "bench":
            penalty_string = (
                f"Penalty: The {penalty_team} take a bench minor ({penalty_duration} minutes). "
                f"The penalty will be served by: {served_by}"
            )
        else:
            penalty_string = (
                f"Penalty: {committed_by} is called for {penalty_name} ({penalty_duration} minutes).\n"
                f"Penalty drawn by: {drawn_by}."
            )

        return penalty_string
