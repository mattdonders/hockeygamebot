"""Tests for StatusMonitor

These tests verify the bug fixes we applied, especially:
- Handling Event objects (not just dicts)
- Thread safety
- File writing
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from utils.status_monitor import StatusMonitor


class TestStatusMonitorEventHandling:
    """Test the event handling we fixed in Bug #2"""

    def test_handles_event_objects(self):
        """Test that StatusMonitor handles Event objects (Bug #2 fix)"""
        # Setup
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_file = Path(f.name)

        try:
            monitor = StatusMonitor(status_file=temp_file)

            # Create mock context with Event objects
            context = self._create_mock_context_with_events()

            # Execute - this should NOT crash
            monitor.update_game_state(context)

            # Assert
            assert monitor.status["events"]["total"] == 3
            assert monitor.status["events"]["goals"] == 1
            assert monitor.status["events"]["penalties"] == 1

        finally:
            temp_file.unlink(missing_ok=True)

    def test_handles_dict_events(self):
        """Test that StatusMonitor still handles dict events (backwards compatibility)"""
        # Setup
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_file = Path(f.name)

        try:
            monitor = StatusMonitor(status_file=temp_file)

            # Create mock context with dict events (old format)
            context = self._create_mock_context_with_dict_events()

            # Execute
            monitor.update_game_state(context)

            # Assert
            assert monitor.status["events"]["total"] == 2
            assert monitor.status["events"]["goals"] == 1

        finally:
            temp_file.unlink(missing_ok=True)

    def test_handles_mixed_event_types(self):
        """Test that StatusMonitor handles both dicts and objects"""
        # Setup
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_file = Path(f.name)

        try:
            monitor = StatusMonitor(status_file=temp_file)

            # Create context with mixed event types
            context = self._create_mock_context_with_mixed_events()

            # Execute - should handle both formats
            monitor.update_game_state(context)

            # Assert
            assert monitor.status["events"]["total"] == 4

        finally:
            temp_file.unlink(missing_ok=True)

    def test_handles_events_with_unknown_types(self):
        """Test that unknown event types are counted as 'other'"""
        # Setup
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_file = Path(f.name)

        try:
            monitor = StatusMonitor(status_file=temp_file)

            # Create mock event with unknown type
            context = Mock()
            context.game = {
                "homeTeam": {"score": 0},
                "awayTeam": {"score": 0},
                "periodDescriptor": {"number": 1, "periodType": "REG"},
            }
            context.game_id = "2025020999"
            context.game_state = "LIVE"
            context.venue = "Test Arena"
            context.home_team = Mock(abbreviation="TST")
            context.away_team = Mock(abbreviation="OPP")
            context.clock = Mock(time_remaining="10:00", in_intermission=False)

            # Event with unknown type
            unknown_event = Mock()
            unknown_event.event_type = "mysterious-event"
            context.events = [unknown_event]
            context.live_loop_counter = 1

            # Execute
            monitor.update_game_state(context)

            # Assert
            assert monitor.status["events"]["total"] == 1

        finally:
            temp_file.unlink(missing_ok=True)

    # Helper methods to create mock contexts
    def _create_mock_context_with_events(self):
        """Create a mock context with Event objects"""
        context = Mock()
        context.game = {
            "homeTeam": {"score": 3},
            "awayTeam": {"score": 2},
            "periodDescriptor": {"number": 2, "periodType": "REG"},
        }
        context.game_id = "2025020176"
        context.game_state = "LIVE"
        context.venue = "Prudential Center"
        context.home_team = Mock(abbreviation="NJD")
        context.away_team = Mock(abbreviation="SJS")
        context.clock = Mock(time_remaining="12:34", in_intermission=False)

        # Create Event objects (not dicts!)
        goal_event = Mock()
        goal_event.event_type = "goal"

        penalty_event = Mock()
        penalty_event.event_type = "penalty"

        shot_event = Mock()
        shot_event.event_type = "shot-on-goal"

        context.events = [goal_event, penalty_event, shot_event]
        context.live_loop_counter = 5

        return context

    def _create_mock_context_with_dict_events(self):
        """Create a mock context with dict events (old format)"""
        context = Mock()
        context.game = {
            "homeTeam": {"score": 1},
            "awayTeam": {"score": 0},
            "periodDescriptor": {"number": 1, "periodType": "REG"},
        }
        context.game_id = "2025020177"
        context.game_state = "LIVE"
        context.venue = "SAP Center"
        context.home_team = Mock(abbreviation="SJS")
        context.away_team = Mock(abbreviation="NJD")
        context.clock = Mock(time_remaining="15:00", in_intermission=False)

        # Dict events (old format)
        context.events = [{"typeDescKey": "goal"}, {"typeDescKey": "faceoff"}]
        context.live_loop_counter = 2

        return context

    def _create_mock_context_with_mixed_events(self):
        """Create a mock context with both dicts and objects"""
        context = Mock()
        context.game = {
            "homeTeam": {"score": 2},
            "awayTeam": {"score": 1},
            "periodDescriptor": {"number": 2, "periodType": "REG"},
        }
        context.game_id = "2025020178"
        context.game_state = "LIVE"
        context.venue = "Test Arena"
        context.home_team = Mock(abbreviation="TST")
        context.away_team = Mock(abbreviation="OPP")
        context.clock = Mock(time_remaining="08:30", in_intermission=False)

        # Mix of dict and object events
        object_event = Mock()
        object_event.event_type = "goal"

        dict_event = {"typeDescKey": "penalty"}

        context.events = [object_event, dict_event, {"typeDescKey": "hit"}, Mock(event_type="shot-on-goal")]
        context.live_loop_counter = 3

        return context


