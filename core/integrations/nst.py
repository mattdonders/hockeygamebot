import logging
from typing import Optional
from urllib.parse import urlencode

from core.models.game_context import GameContext


def get_nst_report_url(context: GameContext, full: bool = False) -> Optional[str]:
    """
    Generate the Natural Stat Trick (NST) report URL for a given NHL game.

    Args:
        game: An NHL Game object containing relevant game details. Expected attributes:
              - season (e.g., "20242025")
              - game_id_gametype_shortid (e.g., "02")
              - game_id_shortid (e.g., "1234")
        full (bool): Whether to return the full report URL. Defaults to False.

    Returns:
        Optional[str]: The NST report URL for the game, or None if the URL cannot be constructed.
    """

    base_url = "https://www.naturalstattrick.com"

    # Validate the `game` object has the required attributes
    required_attrs = ["season", "game_type", "game_shortid"]
    if not all(hasattr(context, attr) for attr in required_attrs):
        logging.error(f"GameContext is missing required attributes: {required_attrs}")
        return None

    # Construct query parameters
    try:
        query_params = {
            "season": context.season_id,
            "view": "full" if full else "limited",
            "game": f"{context.game_type}{context.game_shortid}",
        }
        # Generate the full URL
        nst_rpt_url = f"{base_url}/game.php?{urlencode(query_params)}"
        return nst_rpt_url
    except Exception as e:
        logging.error(f"Failed to construct NST URL: {e}")
        return None
