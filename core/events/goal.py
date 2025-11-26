import logging
from typing import Dict, List, Optional, Union

from core.gifs.edge_goal import generate_goal_gif_from_edge
from core.gifs.goal_video import ensure_goal_video
from socials.platforms import GIF_PLATFORMS, NON_X_PLATFORMS, VIDEO_PLATFORMS, X_PLATFORMS
from utils.team_details import get_team_details_by_id

from .base import Cache, Event

logger = logging.getLogger(__name__)


class GoalEvent(Event):
    cache = Cache(__name__)

    REMOVAL_THRESHOLD = 5  # Configurable threshold for event removal checks

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # These two silence Pylint AND ensure predictable behavior
        self.goal_gif: str | None = None
        self.goal_gif_video: str | None = None
        self.goal_gif_generated: bool = False

    def parse(self):
        """
        Parse a goal event and return a formatted message.
        """
        details = self.details

        # Add preferred team flag
        event_owner_team_id = details.get("eventOwnerTeamId")
        is_preferred = event_owner_team_id == self.context.preferred_team.team_id
        details["is_preferred"] = is_preferred
        self.is_preferred = is_preferred

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

    def check_and_add_gif(self, context: "GameContext") -> None:
        """
        Generate and post an EDGE goal GIF for this GoalEvent.

        This version uses **INFO-level logging for EVERY branch** so that
        re-runs produce a fully traceable audit trail.
        """

        cfg = (getattr(context, "config", {}) or {}).get("goal_gifs", {})
        event_id = getattr(self, "event_id", "?")

        # ----------------------------------------------------------------------
        # 1. GIF disabled
        # ----------------------------------------------------------------------
        if not cfg.get("enabled", False):
            logger.info(
                "[GIF] Skipping event %s — goal_gifs.enabled = False in config.",
                event_id,
            )
            return

        # ----------------------------------------------------------------------
        # 2. Already generated this run
        # ----------------------------------------------------------------------
        if getattr(self, "goal_gif_generated", False):
            logger.info(
                "[GIF] Skipping event %s — GIF already generated earlier in this run.",
                event_id,
            )
            return

        # ----------------------------------------------------------------------
        # 3. Preferred team restriction
        # ----------------------------------------------------------------------
        preferred_only = cfg.get("preferred_team_only", True)
        is_preferred_goal = getattr(self, "is_preferred", False)

        if preferred_only and not is_preferred_goal:
            logger.info(
                "[GIF] Skipping event %s — not preferred team and preferred_team_only=True.",
                event_id,
            )
            return

        # ----------------------------------------------------------------------
        # 4. Extract core params
        # ----------------------------------------------------------------------
        season = str(getattr(context, "season_id"))
        game_id = str(getattr(context, "game_id"))
        home_abbr = getattr(context, "home_abbr", "")
        away_abbr = getattr(context, "away_abbr", "")

        goal_sweater = getattr(self, "scoring_sweater", None)
        goal_player_id = getattr(self, "scoring_player_id", None)

        logger.info(
            "[GIF] Generating GIF for event %s — %s vs %s (game=%s)",
            event_id,
            away_abbr,
            home_abbr,
            game_id,
        )

        # ----------------------------------------------------------------------
        # 5. Attempt GIF generation
        # ----------------------------------------------------------------------
        try:
            gif_path = generate_goal_gif_from_edge(
                season=season,
                game_id=game_id,
                event_id=event_id,
                home_abbr=home_abbr,
                away_abbr=away_abbr,
                goal_sweater=goal_sweater,
                goal_player_id=goal_player_id,
                width=int(cfg.get("width", 1200)),
                fps=int(cfg.get("fps", 18)),
                playback_speed=float(cfg.get("playback_speed", 0.9)),
                trail_length=int(cfg.get("trail", 1)),
                interp_extra_frames=int(cfg.get("interp_extra_frames", 1)),
                flip_vertical=bool(cfg.get("flip_vertical", True)),
                marker_scale=float(cfg.get("marker_scale", 1.8)),
            )
        except Exception:
            logger.exception(
                "❌ [GIF] Exception while generating goal GIF for event %s.",
                event_id,
            )
            return

        # ----------------------------------------------------------------------
        # 5a. Also generate an MP4 video variant for video-friendly platforms.
        # ----------------------------------------------------------------------
        goal_video_path = None
        try:
            goal_video_path = ensure_goal_video(gif_path)
            logger.info(
                "🎞️ [GIF] Generated MP4 variant for event %s → %s",
                event_id,
                goal_video_path,
            )
        except Exception:
            logger.exception(
                "⚠️ [GIF] Failed to generate MP4 variant for event %s; will fall back to GIF on all platforms.",
                event_id,
            )

        # ----------------------------------------------------------------------
        # 6. GIF generator returned nothing
        # ----------------------------------------------------------------------
        if not gif_path:
            logger.info(
                "⚠️ [GIF] Generator returned no file for event %s — skipping GIF post.",
                event_id,
            )
            return

        # ----------------------------------------------------------------------
        # 7. Mark as generated
        # ----------------------------------------------------------------------
        self.goal_gif = str(gif_path)
        self.goal_gif_video = str(goal_video_path) if goal_video_path else None
        self.goal_gif_generated = True

        logger.info(
            "✅ [GIF] Successfully generated GIF for event %s → %s",
            event_id,
            gif_path,
        )

        # ------------------------------------------------------------------
        # 8. Build caption text for the GIF reply
        # ------------------------------------------------------------------
        scorer = getattr(self, "scoring_player_name", "Unknown scorer")
        team = getattr(self, "team_name", "Unknown team")
        shot_type = getattr(self, "shot_type", None) or "shot"
        period_label = getattr(self, "period_label", "the period")
        time_remaining = getattr(self, "time_remaining", "")

        if is_preferred_goal:
            opening = f"EDGE VIZ: {scorer} scores for the {team}!"
        else:
            opening = f"EDGE VIZ: {scorer} strikes for the {team}."

        shot_label = (shot_type or "shot").lower()

        # Example: "Tip-in from the puck-tracking view (07:06 in the 1st)."
        detail = f"{shot_label.capitalize()} from the puck-tracking view"
        if time_remaining and period_label:
            detail += f" ({time_remaining} in the {period_label})."
        elif period_label:
            detail += f" ({period_label})."
        else:
            detail += "."

        gif_caption = f"{opening}\n{detail}"

        # ----------------------------------------------------------------------
        # 9. Attempt posting
        # ----------------------------------------------------------------------
        try:
            logger.info("[GIF] Posting GIF for event %s (w/ GIF Path: %s)", event_id, gif_path)
            self.post_message(
                message=gif_caption,  # GIF-only reply
                media=[gif_path],
                event_type="goal_gif",
                add_hashtags=True,
                add_score=False,
            )
            logger.info(
                "📤 [GIF] Posted GIF reply for event %s across all platforms.",
                event_id,
            )
        except Exception:
            logger.exception(
                "❌ [GIF] Posting failed for event %s (platform-level error).",
                event_id,
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

    def _pick_media_for_platform(self, platform: str, event_type: str, base_media: str) -> str:
        if event_type == "goal_gif":
            gif_path = self.goal_gif or base_media
            video_path = getattr(self, "goal_gif_video", None)

            logger.info(
                "Media selection (%s, %s): %s -> %s",
                platform,
                event_type,
                base_media,
                video_path if (platform in VIDEO_PLATFORMS and video_path) else gif_path,
            )

            if platform in VIDEO_PLATFORMS and video_path:
                return video_path
            return gif_path
        return base_media

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

        if not hasattr(self, "_root_refs"):
            self._root_refs = {}

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
                # ------------------------------------------------------------------
                # Initial post on all enabled platforms; store refs for future replies.
                # ------------------------------------------------------------------
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
                    # record the root ref once
                    if platform not in self._root_refs:
                        self._root_refs[platform] = ref

                if not results:
                    logger.warning(
                        "GoalEvent[%s]: no PostRefs returned from initial post.",
                        getattr(self, "event_id", "unknown"),
                    )

            else:
                # ------------------------------------------------------------------
                # Reply per platform to maintain threading; update refs as we go.
                # This is where we pick GIF vs MP4 per platform for goal_gif events.
                # ------------------------------------------------------------------
                logger.info(
                    "GoalEvent[%s]: replying to existing thread on %d platform(s).",
                    getattr(self, "event_id", "unknown"),
                    len(self._post_refs),
                )

                effective_event_type = event_type or "goal"
                new_refs: Dict[str, any] = {}

                for platform, parent_ref in list(self._post_refs.items()):
                    # Decide which parent to reply to.
                    reply_parent = parent_ref
                    if effective_event_type == "goal_gif" and platform == "threads":
                        # For GIF/MP4 on Threads, always reply to the root goal post
                        reply_parent = self._root_refs.get(platform, parent_ref)

                    # For replies we only send a single media item argument.
                    base_media: Optional[str] = None
                    if isinstance(media, list) and media:
                        base_media = media[0]
                    elif isinstance(media, str):
                        base_media = media

                    media_arg: Optional[str] = None
                    if base_media:
                        media_arg = self._pick_media_for_platform(
                            platform=platform,
                            event_type=effective_event_type,
                            base_media=base_media,
                        )

                    logging.info("Media Arg for %s: %s", platform, media_arg)

                    res = self.context.social.reply(
                        message=text,
                        media=media_arg,
                        platforms=[platform],
                        reply_to=reply_parent,
                        alt_text=alt_text or "",
                        event_type=effective_event_type,
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

                # Handle X GIF reply separately using the stored X PostRef.
                # This remains GIF-only; X_PLATFORMS is typically ["x"].
                if effective_event_type == "goal_gif" and getattr(self, "_x_post_ref", None) and media:
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