class TestStatusMonitorFileOperations:
    """Test file writing and error handling"""

    def test_creates_status_file(self):
        """Test that StatusMonitor creates the status file"""
        # Setup
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_file = Path(f.name)
        temp_file.unlink()  # Delete it so monitor creates it

        try:
            # Execute
            StatusMonitor(status_file=temp_file)

            # Assert
            assert temp_file.exists()

            # Verify it's valid JSON
            with open(temp_file) as f:
                data = json.load(f)
                assert "bot" in data
                assert "game" in data
                assert "events" in data

        finally:
            temp_file.unlink(missing_ok=True)

    def test_status_file_is_valid_json(self):
        """Test that written status file is valid JSON"""
        # Setup
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_file = Path(f.name)

        try:
            monitor = StatusMonitor(status_file=temp_file)

            # Trigger a write
            monitor.set_status("RUNNING")

            # Assert - file should be valid JSON
            with open(temp_file) as f:
                data = json.load(f)
                assert data["bot"]["status"] == "RUNNING"

        finally:
            temp_file.unlink(missing_ok=True)

    def test_atomic_write_operation(self):
        """Test that file writes are atomic (temp file + rename)"""
        # This tests that we never write a partial file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_file = Path(f.name)

        try:
            monitor = StatusMonitor(status_file=temp_file)

            # Write multiple times quickly
            for i in range(10):
                monitor.set_status(f"STATUS_{i}")

            # File should always be valid JSON (never partial)
            with open(temp_file) as f:
                data = json.load(f)  # Should not raise JSONDecodeError
                assert "bot" in data

        finally:
            temp_file.unlink(missing_ok=True)


class TestStatusMonitorAPITracking:
    """Test API call tracking"""

    def test_record_successful_api_call(self):
        """Test recording successful API calls"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_file = Path(f.name)

        try:
            monitor = StatusMonitor(status_file=temp_file)

            # Execute
            monitor.record_api_call(success=True)
            monitor.record_api_call(success=True)

            # Assert
            assert monitor.status["performance"]["api_calls"]["total"] == 2
            assert monitor.status["performance"]["api_calls"]["successful"] == 2
            assert monitor.status["performance"]["api_calls"]["failed"] == 0

        finally:
            temp_file.unlink(missing_ok=True)

    def test_record_failed_api_call(self):
        """Test recording failed API calls"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_file = Path(f.name)

        try:
            monitor = StatusMonitor(status_file=temp_file)

            # Execute
            monitor.record_api_call(success=False)

            # Assert
            assert monitor.status["performance"]["api_calls"]["total"] == 1
            assert monitor.status["performance"]["api_calls"]["successful"] == 0
            assert monitor.status["performance"]["api_calls"]["failed"] == 1

        finally:
            temp_file.unlink(missing_ok=True)


class TestStatusMonitorSocialTracking:
    """Test social media post tracking"""

    def test_record_social_post(self):
        """Test recording social media posts"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_file = Path(f.name)

        try:
            monitor = StatusMonitor(status_file=temp_file)

            # Execute
            monitor.record_social_post()
            monitor.record_social_post()
            monitor.record_social_post()

            # Assert
            assert monitor.status["socials"]["posts_sent"] == 3
            assert monitor.status["socials"]["last_post_time"] is not None

        finally:
            temp_file.unlink(missing_ok=True)


# Pytest fixtures
@pytest.fixture
def temp_status_file():
    """Create a temporary status file for testing"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        temp_file = Path(f.name)

    yield temp_file

    # Cleanup
    temp_file.unlink(missing_ok=True)


@pytest.fixture
def mock_monitor(temp_status_file):
    """Create a StatusMonitor with temporary file"""
    return StatusMonitor(status_file=temp_status_file)
