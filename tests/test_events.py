"""Tests for core/events/ - Event handler classes

These tests cover:
1. Goal event parsing and formatting
2. Assist handling (0, 1, or 2 assists)
3. Removed goal detection (challenges)
4. Highlight clip handling
5. Score updates
6. Edge cases (missing data, None values)

Run with: pytest tests/test_events.py -v
"""

from unittest.mock import Mock, patch

import pytest

from core.events.goal import GoalEvent


class TestGoalEventParsing:
    """Test goal event parsing and message generation"""

    def test_goal_parse_preferred_team_no_assists(self):
        """Test goal by preferred team with no assists.

        This is a simple goal - just the scorer, no helpers.
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.preferred_team = Mock(team_id=1, full_name="New Jersey Devils", score=0)
        mock_context.other_team = Mock(full_name="San Jose Sharks", score=0)
        mock_context.preferred_homeaway = "home"

        event_data = {
            "eventId": 123,
            "typeDescKey": "goal",
            "periodDescriptor": {"number": 1, "periodType": "REG"},
            "timeInPeriod": "05:23",
            "timeRemaining": "14:37",
            "details": {
                "eventOwnerTeamId": 1,  # Preferred team
                "scoringPlayerId": 8478407,
                "scoringPlayerName": "Nico Hischier",
                "scoringPlayerTotal": 5,
                "homeScore": 1,
                "awayScore": 0,
                "shotType": "Wrist Shot",
                "goalieInNetId": 123,  # Not empty net
            },
        }

        # ACT
        goal = GoalEvent(event_data, mock_context)
        message = goal.parse()

        # ASSERT
        assert message is not False
        assert "New Jersey Devils GOAL!" in message
        assert "Nico Hischier (5)" in message
        assert "Wrist Shot" in message
        assert "14:37 remaining" in message
        assert "New Jersey Devils: 1" in message
        assert "San Jose Sharks: 0" in message
        # No assists should be mentioned
        assert "🍎" not in message
        assert "🍏" not in message

    def test_goal_parse_with_one_assist(self):
        """Test goal with one assist.

        Common scenario - goal plus one apple.
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.preferred_team = Mock(team_id=1, full_name="New Jersey Devils", score=0)
        mock_context.other_team = Mock(full_name="San Jose Sharks", score=0)
        mock_context.preferred_homeaway = "home"

        event_data = {
            "eventId": 124,
            "typeDescKey": "goal",
            "periodDescriptor": {"number": 2, "periodType": "REG"},
            "timeInPeriod": "10:15",
            "timeRemaining": "09:45",
            "details": {
                "eventOwnerTeamId": 1,
                "scoringPlayerId": 8478407,
                "scoringPlayerName": "Nico Hischier",
                "scoringPlayerTotal": 6,
                "assist1PlayerId": 8476878,
                "assist1PlayerName": "Dougie Hamilton",
                "assist1PlayerTotal": 10,
                "homeScore": 2,
                "awayScore": 1,
                "shotType": "Snap Shot",
            },
        }

        # ACT
        goal = GoalEvent(event_data, mock_context)
        message = goal.parse()

        # ASSERT
        assert "Nico Hischier (6)" in message
        assert "🍎 Dougie Hamilton (10)" in message
        assert "🍏" not in message  # No second assist

    def test_goal_parse_with_two_assists(self):
        """Test goal with two assists.

        Full credit - scorer plus two apples.
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.preferred_team = Mock(team_id=1, full_name="New Jersey Devils", score=0)
        mock_context.other_team = Mock(full_name="San Jose Sharks", score=0)
        mock_context.preferred_homeaway = "home"

        event_data = {
            "eventId": 125,
            "typeDescKey": "goal",
            "periodDescriptor": {"number": 3, "periodType": "REG"},
            "timeInPeriod": "15:30",
            "timeRemaining": "04:30",
            "details": {
                "eventOwnerTeamId": 1,
                "scoringPlayerId": 8478407,
                "scoringPlayerName": "Nico Hischier",
                "scoringPlayerTotal": 7,
                "assist1PlayerId": 8476878,
                "assist1PlayerName": "Dougie Hamilton",
                "assist1PlayerTotal": 11,
                "assist2PlayerId": 8479318,
                "assist2PlayerName": "Jack Hughes",
                "assist2PlayerTotal": 15,
                "homeScore": 3,
                "awayScore": 1,
                "shotType": "Backhand",
            },
        }

        # ACT
        goal = GoalEvent(event_data, mock_context)
        message = goal.parse()

        # ASSERT
        assert "Nico Hischier (7)" in message
        assert "🍎 Dougie Hamilton (11)" in message
        assert "🍏 Jack Hughes (15)" in message

    def test_goal_parse_other_team(self):
        """Test goal by opponent.

        Should have different emoji and messaging.
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.preferred_team = Mock(team_id=1, full_name="New Jersey Devils", score=0)
        mock_context.other_team = Mock(full_name="San Jose Sharks", score=0)
        mock_context.preferred_homeaway = "home"

        event_data = {
            "eventId": 126,
            "typeDescKey": "goal",
            "periodDescriptor": {"number": 1},
            "timeInPeriod": "08:42",
            "timeRemaining": "11:18",
            "details": {
                "eventOwnerTeamId": 28,  # Other team (Sharks)
                "scoringPlayerId": 8477933,
                "scoringPlayerName": "Tomas Hertl",
                "scoringPlayerTotal": 12,
                "homeScore": 0,
                "awayScore": 1,
                "shotType": "Slap Shot",
            },
        }

        # ACT
        goal = GoalEvent(event_data, mock_context)
        message = goal.parse()

        # ASSERT
        assert "San Jose Sharks goal." in message
        assert "👎" in message  # Thumbs down emoji
        assert "Tomas Hertl (12)" in message
        assert "New Jersey Devils: 0" in message
        assert "San Jose Sharks: 1" in message

    def test_goal_parse_missing_shot_type(self):
        """Test goal with missing shot type data.

        Bug Prevention: Missing data should cause parse to return False
        so we can retry on next loop.
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.preferred_team = Mock(team_id=1)
        mock_context.preferred_homeaway = "home"

        event_data = {
            "eventId": 127,
            "typeDescKey": "goal",
            "periodDescriptor": {"number": 1},
            "timeInPeriod": "05:00",
            "timeRemaining": "15:00",
            "details": {
                "eventOwnerTeamId": 1,
                "scoringPlayerId": 8478407,
                "scoringPlayerName": "Nico Hischier",
                "homeScore": 1,
                "awayScore": 0,
                # Missing shotType!
            },
        }

        # ACT
        goal = GoalEvent(event_data, mock_context)
        result = goal.parse()

        # ASSERT
        # Should return False to indicate data not ready
        assert result is False


class TestGoalEventScoring:
    """Test goal event score tracking and updates"""

    def test_goal_updates_context_scores(self):
        """Test that goal parsing updates team scores in context.

        Important: Other events need to access current scores.
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.preferred_team = Mock(team_id=1, score=0)
        mock_context.other_team = Mock(score=0)
        mock_context.preferred_homeaway = "home"

        event_data = {
            "eventId": 128,
            "typeDescKey": "goal",
            "periodDescriptor": {"number": 1},
            "timeInPeriod": "05:00",
            "timeRemaining": "15:00",
            "details": {"eventOwnerTeamId": 1, "homeScore": 1, "awayScore": 0, "shotType": "Wrist Shot"},
        }

        # ACT
        goal = GoalEvent(event_data, mock_context)
        goal.parse()

        # ASSERT
        assert mock_context.preferred_team.score == 1
        assert mock_context.other_team.score == 0

    def test_goal_away_team_scoring(self):
        """Test goal scoring when preferred team is away.

        Score assignment should swap for away games.
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.preferred_team = Mock(team_id=1, score=0)
        mock_context.other_team = Mock(score=0)
        mock_context.preferred_homeaway = "away"  # Preferred team is away

        event_data = {
            "eventId": 129,
            "typeDescKey": "goal",
            "periodDescriptor": {"number": 1},
            "timeInPeriod": "10:00",
            "timeRemaining": "10:00",
            "details": {
                "eventOwnerTeamId": 1,
                "homeScore": 0,
                "awayScore": 1,  # Preferred team scores
                "shotType": "Snap Shot",
            },
        }

        # ACT
        goal = GoalEvent(event_data, mock_context)
        goal.parse()

        # ASSERT
        assert mock_context.preferred_team.score == 1
        assert mock_context.other_team.score == 0


class TestGoalEventRemoval:
    """Test removed goal detection (for challenges).

    When a goal is challenged and overturned, it disappears from
    the play-by-play feed. We need to detect this.
    """

    def test_goal_not_removed_when_present(self):
        """Test that goal is not marked as removed when still in feed.

        Normal case - goal is valid and present.
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.preferred_team = Mock(team_id=1)
        mock_context.preferred_homeaway = "home"

        event_data = {
            "eventId": 130,
            "typeDescKey": "goal",
            "periodDescriptor": {"number": 1},
            "timeInPeriod": "05:00",
            "timeRemaining": "15:00",
            "details": {"eventOwnerTeamId": 1, "homeScore": 1, "awayScore": 0, "shotType": "Wrist Shot"},
        }

        goal = GoalEvent(event_data, mock_context)
        goal.event_removal_counter = 0

        all_plays = [
            {"eventId": 130, "typeDescKey": "goal"},  # Goal is present
            {"eventId": 131, "typeDescKey": "faceoff"},
        ]

        # ACT
        result = goal.was_goal_removed(all_plays)

        # ASSERT
        assert result is False
        assert goal.event_removal_counter == 0

    def test_goal_removed_after_threshold(self):
        """Test that goal is marked as removed after missing multiple checks.

        Threshold prevents false positives from API delays.
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.preferred_team = Mock(team_id=1)
        mock_context.preferred_homeaway = "home"

        event_data = {
            "eventId": 131,
            "typeDescKey": "goal",
            "periodDescriptor": {"number": 1},
            "timeInPeriod": "05:00",
            "timeRemaining": "15:00",
            "details": {"eventOwnerTeamId": 1, "homeScore": 1, "awayScore": 0, "shotType": "Wrist Shot"},
        }

        goal = GoalEvent(event_data, mock_context)
        goal.event_removal_counter = 0

        # Goal not in feed
        all_plays = [{"eventId": 140, "typeDescKey": "faceoff"}]

        # ACT - Check multiple times to hit threshold
        for i in range(GoalEvent.REMOVAL_THRESHOLD):
            result = goal.was_goal_removed(all_plays)

            if i < GoalEvent.REMOVAL_THRESHOLD - 1:
                # Not yet at threshold
                assert result is False
                assert goal.event_removal_counter == i + 1
            else:
                # At threshold - should be marked for removal
                assert result is True
                assert goal.event_removal_counter == GoalEvent.REMOVAL_THRESHOLD

    def test_goal_removal_counter_resets(self):
        """Test that removal counter resets when goal reappears.

        Handles case where goal temporarily missing from API.
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.preferred_team = Mock(team_id=1)
        mock_context.preferred_homeaway = "home"

        event_data = {
            "eventId": 132,
            "typeDescKey": "goal",
            "periodDescriptor": {"number": 1},
            "timeInPeriod": "05:00",
            "timeRemaining": "15:00",
            "details": {"eventOwnerTeamId": 1, "homeScore": 1, "awayScore": 0, "shotType": "Wrist Shot"},
        }

        goal = GoalEvent(event_data, mock_context)
        goal.event_removal_counter = 3  # Already missing a few times

        # Goal reappears in feed
        all_plays = [
            {"eventId": 132, "typeDescKey": "goal"},  # Goal is back!
        ]

        # ACT
        result = goal.was_goal_removed(all_plays)

        # ASSERT
        assert result is False
        assert goal.event_removal_counter == 0  # Counter reset


