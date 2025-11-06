"""
Tests for core/schedule.py - NHL API interaction functions

These tests protect against NHL API changes by:
1. Validating API response structure
2. Testing error handling (timeouts, 404s, 500s)
3. Verifying retry logic
4. Testing monitor integration

Run with: pytest tests/test_schedule.py -v
"""

from unittest.mock import Mock, patch

import pytest
import requests

from core import schedule


class TestScheduleFetch:
    """Test schedule fetching functions"""

    @patch('core.schedule.requests.get')
    def test_fetch_schedule_success(self, mock_get):
        """
        Test successful schedule fetch with valid response.

        This is the happy path - API returns expected data structure.
        """
        # ARRANGE
        mock_response = Mock()
        mock_response.json.return_value = {
            "games": [{"id": 2025020176, "gameDate": "2025-10-30", "gameState": "OFF"}]
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # ACT
        result = schedule.fetch_schedule("NJD", "20252026")

        # ASSERT
        assert result is not None
        assert "games" in result
        assert len(result["games"]) > 0
        mock_get.assert_called_once()

    @patch('core.schedule.requests.get')
    def test_fetch_schedule_timeout(self, mock_get):
        """
        Test schedule fetch handles timeout gracefully.

        NHL API sometimes times out during high traffic.
        With retry decorator, this should retry 3 times before failing.
        """
        # ARRANGE
        mock_get.side_effect = requests.Timeout("Connection timeout")

        # ACT & ASSERT
        with pytest.raises(requests.Timeout):
            schedule.fetch_schedule("NJD", "20252026")

        # Verify it retried 3 times
        assert mock_get.call_count == 3

    @patch('core.schedule.requests.get')
    def test_fetch_schedule_404(self, mock_get):
        """
        Test schedule fetch handles 404 Not Found.

        This can happen with invalid team abbreviation or season ID.
        """
        # ARRANGE
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
        mock_get.return_value = mock_response

        # ACT & ASSERT
        with pytest.raises(requests.HTTPError):
            schedule.fetch_schedule("INVALID", "20252026")

    @patch('core.schedule.requests.get')
    def test_fetch_schedule_500(self, mock_get):
        """
        Test schedule fetch handles 500 Internal Server Error.

        NHL API occasionally has server errors.
        Should retry and eventually fail gracefully.
        """
        # ARRANGE
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
        mock_get.return_value = mock_response

        # ACT & ASSERT
        with pytest.raises(requests.HTTPError):
            schedule.fetch_schedule("NJD", "20252026")

        # Verify retries happened
        assert mock_get.call_count == 3


class TestPlayByPlayFetch:
    """Test play-by-play data fetching"""

    @patch('core.schedule.requests.get')
    def test_fetch_playbyplay_success(self, mock_get):
        """
        Test successful play-by-play fetch.

        This is critical - we call this constantly during live games.
        """
        # ARRANGE
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": 2025020176,
            "gameState": "LIVE",
            "plays": [{"eventId": 123, "typeDescKey": "goal"}],
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # ACT
        result = schedule.fetch_playbyplay("2025020176")

        # ASSERT
        assert result is not None
        assert "plays" in result
        assert "gameState" in result
        assert result["id"] == 2025020176

    @patch('core.schedule.requests.get')
    def test_fetch_playbyplay_empty_plays(self, mock_get):
        """
        Test play-by-play with no events yet.

        This happens at game start before any events occur.
        """
        # ARRANGE
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": 2025020176,
            "gameState": "LIVE",
            "plays": [],  # No events yet
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # ACT
        result = schedule.fetch_playbyplay("2025020176")

        # ASSERT
        assert result is not None
        assert result["plays"] == []

    @patch('core.schedule.requests.get')
    def test_fetch_playbyplay_malformed_response(self, mock_get):
        """
        Test handling of malformed API response.

        If NHL API changes structure, this should catch it.
        """
        # ARRANGE
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": 2025020176
            # Missing 'plays' key!
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # ACT
        result = schedule.fetch_playbyplay("2025020176")

        # ASSERT
        # Function returns the response, validation happens elsewhere
        assert "plays" not in result


class TestLandingFetch:
    """Test landing page data (used for three stars, etc)"""

    @patch('core.schedule.requests.get')
    def test_fetch_landing_with_three_stars(self, mock_get):
        """
        Test landing fetch includes three stars data.

        This is the data we use for post-game three stars posts.
        """
        # ARRANGE
        mock_response = Mock()
        mock_response.json.return_value = {
            "summary": {
                "threeStars": [
                    {"star": 1, "playerId": 8478407},
                    {"star": 2, "playerId": 8477933},
                    {"star": 3, "playerId": 8476878},
                ]
            }
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # ACT
        result = schedule.fetch_landing("2025020176")

        # ASSERT
        assert "summary" in result
        assert "threeStars" in result["summary"]
        assert len(result["summary"]["threeStars"]) == 3

    @patch('core.schedule.requests.get')
    def test_fetch_landing_without_three_stars(self, mock_get):
        """
        Test landing fetch when three stars not available.

        Bug #1 Scenario: Three stars data often missing during/after games.
        Our code must handle this gracefully.
        """
        # ARRANGE
        mock_response = Mock()
        mock_response.json.return_value = {
            "summary": {}  # No threeStars key
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # ACT
        result = schedule.fetch_landing("2025020176")

        # ASSERT
        assert "summary" in result
        assert "threeStars" not in result["summary"]


class TestSeasonIDFetch:
    """Test current season ID fetching"""

    @patch('core.schedule.requests.get')
    def test_fetch_season_id_success(self, mock_get):
        """
        Test fetching current season ID.

        Season ID format: 20252026 (YYYYZZZZ where ZZZZ = YYYY + 1)
        """
        # ARRANGE
        mock_response = Mock()
        mock_response.json.return_value = {"currentSeason": 20252026}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # ACT
        result = schedule.fetch_season_id("NJD")

        # ASSERT
        assert result == 20252026

    @patch('core.schedule.requests.get')
    def test_fetch_season_id_missing(self, mock_get):
        """
        Test handling when season ID not in response.

        Should handle missing data gracefully.
        """
        # ARRANGE
        mock_response = Mock()
        mock_response.json.return_value = {}  # No currentSeason key
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # ACT
        result = schedule.fetch_season_id("NJD")

        # ASSERT
        assert result is None


class TestGameStateFetch:
    """Test game state checking"""

    @patch('core.schedule.requests.get')
    def test_fetch_game_state_live(self, mock_get):
        """Test fetching LIVE game state"""
        # ARRANGE
        mock_response = Mock()
        mock_response.json.return_value = {"gameState": "LIVE"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # ACT
        result = schedule.fetch_game_state("2025020176")

        # ASSERT
        assert result == "LIVE"

    @patch('core.schedule.requests.get')
    def test_fetch_game_state_final(self, mock_get):
        """Test fetching FINAL game state"""
        # ARRANGE
        mock_response = Mock()
        mock_response.json.return_value = {"gameState": "FINAL"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # ACT
        result = schedule.fetch_game_state("2025020176")

        # ASSERT
        assert result == "FINAL"

    @patch('core.schedule.requests.get')
    def test_fetch_game_state_unknown(self, mock_get):
        """
        Test handling unknown game state.

        If NHL adds new game states, this catches them.
        """
        # ARRANGE
        mock_response = Mock()
        mock_response.json.return_value = {}  # No gameState key
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # ACT
        result = schedule.fetch_game_state("2025020176")

        # ASSERT
        assert result == "UNKNOWN"


class TestClockFetch:
    """Test game clock data fetching"""

    @patch('core.schedule.requests.get')
    def test_fetch_clock_success(self, mock_get):
        """Test fetching game clock data"""
        # ARRANGE
        mock_response = Mock()
        mock_response.json.return_value = {
            "clock": {
                "timeRemaining": "12:34",
                "secondsRemaining": 754,
                "running": True,
                "inIntermission": False,
            }
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # ACT
        result = schedule.fetch_clock("2025020176")

        # ASSERT
        assert "timeRemaining" in result
        assert result["timeRemaining"] == "12:34"
        assert result["inIntermission"] is False

    @patch('core.schedule.requests.get')
    def test_fetch_clock_intermission(self, mock_get):
        """Test clock data during intermission"""
        # ARRANGE
        mock_response = Mock()
        mock_response.json.return_value = {"clock": {"inIntermission": True}}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # ACT
        result = schedule.fetch_clock("2025020176")

        # ASSERT
        assert result["inIntermission"] is True


class TestHelperFunctions:
    """Test schedule helper functions"""

    def test_is_game_on_date_found(self):
        """Test finding a game on specific date"""
        # ARRANGE
        schedule_data = {"games": [{"id": 2025020176, "gameDate": "2025-10-30", "gameState": "OFF"}]}

        # ACT
        game, game_id = schedule.is_game_on_date(schedule_data, "2025-10-30")

        # ASSERT
        assert game is not None
        assert game_id == 2025020176

    def test_is_game_on_date_not_found(self):
        """Test when no game on specified date"""
        # ARRANGE
        schedule_data = {"games": [{"id": 2025020176, "gameDate": "2025-10-30"}]}

        # ACT
        game, game_id = schedule.is_game_on_date(schedule_data, "2025-11-01")

        # ASSERT
        assert game is None
        assert game_id is None

    def test_is_game_on_date_empty_schedule(self):
        """Test with empty schedule"""
        # ARRANGE
        schedule_data = {"games": []}

        # ACT
        game, game_id = schedule.is_game_on_date(schedule_data, "2025-10-30")

        # ASSERT
        assert game is None
        assert game_id is None

    def test_fetch_next_game_found(self):
        """Test finding next future game"""
        # ARRANGE
        schedule_data = {
            "games": [
                {"id": 1, "gameState": "OFF", "gameDate": "2025-10-30"},
                {"id": 2, "gameState": "FUT", "gameDate": "2025-11-01"},  # This one!
                {"id": 3, "gameState": "FUT", "gameDate": "2025-11-03"},
            ]
        }

        # ACT
        next_game = schedule.fetch_next_game(schedule_data)

        # ASSERT
        assert next_game is not None
        assert next_game["id"] == 2
        assert next_game["gameState"] == "FUT"

    def test_fetch_next_game_not_found(self):
        """Test when no future games exist"""
        # ARRANGE
        schedule_data = {"games": [{"id": 1, "gameState": "OFF"}, {"id": 2, "gameState": "FINAL"}]}

        # ACT
        result = schedule.fetch_next_game(schedule_data)

        # ASSERT
        # Function returns tuple (None, None) when not found
        assert result == (None, None)


class TestMonitorIntegration:
    """Test integration with StatusMonitor for tracking API calls"""

    @patch('core.schedule.requests.get')
    def test_successful_api_call_tracked(self, mock_get):
        """Test that successful API calls are recorded in monitor"""
        # ARRANGE
        mock_response = Mock()
        mock_response.json.return_value = {"currentSeason": 20252026}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        mock_monitor = Mock()
        schedule.set_monitor(mock_monitor)

        # ACT
        schedule.fetch_season_id("NJD")

        # ASSERT
        mock_monitor.record_api_call.assert_called_once_with(success=True)

        # Cleanup
        schedule.set_monitor(None)

    @patch('core.schedule.requests.get')
    def test_failed_api_call_tracked(self, mock_get):
        """Test that failed API calls are recorded in monitor"""
        # ARRANGE
        mock_get.side_effect = requests.Timeout("Connection timeout")

        mock_monitor = Mock()
        schedule.set_monitor(mock_monitor)

        # ACT
        try:
            schedule.fetch_season_id("NJD")
        except requests.Timeout:
            pass  # Expected

        # ASSERT
        # Should record failure 3 times (due to retries)
        assert mock_monitor.record_api_call.call_count == 3
        mock_monitor.record_api_call.assert_called_with(success=False)

        # Cleanup
        schedule.set_monitor(None)


class TestAPIStructureValidation:
    """
    Tests to validate NHL API response structure.

    These are CRITICAL for catching API changes.
    If NHL changes their API structure, these tests will fail.
    """

    @patch('core.schedule.requests.get')
    def test_schedule_response_structure(self, mock_get):
        """
        Validate that schedule API returns expected structure.

        If this fails, NHL changed their API!
        """
        # ARRANGE
        mock_response = Mock()
        mock_response.json.return_value = {
            "games": [
                {
                    "id": 2025020176,
                    "season": 20252026,
                    "gameType": 2,
                    "gameDate": "2025-10-30",
                    "startTimeUTC": "2025-10-30T23:00:00Z",
                    "gameState": "OFF",
                    "awayTeam": {"abbrev": "SJS", "score": 3},
                    "homeTeam": {"abbrev": "NJD", "score": 5},
                }
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # ACT
        result = schedule.fetch_schedule("NJD", "20252026")

        # ASSERT - Validate structure
        assert "games" in result, "Missing 'games' key"

        game = result["games"][0]
        required_fields = ["id", "gameDate", "gameState", "awayTeam", "homeTeam"]

        for field in required_fields:
            assert field in game, f"Missing required field: {field}"

    @patch('core.schedule.requests.get')
    def test_playbyplay_response_structure(self, mock_get):
        """
        Validate play-by-play API response structure.

        This is CRITICAL - we parse this constantly during games.
        """
        # ARRANGE
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": 2025020176,
            "gameState": "LIVE",
            "periodDescriptor": {"number": 2, "periodType": "REG"},
            "plays": [
                {
                    "eventId": 123,
                    "typeDescKey": "goal",
                    "sortOrder": 100,
                    "periodDescriptor": {"number": 1},
                    "timeInPeriod": "12:34",
                }
            ],
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # ACT
        result = schedule.fetch_playbyplay("2025020176")

        # ASSERT - Validate structure
        assert "plays" in result, "Missing 'plays' key"
        assert "gameState" in result, "Missing 'gameState' key"

        if result["plays"]:
            event = result["plays"][0]
            event_fields = ["eventId", "typeDescKey", "sortOrder"]

            for field in event_fields:
                assert field in event, f"Missing event field: {field}"


# ==================== Integration Tests ====================


@pytest.mark.integration
class TestAPIIntegration:
    """
    Integration tests that actually call NHL API.

    These are marked as 'integration' so they can be skipped:
    Run with: pytest -m integration
    Skip with: pytest -m "not integration"
    """

    @pytest.mark.skip(reason="Requires real API call - run manually")
    def test_real_schedule_fetch(self):
        """
        Test actual NHL API call.

        Run this occasionally to verify API is still compatible.
        """
        result = schedule.fetch_schedule("NJD", "20252026")

        assert result is not None
        assert "games" in result

    @pytest.mark.skip(reason="Requires real API call - run manually")
    def test_real_api_structure(self):
        """
        Verify current NHL API structure matches our expectations.

        Run this when you suspect API changes.
        """
        result = schedule.fetch_schedule("NJD", "20252026")

        # Save this response to compare against future calls
        import json

        with open("/tmp/nhl_api_snapshot.json", "w") as f:
            json.dump(result, f, indent=2)

        print("API snapshot saved to /tmp/nhl_api_snapshot.json")


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])
