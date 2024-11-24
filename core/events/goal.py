import logging
from .base import Cache, Event
from utils.others import ordinal, get_player_name


class GoalEvent(Event):
    cache = Cache(__name__)

    def parse(self):
        """
        Parse a goal event and return a formatted message.
        """
        details = self.details

        # Add preferred team flag
        event_owner_team_id = details.get("eventOwnerTeamId")
        is_preferred = event_owner_team_id == self.context.preferred_team.team_id
        details["is_preferred"] = is_preferred

        # Adjust scores
        if self.context.preferred_homeaway == "home":
            details["preferredScore"] = details["homeScore"]
            details["otherScore"] = details["awayScore"]
        else:
            details["preferredScore"] = details["awayScore"]
            details["otherScore"] = details["homeScore"]

        # Add Updated Scores to Game Context
        # This allows us to print scores for non-goal events
        self.context.preferred_team.score = details["preferredScore"]
        self.context.other_team.score = details["otherScore"]

        details.pop("homeScore", None)
        details.pop("awayScore", None)

        # Get additional fields
        scoring_player_name = details.get("scoringPlayerName")
        scoring_player_total = details.get("scoringPlayerTotal", 0)
        assist1_name = details.get("assist1PlayerName")
        assist1_total = details.get("assist1PlayerTotal", 0)
        assist2_name = details.get("assist2PlayerName")
        assist2_total = details.get("assist2PlayerTotal", 0)
        shot_type = details.get("shotType")

        # 'Force Fail' on missing data
        if not shot_type:
            logging.warning("Goal data not fully available - force fail & will retry next loop.")
            return False

        # Get Video Highlight Fields

        # Check if Empty Net Goal
        empty_net_goal = details.get("goalieInNetId") is None

        if is_preferred:
            goal_emoji = "🚨" * details["preferredScore"]
            goal_message = (
                f"{self.context.preferred_team.full_name} GOAL! {goal_emoji}\n\n"
                f"{scoring_player_name} ({scoring_player_total}) scores on a {shot_type} shot "
                f"with {self.time_remaining} remaining in the {self.period_number_ordinal} period.\n\n"
            )
        else:
            goal_emoji = "👎" * details["otherScore"]
            goal_message = (
                f"{self.context.other_team.full_name} goal. {goal_emoji}\n\n"
                f"{scoring_player_name} ({scoring_player_total}) scores on a {shot_type} shot "
                f"with {self.time_remaining} remaining in the {self.period_number_ordinal} period.\n\n"
            )

        # Dynamically add assists if they exist
        assists = []
        if assist1_name:
            assists.append(f"🍎 {assist1_name} ({assist1_total})")
        if assist2_name:
            assists.append(f"🍏 {assist2_name} ({assist2_total})")

        if assists:
            goal_message += "\n".join(assists) + "\n\n"

        # Add team scores
        goal_message += (
            f"{self.context.preferred_team.full_name}: {details['preferredScore']}\n"
            f"{self.context.other_team.full_name}: {details['otherScore']}"
        )

        return goal_message
