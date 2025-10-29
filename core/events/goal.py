import logging
from .base import Cache, Event
from utils.others import ordinal, get_player_name
from utils.team_details import get_team_details_by_id


class GoalEvent(Event):
    cache = Cache(__name__)

    REMOVAL_THRESHOLD = 5  # Configurable threshold for event removal checks

    def parse(self):
        """
        Parse a goal event and return a formatted message.
        """
        details = self.details

        # Add preferred team flag
        event_owner_team_id = details.get("eventOwnerTeamId")
        is_preferred = event_owner_team_id == self.context.preferred_team.team_id
        details["is_preferred"] = is_preferred

        # Add Team Details to Goal Object (better logging)
        event_team_details = get_team_details_by_id(event_owner_team_id)
        self.team_name = event_team_details.get("full_name")
        self.team_abbreviation = event_team_details.get("abbreviation")

        # Adjust scores
        if self.context.preferred_homeaway == "home":
            self.preferred_score = details["homeScore"]
            self.other_score = details["awayScore"]
        else:
            self.preferred_score = details["awayScore"]
            self.other_score = details["homeScore"]

        # Add Updated Scores to Game Context
        # This allows us to print scores for non-goal events
        self.context.preferred_team.score = self.preferred_score
        self.context.other_team.score = self.other_score

        details.pop("homeScore", None)
        details.pop("awayScore", None)

        # Store Scoring Player Details
        self.scoring_player_id = details.get("scoringPlayerId")
        self.scoring_player_name = details.get("scoringPlayerName", "Unknown")
        self.scoring_player_total = details.get("scoringPlayerTotal", 0)

        # Store Assist Details
        self.assist1_player_id = details.get("assist1PlayerId")
        self.assist1_name = details.get("assist1PlayerName", None)
        self.assist1_total = details.get("assist1PlayerTotal", 0)
        self.assist2_player_id = details.get("assist2PlayerId")
        self.assist2_name = details.get("assist2PlayerName", None)
        self.assist2_total = details.get("assist2PlayerTotal", 0)

        # Store Other Relevant Fields
        self.shot_type = details.get("shotType", None)
        self.highlight_clip_url = details.get("highlightClipSharingUrl", None)

        # 'Force Fail' on missing data
        if not self.shot_type:
            logging.warning("Goal data not fully available - force fail & will retry next loop.")
            return False

        # Get Video Highlight Fields

        # Check if Empty Net Goal
        empty_net_goal = details.get("goalieInNetId") is None

        if is_preferred:
            goal_emoji = "🚨" * self.preferred_score
            goal_message = (
                f"{self.context.preferred_team.full_name} GOAL! {goal_emoji}\n\n"
                f"{self.scoring_player_name} ({self.scoring_player_total}) scores on a {self.shot_type} shot "
                f"with {self.time_remaining} remaining in the {self.period_number_ordinal} period.\n\n"
            )
        else:
            goal_emoji = "👎" * self.other_score
            goal_message = (
                f"{self.context.other_team.full_name} goal. {goal_emoji}\n\n"
                f"{self.scoring_player_name} ({self.scoring_player_total}) scores on a {self.shot_type} shot "
                f"with {self.time_remaining} remaining in the {self.period_number_ordinal} period.\n\n"
            )

        # Dynamically add assists if they exist
        assists = []
        if self.assist1_name:
            assists.append(f"🍎 {self.assist1_name} ({self.assist1_total})")
        if self.assist2_name:
            assists.append(f"🍏 {self.assist2_name} ({self.assist2_total})")

        if assists:
            goal_message += "\n".join(assists) + "\n\n"

        # Add team scores
        goal_message += (
            f"{self.context.preferred_team.full_name}: {self.preferred_score}\n"
            f"{self.context.other_team.full_name}: {self.other_score}"
        )

        return goal_message

    def check_scoring_changes(self, data: dict):
        logging.info("Checking for scoring changes (team: %s, event ID: %s).", self.team_name, self.event_id)

        # Extract updated information from payload
        details = data.get("details", {})
        new_scoring_player_id = details.get("scoringPlayerId")
        new_assist1_player_id = details.get("assist1PlayerId")
        new_assist2_player_id = details.get("assist2PlayerId")

        # Compile assists into a list for comparison
        new_assists = [new_assist1_player_id, new_assist2_player_id]
        current_assists = [self.assist1_player_id, self.assist2_player_id]

        # Check for changes
        scorer_change = new_scoring_player_id != self.scoring_player_id
        assist_change = new_assists != current_assists

    def check_and_add_highlight(self, event_data):
        """
        Check event_data for highlight_clip_url, post a message if found, and update the event object.

        Args:
            event_data (dict): The raw event data from the NHL Play-by-Play API.

        Returns:
            None
        """
        # Extract highlight clip URL from event_data
        highlight_clip_url = event_data.get("details", {}).get("highlightClipSharingUrl")
        if not highlight_clip_url:
            logging.info("No highlight clip URL found for event ID %s.", event_data["eventId"])
            return

        if highlight_clip_url == "https://www.nhl.com/video/":
            logging.info("Invalid highlight clip URL found for event ID %s.", event_data["eventId"])
            return

        # Update the GoalEvent object
        highlight_clip_url = highlight_clip_url.replace("https://nhl.com", "https://www.nhl.com")
        self.highlight_clip_url = highlight_clip_url
        logging.info("Added highlight clip URL to GoalEvent (event ID: %s).", event_data["eventId"])

        # Construct the social media post
        message = f"🎥 HIGHLIGHT: {self.scoring_player_name} scores for the {self.team_name}!"

        self.post_message(
            message,
            add_hashtags=False,
            add_score=False,
            link=self.highlight_clip_url,
            bsky_root=self.bsky_root,
            bsky_parent=self.bsky_parent,
        )

    def was_goal_removed(self, all_plays: dict) -> bool:
        """
        Checks if the goal was removed from the live feed (e.g., due to a Challenge).
        Returns True if the goal should be removed, False otherwise.
        """
        goal_still_exists = next((play for play in all_plays if play["eventId"] == self.event_id), None)

        if goal_still_exists:
            # Reset the counter if the goal reappears
            self.event_removal_counter = 0
            logging.info("Goal (event ID: %s) is still present in the live feed.", self.event_id)
            return False

        # Goal is missing; increment the removal counter
        self.event_removal_counter += 1
        if self.event_removal_counter < self.REMOVAL_THRESHOLD:
            logging.info(
                "Goal (event ID: %s) is missing (check #%d). Will retry.",
                self.event_id,
                self.event_removal_counter,
            )
            return False

        # Goal has been missing for the threshold duration
        logging.warning(
            "Goal (event ID: %s) has been missing for %d checks. Marking for removal.",
            self.event_id,
            self.REMOVAL_THRESHOLD,
        )
        return True
