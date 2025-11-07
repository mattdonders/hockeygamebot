import logging
from datetime import datetime

import utils.others as otherutils
from core import charts, schedule
from core.models.game_context import GameContext


def final_score(context: GameContext):
    logging.info("Starting the core Final Score work now.")

    schedule.fetch_playbyplay(context.game_id)

    pref_home_text = "on the road" if context.preferred_homeaway == "away" else "at home"

    if context.preferred_team.score > context.other_team.score:
        final_score_text = (
            f"{context.preferred_team.full_name} win {pref_home_text} over the "
            f"{context.other_team.full_name} by a score of {context.preferred_team.score} to "
            f"{context.other_team.score}! 🚨🚨🚨"
        )
    else:
        final_score_text = (
            f"{context.preferred_team.full_name} lose {pref_home_text} to the "
            f"{context.other_team.full_name} by a score of {context.preferred_team.score} to "
            f"{context.other_team.score}! 👎🏻👎🏻👎🏻"
        )

    next_game_str = next_game(context)
    if next_game_str:
        final_score_text += f"\n\n{next_game_str}"

    final_score_text += f"\n\n{context.preferred_team.hashtag} | {context.game_hashtag}"

    return final_score_text


def next_game(context: GameContext):
    logging.info("Getting next game and formatting message.")

    full_schedule = schedule.fetch_schedule(context.preferred_team.abbreviation, context.season_id)
    next_game = schedule.fetch_next_game(full_schedule)
    if not next_game:
        return ""

    next_game_starttime = next_game["startTimeUTC"]
    next_game_time_local = otherutils.convert_utc_to_localteam_dt(
        next_game_starttime,
        context.preferred_team.timezone,
    )
    next_game_string = datetime.strftime(next_game_time_local, "%A %B %d @ %I:%M%p")

    away_team = next_game["awayTeam"]
    away_team_abbrev = away_team["abbrev"]
    away_team_name = away_team["placeName"]["default"] + " " + away_team["commonName"]["default"]
    home_team = next_game["homeTeam"]
    home_team["abbrev"]
    home_team_name = home_team["placeName"]["default"] + " " + home_team["commonName"]["default"]

    next_opponent = home_team_name if away_team_abbrev == context.preferred_team.abbreviation else away_team_name

    next_game_venue = next_game["venue"]["default"]
    return f"Next Game: {next_game_string} vs. {next_opponent} (at {next_game_venue})!"


def three_stars(context: GameContext):
    logging.info("Getting the three stars of the game.")

    landing_data = schedule.fetch_landing(context.game_id)
    three_stars = landing_data.get("summary", {}).get("threeStars")

    if not three_stars:
        logging.info("3-stars have not yet posted - try again in next iteration.")
        return None

    first_star = next((star for star in three_stars if star["star"] == 1), None)
    first_star_id = first_star["playerId"]
    first_star_abbrev = first_star["teamAbbrev"]
    first_star_name = otherutils.get_player_name(first_star_id, context.combined_roster)
    first_star_full = f"{first_star_name} ({first_star_abbrev})"

    second_star = next((star for star in three_stars if star["star"] == 2), None)
    second_star_id = second_star["playerId"]
    second_star_abbrev = second_star["teamAbbrev"]
    second_star_name = otherutils.get_player_name(second_star_id, context.combined_roster)
    second_star_full = f"{second_star_name} ({second_star_abbrev})"

    third_star = next((star for star in three_stars if star["star"] == 3), None)
    third_star_id = third_star["playerId"]
    third_star_abbrev = third_star["teamAbbrev"]
    third_star_name = otherutils.get_player_name(third_star_id, context.combined_roster)
    third_star_full = f"{third_star_name} ({third_star_abbrev})"

    stars_text = f"⭐️: {first_star_full}\n⭐️⭐️: {second_star_full}\n⭐️⭐️⭐️: {third_star_full}"
    three_stars_msg = f"The three stars for the game are - \n{stars_text}"

    three_stars_msg += f"\n\n{context.preferred_team.hashtag} | {context.game_hashtag}"

    return three_stars_msg


def team_stats_chart(context: GameContext) -> tuple[str, str]:
    """Sends the final team stats chart when the game is over."""
    right_rail_data = schedule.fetch_rightrail(context.game_id)
    team_stats_data = right_rail_data.get("teamGameStats")
    if not team_stats_data:
        return None, None

    charts.teamstats_chart(context, team_stats_data, ingame=True)
    return None
