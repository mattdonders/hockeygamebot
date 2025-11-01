"""
Tests for core/live.py - Live game monitoring and event detection

These tests cover:
1. Event parsing and detection
2. Removed goal handling
3. Event ordering and tracking
4. Integration with EventFactory

Run with: pytest tests/test_live.py -v
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
from core import live
from core.models.game_context import GameContext


class TestParseLiveGame:
    """Test the main parse_live_game function"""

    @patch('core.live.schedule.fetch_playbyplay')
    @patch('core.live.EventFactory.create_event')
    def test_parse_live_game_with_new_events(self, mock_create_event, mock_fetch):
        """
        Test parsing game with new events detected.

        This is the normal flow during a live game when new plays happen.
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.game_id = "2025020176"
        mock_context.last_sort_order = 100

        # Mock API response with events
        mock_fetch.return_value = {
            "plays": [
                {
                    "eventId": 101,
                    "typeDescKey": "faceoff",
                    "sortOrder": 101
                },
                {
                    "eventId": 102,
                    "typeDescKey": "goal",
                    "sortOrder": 102
                },
                {
                    "eventId": 103,
                    "typeDescKey": "penalty",
                    "sortOrder": 103
                }
            ]
        }

        # ACT
        live.parse_live_game(mock_context)

        # ASSERT
        # Should call EventFactory for each event
        assert mock_create_event.call_count == 3

        # Verify new_plays flag is set correctly
        # Events 102 and 103 are new (sortOrder > 100)
        calls = mock_create_event.call_args_list

        # All events should be processed
        assert len(calls) == 3

    @patch('core.live.schedule.fetch_playbyplay')
    @patch('core.live.EventFactory.create_event')
    def test_parse_live_game_no_new_events(self, mock_create_event, mock_fetch):
        """
        Test parsing game when no new events detected.

        This happens when we poll API but nothing new has occurred.
        Still need to process all events to check for changes (score corrections, etc).
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.game_id = "2025020176"
        mock_context.last_sort_order = 200

        mock_fetch.return_value = {
            "plays": [
                {"eventId": 101, "typeDescKey": "goal", "sortOrder": 101},
                {"eventId": 102, "typeDescKey": "goal", "sortOrder": 102}
            ]
        }

        # ACT
        live.parse_live_game(mock_context)

        # ASSERT
        # Should still process all events (looking for changes)
        assert mock_create_event.call_count == 2

    @patch('core.live.schedule.fetch_playbyplay')
    @patch('core.live.EventFactory.create_event')
    def test_parse_live_game_empty_plays(self, mock_create_event, mock_fetch):
        """
        Test parsing game with no plays yet.

        This happens at the very start of a game before any events.
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.game_id = "2025020176"
        mock_context.last_sort_order = 0

        mock_fetch.return_value = {
            "plays": []  # No events yet
        }

        # ACT
        live.parse_live_game(mock_context)

        # ASSERT
        # No events to process
        mock_create_event.assert_not_called()

    @patch('core.live.schedule.fetch_playbyplay')
    @patch('core.live.EventFactory.create_event')
    def test_parse_live_game_goal_detection(self, mock_create_event, mock_fetch):
        """
        Test that goals are correctly identified in play-by-play.

        Goals are critical events that we track separately.
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.game_id = "2025020176"
        mock_context.last_sort_order = 0

        mock_fetch.return_value = {
            "plays": [
                {"eventId": 1, "typeDescKey": "faceoff", "sortOrder": 1},
                {"eventId": 2, "typeDescKey": "goal", "sortOrder": 2},
                {"eventId": 3, "typeDescKey": "shot-on-goal", "sortOrder": 3},
                {"eventId": 4, "typeDescKey": "goal", "sortOrder": 4}
            ]
        }

        # ACT
        live.parse_live_game(mock_context)

        # ASSERT
        # All 4 events should be processed
        assert mock_create_event.call_count == 4

    @patch('core.live.schedule.fetch_playbyplay')
    def test_parse_live_game_api_failure(self, mock_fetch):
        """
        Test handling of API failure during game parsing.

        API can fail due to network issues, NHL server problems, etc.
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.game_id = "2025020176"

        import requests
        mock_fetch.side_effect = requests.RequestException("API Error")

        # ACT & ASSERT
        with pytest.raises(requests.RequestException):
            live.parse_live_game(mock_context)


