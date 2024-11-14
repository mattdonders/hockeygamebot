# models/game_event.py

from dataclasses import dataclass


@dataclass
class GameEvent:
    event_id: int
    event_type: str
    description: str
    period: int
    timestamp: str
    team: dict
    players: list

    @classmethod
    def from_api_data(cls, data):
        return cls(
            event_id=data.get("about", {}).get("eventId"),
            event_type=data.get("result", {}).get("eventTypeId"),
            description=data.get("result", {}).get("description"),
            period=data.get("about", {}).get("period"),
            timestamp=data.get("about", {}).get("dateTime"),
            team=data.get("team", {}),
            players=data.get("players", []),
        )
