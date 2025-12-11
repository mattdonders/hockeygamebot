"""
Status Monitor for Hockey Game Bot

This module provides real-time monitoring and health tracking for the bot.
It writes status information to status.json which can be viewed via dashboard.html

Usage:
    from utils.status_monitor import StatusMonitor

    # Initialize at startup
    monitor = StatusMonitor()

    # Update throughout execution
    monitor.update_game_state(context)
    monitor.increment_event("goal")
    monitor.record_api_call(success=True)
    monitor.record_error("API timeout")
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class StatusMonitor:
    """Monitor and track bot health, statistics, and current state."""

    def __init__(self, status_file: Path = None):
        """
        Initialize the StatusMonitor.

        Args:
            status_file: Path to the JSON file where status will be written.
                        Defaults to 'status.json' in the current directory.
        """
        self.status_file = status_file or Path("status.json")
        self.lock = Lock()
        self.start_time = datetime.now()

        # Track write failures
        self._consecutive_write_failures = 0
        self._max_consecutive_failures = 10
        self._monitoring_enabled = True

        # Initialize status structure
        self.status = {
            "bot": {
                "status": "STARTING",
                "version": "2.0",
                "start_time": self.start_time.isoformat(),
                "last_update": None,
                "uptime_seconds": 0,
            },
            "game": {
                "game_id": None,
                "game_state": None,
                "home_team": None,
                "away_team": None,
                "home_score": None,
                "away_score": None,
                "period": None,
                "time_remaining": None,
                "venue": None,
                "in_intermission": False,
            },
            "social": {
                "x": None,
            },
            "events": {
                "total": 0,
                "goals": 0,
                "penalties": 0,
                "saves": 0,
                "shots": 0,
                "hits": 0,
                "blocks": 0,
                "takeaways": 0,
                "giveaways": 0,
                "faceoffs": 0,
                "other": 0,
            },
            "performance": {
                "live_loop_count": 0,
                "last_loop_time": None,
                "api_calls": {
                    "total": 0,
                    "successful": 0,
                    "failed": 0,
                },
            },
            "errors": {
                "count": 0,
                "last_error": None,
                "last_error_time": None,
            },
            "socials": {
                "posts_sent": 0,
                "preview_posts": {
                    "core_sent": False,
                    "milestone_sent": False,
                    "officials_sent": False,
                },
                "last_post_time": None,
            },
            "health": {
                "healthy": True,
                "issues": [],
            },
            "cache": {
                "enabled": False,
                "summary": None,
                "raw": None,
                "last_updated": None,
            },
        }

        # Write initial status
        self._write_status()
        logger.info(f"StatusMonitor initialized, writing to {self.status_file}")

    def update_game_state(self, context) -> None:
        """
        Update game state from GameContext (thread-safe with snapshots).

        Args:
            context: GameContext object containing current game state
        """
        # STEP 1: Create immutable snapshots (fast, no lock needed)
        game_snapshot = None
        game_id = None
        game_state = None
        venue = None
        home_team_abbrev = None
        away_team_abbrev = None
        home_score = None
        away_score = None
        clock_time_remaining = None
        clock_in_intermission = False
        period = None
        period_type = None
        events_snapshot = []
        live_loop_counter = 0
        cache_snapshot = None
        x_limit_snapshot = None

        # Quickly copy only what we need
        try:
            if context.game:
                game_snapshot = dict(context.game)
                game_id = context.game_id
                game_state = context.game_state
                venue = context.venue

                if context.home_team:
                    home_team_abbrev = context.home_team.abbreviation
                    home_score = game_snapshot.get("homeTeam", {}).get("score")

                if context.away_team:
                    away_team_abbrev = context.away_team.abbreviation
                    away_score = game_snapshot.get("awayTeam", {}).get("score")

                # Fallback: if the game snapshot doesn't have scores yet, derive them
                # from the running GoalEvent context (preferred_team/other_team).
                #
                # GoalEvent keeps these up to date on every goal:
                #   context.preferred_team.score
                #   context.other_team.score
                try:
                    pref_team = getattr(context, "preferred_team", None)
                    other_team = getattr(context, "other_team", None)
                    pref_homeaway = getattr(context, "preferred_homeaway", None)

                    pref_score = getattr(pref_team, "score", None) if pref_team else None
                    other_score = getattr(other_team, "score", None) if other_team else None

                    # Only override if the game dict has no scores at all
                    if (
                        pref_homeaway in ("home", "away")
                        and pref_score is not None
                        and other_score is not None
                        and home_score is None
                        and away_score is None
                    ):
                        if pref_homeaway == "home":
                            home_score = pref_score
                            away_score = other_score
                        else:
                            home_score = other_score
                            away_score = pref_score
                except Exception:
                    # Never let scoreboard issues break status updates
                    pass

                if context.clock:
                    clock_time_remaining = context.clock.time_remaining
                    clock_in_intermission = context.clock.in_intermission

                # --- Prefer live period info from context, fall back to snapshot ---
                period = None
                period_type = None

                # 1) Prefer live periodDescriptor from the PBP (parse_live_game)
                pd_live = getattr(context, "period_descriptor", None)
                if isinstance(pd_live, dict) and pd_live:
                    period = pd_live.get("number")
                    period_type = pd_live.get("periodType")

                # 2) Next, prefer live displayPeriod from the PBP
                if period is None:
                    display_period = getattr(context, "display_period", None)
                    if display_period is not None:
                        period = display_period

                # 3) Finally, fall back to the original schedule snapshot if we have nothing else
                if period is None and game_snapshot:
                    pd_snap = game_snapshot.get("periodDescriptor") or {}
                    if pd_snap:
                        # only fill things that are still missing
                        period = period or pd_snap.get("number")
                        period_type = period_type or pd_snap.get("periodType")

                    if period is None:
                        # last-ditch fallback
                        period = game_snapshot.get("displayPeriod")

            if context.events:
                events_snapshot = list(context.events)

            if hasattr(context, 'live_loop_counter'):
                live_loop_counter = context.live_loop_counter

            # Snapshot cache (if present)
            if hasattr(context, "cache") and context.cache is not None:
                try:
                    cache_snapshot = context.cache.to_dict()
                except Exception as e:
                    logger.warning(f"Failed to snapshot cache: {e}")
                    cache_snapshot = None

            # Copy social tracking state
            preview_socials_data = None
            if hasattr(context, 'preview_socials'):
                preview_socials_data = {
                    "core_sent": context.preview_socials.core_sent,
                    "milestones_sent": context.preview_socials.milestones_sent,
                    "officials_sent": context.preview_socials.officials_sent,
                    "all_pregame_sent": context.preview_socials.all_pregame_sent,
                }

            limiter = None
            social = getattr(context, "social", None)

            if social is not None and hasattr(social, "x_rate_limiter"):
                limiter = social.x_rate_limiter
            elif hasattr(context, "x_rate_limiter") and context.x_rate_limiter is not None:
                limiter = context.x_rate_limiter

            if limiter is not None:
                try:
                    state = limiter.get_state() or {}
                    x_limit_snapshot = {
                        "utc_day": state.get("day"),
                        "count": state.get("count", 0),
                        "warning_sent": state.get("warning_sent", False),
                        "content_limit": getattr(limiter, "CONTENT_LIMIT", 15),
                        "daily_limit": getattr(limiter, "DAILY_LIMIT", 17),
                    }
                except Exception as e:
                    logger.warning(f"Failed to snapshot X rate-limit state: {e}")
                    x_limit_snapshot = None
            else:
                logger.warning("No X rate limiter found in context or social publisher")
                x_limit_snapshot = None

        except Exception as e:
            # If snapshot fails, log but don't crash
            logger.error(f"Error creating game state snapshot: {e}")
            return

        # STEP 2: Now update status with lock (using snapshots)
        with self.lock:
            # Update game info
            if game_snapshot:
                self.status["game"]["game_id"] = game_id
                self.status["game"]["game_state"] = game_state
                self.status["game"]["venue"] = venue
                self.status["game"]["home_team"] = home_team_abbrev
                self.status["game"]["home_score"] = home_score
                self.status["game"]["away_team"] = away_team_abbrev
                self.status["game"]["away_score"] = away_score
                self.status["game"]["time_remaining"] = clock_time_remaining
                self.status["game"]["in_intermission"] = clock_in_intermission

                # Period info
                self.status["game"]["period"] = period
                self.status["game"]["period_type"] = period_type

            # Update event counts
            if events_snapshot:
                self.status["events"]["total"] = len(events_snapshot)

                # Count events by type
                event_types = {}
                for event in events_snapshot:
                    # Events are objects with event_type attribute, not dicts
                    if isinstance(event, dict):
                        event_type = event.get("typeDescKey", "other")
                    else:
                        event_type = getattr(event, 'event_type', 'other')
                    event_types[event_type] = event_types.get(event_type, 0) + 1

                # Map to tracking categories
                self.status["events"]["goals"] = event_types.get("goal", 0)
                self.status["events"]["penalties"] = event_types.get("penalty", 0)
                self.status["events"]["saves"] = event_types.get("shot-on-goal", 0)
                self.status["events"]["shots"] = event_types.get("shot-on-goal", 0)
                self.status["events"]["hits"] = event_types.get("hit", 0)
                self.status["events"]["blocks"] = event_types.get("blocked-shot", 0)
                self.status["events"]["takeaways"] = event_types.get("takeaway", 0)
                self.status["events"]["giveaways"] = event_types.get("giveaway", 0)
                self.status["events"]["faceoffs"] = event_types.get("faceoff", 0)

            # Update loop counter
            self.status["performance"]["live_loop_count"] = live_loop_counter
            self.status["performance"]["last_loop_time"] = datetime.now().isoformat()

            # Update cache info
            if cache_snapshot:
                processed = cache_snapshot.get("processed_event_ids") or []
                goals = cache_snapshot.get("goal_snapshots") or {}

                self.status["cache"]["enabled"] = True
                self.status["cache"]["summary"] = {
                    "season_id": cache_snapshot.get("season_id"),
                    "game_id": cache_snapshot.get("game_id"),
                    "team_abbrev": cache_snapshot.get("team_abbrev"),
                    "processed_events": len(processed),
                    "goal_snapshots": len(goals),
                    "last_sort_order": cache_snapshot.get("last_sort_order"),
                }
                self.status["cache"]["raw"] = cache_snapshot
                self.status["cache"]["last_updated"] = datetime.now().isoformat()
            else:
                self.status["cache"]["enabled"] = False
                self.status["cache"]["summary"] = None
                self.status["cache"]["raw"] = None
                # keep last_updated as-is so you can see when it last existed

            # Update social tracking
            if preview_socials_data:
                self.status["socials"]["preview_posts"]["core_sent"] = preview_socials_data['core_sent']
                self.status["socials"]["preview_posts"]["milestones_sent"] = preview_socials_data['milestones_sent']
                self.status["socials"]["preview_posts"]["officials_sent"] = preview_socials_data['officials_sent']
                self.status["socials"]["preview_posts"]["all_pregame_sent"] = preview_socials_data['all_pregame_sent']

            # Update structured X / Twitter limit info for dashboard
            if x_limit_snapshot is not None:
                self.status.setdefault("social", {})
                self.status["social"]["x"] = x_limit_snapshot

            self._check_health()
            self._write_status()

    def increment_event(self, event_type: str) -> None:
        """
        Increment counter for a specific event type.

        Args:
            event_type: Type of event (goal, penalty, shot, etc.)
        """
        with self.lock:
            self.status["events"]["total"] += 1

            event_key = event_type.lower()
            if event_key in self.status["events"]:
                self.status["events"][event_key] += 1
            else:
                self.status["events"]["other"] += 1

            self._write_status()

    def record_api_call(self, success: bool = True) -> None:
        """
        Record an API call and its result.

        Args:
            success: Whether the API call was successful
        """
        with self.lock:
            self.status["performance"]["api_calls"]["total"] += 1
            if success:
                self.status["performance"]["api_calls"]["successful"] += 1
            else:
                self.status["performance"]["api_calls"]["failed"] += 1

            self._check_health()
            self._write_status()

    def record_error(self, error_message: str) -> None:
        """
        Record an error occurrence.

        Args:
            error_message: Description of the error
        """
        with self.lock:
            self.status["errors"]["count"] += 1
            self.status["errors"]["last_error"] = error_message
            self.status["errors"]["last_error_time"] = datetime.now().isoformat()

            self._check_health()
            self._write_status()

            logger.warning(f"Error recorded: {error_message}")

    def record_social_post(self) -> None:
        """Record that a social media post was sent."""
        with self.lock:
            self.status["socials"]["posts_sent"] += 1
            self.status["socials"]["last_post_time"] = datetime.now().isoformat()
            self._write_status()

    def set_status(self, status: str) -> None:
        """
        Set the bot's current status.

        Args:
            status: Status string (STARTING, RUNNING, SLEEPING, ERROR, STOPPED)
        """
        with self.lock:
            self.status["bot"]["status"] = status
            self._write_status()

    def _check_health(self) -> None:
        """Check bot health and update health status."""
        issues = []

        # Check error rate
        if self.status["errors"]["count"] > 10:
            issues.append(f"High error count ({self.status['errors']['count']} errors)")

        # Check API failure rate
        api_calls = self.status["performance"]["api_calls"]
        total_calls = api_calls["total"]
        failed_calls = api_calls["failed"]
        if total_calls > 10 and (failed_calls / total_calls) > 0.1:  # >10% failure rate
            failure_rate = (failed_calls / total_calls) * 100
            issues.append(f"High API failure rate ({failure_rate:.1f}%)")

        # Check if last update is recent (if running)
        if self.status["bot"]["status"] == "RUNNING":
            last_update = self.status["bot"]["last_update"]
            if last_update:
                try:
                    last_update_time = datetime.fromisoformat(last_update)
                    seconds_since_update = (datetime.now() - last_update_time).total_seconds()
                    if seconds_since_update > 300:  # No update in 5 minutes
                        issues.append(f"No recent updates ({int(seconds_since_update/60)} minutes)")
                except ValueError:
                    pass

        self.status["health"]["healthy"] = len(issues) == 0
        self.status["health"]["issues"] = issues

    def _write_status(self) -> None:
        """Write status to JSON file with error recovery."""
        # If monitoring is disabled due to too many failures, skip
        if not self._monitoring_enabled:
            return

        try:
            # Update timestamps and uptime
            now = datetime.now()
            self.status["bot"]["last_update"] = now.isoformat()
            self.status["bot"]["uptime_seconds"] = int((now - self.start_time).total_seconds())

            # Write to file atomically
            temp_file = self.status_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(self.status, f, indent=2)
            temp_file.replace(self.status_file)

            # Success - reset failure counter
            self._consecutive_write_failures = 0

        except PermissionError as e:
            self._consecutive_write_failures += 1
            logger.error(f"Permission denied writing status file (failure {self._consecutive_write_failures}): {e}")
            self._check_disable_monitoring()

        except OSError as e:
            self._consecutive_write_failures += 1
            logger.error(f"OS error writing status file (failure {self._consecutive_write_failures}): {e}")
            self._check_disable_monitoring()

        except Exception as e:
            self._consecutive_write_failures += 1
            logger.error(
                f"Unexpected error writing status file (failure {self._consecutive_write_failures}): {e}", exc_info=True
            )
            self._check_disable_monitoring()

    def _check_disable_monitoring(self) -> None:
        """Disable monitoring if too many consecutive failures."""
        if self._consecutive_write_failures >= self._max_consecutive_failures:
            self._monitoring_enabled = False
            logger.critical(
                f"Monitoring disabled after {self._max_consecutive_failures} consecutive write failures. "
                "Bot will continue running but dashboard will show stale data."
            )
            logger.critical("To re-enable, fix the status.json write issue and restart the bot.")

    def get_status(self) -> Dict[str, Any]:
        """Get current status as dictionary."""
        with self.lock:
            return self.status.copy()

    def shutdown(self) -> None:
        """Mark bot as stopped."""
        with self.lock:
            self.status["bot"]["status"] = "STOPPED"
            self._write_status()
            logger.info("StatusMonitor shutdown complete")


# Convenience function for easy import
def create_status_monitor(status_file: str = "status.json") -> StatusMonitor:
    """
    Create and return a StatusMonitor instance.

    Args:
        status_file: Path to status JSON file

    Returns:
        StatusMonitor instance
    """
    return StatusMonitor(Path(status_file))
