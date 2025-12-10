"""
NHL Game Type Constants

The NHL API uses numeric gameType codes:

1 = Preseason (PR)
2 = Regular Season (R)
3 = Playoffs (P)
4 = All-Star (AS)        # Not always used consistently, but reserved.

We centralize these here to avoid magic numbers scattered across the codebase.
"""

GAME_TYPE_PRESEASON = 1  # PR
GAME_TYPE_REGULAR_SEASON = 2  # R
GAME_TYPE_PLAYOFFS = 3  # P
GAME_TYPE_ALL_STAR = 4  # AS (rare, but supported)

# Convenience sets for logic elsewhere in the bot
REGULAR_SEASON_ONLY = {GAME_TYPE_REGULAR_SEASON}
PLAYOFFS_ONLY = {GAME_TYPE_PLAYOFFS}
NON_REGULAR_SEASON = {GAME_TYPE_PRESEASON, GAME_TYPE_PLAYOFFS, GAME_TYPE_ALL_STAR}
