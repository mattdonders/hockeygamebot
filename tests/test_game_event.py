# tests/test_game_event.py

from models.game_event import GameEvent


def test_game_event_from_api_data():
    sample_data = {
        "about": {"eventId": 123, "period": 1, "dateTime": "2021-10-12T19:15:00Z"},
        "result": {"eventTypeId": "GOAL", "description": "Player scored a goal"},
        "team": {"id": 1, "name": "New Jersey Devils"},
        "players": [],
    }

    event = GameEvent.from_api_data(sample_data)

    assert event.event_id == 123
    assert event.event_type == "GOAL"
    assert event.description == "Player scored a goal"
    assert event.period == 1
    assert event.timestamp == "2021-10-12T19:15:00Z"
