import logging
from typing import Any, Dict, List, Optional, Union

from core.gifs.edge_goal import generate_goal_gif_from_edge
from core.gifs.goal_video import ensure_goal_video
from core.milestones import MilestoneService
from socials.platforms import GIF_PLATFORMS, NON_X_PLATFORMS, VIDEO_PLATFORMS, X_PLATFORMS
from utils.team_details import get_team_details_by_id

from .base import Cache, Event

logger = logging.getLogger(__name__)


class GoalEvent(Event):
    cache = Cache(__name__)

    SCORING_CHANGE_STABILITY: int = 5  # loops required before posting a scoring change
    REMOVAL_THRESHOLD = 5  # Configurable threshold for event removal checks

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # These two silence Pylint AND ensure predictable behavior
        self.goal_gif: str | None = None
        self.goal_gif_video: str | None = None
        self.goal_gif_generated: bool = False

        # Used for Goal / Scoring Changes (In-Memory Cache)
        self._pending_scoring: dict | None = None
        self._pending_scoring_count: int = 0

    def _build_goal_title_text(self) -> str:
        """Builds the headline line: GOAL / OT GOAL / empty net, etc."""
        is_preferred = getattr(self, "is_preferred", False)
        period_type = getattr(self, "period_type", "").upper()  # "REG", "OT", etc.
        empty_net = self.details.get("goalieInNetId") is None

        pref_team = self.context.preferred_team.full_name
        other_team = self.context.other_team.full_name

        pref_goals = self.preferred_score
        other_goals = self.other_score

        if is_preferred:
            goal_emoji = "🚨" * max(pref_goals, 1)

            # NOTE: OT here is just "overtime goal", not necessarily "winner"
            if period_type == "OT":
                title_core = f"{pref_team} OVERTIME GOAL!!"
            elif empty_net:
                title_core = f"{pref_team} empty net GOAL!"
            elif pref_goals == 7:
                title_core = f"{pref_team} TOUCHDOWN!"
            else:
                title_core = f"{pref_team} GOAL!"
        else:
            goal_emoji = "👎" * max(other_goals, 1)
            title_core = f"{other_team} goal."

        return f"{title_core} {goal_emoji}"

    def _build_goal_main_text(self) -> str:
        """Builds the descriptive text: who scored, how, when, and assists."""
        scorer = getattr(self, "scoring_player_name", "Unknown scorer")
        season_total = getattr(self, "scoring_player_total", None)

        shot_msg = f"scores on a {self.shot_type} shot" if self.shot_type else "scores"
        time_remaining = self.time_remaining
        period_label = self.period_label

        # Scoring line – season total if you have it
        if season_total is not None:
            scoring_line = (
                f"{scorer} ({season_total}) {shot_msg} with " f"{time_remaining} remaining in {period_label}."
            )
        else:
            scoring_line = f"{scorer} {shot_msg} with " f"{time_remaining} remaining in {period_label}."

        # Assists — based on fields you’re already populating
        num_assists = 0
        if getattr(self, "assist1_name", None):
            num_assists += 1
        if getattr(self, "assist2_name", None):
            num_assists += 1

        if num_assists == 1:
            assists_text = f"🍎 {self.assist1_name} ({self.assist1_total})"
        elif num_assists == 2:
            assists_text = (
                f"🍎 {self.assist1_name} ({self.assist1_total})\n" f"🍏 {self.assist2_name} ({self.assist2_total})"
            )
        else:
            assists_text = None

        if assists_text:
            return f"{scoring_line}\n\n{assists_text}"
        return scoring_line

    def _resolve_player_name(self, pid: int) -> str:
        """Best-effort player name resolver for milestone banners."""
        if not pid:
            return "Unknown"

        # 1) Check combined roster
        roster = getattr(self.context, "combined_roster", {}) or {}
        entry = roster.get(pid) or roster.get(str(pid))
        if isinstance(entry, dict):
            name = entry.get("name") or entry.get("full_name")
            if name:
                return name
        elif isinstance(entry, str) and entry.strip():
            return entry.strip()

        # 2) Fallback to names from this event
        if pid == getattr(self, "scoring_player_id", None) and getattr(self, "scoring_player_name", None):
            return self.scoring_player_name
        if pid == getattr(self, "assist1_player_id", None) and getattr(self, "assist1_name", None):
            return self.assist1_name
        if pid == getattr(self, "assist2_player_id", None) and getattr(self, "assist2_name", None):
            return self.assist2_name

        # 3) Last resort: raw ID
        return str(pid)

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

        # 'Log Warning' on missing data
        # We handle missing shot-type via conditional strings now
        if not self.shot_type:
            logger.info("GoalEvent[%s] missing shotType; continuing without it.", self.event_id)

        # --- Milestone integration -------------------------------------------
        milestone_prefix = ""
        milestone_service: MilestoneService = getattr(self.context, "milestone_service", None)

        if milestone_service is not None:
            try:
                hits = milestone_service.handle_goal_event(
                    scoring_player_id=self.scoring_player_id,
                    primary_assist_id=self.assist1_player_id,
                    secondary_assist_id=self.assist2_player_id,
                    is_power_play=False,
                )

                if hits:
                    logger.info(
                        "MilestoneService returned %d hit(s) for goal event %s "
                        "(scorer_id=%s, a1_id=%s, a2_id=%s): %r",
                        len(hits),
                        getattr(self, "event_id", "unknown"),
                        self.scoring_player_id,
                        self.assist1_player_id,
                        self.assist2_player_id,
                        hits,
                    )

                    milestone_prefix = milestone_service.format_hits(
                        hits,
                        player_name_resolver=self._resolve_player_name,
                    )
                    if milestone_prefix:
                        logger.info("Milestone hit on goal: %s", milestone_prefix)
            except Exception:
                logger.exception(
                    "MilestoneService: error while handling goal event; ignoring milestones for this goal."
                )

        # Build Goal Message
        title = self._build_goal_title_text()
        body = self._build_goal_main_text()

        score_line = (
            f"{self.context.preferred_team.full_name}: {self.preferred_score}\n"
            f"{self.context.other_team.full_name}: {self.other_score}"
        )

        if milestone_prefix:
            goal_message = f"{milestone_prefix}\n\n{title}\n\n{body}\n\n{score_line}"
        else:
            goal_message = f"{title}\n\n{body}\n\n{score_line}"

        # Persist the initial scorer/assist IDs so that scoring-change detection
        # is restart-safe and milestone accounting can de-duplicate later.
        self._snapshot_initial_scoring_ids()

        return goal_message

    def _snapshot_initial_scoring_ids(self) -> None:
        """Persist the initial scorer/assist IDs for this goal into GameCache.

        This gives us a baseline for later scoring-change detection and ensures
        restart safety for both change debouncing and milestone accounting.
        """
        cache = getattr(self.context, "cache", None)
        if cache is None:
            return

        scoring = {
            "scorer_id": getattr(self, "scoring_player_id", None),
            "assist1_id": getattr(self, "assist1_player_id", None),
            "assist2_id": getattr(self, "assist2_player_id", None),
        }

        credited_ids = [
            pid
            for pid in (
                scoring.get("scorer_id"),
                scoring.get("assist1_id"),
                scoring.get("assist2_id"),
            )
            if pid
        ]

        try:
            cache.update_goal_snapshot(
                self.event_id, scoring=scoring, initial_scoring=scoring, credited_player_ids=credited_ids
            )
        except Exception as e:
            logger.warning(
                "GoalEvent[%s]: failed to snapshot initial scoring ids: %s",
                getattr(self, "event_id", "unknown"),
                e,
            )

    def check_scoring_changes(self, data: dict) -> Dict[str, object]:
        """Compare current scorer/assist IDs with the latest PBP payload.

        This does **not** mutate the event. It returns a change descriptor that
        `handle_scoring_change` can consume.

        The return dict always contains the following keys:

        - changed: bool
        - scorer_changed / assist1_changed / assist2_changed: bool
        - old_scorer_id / new_scorer_id
        - old_assist1_id / new_assist1_id
        - old_assist2_id / new_assist2_id
        """
        logger.info(
            "Checking for scoring changes (team: %s, event ID: %s).",
            getattr(self, "team_name", "unknown"),
            getattr(self, "event_id", "unknown"),
        )

        details = data.get("details", {}) or {}

        old_scorer = getattr(self, "scoring_player_id", None)
        old_a1 = getattr(self, "assist1_player_id", None)
        old_a2 = getattr(self, "assist2_player_id", None)

        new_scorer = details.get("scoringPlayerId")
        new_a1 = details.get("assist1PlayerId")
        new_a2 = details.get("assist2PlayerId")

        # If the feed temporarily returns no scoring IDs at all, don't treat
        # that as a real scoring change. True overturns are handled via
        # `was_goal_removed` when the entire event disappears.
        if new_scorer is None and new_a1 is None and new_a2 is None:
            return {
                "changed": False,
                "scorer_changed": False,
                "assist1_changed": False,
                "assist2_changed": False,
                "old_scorer_id": old_scorer,
                "new_scorer_id": new_scorer,
                "old_assist1_id": old_a1,
                "new_assist1_id": new_a1,
                "old_assist2_id": old_a2,
                "new_assist2_id": new_a2,
            }

        scorer_changed = new_scorer != old_scorer
        assist1_changed = new_a1 != old_a1
        assist2_changed = new_a2 != old_a2

        changed = scorer_changed or assist1_changed or assist2_changed

        change = {
            "changed": changed,
            "scorer_changed": scorer_changed,
            "assist1_changed": assist1_changed,
            "assist2_changed": assist2_changed,
            "old_scorer_id": old_scorer,
            "new_scorer_id": new_scorer,
            "old_assist1_id": old_a1,
            "new_assist1_id": new_a1,
            "old_assist2_id": old_a2,
            "new_assist2_id": new_a2,
        }

        logger.debug(
            "Scoring change diff for event %s: %r",
            getattr(self, "event_id", "unknown"),
            change,
        )
        return change

    def _build_current_scoring_block(self) -> str:
        """Return a block showing the *current* official scoring for this goal.

        Example:
            🚨 Jack Hughes (23)
            🍎 Jesper Bratt (31)
            🍏 Luke Hughes (12)
        """
        lines: List[str] = []

        scorer_name = getattr(self, "scoring_player_name", None)
        scorer_total = getattr(self, "scoring_player_total", None)

        a1_name = getattr(self, "assist1_name", None)
        a1_total = getattr(self, "assist1_total", None)

        a2_name = getattr(self, "assist2_name", None)
        a2_total = getattr(self, "assist2_total", None)

        # Goal line
        if scorer_name:
            line = f"🚨 {scorer_name}"
            if scorer_total not in (None, 0):
                line += f" ({scorer_total})"
            lines.append(line)

        # Primary assist
        if a1_name:
            line = f"🍎 {a1_name}"
            if a1_total not in (None, 0):
                line += f" ({a1_total})"
            lines.append(line)

        # Secondary assist
        if a2_name:
            line = f"🍏 {a2_name}"
            if a2_total not in (None, 0):
                line += f" ({a2_total})"
            lines.append(line)

        return "\n".join(lines)

    def _build_scoring_change_text(self, change: Dict[str, object]) -> str:
        """Build user-facing text for a scoring-change update.

        Target format:

        The scoring on this goal has changed.
        Primary assist added for Jesper Bratt.

        🚨 Jack Hughes (23)
        🍎 Jesper Bratt (31)
        🍏 Luke Hughes (12)
        """
        lines: List[str] = ["The scoring on this goal has changed."]

        new_scorer_id = change.get("new_scorer_id")
        old_scorer_id = change.get("old_scorer_id")
        new_a1_id = change.get("new_assist1_id")
        old_a1_id = change.get("old_assist1_id")
        new_a2_id = change.get("new_assist2_id")
        old_a2_id = change.get("old_assist2_id")

        scorer_changed = bool(change.get("scorer_changed"))
        assist1_changed = bool(change.get("assist1_changed"))
        assist2_changed = bool(change.get("assist2_changed"))

        diff_clauses: List[str] = []

        # --- Scorer diffs ----------------------------------------------------
        if scorer_changed:
            new_name = self._safe_player_name(new_scorer_id)
            old_name = self._safe_player_name(old_scorer_id) if old_scorer_id else None

            if new_scorer_id and old_scorer_id:
                diff_clauses.append(f"Goal now credited to {new_name} (was {old_name}).")
            elif new_scorer_id and not old_scorer_id:
                diff_clauses.append(f"Goal now credited to {new_name}.")
            elif not new_scorer_id and old_scorer_id:
                diff_clauses.append(f"Goal has been removed from {old_name}.")

        # --- Primary assist diffs --------------------------------------------
        if assist1_changed:
            new_name = self._safe_player_name(new_a1_id)
            old_name = self._safe_player_name(old_a1_id) if old_a1_id else None

            if new_a1_id and old_a1_id:
                diff_clauses.append(f"Primary assist now {new_name} (was {old_name}).")
            elif new_a1_id and not old_a1_id:
                diff_clauses.append(f"Primary assist added for {new_name}.")
            elif not new_a1_id and old_a1_id:
                diff_clauses.append(f"Primary assist removed from {old_name}.")

        # --- Secondary assist diffs ------------------------------------------
        if assist2_changed:
            new_name = self._safe_player_name(new_a2_id)
            old_name = self._safe_player_name(old_a2_id) if old_a2_id else None

            if new_a2_id and old_a2_id:
                diff_clauses.append(f"Secondary assist now {new_name} (was {old_name}).")
            elif new_a2_id and not old_a2_id:
                diff_clauses.append(f"Secondary assist added for {new_name}.")
            elif not new_a2_id and old_a2_id:
                diff_clauses.append(f"Secondary assist removed from {old_name}.")

        # Attach a single diff line (or multiple joined with spaces)
        if diff_clauses:
            lines.append(" ".join(diff_clauses))

        # Blank line, then current official scoring block
        block = self._build_current_scoring_block()
        if block:
            lines.append("")
            lines.append(block)

        return "\n".join(lines)

    def _safe_player_name(self, player_id: Optional[int]) -> str:
        """Resolve a player ID to a name using context.combined_roster.

        combined_roster is built from flatten_roster/load_team_rosters and
        uses int player IDs mapped to "First Last".
        """
        if not player_id:
            return "Unknown"

        roster = getattr(self.context, "combined_roster", {}) or {}

        # Keys are usually ints, but be defensive and try a few variants.
        name = roster.get(player_id)
        if name is None and isinstance(player_id, str):
            try:
                name = roster.get(int(player_id))
            except ValueError:
                pass
        if name is None:
            name = roster.get(str(player_id))

        if isinstance(name, str) and name.strip():
            return name.strip()

        return "Unknown"

    def handle_scoring_change(self, change: Dict[str, object]) -> None:
        """Apply a confirmed scoring change and, if stable, post an update.

        This is called from the event factory when an existing GoalEvent is
        seen again on a loop with **no new plays** and the PBP payload
        indicates a scorer/assist change.

        Debounce behavior:
        - Uses in-memory attributes `_pending_scoring` and
          `_pending_scoring_count` to require the same candidate scoring triple
          to appear `SCORING_CHANGE_STABILITY` times in a row before we accept it.
        - Only when the change is accepted do we write to GameCache.goal_snapshots.
        """
        if not change.get("changed"):
            return

        cache = getattr(self.context, "cache", None)
        snapshot: Dict[str, Any] = cache.get_goal_snapshot(self.event_id) if cache else {}

        # ----- Figure out the current accepted scoring triple ----------------
        current_scoring = snapshot.get("scoring") or {
            "scorer_id": getattr(self, "scoring_player_id", None),
            "assist1_id": getattr(self, "assist1_player_id", None),
            "assist2_id": getattr(self, "assist2_player_id", None),
        }

        new_scoring = {
            "scorer_id": change.get("new_scorer_id"),
            "assist1_id": change.get("new_assist1_id"),
            "assist2_id": change.get("new_assist2_id"),
        }

        # If the "new" triple is identical to the accepted triple, nothing to do.
        if new_scoring == current_scoring:
            logger.debug(
                "GoalEvent[%s]: scoring change payload matches accepted scoring; " "no update needed.",
                getattr(self, "event_id", "unknown"),
            )
            return

        # ----- Debounce using in-memory pending state ------------------------
        pending_scoring = getattr(self, "_pending_scoring", None)
        pending_count = getattr(self, "_pending_scoring_count", 0)

        if pending_scoring == new_scoring:
            pending_count += 1
        else:
            pending_scoring = new_scoring
            pending_count = 1

        # Persist back to the instance so it survives across iterations in
        # this process (but not across restarts).
        self._pending_scoring = pending_scoring
        self._pending_scoring_count = pending_count

        logger.debug(
            "GoalEvent[%s]: pending scoring change=%r (count=%d/%d).",
            getattr(self, "event_id", "unknown"),
            pending_scoring,
            pending_count,
            self.SCORING_CHANGE_STABILITY,
        )

        if pending_count < self.SCORING_CHANGE_STABILITY:
            # Not stable yet; wait for more consistent loops before posting.
            return

        # At this point the new scoring is considered stable. Reset pending state.
        self._pending_scoring = None
        self._pending_scoring_count = 0

        # ----- Update in-memory scoring IDs ----------------------------------
        logger.info(
            "GoalEvent[%s]: accepting scoring change; new scoring=%r (previous=%r).",
            getattr(self, "event_id", "unknown"),
            new_scoring,
            current_scoring,
        )

        self.scoring_player_id = new_scoring["scorer_id"]
        self.assist1_player_id = new_scoring["assist1_id"]
        self.assist2_player_id = new_scoring["assist2_id"]

        # ----- Milestones: figure out who is newly credited -------------------
        milestone_hits: List[Any] = []
        milestone_service = getattr(self.context, "milestone_service", None)

        already_credited: set[int] = set(snapshot.get("credited_player_ids") or [])

        newly_credited_ids: set[int] = {
            pid
            for pid in (
                new_scoring.get("scorer_id"),
                new_scoring.get("assist1_id"),
                new_scoring.get("assist2_id"),
            )
            if pid
        }
        newly_credited_ids.difference_update(already_credited)

        if milestone_service is not None and newly_credited_ids:
            try:
                scorer_ids: List[int] = []
                assist_ids: List[int] = []

                if new_scoring.get("scorer_id") in newly_credited_ids:
                    scorer_ids.append(new_scoring["scorer_id"])

                for key in ("assist1_id", "assist2_id"):
                    pid = new_scoring.get(key)
                    if pid in newly_credited_ids:
                        assist_ids.append(pid)

                milestone_hits = milestone_service.handle_scoring_change(
                    new_scorer_ids=scorer_ids,
                    new_assist_ids=assist_ids,
                    is_power_play=False,  # PP milestones disabled for now
                )
            except Exception:
                logger.exception(
                    "MilestoneService: error while handling scoring change; " "ignoring milestones for this change.",
                )
                milestone_hits = []

        # ----- Persist durable scoring state into GameCache -------------------
        updated_credited = set(already_credited)
        updated_credited.update(
            pid
            for pid in (
                new_scoring.get("scorer_id"),
                new_scoring.get("assist1_id"),
                new_scoring.get("assist2_id"),
            )
            if pid
        )

        if cache is not None:
            try:
                cache.update_goal_snapshot(
                    self.event_id,
                    scoring=new_scoring,
                    credited_player_ids=sorted(updated_credited),
                )
            except Exception as e:
                logger.warning(
                    "GoalEvent[%s]: failed to update goal snapshot after scoring change: %s",
                    getattr(self, "event_id", "unknown"),
                    e,
                )

        # ----- Build and send the scoring-change post ------------------------
        change_text = self._build_scoring_change_text(change)

        milestone_prefix = ""
        if milestone_hits:
            try:
                # We can keep this simple and rely on the existing formatter.
                milestone_prefix = milestone_service.format_hits(milestone_hits)
            except Exception:
                logger.exception(
                    "GoalEvent[%s]: failed to format milestone hits for scoring change.",
                    getattr(self, "event_id", "unknown"),
                )
                milestone_prefix = ""

        if milestone_prefix:
            post_text = f"{milestone_prefix}\n\n{change_text}"
        else:
            post_text = change_text

        # Use the existing threading/hashtag/scoreline behavior in Event.post_message
        self.post_message(post_text, add_hashtags=True, add_score=True, event_type="scoring_change")

    def check_and_add_highlight(self, event_data):
        """
        Check event_data for highlight_clip_url, post a message if found, and update the event object.

        Args:
            event_data (dict): The raw event data from the NHL Play-by-Play API.
        """
        # Extract highlight clip URL from event_data
        highlight_clip_url = event_data.get("details", {}).get("highlightClipSharingUrl")
        event_id = event_data.get("eventId")

        if not highlight_clip_url:
            logger.info("No highlight clip URL found for event ID %s.", event_data.get("eventId"))
            return

        normalized = highlight_clip_url.rstrip("/").lower()
        invalid_roots = {
            "https://nhl.com/video",
            "https://www.nhl.com/video",
        }

        if normalized in invalid_roots:
            logger.info(
                "Invalid highlight clip root URL %s found for event ID %s — skipping.",
                highlight_clip_url,
                event_id,
            )
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

        # ------------------------------------------------------------------
        # 2A. Per-context guard: covers duplicate GoalEvent objects and multiple
        # call sites (live loop + wait_for_goal_gifs).
        # ------------------------------------------------------------------
        seen_ids = getattr(context, "generated_goal_gif_ids", None)
        if seen_ids is None:
            seen_ids = set()
            setattr(context, "generated_goal_gif_ids", seen_ids)

        if event_id in seen_ids:
            logger.info(
                "[GIF] Skipping event %s — GIF already generated earlier for this game (context-level).",
                event_id,
            )
            # Keep the instance flag in sync so later calls on this object
            # also fast-path through the per-instance guard.
            self.goal_gif_generated = True
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
        home_abbr = getattr(context.home_team, "abbreviation", "")
        away_abbr = getattr(context.away_team, "abbreviation", "")

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
        # 5A. Bail out if we still don't have a GIF
        # ----------------------------------------------------------------------
        if not gif_path:
            logger.info(
                "⚠️ [GIF] Generator returned no file for event %s — skipping GIF post.",
                event_id,
            )
            return

        # ----------------------------------------------------------------------
        # 5a. Also generate an MP4 video variant for video-friendly platforms.
        # ----------------------------------------------------------------------
        goal_video_path: Optional[Path] = None
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

        # Mark Goal GIF Generated at Context Level Too
        try:
            seen_ids = getattr(context, "generated_goal_gif_ids", None)
            if isinstance(seen_ids, set):
                seen_ids.add(event_id)
        except Exception:
            # Non-fatal; just means we won't get the extra protection.
            pass

        # ------------------------------------------------------------------
        # 8. Build caption text for the GIF reply
        # ------------------------------------------------------------------
        scorer = getattr(self, "scoring_player_name", "Unknown scorer")
        team = getattr(self, "team_name", "Unknown team")
        shot_type = getattr(self, "shot_type", None) or "shot"
        period_label = getattr(self, "period_label", "the period")
        time_remaining = getattr(self, "time_remaining", "")

        if is_preferred_goal:
            opening = f"🎥 EDGE VIZ: {scorer} scores for the {team}!"
        else:
            opening = f"🎥 EDGE VIZ: {scorer} strikes for the {team}."

        shot_label = (shot_type or "shot").lower()

        # Example: "Tip-in from the puck-tracking view (07:06 in the 1st)."
        detail = f"on a {shot_label.lower()}"
        if time_remaining and period_label:
            detail += f" ({time_remaining} remaining in {period_label})."
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

        # Ensure we track whether the initial post was ever made,
        # independent of whether we have non-X refs in _post_refs.
        if not hasattr(self, "_has_initial_post"):
            self._has_initial_post = False

        # Restart-safe guard: if this would be treated as an initial post
        # (no in-memory refs yet), consult the per-game cache to avoid
        # re-posting goals after a process restart.
        cache = getattr(self.context, "cache", None)
        if cache is not None and not self._post_refs:
            followup_types = {"goal_gif", "goal_highlight", "scoring_change"}
            if (event_type or "goal") not in followup_types and cache.was_goal_posted(self.event_id):
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
            if not self._has_initial_post:
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

                # Only flip the flag if we actually got something back
                if results:
                    self._has_initial_post = True

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

                    # NEW: skip X here for goal_gif, we handle it separately
                    if effective_event_type == "goal_gif" and platform in X_PLATFORMS:
                        continue

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
                            message=text,
                            media=media_arg,
                            platforms=X_PLATFORMS,  # ["x"]
                            reply_to=self._x_post_ref,
                        )
        except Exception as e:
            if getattr(self.context, "logger", None):
                self.context.logger.exception("GoalEvent post failed: %s", e)
            else:
                logger.exception("GoalEvent post failed: %s", e)
