# models/team.py

from dataclasses import dataclass


@dataclass
class Team:
    id: int
    name: str
    abbreviation: str
    venue: dict
    team_name: str

    @classmethod
    def from_api_data(cls, data):
        return cls(
            id=data.get("id"),
            name=data.get("name"),
            abbreviation=data.get("abbreviation"),
            venue=data.get("venue", {}),
            team_name=data.get("teamName"),
        )
