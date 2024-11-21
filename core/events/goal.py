from .base import Event
from utils.others import ordinal, get_player_name


class GoalEvent(Event):
    def parse(self):
        """
        Parse a goal event and return a formatted message.
        """
        details = self.details

        # Add preferred team flag
        event_owner_team_id = details.get("eventOwnerTeamId")
        is_preferred = event_owner_team_id == self.context.preferred_team_id
        details["is_preferred"] = is_preferred

        # Adjust scores
        if self.context.preferred_homeaway == "home":
            details["preferredScore"] = details["homeScore"]
            details["otherScore"] = details["awayScore"]
        else:
            details["preferredScore"] = details["awayScore"]
            details["otherScore"] = details["homeScore"]

        details.pop("homeScore", None)
        details.pop("awayScore", None)

        # Get additional fields
        scoring_player_name = get_player_name(details.get("scoringPlayerId"), self.context.combined_roster)
        scoring_player_total = details.get("scoringPlayerTotal", 0)
        assist1_name = get_player_name(details.get("assist1PlayerId"), self.context.combined_roster)
        assist1_total = details.get("assist1PlayerTotal", 0)
        assist2_name = get_player_name(details.get("assist2PlayerId"), self.context.combined_roster)
        assist2_total = details.get("assist2PlayerTotal", 0)
        shot_type = details.get("shotType", "unknown shot")

        empty_net_goal = details.get("goalieInNetId") is None
        period_number_ordinal = ordinal(self.period_number)

        if is_preferred:
            goal_emoji = "🚨" * details["preferredScore"]
            goal_message = (
                f"{self.context.preferred_team_name} GOAL! {goal_emoji}\n\n"
                f"{scoring_player_name} ({scoring_player_total}) scores on a {shot_type} shot "
                f"with {self.time_remaining} remaining in the {period_number_ordinal} period.\n\n"
            )
        else:
            goal_emoji = "👎" * details["otherScore"]
            goal_message = (
                f"{self.context.other_team_name} scores. {goal_emoji}\n\n"
                f"{scoring_player_name} ({scoring_player_total}) scores on a {shot_type} shot "
                f"with {self.time_remaining} remaining in the {period_number_ordinal} period.\n\n"
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
            f"{self.context.preferred_team_name}: {details['preferredScore']}\n"
            f"{self.context.other_team_name}: {details['otherScore']}"
        )

        goal_message += f"\n\n{self.context.preferred_team_hashtag} | {self.context.game_hashtag}"

        return goal_message
