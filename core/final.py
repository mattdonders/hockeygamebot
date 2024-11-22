import logging
from core import schedule
from core.game_context import GameContext


def final_score(context: GameContext):
    logging.info("Starting the core Final Score work now.")

    play_by_play_data = schedule.fetch_playbyplay(context.game_id)

    pref_home_text = "on the road" if context.preferred_homeaway == "away" else "at home"

    if context.preferred_score > context.other_score:
        final_score_text = (
            f"{context.preferred_team_name} win {pref_home_text} over the "
            f"{context.other_team_name} by a score of {context.preferred_score} to "
            f"{context.other_score}! 🚨🚨🚨"
        )
    else:
        final_score_text = (
            f"{context.preferred_team_name} lose {pref_home_text} to the "
            f"{context.other_team_name} by a score of {context.preferred_score} to "
            f"{context.preferred_score}! 👎🏻👎🏻👎🏻"
        )

    final_score_text += f"\n\n{context.preferred_team_hashtag} | {context.game_hashtag}"

    return final_score_text
