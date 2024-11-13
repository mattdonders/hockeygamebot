from enum import Enum


class GameState(Enum):
    """Enum for tracking the abstractGameState attribute."""

    PREVIEW = "Preview"
    LIVE = "Live"
    FINAL = "Final"


class GameStateCode(Enum):
    """Enum for tracking the codedGameState attribute."""

    PREVIEW = 1
    PREGAME = 2
    LIVE = 3
    CRITICAL = 4
    GAMEOVER = 5
    NEWLYFINAL = 6
    FINAL = 7
    SCHEDULED = 8
    POSTPONED = 9
