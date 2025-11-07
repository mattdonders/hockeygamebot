"""Shared pytest fixtures and configuration

This file contains fixtures that can be used across all test files.
Pytest automatically discovers this file and makes fixtures available.
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

# ==================== Mock Objects ====================


@pytest.fixture
def mock_game_context():
    """Create a mock GameContext for testing"""
    context = Mock()
    context.game_id = "2025020176"
    context.game_state = "LIVE"
    context.venue = "Prudential Center"
    context.season_id = "20252026"

    # Teams
    context.preferred_team = Mock(abbreviation="NJD", emoji="😈")
    context.home_team = Mock(abbreviation="NJD", emoji="😈")
    context.away_team = Mock(abbreviation="SJS", emoji="🦈")

    # Clock
    context.clock = Mock(time_remaining="12:34", in_intermission=False)

    # Game data
    context.game = {
        "homeTeam": {"score": 3, "abbrev": "NJD"},
        "awayTeam": {"score": 2, "abbrev": "SJS"},
        "periodDescriptor": {"number": 2, "periodType": "REG"},
    }

    # Events
    context.events = []
    context.live_loop_counter = 0

    # Socials
    context.preview_socials = Mock(
        core_sent=False,
        season_series_sent=False,
        team_stats_sent=False,
        officials_sent=False,
    )

    context.final_socials = Mock(
        final_score_sent=False,
        three_stars_sent=False,
        team_stats_sent=False,
        bluesky_root=None,
        bluesky_parent=None,
    )

    return context


@pytest.fixture
def mock_bluesky_client():
    """Create a mock BlueskyClient for testing"""
    from socials.bluesky import BlueskyClient

    return BlueskyClient(nosocial=True)


@pytest.fixture
def mock_event_object():
    """Create a mock Event object"""
    event = Mock()
    event.event_id = 123
    event.event_type = "goal"
    event.period_number = 2
    event.time_in_period = "12:34"
    event.sort_order = 100
    return event


@pytest.fixture
def mock_event_dict():
    """Create a mock event in dict format (legacy)"""
    return {
        "eventId": 123,
        "typeDescKey": "goal",
        "periodDescriptor": {"number": 2},
        "timeInPeriod": "12:34",
        "sortOrder": 100,
    }


# ==================== File System Fixtures ====================


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_status_file():
    """Create a temporary status.json file"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        temp_file = Path(f.name)

    yield temp_file

    # Cleanup
    temp_file.unlink(missing_ok=True)


@pytest.fixture
def temp_log_file():
    """Create a temporary log file"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        temp_file = Path(f.name)

    yield temp_file

    # Cleanup
    temp_file.unlink(missing_ok=True)


# ==================== API Response Fixtures ====================


@pytest.fixture
def mock_schedule_response():
    """Mock NHL API schedule response"""
    return {
        "games": [
            {
                "id": 2025020176,
                "season": 20252026,
                "gameType": 2,
                "gameDate": "2025-10-30",
                "startTimeUTC": "2025-10-30T23:00:00Z",
                "awayTeam": {"id": 28, "abbrev": "SJS", "score": 3},
                "homeTeam": {"id": 1, "abbrev": "NJD", "score": 5},
                "gameState": "OFF",
                "gameScheduleState": "OK",
            },
        ],
    }


@pytest.fixture
def mock_playbyplay_response():
    """Mock NHL API play-by-play response"""
    return {
        "id": 2025020176,
        "awayTeam": {"abbrev": "SJS", "score": 3},
        "homeTeam": {"abbrev": "NJD", "score": 5},
        "periodDescriptor": {"number": 3, "periodType": "REG"},
        "plays": [
            {
                "eventId": 123,
                "typeDescKey": "goal",
                "periodDescriptor": {"number": 1},
                "timeInPeriod": "05:23",
                "sortOrder": 100,
            },
        ],
    }


@pytest.fixture
def mock_landing_with_three_stars():
    """Mock NHL API landing response WITH three stars"""
    return {
        "summary": {
            "threeStars": [
                {"star": 1, "playerId": 8478407, "teamAbbrev": "NJD"},
                {"star": 2, "playerId": 8477933, "teamAbbrev": "SJS"},
                {"star": 3, "playerId": 8476878, "teamAbbrev": "NJD"},
            ],
        },
    }


@pytest.fixture
def mock_landing_without_three_stars():
    """Mock NHL API landing response WITHOUT three stars (Bug #1 scenario)"""
    return {
        "summary": {},  # Missing threeStars key
    }


# ==================== Time Fixtures ====================


@pytest.fixture
def frozen_time():
    """Freeze time for testing (requires freezegun)"""
    from freezegun import freeze_time

    frozen = freeze_time("2025-10-31 20:00:00")
    frozen.start()

    yield datetime(2025, 10, 31, 20, 0, 0)

    frozen.stop()


# ==================== Pytest Configuration ====================


def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line("markers", "unit: mark test as a unit test")
    config.addinivalue_line("markers", "integration: mark test as an integration test")
    config.addinivalue_line("markers", "slow: mark test as slow")
    config.addinivalue_line("markers", "api: mark test as requiring API access")


# ==================== Helper Functions ====================


@pytest.fixture
def assert_valid_json():
    """Fixture that provides a helper to validate JSON files"""

    def _assert_valid_json(file_path):
        """Validate that a file contains valid JSON"""
        with open(file_path) as f:
            return json.load(f)  # Will raise if invalid

    return _assert_valid_json


@pytest.fixture
def create_mock_context_with_events():
    """Factory fixture to create mock contexts with events"""

    def _create(num_events=3, event_types=None):
        """Create a mock context with specified events

        Args:
            num_events: Number of events to create
            event_types: List of event types, defaults to ["goal", "penalty", "shot-on-goal"]

        """
        if event_types is None:
            event_types = ["goal", "penalty", "shot-on-goal"]

        context = Mock()
        context.game = {
            "homeTeam": {"score": 3},
            "awayTeam": {"score": 2},
            "periodDescriptor": {"number": 2, "periodType": "REG"},
        }
        context.game_id = "2025020176"
        context.game_state = "LIVE"
        context.venue = "Test Arena"
        context.home_team = Mock(abbreviation="NJD")
        context.away_team = Mock(abbreviation="SJS")
        context.clock = Mock(time_remaining="12:34", in_intermission=False)

        # Create events
        events = []
        for i in range(num_events):
            event = Mock()
            event.event_type = event_types[i % len(event_types)]
            events.append(event)

        context.events = events
        context.live_loop_counter = 5

        return context

    return _create
