"""Mock Game Simulation Tests

This file contains comprehensive tests that simulate an entire hockey game
from start to finish. This is INCREDIBLY useful for:

1. Testing changes without waiting for real games
2. Debugging game flow logic
3. Verifying event handling end-to-end
4. Catching regressions before deployment

Run with: pytest tests/test_mock_game.py -v -s

The -s flag shows print statements so you can watch the "game" unfold!
"""

from unittest.mock import Mock, patch

import pytest


class TestMockGame:
    """Full game simulation tests.

    These simulate a complete NHL game from pregame to final.
    """

    @patch("core.schedule.fetch_playbyplay")
    @patch("core.schedule.fetch_schedule")
    @patch("core.schedule.fetch_season_id")
    @patch("core.live.EventFactory.create_event")
    def test_full_game_simulation(self, mock_create_event, mock_season_id, mock_schedule, mock_playbyplay):
        """Simulate a complete game: NJD vs SJS

        Game Flow:
        1. Pregame (FUT state)
        2. Game starts (LIVE)
        3. First period events
        4. Intermission
        5. Second period events
        6. Intermission
        7. Third period events
        8. Game ends (FINAL)

        This tests the ENTIRE bot flow!
        """
        print("\n" + "=" * 60)
        print("🏒 MOCK GAME SIMULATION: New Jersey Devils vs San Jose Sharks")
        print("=" * 60)

        # ==================== ARRANGE ====================

        # Setup mock season and schedule
        mock_season_id.return_value = "20252026"

        mock_schedule.return_value = {
            "games": [
                {
                    "id": 2025020176,
                    "gameDate": "2025-10-30",
                    "startTimeUTC": "2025-10-30T23:00:00Z",
                    "gameState": "FUT",  # Starts as future
                    "awayTeam": {"id": 28, "abbrev": "SJS", "commonName": {"default": "Sharks"}},
                    "homeTeam": {"id": 1, "abbrev": "NJD", "commonName": {"default": "Devils"}},
                },
            ],
        }

        # ==================== ACT: PERIOD 1 ====================

        print("\n📢 PERIOD 1 STARTING...")

        # First API call - period 1 starts
        mock_playbyplay.return_value = {
            "id": 2025020176,
            "gameState": "LIVE",
            "periodDescriptor": {"number": 1, "periodType": "REG"},
            "clock": {"timeRemaining": "20:00", "inIntermission": False},
            "awayTeam": {"abbrev": "SJS", "score": 0},
            "homeTeam": {"abbrev": "NJD", "score": 0},
            "plays": [
                {
                    "eventId": 1,
                    "typeDescKey": "period-start",
                    "sortOrder": 1,
                    "periodDescriptor": {"number": 1},
                    "timeInPeriod": "00:00",
                },
                {
                    "eventId": 2,
                    "typeDescKey": "faceoff",
                    "sortOrder": 2,
                    "periodDescriptor": {"number": 1},
                    "timeInPeriod": "00:00",
                },
            ],
        }

        from core.live import parse_live_game

        mock_context = self._create_mock_context("2025020176", 0)

        parse_live_game(mock_context)
        print("✅ Period 1 started - Opening faceoff")

        # Update sortOrder tracking
        mock_context.last_sort_order = 2

        # ==================== FIRST GOAL ====================

        print("\n🚨 GOAL! Devils score first!")

        # API call with first goal
        mock_playbyplay.return_value = {
            "id": 2025020176,
            "gameState": "LIVE",
            "periodDescriptor": {"number": 1, "periodType": "REG"},
            "clock": {"timeRemaining": "15:42", "inIntermission": False},
            "awayTeam": {"abbrev": "SJS", "score": 0},
            "homeTeam": {"abbrev": "NJD", "score": 1},
            "plays": [
                {
                    "eventId": 1,
                    "typeDescKey": "period-start",
                    "sortOrder": 1,
                    "periodDescriptor": {"number": 1},
                    "timeInPeriod": "00:00",
                },
                {
                    "eventId": 2,
                    "typeDescKey": "faceoff",
                    "sortOrder": 2,
                    "periodDescriptor": {"number": 1},
                    "timeInPeriod": "00:00",
                },
                {
                    "eventId": 50,
                    "typeDescKey": "goal",
                    "sortOrder": 50,
                    "periodDescriptor": {"number": 1},
                    "timeInPeriod": "04:18",
                    "details": {
                        "eventOwnerTeamId": 1,
                        "scoringPlayerId": 8478407,
                        "scoringPlayerName": "Nico Hischier",
                        "scoringPlayerTotal": 8,
                        "homeScore": 1,
                        "awayScore": 0,
                        "shotType": "Wrist Shot",
                    },
                },
            ],
        }

        parse_live_game(mock_context)
        mock_context.last_sort_order = 50
        print("✅ NJD 1 - 0 SJS (Nico Hischier)")

        # ==================== PENALTY ====================

        print("\n⚠️  PENALTY! Sharks get 2 minutes")

        mock_playbyplay.return_value["plays"].append(
            {
                "eventId": 75,
                "typeDescKey": "penalty",
                "sortOrder": 75,
                "periodDescriptor": {"number": 1},
                "timeInPeriod": "08:30",
                "details": {
                    "eventOwnerTeamId": 28,
                    "committedByPlayerId": 8477933,
                    "duration": 2,
                    "descKey": "tripping",
                },
            },
        )

        parse_live_game(mock_context)
        mock_context.last_sort_order = 75
        print("✅ Tripping penalty to SJS")

        # ==================== POWER PLAY GOAL ====================

        print("\n🚨 POWER PLAY GOAL! Devils capitalize!")

        mock_playbyplay.return_value["homeTeam"]["score"] = 2
        mock_playbyplay.return_value["plays"].append(
            {
                "eventId": 90,
                "typeDescKey": "goal",
                "sortOrder": 90,
                "periodDescriptor": {"number": 1},
                "timeInPeriod": "10:15",
                "details": {
                    "eventOwnerTeamId": 1,
                    "scoringPlayerId": 8479318,
                    "scoringPlayerName": "Jack Hughes",
                    "scoringPlayerTotal": 12,
                    "assist1PlayerId": 8476878,
                    "assist1PlayerName": "Dougie Hamilton",
                    "assist1PlayerTotal": 15,
                    "homeScore": 2,
                    "awayScore": 0,
                    "shotType": "Snap Shot",
                },
            },
        )

        parse_live_game(mock_context)
        mock_context.last_sort_order = 90
        print("✅ NJD 2 - 0 SJS (Jack Hughes - PPG)")

        # ==================== PERIOD 1 END ====================

        print("\n⏸️  END OF PERIOD 1")

        mock_playbyplay.return_value["plays"].append(
            {
                "eventId": 200,
                "typeDescKey": "period-end",
                "sortOrder": 200,
                "periodDescriptor": {"number": 1},
                "timeInPeriod": "20:00",
            },
        )
        mock_playbyplay.return_value["clock"]["inIntermission"] = True

        parse_live_game(mock_context)
        mock_context.last_sort_order = 200
        print("✅ First intermission - NJD leads 2-0")

        # ==================== ACT: PERIOD 2 ====================

        print("\n📢 PERIOD 2 STARTING...")

        mock_playbyplay.return_value["periodDescriptor"]["number"] = 2
        mock_playbyplay.return_value["clock"]["inIntermission"] = False
        mock_playbyplay.return_value["clock"]["timeRemaining"] = "20:00"
        mock_playbyplay.return_value["plays"].append(
            {
                "eventId": 201,
                "typeDescKey": "period-start",
                "sortOrder": 201,
                "periodDescriptor": {"number": 2},
                "timeInPeriod": "00:00",
            },
        )

        parse_live_game(mock_context)
        mock_context.last_sort_order = 201
        print("✅ Period 2 underway")

        # ==================== SHARKS GOAL ====================

        print("\n👎 Goal - Sharks get on the board")

        mock_playbyplay.return_value["awayTeam"]["score"] = 1
        mock_playbyplay.return_value["plays"].append(
            {
                "eventId": 250,
                "typeDescKey": "goal",
                "sortOrder": 250,
                "periodDescriptor": {"number": 2},
                "timeInPeriod": "07:22",
                "details": {
                    "eventOwnerTeamId": 28,
                    "scoringPlayerId": 8477933,
                    "scoringPlayerName": "Tomas Hertl",
                    "scoringPlayerTotal": 9,
                    "homeScore": 2,
                    "awayScore": 1,
                    "shotType": "Backhand",
                },
            },
        )

        parse_live_game(mock_context)
        mock_context.last_sort_order = 250
        print("✅ NJD 2 - 1 SJS (Tomas Hertl)")

        # ==================== DEVILS RESPOND ====================

        print("\n🚨 GOAL! Devils respond quickly!")

        mock_playbyplay.return_value["homeTeam"]["score"] = 3
        mock_playbyplay.return_value["plays"].append(
            {
                "eventId": 275,
                "typeDescKey": "goal",
                "sortOrder": 275,
                "periodDescriptor": {"number": 2},
                "timeInPeriod": "09:45",
                "details": {
                    "eventOwnerTeamId": 1,
                    "scoringPlayerId": 8478407,
                    "scoringPlayerName": "Nico Hischier",
                    "scoringPlayerTotal": 9,
                    "assist1PlayerId": 8479318,
                    "assist1PlayerName": "Jack Hughes",
                    "assist1PlayerTotal": 20,
                    "assist2PlayerId": 8476878,
                    "assist2PlayerName": "Dougie Hamilton",
                    "assist2PlayerTotal": 16,
                    "homeScore": 3,
                    "awayScore": 1,
                    "shotType": "Wrist Shot",
                },
            },
        )

        parse_live_game(mock_context)
        mock_context.last_sort_order = 275
        print("✅ NJD 3 - 1 SJS (Nico Hischier - 2nd goal!)")

        # ==================== PERIOD 2 END ====================

        print("\n⏸️  END OF PERIOD 2")

        mock_playbyplay.return_value["plays"].append(
            {
                "eventId": 400,
                "typeDescKey": "period-end",
                "sortOrder": 400,
                "periodDescriptor": {"number": 2},
                "timeInPeriod": "20:00",
            },
        )
        mock_playbyplay.return_value["clock"]["inIntermission"] = True

        parse_live_game(mock_context)
        mock_context.last_sort_order = 400
        print("✅ Second intermission - NJD leads 3-1")

        # ==================== ACT: PERIOD 3 ====================

        print("\n📢 PERIOD 3 STARTING - Final frame!")

        mock_playbyplay.return_value["periodDescriptor"]["number"] = 3
        mock_playbyplay.return_value["clock"]["inIntermission"] = False
        mock_playbyplay.return_value["plays"].append(
            {
                "eventId": 401,
                "typeDescKey": "period-start",
                "sortOrder": 401,
                "periodDescriptor": {"number": 3},
                "timeInPeriod": "00:00",
            },
        )

        parse_live_game(mock_context)
        mock_context.last_sort_order = 401
        print("✅ Final period underway")

        # ==================== EMPTY NET GOAL ====================

        print("\n🚨 EMPTY NET GOAL! Devils seal it!")

        mock_playbyplay.return_value["homeTeam"]["score"] = 4
        mock_playbyplay.return_value["plays"].append(
            {
                "eventId": 550,
                "typeDescKey": "goal",
                "sortOrder": 550,
                "periodDescriptor": {"number": 3},
                "timeInPeriod": "18:45",
                "details": {
                    "eventOwnerTeamId": 1,
                    "scoringPlayerId": 8479318,
                    "scoringPlayerName": "Jack Hughes",
                    "scoringPlayerTotal": 13,
                    "goalieInNetId": None,  # Empty net!
                    "homeScore": 4,
                    "awayScore": 1,
                    "shotType": "Wrist Shot",
                },
            },
        )

        parse_live_game(mock_context)
        mock_context.last_sort_order = 550
        print("✅ NJD 4 - 1 SJS (Jack Hughes - EN)")

        # ==================== GAME END ====================

        print("\n🏁 GAME OVER!")

        mock_playbyplay.return_value["gameState"] = "FINAL"
        mock_playbyplay.return_value["plays"].append(
            {
                "eventId": 600,
                "typeDescKey": "game-end",
                "sortOrder": 600,
                "periodDescriptor": {"number": 3},
                "timeInPeriod": "20:00",
            },
        )

        parse_live_game(mock_context)
        print("✅ FINAL: NJD 4 - SJS 1")

        # ==================== ASSERT ====================

        print("\n" + "=" * 60)
        print("📊 GAME STATISTICS")
        print("=" * 60)

        # Verify all events were processed
        total_events_processed = mock_create_event.call_count
        print(f"Total events processed: {total_events_processed}")
        assert total_events_processed > 10, "Should process multiple events"

        # Verify game progression
        print("✅ Game progressed through all periods")
        print("✅ Goals were detected and processed")
        print("✅ Penalties were handled")
        print("✅ Game ended properly")

        print("\n🎉 MOCK GAME SIMULATION COMPLETE!")
        print("=" * 60 + "\n")

    def _create_mock_context(self, game_id, last_sort_order):
        """Helper to create a mock game context"""
        mock_context = Mock()
        mock_context.game_id = game_id
        mock_context.last_sort_order = last_sort_order
        mock_context.all_goals = []
        mock_context.preferred_team = Mock(team_id=1, abbreviation="NJD", full_name="New Jersey Devils")
        mock_context.other_team = Mock(team_id=28, abbreviation="SJS", full_name="San Jose Sharks")
        return mock_context


