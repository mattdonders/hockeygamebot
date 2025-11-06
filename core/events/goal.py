import logging

from socials.types import PostRef
from utils.team_details import get_team_details_by_id

from .base import Cache, Event


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
        """
        # Extract highlight clip URL from event_data
        highlight_clip_url = event_data.get("details", {}).get("highlightClipSharingUrl")
        if not highlight_clip_url:
            logging.info("No highlight clip URL found for event ID %s.", event_data.get("eventId"))
            return

        if highlight_clip_url == "https://www.nhl.com/video/":
            logging.info("Invalid highlight clip URL found for event ID %s.", event_data.get("eventId"))
            return

        # Normalize and store
        highlight_clip_url = highlight_clip_url.replace("https://nhl.com", "https://www.nhl.com")
        self.highlight_clip_url = highlight_clip_url
        logging.info("Added highlight clip URL to GoalEvent (event ID: %s).", event_data.get("eventId"))

        # Construct message and post as a reply within the existing goal thread (if present)
        message = f"🎥 HIGHLIGHT: {self.scoring_player_name} scores for the {self.team_name}!"
        # Threading is handled by GoalEvent.post_message(): if refs exist → reply; else → initial post
        self.post_message(
            message,
            add_hashtags=False,
            add_score=False,
            link=self.highlight_clip_url,
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

    def post_message(
        self,
        message: str,
        link: str | None = None,
        add_hashtags: bool = True,
        add_score: bool = True,
        media: str | list[str] | None = None,
        alt_text: str = "",
    ) -> None:
        """
        Threaded posting for GoalEvent:
        - First call: post on all enabled platforms, store PostRef(s).
        - Subsequent calls: reply in-place per platform and advance stored refs.
        Never raises; logs exceptions via context.logger if available.
        """
        # Ensure per-event thread map exists (platform -> PostRef)
        if not hasattr(self, "_post_refs"):
            self._post_refs = {}

        # Respect debugsocial for hashtags
        add_hashtags = False if getattr(self.context, "debugsocial", False) else add_hashtags

        # Footer (hashtags + score)
        footer_parts: list[str] = []
        if add_hashtags:
            try:
                ht = getattr(self.context.preferred_team, "hashtag", "")
                if ht:
                    footer_parts.append(ht)
            except Exception:
                pass

        if add_score:
            try:
                pref = self.context.preferred_team
                other = self.context.other_team
                footer_parts.append(
                    f"{pref.abbreviation}: {pref.score} / {other.abbreviation}: {other.score}"
                )
            except Exception:
                pass

        text = message
        if footer_parts:
            text += "\n\n" + " | ".join(footer_parts)
        if link:
            text += f"\n\n{link}"

        try:
            if not self._post_refs:
                # Initial post on all enabled platforms; store refs for future replies.
                logging.info(
                    "GoalEvent[%s]: initial post across platforms.", getattr(self, "event_id", "unknown")
                )
                results = self.context.social.post(
                    message=text,
                    media=media,
                    alt_text=alt_text or "",
                    platforms="enabled",
                )
                for platform, ref in (results or {}).items():
                    self._post_refs[platform] = ref
                if not results:
                    logging.warning(
                        "GoalEvent[%s]: no PostRefs returned from initial post.",
                        getattr(self, "event_id", "unknown"),
                    )
            else:
                # Reply per platform to maintain threading; update refs as we go.
                logging.info(
                    "GoalEvent[%s]: replying to existing thread on %d platform(s).",
                    getattr(self, "event_id", "unknown"),
                    len(self._post_refs),
                )
                new_refs: dict[str, PostRef] = {}
                for platform, parent_ref in list(self._post_refs.items()):
                    # For replies we only send a single media item argument.
                    # (Threads carousel emulation still happens in .post(); reply() remains single-media.)
                    media_arg: str | None = None
                    if isinstance(media, list) and media:
                        media_arg = media[0]
                    elif isinstance(media, str):
                        media_arg = media

                    res = self.context.social.reply(
                        message=text,
                        media=media_arg,
                        platforms=[platform],
                        reply_to=parent_ref,
                        alt_text=alt_text or "",
                    )
                    if platform in res:
                        new_refs[platform] = res[platform]
                        logging.debug(
                            "GoalEvent[%s]: advanced %s thread id=%s",
                            getattr(self, "event_id", "unknown"),
                            platform,
                            res[platform].id,
                        )
                    else:
                        logging.warning(
                            "GoalEvent[%s]: no reply PostRef for %s",
                            getattr(self, "event_id", "unknown"),
                            platform,
                        )
                # Advance stored refs
                self._post_refs.update(new_refs)
        except Exception as e:
            if getattr(self.context, "logger", None):
                self.context.logger.exception("GoalEvent post failed: %s", e)
            else:
                logging.exception("GoalEvent post failed: %s", e)
