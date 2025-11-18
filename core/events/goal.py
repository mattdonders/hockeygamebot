import logging
from typing import Dict, List, Optional, Union

from socials.platforms import NON_X_PLATFORMS, X_PLATFORMS
from utils.team_details import get_team_details_by_id

from .base import Cache, Event

logger = logging.getLogger(__name__)


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

        # Make sure these always exist for downstream code:
        self.event_team = getattr(self, "event_team", self.team_name)
        self.event_removal_counter = getattr(self, "event_removal_counter", 0)

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
            logger.warning("Goal data not fully available - force fail & will retry next loop.")
            return False

        # Get Video Highlight Fields

        # Check if Empty Net Goal
        empty_net_goal = details.get("goalieInNetId") is None

        if is_preferred:
            goal_emoji = "🚨" * self.preferred_score
            goal_message = (
                f"{self.context.preferred_team.full_name} GOAL! {goal_emoji}\n\n"
                f"{self.scoring_player_name} ({self.scoring_player_total}) scores on a {self.shot_type} shot "
                f"with {self.time_remaining} remaining in {self.period_label}.\n\n"
            )
        else:
            goal_emoji = "👎" * self.other_score
            goal_message = (
                f"{self.context.other_team.full_name} goal. {goal_emoji}\n\n"
                f"{self.scoring_player_name} ({self.scoring_player_total}) scores on a {self.shot_type} shot "
                f"with {self.time_remaining} remaining in {self.period_label}.\n\n"
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
        logger.info("Checking for scoring changes (team: %s, event ID: %s).", self.team_name, self.event_id)
        details = data.get("details", {})

        new_scorer = details.get("scoringPlayerId")
        new_a1 = details.get("assist1PlayerId")
        new_a2 = details.get("assist2PlayerId")

        scorer_change = new_scorer != self.scoring_player_id
        assist_change = [new_a1, new_a2] != [self.assist1_player_id, self.assist2_player_id]

        return {
            "scorer_changed": scorer_change,
            "assist_changed": assist_change,
            "new": {
                "scorer_id": new_scorer,
                "assist1_id": new_a1,
                "assist2_id": new_a2,
            },
        }

    def check_and_add_highlight(self, event_data):
        """
        Check event_data for highlight_clip_url, post a message if found, and update the event object.

        Args:
            event_data (dict): The raw event data from the NHL Play-by-Play API.
        """
        # Extract highlight clip URL from event_data
        highlight_clip_url = event_data.get("details", {}).get("highlightClipSharingUrl")
        if not highlight_clip_url:
            logger.info("No highlight clip URL found for event ID %s.", event_data.get("eventId"))
            return

        if highlight_clip_url == "https://www.nhl.com/video/":
            logger.info("Invalid highlight clip URL found for event ID %s.", event_data.get("eventId"))
            return

        # Normalize and store
        highlight_clip_url = highlight_clip_url.replace("https://nhl.com", "https://www.nhl.com")
        self.highlight_clip_url = highlight_clip_url
        logger.info("Added highlight clip URL to GoalEvent (event ID: %s).", event_data.get("eventId"))

        # Construct message and post as a reply within the existing goal thread (if present)
        message = f"🎥 HIGHLIGHT: {self.scoring_player_name} scores for the {self.team_name}!"
        # Threading is handled by GoalEvent.post_message(): if refs exist → reply; else → initial post
        self.post_message(
            message,
            add_hashtags=False,
            add_score=False,
            link=self.highlight_clip_url,
            event_type="goal_highlight",
        )

    def check_and_add_gif(self, event_data: dict) -> None:
        # gif_path = build_goal_gif_if_available(event_data)  # however you wire it
        gif_path = None
        if not gif_path:
            logger.info("No goal GIF available for event %s", event_data.get("eventId"))
            return

        # Store on the event if you want to reuse it later
        self.goal_gif_path = gif_path

        logger.info(
            "GoalEvent[%s]: built GIF at %s, posting threaded reply.",
            getattr(self, "event_id", "unknown"),
            gif_path,
        )

        # Thread under the existing goal post
        self.post_message(
            message="",  # or None if you want pure media
            add_hashtags=False,
            add_score=False,
            media=[gif_path],
            alt_text=f"Shot map for {self.scoring_player_name}'s goal",
            # 👇 new arg so Publisher can apply X rules
            event_type="goal_gif",
        )

    def was_goal_removed(self, all_plays: list) -> bool:
        """
        Checks if the goal was removed from the live feed (e.g., coach's challenge).
        Returns True if the goal should be removed, False otherwise.
        """
        present = any(play.get("eventId") == self.event_id for play in all_plays)
        if present:
            self.event_removal_counter = 0
            logger.info("Goal (event ID: %s) still present in live feed.", self.event_id)
            return False

        self.event_removal_counter = getattr(self, "event_removal_counter", 0) + 1
        if self.event_removal_counter < self.REMOVAL_THRESHOLD:
            logger.info(
                "Goal (event ID: %s) missing (check #%d). Will retry.",
                self.event_id,
                self.event_removal_counter,
            )
            return False

        logger.warning(
            "Goal (event ID: %s) missing for %d checks. Marking for removal.",
            self.event_id,
            self.REMOVAL_THRESHOLD,
        )
        return True

    # ------------------------------------------------------------------
    # Social posting / threading with restart-safe goal cache
    # ------------------------------------------------------------------

    def post_message(
        self,
        message: str,
        link: Optional[str] = None,
        add_hashtags: bool = True,
        add_score: bool = True,
        media: Optional[Union[str, List[str]]] = None,
        alt_text: str = "",
        event_type: str | None = None,  # optional event_type for per-event routing
    ) -> None:
        """
        Threaded posting for GoalEvent:
        - First call: post on all enabled platforms, store PostRef(s).
        - Subsequent calls: reply in-place per platform and advance stored refs.
        Never raises; logs exceptions via context.logger if available.

        Integrates with the restart-safe GameCache (context.cache) so that
        initial goal posts are not duplicated after a process restart.
        """

        # Ensure per-event thread map exists (platform -> PostRef)
        if not hasattr(self, "_post_refs"):
            self._post_refs = {}

        # Restart-safe guard: if this would be treated as an initial post
        # (no in-memory refs yet), consult the per-game cache to avoid
        # re-posting goals after a process restart.
        cache = getattr(self.context, "cache", None)
        if cache is not None and not self._post_refs:
            if cache.was_goal_posted(self.event_id):
                logger.info(
                    "GoalEvent[%s]: initial goal already posted in a previous run; skipping re-post.",
                    self.event_id,
                )
                return

        # Respect debugsocial for hashtags
        add_hashtags = False if getattr(self.context, "debugsocial", False) else add_hashtags

        # Footer (hashtags + score)
        footer_parts: List[str] = []
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
                footer_parts.append(f"{pref.abbreviation}: {pref.score} / {other.abbreviation}: {other.score}")
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
                logger.info(
                    "GoalEvent[%s]: initial post across platforms.",
                    getattr(self, "event_id", "unknown"),
                )
                results = self.context.social.post(
                    message=text,
                    media=media,
                    alt_text=alt_text or "",
                    platforms="enabled",
                    event_type=event_type or "goal",
                )

                # After a successful initial post, mark this goal as posted in the
                # restart-safe cache so we don't re-post it on a future restart.
                if cache is not None:
                    try:
                        cache.mark_goal_posted(
                            self.event_id,
                            team_abbrev=getattr(self, "team_abbreviation", None),
                            sort_order=getattr(self, "sort_order", None),
                        )
                    except Exception as e:
                        logger.warning(
                            "GoalEvent[%s]: failed to mark goal as posted in cache: %s",
                            self.event_id,
                            e,
                        )

                # Store the X ref separately on the event when we get it back
                self._x_post_ref = (results or {}).get("x")

                # Because we never store x into _post_refs, X will only receive the initial goal post,
                # not the later highlight/GIF/whatever replies,
                # while Bluesky + Threads get the full threaded sequence.
                for platform, ref in (results or {}).items():
                    if platform == "x":
                        continue
                    self._post_refs[platform] = ref

                if not results:
                    logger.warning(
                        "GoalEvent[%s]: no PostRefs returned from initial post.",
                        getattr(self, "event_id", "unknown"),
                    )

            else:
                # Reply per platform to maintain threading; update refs as we go.
                logger.info(
                    "GoalEvent[%s]: replying to existing thread on %d platform(s).",
                    getattr(self, "event_id", "unknown"),
                    len(self._post_refs),
                )

                new_refs: Dict[str, any] = {}
                for platform, parent_ref in list(self._post_refs.items()):
                    # For replies we only send a single media item argument.
                    media_arg: Optional[str] = None
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
                        logger.debug(
                            "GoalEvent[%s]: advanced %s thread id=%s",
                            getattr(self, "event_id", "unknown"),
                            platform,
                            res[platform].id,
                        )
                    else:
                        logger.warning(
                            "GoalEvent[%s]: no reply PostRef for %s",
                            getattr(self, "event_id", "unknown"),
                            platform,
                        )

                # Advance stored refs for non-X platforms
                self._post_refs.update(new_refs)

                # Handle X GIF reply separately using the stored X PostRef
                if event_type == "goal_gif" and getattr(self, "_x_post_ref", None) and media:
                    media_arg: Optional[str] = None
                    if isinstance(media, list) and media:
                        media_arg = media[0]
                    elif isinstance(media, str):
                        media_arg = media

                    if media_arg:
                        logger.info(
                            "GoalEvent[%s]: replying with GIF to X thread.",
                            getattr(self, "event_id", "unknown"),
                        )
                        self.context.social.reply(
                            message="",
                            media=media_arg,
                            platforms=X_PLATFORMS,  # ["x"]
                            reply_to=self._x_post_ref,
                        )
        except Exception as e:
            if getattr(self.context, "logger", None):
                self.context.logger.exception("GoalEvent post failed: %s", e)
            else:
                logger.exception("GoalEvent post failed: %s", e)
