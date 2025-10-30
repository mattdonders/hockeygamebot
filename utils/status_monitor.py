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
from typing import Dict, Any, Optional

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
                    "season_series_sent": False,
                    "team_stats_sent": False,
                    "officials_sent": False,
                },
                "last_post_time": None,
            },
            "health": {
                "healthy": True,
                "issues": [],
            }
        }

        # Write initial status
        self._write_status()
        logger.info(f"StatusMonitor initialized, writing to {self.status_file}")

    def update_game_state(self, context) -> None:
        """
        Update game state from GameContext.

        Args:
            context: GameContext object containing current game state
        """
        with self.lock:
            # Update game info
            if context.game:
                self.status["game"]["game_id"] = context.game_id
                self.status["game"]["game_state"] = context.game_state
                self.status["game"]["venue"] = context.venue

                # Team info
                if context.home_team:
                    self.status["game"]["home_team"] = f"{context.home_team.abbreviation}"
                    self.status["game"]["home_score"] = context.game.get("homeTeam", {}).get("score")

                if context.away_team:
                    self.status["game"]["away_team"] = f"{context.away_team.abbreviation}"
                    self.status["game"]["away_score"] = context.game.get("awayTeam", {}).get("score")

                # Clock info (Clock object only has time_remaining and in_intermission)
                if context.clock:
                    self.status["game"]["time_remaining"] = context.clock.time_remaining
                    self.status["game"]["in_intermission"] = context.clock.in_intermission

                # Period info comes from the game data, not Clock
                if context.game:
                    period_descriptor = context.game.get("periodDescriptor", {})
                    self.status["game"]["period"] = period_descriptor.get("number")
                    # Also store period type (REG, OT, SO) if available
                    period_type = period_descriptor.get("periodType")
                    if period_type and period_type != "REG":
                        period_num = self.status["game"]["period"]
                        self.status["game"]["period"] = f"{period_num} ({period_type})"

            # Update event counts
            if context.events:
                self.status["events"]["total"] = len(context.events)

                # Count events by type
                event_types = {}
                for event in context.events:
                    event_type = event.get("typeDescKey", "other")
                    event_types[event_type] = event_types.get(event_type, 0) + 1

                # Map to our tracking categories
                self.status["events"]["goals"] = event_types.get("goal", 0)
                self.status["events"]["penalties"] = event_types.get("penalty", 0)
                self.status["events"]["saves"] = event_types.get("shot-on-goal", 0)  # Approximate
                self.status["events"]["shots"] = event_types.get("shot-on-goal", 0)
                self.status["events"]["hits"] = event_types.get("hit", 0)
                self.status["events"]["blocks"] = event_types.get("blocked-shot", 0)
                self.status["events"]["takeaways"] = event_types.get("takeaway", 0)
                self.status["events"]["giveaways"] = event_types.get("giveaway", 0)
                self.status["events"]["faceoffs"] = event_types.get("faceoff", 0)

            # Update loop counter
            if hasattr(context, 'live_loop_counter'):
                self.status["performance"]["live_loop_count"] = context.live_loop_counter
                self.status["performance"]["last_loop_time"] = datetime.now().isoformat()

            # Update social tracking
            if hasattr(context, 'preview_socials'):
                self.status["socials"]["preview_posts"]["core_sent"] = context.preview_socials.core_sent
                self.status["socials"]["preview_posts"]["season_series_sent"] = context.preview_socials.season_series_sent
                self.status["socials"]["preview_posts"]["team_stats_sent"] = context.preview_socials.team_stats_sent
                self.status["socials"]["preview_posts"]["officials_sent"] = context.preview_socials.officials_sent

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
        """Write status to JSON file."""
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

        except Exception as e:
            logger.error(f"Error writing status file: {e}")

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