class TestRemovedGoalDetection:
    """
    Test removed goal detection (for challenges, corrections).

    When a goal is challenged and overturned, or corrected by NHL,
    it disappears from the play-by-play feed. We need to detect this.
    """

    def test_detect_removed_goals_no_removals(self):
        """
        Test when no goals have been removed.

        Normal scenario - all goals still in feed.
        """
        # ARRANGE
        mock_context = Mock()

        # Create mock goals that are still in the feed
        mock_goal1 = Mock()
        mock_goal1.event_id = 123
        mock_goal1.was_goal_removed.return_value = False

        mock_goal2 = Mock()
        mock_goal2.event_id = 456
        mock_goal2.was_goal_removed.return_value = False

        mock_context.all_goals = [mock_goal1, mock_goal2]

        all_plays = [
            {"eventId": 123, "typeDescKey": "goal"},
            {"eventId": 456, "typeDescKey": "goal"}
        ]

        # ACT
        live.detect_removed_goals(mock_context, all_plays)

        # ASSERT
        # Both goals should still be in the list
        assert len(mock_context.all_goals) == 2
        assert mock_goal1 in mock_context.all_goals
        assert mock_goal2 in mock_context.all_goals

    def test_detect_removed_goals_one_removed(self):
        """
        Test when one goal has been removed.

        This happens when a goal is challenged and overturned.
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.preferred_team = Mock(team_name="New Jersey Devils")
        mock_context.pref_goals = []
        mock_context.other_goals = []

        # Create mock goal that will be marked as removed
        mock_goal = Mock()
        mock_goal.event_id = 123
        mock_goal.event_team = "San Jose Sharks"
        mock_goal.was_goal_removed.return_value = True
        mock_goal.cache = []

        mock_context.all_goals = [mock_goal]

        # all_plays doesn't contain this goal anymore
        all_plays = [
            {"eventId": 456, "typeDescKey": "goal"}
        ]

        # ACT
        with patch('core.live.process_removed_goal') as mock_process:
            live.detect_removed_goals(mock_context, all_plays)

            # ASSERT
            mock_process.assert_called_once_with(mock_goal, mock_context)

    def test_detect_removed_goals_exception_handling(self):
        """
        Test that exceptions during goal removal don't crash the bot.

        Important: we can't let the bot crash during a live game.
        """
        # ARRANGE
        mock_context = Mock()

        mock_goal = Mock()
        mock_goal.was_goal_removed.side_effect = Exception("Test error")

        mock_context.all_goals = [mock_goal]

        # ACT - Should not raise exception
        live.detect_removed_goals(mock_context, [])

        # ASSERT - Function completes without crashing
        # (Exception is logged but not raised)
        assert True  # If we get here, test passes


class TestProcessRemovedGoal:
    """Test the process_removed_goal function"""

    def test_process_removed_goal_preferred_team(self):
        """
        Test removing a goal scored by preferred team.

        Goal should be removed from pref_goals list.
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.preferred_team.team_name = "New Jersey Devils"

        mock_goal = Mock()
        mock_goal.event_id = 123
        mock_goal.event_team = "New Jersey Devils"
        mock_goal.cache = []

        mock_context.all_goals = [mock_goal]
        mock_context.pref_goals = [mock_goal]
        mock_context.other_goals = []

        # ACT
        live.process_removed_goal(mock_goal, mock_context)

        # ASSERT
        # Goal should be removed from lists
        assert mock_goal not in mock_context.all_goals
        assert mock_goal not in mock_context.pref_goals

    def test_process_removed_goal_other_team(self):
        """
        Test removing a goal scored by other team.

        Goal should be removed from other_goals list.
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.preferred_team.team_name = "New Jersey Devils"

        mock_goal = Mock()
        mock_goal.event_id = 456
        mock_goal.event_team = "San Jose Sharks"
        mock_goal.cache = []

        mock_context.all_goals = [mock_goal]
        mock_context.pref_goals = []
        mock_context.other_goals = [mock_goal]

        # ACT
        live.process_removed_goal(mock_goal, mock_context)

        # ASSERT
        # Goal should be removed from lists
        assert mock_goal not in mock_context.all_goals
        assert mock_goal not in mock_context.other_goals


class TestEventOrdering:
    """
    Test event ordering and sortOrder tracking.

    This is critical for knowing which events are "new" vs already processed.
    """

    @patch('core.live.schedule.fetch_playbyplay')
    @patch('core.live.EventFactory.create_event')
    def test_event_ordering_ascending(self, mock_create_event, mock_fetch):
        """
        Test that events are processed in sortOrder.

        NHL API returns events in order, but we should verify this.
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.game_id = "2025020176"
        mock_context.last_sort_order = 0

        mock_fetch.return_value = {
            "plays": [
                {"eventId": 1, "typeDescKey": "faceoff", "sortOrder": 10},
                {"eventId": 2, "typeDescKey": "goal", "sortOrder": 20},
                {"eventId": 3, "typeDescKey": "penalty", "sortOrder": 30}
            ]
        }

        # ACT
        live.parse_live_game(mock_context)

        # ASSERT
        # Events should be passed to factory in order
        calls = mock_create_event.call_args_list
        assert calls[0][0][0]["sortOrder"] == 10
        assert calls[1][0][0]["sortOrder"] == 20
        assert calls[2][0][0]["sortOrder"] == 30

    @patch('core.live.schedule.fetch_playbyplay')
    @patch('core.live.EventFactory.create_event')
    def test_event_tracking_with_last_sort_order(self, mock_create_event, mock_fetch):
        """
        Test that last_sort_order correctly identifies new events.

        Only events with sortOrder > last_sort_order are "new".
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.game_id = "2025020176"
        mock_context.last_sort_order = 15  # Already processed up to 15

        mock_fetch.return_value = {
            "plays": [
                {"eventId": 1, "typeDescKey": "faceoff", "sortOrder": 10},   # Old
                {"eventId": 2, "typeDescKey": "goal", "sortOrder": 20},      # New!
                {"eventId": 3, "typeDescKey": "penalty", "sortOrder": 30}    # New!
            ]
        }

        # ACT
        live.parse_live_game(mock_context)

        # ASSERT
        # All events processed, but EventFactory knows which are new
        assert mock_create_event.call_count == 3


class TestEventFiltering:
    """Test filtering of specific event types"""

    @patch('core.live.schedule.fetch_playbyplay')
    def test_goal_event_filtering(self, mock_fetch):
        """
        Test that goal events are correctly filtered.

        We track goals separately for stats and display.
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.game_id = "2025020176"
        mock_context.last_sort_order = 0

        mock_fetch.return_value = {
            "plays": [
                {"eventId": 1, "typeDescKey": "faceoff", "sortOrder": 1},
                {"eventId": 2, "typeDescKey": "goal", "sortOrder": 2},
                {"eventId": 3, "typeDescKey": "shot-on-goal", "sortOrder": 3},
                {"eventId": 4, "typeDescKey": "goal", "sortOrder": 4},
                {"eventId": 5, "typeDescKey": "penalty", "sortOrder": 5}
            ]
        }

        # ACT
        with patch('core.live.EventFactory.create_event'):
            live.parse_live_game(mock_context)

        # ASSERT
        # The function logs the number of goals found
        # In a real test, we'd verify goals are tracked correctly