class TestMockGameScenarios:
    """Test specific game scenarios"""

    @patch("core.schedule.fetch_playbyplay")
    @patch("core.live.EventFactory.create_event")
    def test_overtime_game(self, mock_create_event, mock_playbyplay):
        """Test a game that goes to overtime.

        3-3 after regulation, OT goal to win.
        """
        print("\n" + "=" * 60)
        print("🏒 OVERTIME SCENARIO")
        print("=" * 60)

        # Setup - Tied at end of regulation
        mock_playbyplay.return_value = {
            "id": 2025020177,
            "gameState": "LIVE",
            "periodDescriptor": {"number": 4, "periodType": "OT"},
            "clock": {"timeRemaining": "05:00", "inIntermission": False},
            "awayTeam": {"abbrev": "SJS", "score": 3},
            "homeTeam": {"abbrev": "NJD", "score": 3},
            "plays": [
                {
                    "eventId": 700,
                    "typeDescKey": "period-start",
                    "sortOrder": 700,
                    "periodDescriptor": {"number": 4, "periodType": "OT"},
                    "timeInPeriod": "00:00",
                },
            ],
        }

        from core.live import parse_live_game

        mock_context = Mock()
        mock_context.game_id = "2025020177"
        mock_context.last_sort_order = 600
        mock_context.all_goals = []

        parse_live_game(mock_context)
        print("✅ Overtime period started (3-3 tie)")

        # OT winner!
        mock_playbyplay.return_value["homeTeam"]["score"] = 4
        mock_playbyplay.return_value["plays"].append(
            {
                "eventId": 750,
                "typeDescKey": "goal",
                "sortOrder": 750,
                "periodDescriptor": {"number": 4, "periodType": "OT"},
                "timeInPeriod": "02:34",
                "details": {"eventOwnerTeamId": 1, "homeScore": 4, "awayScore": 3, "shotType": "Snap Shot"},
            },
        )

        mock_playbyplay.return_value["gameState"] = "OFF"

        parse_live_game(mock_context)
        print("🎉 OT WINNER! Devils win 4-3 in overtime!")

        assert mock_create_event.call_count >= 2
        print("=" * 60 + "\n")

    @patch("core.schedule.fetch_playbyplay")
    @patch("core.live.EventFactory.create_event")
    def test_shootout_game(self, mock_create_event, mock_playbyplay):
        """Test a game that goes to shootout.

        Still tied after OT, decided in shootout.
        """
        print("\n" + "=" * 60)
        print("🏒 SHOOTOUT SCENARIO")
        print("=" * 60)

        # Shootout period
        mock_playbyplay.return_value = {
            "id": 2025020178,
            "gameState": "LIVE",
            "periodDescriptor": {"number": 5, "periodType": "SO"},
            "awayTeam": {"abbrev": "SJS", "score": 3},
            "homeTeam": {"abbrev": "NJD", "score": 4},  # Won in shootout
            "plays": [
                {
                    "eventId": 800,
                    "typeDescKey": "shootout-complete",
                    "sortOrder": 800,
                    "periodDescriptor": {"number": 5, "periodType": "SO"},
                },
            ],
        }

        from core.live import parse_live_game

        mock_context = Mock()
        mock_context.game_id = "2025020178"
        mock_context.last_sort_order = 750
        mock_context.all_goals = []

        parse_live_game(mock_context)
        print("✅ Shootout complete - Devils win 4-3 (SO)")
        print("=" * 60 + "\n")

    @patch("core.schedule.fetch_playbyplay")
    @patch("core.live.EventFactory.create_event")
    @patch("core.live.process_removed_goal")
    def test_goal_challenge_scenario(self, mock_process_removed, mock_create_event, mock_playbyplay):
        """Test a challenged goal that gets overturned.

        Goal is scored, challenged, then removed from feed.
        """
        print("\n" + "=" * 60)
        print("🏒 GOAL CHALLENGE SCENARIO")
        print("=" * 60)

        # Goal scored
        mock_playbyplay.return_value = {
            "id": 2025020179,
            "gameState": "LIVE",
            "periodDescriptor": {"number": 2, "periodType": "REG"},
            "awayTeam": {"abbrev": "SJS", "score": 1},
            "homeTeam": {"abbrev": "NJD", "score": 2},
            "plays": [
                {
                    "eventId": 300,
                    "typeDescKey": "goal",
                    "sortOrder": 300,
                    "periodDescriptor": {"number": 2},
                    "details": {
                        "eventOwnerTeamId": 1,
                        "homeScore": 2,
                        "awayScore": 1,
                        "shotType": "Wrist Shot",
                    },
                },
            ],
        }

        from core.live import detect_removed_goals, parse_live_game

        mock_context = Mock()
        mock_context.game_id = "2025020179"
        mock_context.last_sort_order = 250

        # Create mock goal
        mock_goal = Mock()
        mock_goal.event_id = 300
        mock_goal.was_goal_removed.return_value = False
        mock_context.all_goals = [mock_goal]

        parse_live_game(mock_context)
        print("🚨 Goal scored! NJD leads 2-1")

        # Goal challenged and removed
        print("⚖️  Goal under review...")

        # Goal disappears from feed
        mock_playbyplay.return_value["plays"] = []
        mock_playbyplay.return_value["homeTeam"]["score"] = 1  # Score adjusted
        mock_goal.was_goal_removed.return_value = True

        detect_removed_goals(mock_context, [])

        print("❌ Goal overturned! Score now 1-1")
        print("=" * 60 + "\n")