class TestGoalEventHighlights:
    """Test highlight clip handling for goals"""

    def test_check_and_add_highlight_valid_url(self):
        """Test adding a valid highlight clip URL.

        NHL provides video highlights that we post.
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.preferred_team = Mock(team_id=1)
        mock_context.preferred_homeaway = "home"

        event_data = {
            "eventId": 133,
            "typeDescKey": "goal",
            "periodDescriptor": {"number": 1},
            "timeInPeriod": "05:00",
            "timeRemaining": "15:00",
            "details": {"eventOwnerTeamId": 1, "homeScore": 1, "awayScore": 0, "shotType": "Wrist Shot"},
        }

        goal = GoalEvent(event_data, mock_context)
        goal.scoring_player_name = "Nico Hischier"
        goal.team_name = "New Jersey Devils"
        goal.bsky_root = None
        goal.bsky_parent = None

        # Mock the post_message method
        goal.post_message = Mock()

        updated_event_data = {
            "eventId": 133,
            "details": {"highlightClipSharingUrl": "https://nhl.com/video/c-12345"},
        }

        # ACT
        goal.check_and_add_highlight(updated_event_data)

        # ASSERT
        assert goal.highlight_clip_url == "https://www.nhl.com/video/c-12345"
        goal.post_message.assert_called_once()

    def test_check_and_add_highlight_invalid_url(self):
        """Test handling of invalid highlight URL.

        Sometimes NHL returns placeholder URLs that aren't real.
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.preferred_team = Mock(team_id=1)
        mock_context.preferred_homeaway = "home"

        event_data = {
            "eventId": 134,
            "typeDescKey": "goal",
            "periodDescriptor": {"number": 1},
            "timeInPeriod": "05:00",
            "timeRemaining": "15:00",
            "details": {"eventOwnerTeamId": 1, "homeScore": 1, "awayScore": 0, "shotType": "Wrist Shot"},
        }

        goal = GoalEvent(event_data, mock_context)
        goal.post_message = Mock()

        updated_event_data = {
            "eventId": 134,
            "details": {
                "highlightClipSharingUrl": "https://www.nhl.com/video/",  # Invalid!
            },
        }

        # ACT
        goal.check_and_add_highlight(updated_event_data)

        # ASSERT
        # Should not post message for invalid URL
        goal.post_message.assert_not_called()

    def test_check_and_add_highlight_missing(self):
        """Test handling when no highlight URL provided.

        Highlights aren't always available immediately.
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.preferred_team = Mock(team_id=1)
        mock_context.preferred_homeaway = "home"

        event_data = {
            "eventId": 135,
            "typeDescKey": "goal",
            "periodDescriptor": {"number": 1},
            "timeInPeriod": "05:00",
            "timeRemaining": "15:00",
            "details": {"eventOwnerTeamId": 1, "homeScore": 1, "awayScore": 0, "shotType": "Wrist Shot"},
        }

        goal = GoalEvent(event_data, mock_context)
        goal.post_message = Mock()

        updated_event_data = {
            "eventId": 135,
            "details": {},  # No highlight URL
        }

        # ACT
        goal.check_and_add_highlight(updated_event_data)

        # ASSERT
        goal.post_message.assert_not_called()


class TestGoalEventEdgeCases:
    """Test edge cases and error conditions"""

    def test_goal_with_none_assist_names(self):
        """Test goal where assist player names are None.

        Sometimes API doesn't provide names immediately.
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.preferred_team = Mock(team_id=1, full_name="New Jersey Devils", score=0)
        mock_context.other_team = Mock(full_name="San Jose Sharks", score=0)
        mock_context.preferred_homeaway = "home"

        event_data = {
            "eventId": 136,
            "typeDescKey": "goal",
            "periodDescriptor": {"number": 1},
            "timeInPeriod": "05:00",
            "timeRemaining": "15:00",
            "details": {
                "eventOwnerTeamId": 1,
                "scoringPlayerId": 8478407,
                "scoringPlayerName": "Nico Hischier",
                "scoringPlayerTotal": 5,
                "assist1PlayerId": 8476878,
                "assist1PlayerName": None,  # Name not available
                "homeScore": 1,
                "awayScore": 0,
                "shotType": "Wrist Shot",
            },
        }

        # ACT
        goal = GoalEvent(event_data, mock_context)
        message = goal.parse()

        # ASSERT
        # Should handle gracefully, no assists section since name is None
        assert message is not False
        assert "🍎" not in message

    def test_goal_with_zero_totals(self):
        """Test first career goal (totals = 1).

        Special milestone!
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.preferred_team = Mock(team_id=1, full_name="New Jersey Devils", score=0)
        mock_context.other_team = Mock(full_name="San Jose Sharks", score=0)
        mock_context.preferred_homeaway = "home"

        event_data = {
            "eventId": 137,
            "typeDescKey": "goal",
            "periodDescriptor": {"number": 1},
            "timeInPeriod": "05:00",
            "timeRemaining": "15:00",
            "details": {
                "eventOwnerTeamId": 1,
                "scoringPlayerId": 8478407,
                "scoringPlayerName": "Rookie Player",
                "scoringPlayerTotal": 1,  # First goal!
                "homeScore": 1,
                "awayScore": 0,
                "shotType": "Wrist Shot",
            },
        }

        # ACT
        goal = GoalEvent(event_data, mock_context)
        message = goal.parse()

        # ASSERT
        assert "Rookie Player (1)" in message


class TestGoalEventIntegration:
    """Integration tests for goal events"""

    @patch("core.events.goal.get_team_details_by_id")
    def test_goal_full_flow_with_post(self, mock_team_details):
        """Test complete goal event flow from parse to post.

        This simulates the entire lifecycle of a goal event.
        """
        # ARRANGE
        mock_team_details.return_value = {"full_name": "New Jersey Devils", "abbreviation": "NJD"}

        mock_context = Mock()
        mock_context.preferred_team = Mock(team_id=1, full_name="New Jersey Devils", score=0)
        mock_context.other_team = Mock(full_name="San Jose Sharks", score=0)
        mock_context.preferred_homeaway = "home"
        mock_context.social = Mock()

        event_data = {
            "eventId": 138,
            "typeDescKey": "goal",
            "periodDescriptor": {"number": 2, "periodType": "REG"},
            "timeInPeriod": "12:34",
            "timeRemaining": "07:26",
            "details": {
                "eventOwnerTeamId": 1,
                "scoringPlayerId": 8478407,
                "scoringPlayerName": "Nico Hischier",
                "scoringPlayerTotal": 10,
                "assist1PlayerId": 8476878,
                "assist1PlayerName": "Dougie Hamilton",
                "assist1PlayerTotal": 20,
                "homeScore": 3,
                "awayScore": 2,
                "shotType": "Wrist Shot",
            },
        }

        # ACT
        goal = GoalEvent(event_data, mock_context)
        message = goal.parse()

        # ASSERT
        assert message is not False
        assert "Nico Hischier" in message
        assert "Dougie Hamilton" in message
        assert goal.team_name == "New Jersey Devils"
        assert goal.team_abbreviation == "NJD"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