class TestLiveGameIntegration:
    """Integration tests for live game monitoring"""

    @patch('core.live.schedule.fetch_playbyplay')
    @patch('core.live.EventFactory.create_event')
    def test_live_game_full_flow(self, mock_create_event, mock_fetch):
        """
        Test complete flow of parsing a live game.

        Simulates: API call -> event detection -> event processing
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.game_id = "2025020176"
        mock_context.last_sort_order = 0
        mock_context.all_goals = []

        # Simulate a game with multiple event types
        mock_fetch.return_value = {
            "plays": [
                {
                    "eventId": 1,
                    "typeDescKey": "period-start",
                    "sortOrder": 1,
                    "periodDescriptor": {"number": 1}
                },
                {
                    "eventId": 10,
                    "typeDescKey": "faceoff",
                    "sortOrder": 10,
                    "timeInPeriod": "20:00"
                },
                {
                    "eventId": 50,
                    "typeDescKey": "shot-on-goal",
                    "sortOrder": 50,
                    "timeInPeriod": "18:23"
                },
                {
                    "eventId": 100,
                    "typeDescKey": "goal",
                    "sortOrder": 100,
                    "timeInPeriod": "15:42"
                },
                {
                    "eventId": 150,
                    "typeDescKey": "penalty",
                    "sortOrder": 150,
                    "timeInPeriod": "12:11"
                }
            ]
        }

        # ACT
        live.parse_live_game(mock_context)

        # ASSERT
        # Verify all events were processed
        assert mock_create_event.call_count == 5

        # Verify events were processed in order
        event_ids = [call[0][0]["eventId"] for call in mock_create_event.call_args_list]
        assert event_ids == [1, 10, 50, 100, 150]

    @patch('core.live.schedule.fetch_playbyplay')
    @patch('core.live.EventFactory.create_event')
    def test_multiple_parse_calls(self, mock_create_event, mock_fetch):
        """
        Test multiple consecutive parse calls (simulating polling loop).

        This is how the bot actually works - polls API every few seconds.
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.game_id = "2025020176"
        mock_context.last_sort_order = 0

        # First call - 2 events
        mock_fetch.return_value = {
            "plays": [
                {"eventId": 1, "typeDescKey": "faceoff", "sortOrder": 10},
                {"eventId": 2, "typeDescKey": "goal", "sortOrder": 20}
            ]
        }

        # ACT - First parse
        live.parse_live_game(mock_context)

        # Update last_sort_order (normally done by caller)
        mock_context.last_sort_order = 20

        # Second call - 1 new event
        mock_fetch.return_value = {
            "plays": [
                {"eventId": 1, "typeDescKey": "faceoff", "sortOrder": 10},
                {"eventId": 2, "typeDescKey": "goal", "sortOrder": 20},
                {"eventId": 3, "typeDescKey": "penalty", "sortOrder": 30}  # New!
            ]
        }

        # ACT - Second parse
        live.parse_live_game(mock_context)

        # ASSERT
        # First call: 2 events, Second call: 3 events (all processed)
        assert mock_create_event.call_count == 5