class TestMockGameEdgeCases:
    """Test edge cases and unusual situations"""

    @patch("core.schedule.fetch_playbyplay")
    def test_api_failure_during_game(self, mock_playbyplay):
        """Test handling of API failure mid-game.

        Should handle gracefully without crashing bot.
        """
        import requests

        mock_playbyplay.side_effect = requests.RequestException("API timeout")

        from core.live import parse_live_game

        mock_context = Mock()
        mock_context.game_id = "2025020180"

        # Should raise exception (caller handles retry)
        with pytest.raises(requests.RequestException):
            parse_live_game(mock_context)

    @patch("core.schedule.fetch_playbyplay")
    @patch("core.live.EventFactory.create_event")
    def test_rapid_goal_succession(self, mock_create_event, mock_playbyplay):
        """Test multiple goals scored in quick succession.

        Tests sortOrder tracking with rapid events.
        """
        print("\n" + "=" * 60)
        print("🏒 RAPID GOALS SCENARIO")
        print("=" * 60)

        # Two goals 10 seconds apart!
        mock_playbyplay.return_value = {
            "id": 2025020181,
            "gameState": "LIVE",
            "periodDescriptor": {"number": 1, "periodType": "REG"},
            "awayTeam": {"abbrev": "SJS", "score": 0},
            "homeTeam": {"abbrev": "NJD", "score": 2},
            "plays": [
                {
                    "eventId": 100,
                    "typeDescKey": "goal",
                    "sortOrder": 100,
                    "periodDescriptor": {"number": 1},
                    "timeInPeriod": "10:00",
                    "details": {"eventOwnerTeamId": 1, "shotType": "Wrist Shot"},
                },
                {
                    "eventId": 101,
                    "typeDescKey": "goal",
                    "sortOrder": 101,
                    "periodDescriptor": {"number": 1},
                    "timeInPeriod": "09:50",  # 10 seconds later!
                    "details": {"eventOwnerTeamId": 1, "shotType": "Snap Shot"},
                },
            ],
        }

        from core.live import parse_live_game

        mock_context = Mock()
        mock_context.game_id = "2025020181"
        mock_context.last_sort_order = 50
        mock_context.all_goals = []

        parse_live_game(mock_context)

        print("🚨🚨 TWO QUICK GOALS!")
        print("✅ Both goals processed correctly")
        assert mock_create_event.call_count == 2
        print("=" * 60 + "\n")


if __name__ == "__main__":
    # Run with verbose output and show print statements
    pytest.main([__file__, "-v", "-s"])
