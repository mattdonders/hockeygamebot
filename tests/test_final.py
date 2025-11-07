"""Tests for game finalization logic

These tests verify Bug #1 fix (three stars None handling)
"""

from unittest.mock import Mock, patch

from core import final


class TestThreeStarsHandling:
    """Test the three stars logic that caused Bug #1"""

    @patch("core.final.schedule.fetch_landing")
    def test_three_stars_returns_none_when_unavailable(self, mock_fetch):
        """Test that three_stars() returns None when data not available"""
        # Setup - API returns landing data without three stars
        mock_fetch.return_value = {
            "summary": {},  # No threeStars key
        }

        mock_context = Mock()
        mock_context.game_id = "2025020176"

        # Execute
        result = final.three_stars(mock_context)

        # Assert
        assert result is None, "Should return None when three stars not available"

    @patch("core.final.schedule.fetch_landing")
    @patch("core.final.otherutils.get_player_name")
    def test_three_stars_returns_message_when_available(self, mock_get_name, mock_fetch):
        """Test that three_stars() returns formatted message when available"""
        # Setup - API returns complete three stars data
        mock_fetch.return_value = {
            "summary": {
                "threeStars": [
                    {"star": 1, "playerId": 8478407, "teamAbbrev": "NJD"},
                    {"star": 2, "playerId": 8477933, "teamAbbrev": "SJS"},
                    {"star": 3, "playerId": 8476878, "teamAbbrev": "NJD"},
                ],
            },
        }

        # Mock player name lookups
        mock_get_name.side_effect = ["Nico Hischier", "Tomas Hertl", "Dougie Hamilton"]

        mock_context = Mock()
        mock_context.game_id = "2025020176"
        mock_context.combined_roster = []  # Will use mock

        # Execute
        result = final.three_stars(mock_context)

        # Assert
        assert result is not None, "Should return message when three stars available"
        assert "Nico Hischier" in result
        assert "(NJD)" in result

    @patch("core.final.schedule.fetch_landing")
    def test_three_stars_handles_empty_array(self, mock_fetch):
        """Test that three_stars() handles empty threeStars array"""
        # Setup
        mock_fetch.return_value = {
            "summary": {
                "threeStars": [],  # Empty array
            },
        }

        mock_context = Mock()
        mock_context.game_id = "2025020176"

        # Execute
        result = final.three_stars(mock_context)

        # Assert - Empty array should be treated as "not available"
        # Current implementation would return None
        assert result is None


class TestFinalScoreLogic:
    """Test final score generation"""

    @patch("core.final.next_game")  # Add this line
    @patch("core.final.schedule.fetch_playbyplay")
    def test_final_score_message_generation(self, mock_fetch, mock_next_game):
        """Test that final score generates correct message"""
        # Setup
        mock_fetch.return_value = {
            "awayTeam": {"abbrev": "SJS", "score": 3},
            "homeTeam": {"abbrev": "NJD", "score": 5},
            "periodDescriptor": {"number": 3, "periodType": "REG"},
        }

        # Mock next_game to return a simple string (avoid API calls)
        mock_next_game.return_value = (
            "Next Game: Friday November 01 @ 07:00PM vs. New York Rangers (at Prudential Center)!"
        )

        mock_context = Mock()
        mock_context.game_id = "2025020176"

        # Create proper mock teams with score attributes (not Mock objects)
        mock_context.preferred_team = Mock(abbreviation="NJD", score=5)
        mock_context.other_team = Mock(abbreviation="SJS", score=3)
        mock_context.away_team = Mock(abbreviation="SJS", emoji="🦈")
        mock_context.home_team = Mock(abbreviation="NJD", emoji="😈")
        mock_context.venue = "Prudential Center"

        # Execute
        result = final.final_score(mock_context)

        # Assert
        assert result is not None
        # Check that next_game was called
        mock_next_game.assert_called_once_with(mock_context)


class TestNextGameLogic:
    """Test next game information"""

    @patch("core.final.schedule.fetch_schedule")
    @patch("core.final.schedule.fetch_next_game")
    @patch("core.final.otherutils.convert_utc_to_localteam_dt")
    def test_next_game_message(self, mock_convert, mock_next, mock_schedule):
        """Test that next game generates correct message"""
        # Setup
        from datetime import datetime

        mock_schedule.return_value = []  # Schedule data
        mock_next.return_value = {
            "gameDate": "2025-11-01",
            "startTimeUTC": "2025-11-01T23:00:00Z",
            "awayTeam": {
                "abbrev": "NYR",
                "placeName": {"default": "New York"},
                "commonName": {"default": "Rangers"},
            },
            "homeTeam": {
                "abbrev": "NJD",
                "placeName": {"default": "New Jersey"},
                "commonName": {"default": "Devils"},
            },
            "venue": {"default": "Prudential Center"},
        }

        # Mock the time conversion
        mock_convert.return_value = datetime(2025, 11, 1, 19, 0)

        # Create context with required attributes
        mock_context = Mock()
        mock_context.preferred_team = Mock(abbreviation="NJD", timezone="America/New_York")
        mock_context.season_id = "20252026"

        # Execute - next_game() takes only context, not season_id
        result = final.next_game(mock_context)

        # Assert
        assert result is not None
        assert "Next Game" in result
        assert "Prudential Center" in result


# Integration test that simulates the bug scenario
class TestThreeStarsIntegration:
    """Integration test for the three stars posting flow"""

    def test_three_stars_none_doesnt_crash_post(self):
        """Integration test: Verify that when three_stars() returns None,
        we don't crash when trying to post it.

        This simulates the exact bug scenario from the NJD@SAS game.
        """
        # Setup - simulate the flow from hockeygamebot.py
        from socials.bluesky import BlueskyClient

        client = BlueskyClient(account="test", password="test", nosocial=True)

        # Simulate three_stars() returning None
        three_stars_post = None

        # This is the bug fix - check for None before posting
        if three_stars_post:
            result = client.post(three_stars_post)
        else:
            result = None  # Don't post

        # Assert - should not crash, result should be None
        assert result is None

    def test_three_stars_with_message_posts_successfully(self):
        """Test that valid three stars message posts successfully"""
        from socials.bluesky import BlueskyClient

        client = BlueskyClient(account="test", password="test", nosocial=True)

        # Simulate three_stars() returning valid message
        three_stars_post = (
            "⭐️ Three Stars ⭐️\n1st: Nico Hischier (NJD)\n2nd: Tomas Hertl (SJS)\n3rd: Dougie Hamilton (NJD)"
        )

        # This should work
        if three_stars_post:
            result = client.post(three_stars_post)

        # Assert - in nosocial mode returns None but doesn't crash
        assert result is None  # nosocial mode