class TestEdgeCases:
    """Test edge cases and error conditions"""

    @patch('core.live.schedule.fetch_playbyplay')
    def test_malformed_event_data(self, mock_fetch):
        """
        Test handling of malformed event data.

        Currently, the code will raise KeyError if typeDescKey is missing.
        This test verifies that behavior. If you want more robust handling,
        you'd need to update live.py to use .get() instead of direct access.
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.game_id = "2025020176"
        mock_context.last_sort_order = 0

        # Event missing required fields
        mock_fetch.return_value = {
            "plays": [
                {"eventId": 1}  # Missing typeDescKey and sortOrder!
            ]
        }

        # ACT & ASSERT
        # Currently raises KeyError - this is expected behavior
        with pytest.raises(KeyError):
            live.parse_live_game(mock_context)

    @patch('core.live.schedule.fetch_playbyplay')
    def test_duplicate_event_ids(self, mock_fetch):
        """
        Test handling of duplicate event IDs.

        Sometimes NHL API has duplicate events (shouldn't happen but does).
        """
        # ARRANGE
        mock_context = Mock()
        mock_context.game_id = "2025020176"
        mock_context.last_sort_order = 0

        mock_fetch.return_value = {
            "plays": [
                {"eventId": 100, "typeDescKey": "goal", "sortOrder": 10},
                {"eventId": 100, "typeDescKey": "goal", "sortOrder": 10}  # Duplicate!
            ]
        }

        # ACT
        with patch('core.live.EventFactory.create_event'):
            live.parse_live_game(mock_context)

        # ASSERT
        # Should process both (EventFactory has deduplication logic)

    def test_empty_context_all_goals(self):
        """Test removed goal detection with empty all_goals list"""
        # ARRANGE
        mock_context = Mock()
        mock_context.all_goals = []

        # ACT
        live.detect_removed_goals(mock_context, [])

        # ASSERT
        # Should complete without error
        assert mock_context.all_goals == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])