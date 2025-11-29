import logging
from datetime import datetime
from typing import Optional, Tuple

import core.charts as charts
import utils.others as otherutils
from core import schedule
from core.milestones import MilestoneHit
from core.models.game_context import GameContext

logger = logging.getLogger(__name__)


def _resolve_final_result(context: GameContext) -> Tuple[str, int, int]:
    """
    Resolve the authoritative final result for this game using the
    club-schedule-season endpoint.

    Returns:
        (result_type, preferred_score, other_score)

        result_type is usually "REG", "OT", or "SO" based on
        gameOutcome.lastPeriodType.
    """
    preferred_abbr = context.preferred_team.abbreviation
    season_id = context.season_id

    try:
        full_schedule = schedule.fetch_schedule(preferred_abbr, season_id)
        games = full_schedule.get("games", [])
    except Exception as exc:  # defensive fallback
        logger.exception(
            "Final result: failed to fetch schedule for %s (%s); " "falling back to context scores.",
            preferred_abbr,
            exc,
        )
        return "REG", context.preferred_team.score, context.other_team.score

    game_entry = None
    for game in games:
        # Game IDs in schedule and context should match when cast to str
        if str(game.get("id")) == str(context.game_id):
            game_entry = game
            break

    if game_entry is None:
        logger.warning(
            "Final result: could not locate game %s in schedule for %s; " "falling back to context scores.",
            context.game_id,
            preferred_abbr,
        )
        return "REG", context.preferred_team.score, context.other_team.score

    game_outcome = game_entry.get("gameOutcome") or {}
    result_type = game_outcome.get("lastPeriodType", "REG")

    home = game_entry.get("homeTeam", {}) or {}
    away = game_entry.get("awayTeam", {}) or {}

    home_score = home.get("score", 0)
    away_score = away.get("score", 0)

    if context.preferred_homeaway == "home":
        preferred_score = home_score
        other_score = away_score
    elif context.preferred_homeaway == "away":
        preferred_score = away_score
        other_score = home_score
    else:
        logger.warning(
            "Final result: preferred team %s not found as home/away in game %s; falling back to context scores.",
            context.preferred_team.abbreviation,
            context.game_id,
        )
        return result_type, context.preferred_team.score, context.other_team.score

    # Optionally keep the context in sync with the official record
    try:
        context.preferred_team.score = preferred_score
        context.other_team.score = other_score
    except Exception:
        logger.debug("Unable to write resolved scores back to context.", exc_info=True)

    return result_type, preferred_score, other_score


def final_score(context: GameContext):
    logger.info("Starting the core Final Score work now.")

    # We still fetch play-by-play here in case we want richer summaries later.
    try:
        play_by_play_data = schedule.fetch_playbyplay(context.game_id)
    except Exception:
        play_by_play_data = None
        logger.debug("Unable to fetch play-by-play in final_score.", exc_info=True)

    # Use the authoritative final result from the schedule API
    result_type, preferred_score, other_score = _resolve_final_result(context)

    # Home/road text stays exactly as before
    pref_home_text = "on the road" if context.preferred_homeaway == "away" else "at home"

    preferred_won = preferred_score > other_score

    # For REG and OT, keep the text as close as possible to your existing style.
    # For SO, append a short "in a shootout" suffix.
    if result_type == "SO":
        result_suffix = " in a shootout"
    elif result_type == "OT":
        result_suffix = " in overtime"
    else:
        result_suffix = ""

    # Structured logging for debugging
    try:
        home_abbr = context.home_team.abbreviation
        away_abbr = context.away_team.abbreviation
    except Exception:
        home_abbr = "HOME"
        away_abbr = "AWAY"

    winner_abbr = context.preferred_team.abbreviation if preferred_won else context.other_team.abbreviation

    logger.info(
        "Final result: %s @ %s, result_type=%s, winner=%s, displayed_score=%s-%s",
        away_abbr,
        home_abbr,
        result_type,
        winner_abbr,
        preferred_score,
        other_score,
    )

    if preferred_won:
        final_score_text = (
            f"{context.preferred_team.full_name} win {pref_home_text} over the "
            f"{context.other_team.full_name} by a score of {preferred_score} to "
            f"{other_score}{result_suffix}! 🚨🚨🚨"
        )
    else:
        final_score_text = (
            f"{context.preferred_team.full_name} lose {pref_home_text} to the "
            f"{context.other_team.full_name} by a score of {preferred_score} to "
            f"{other_score}{result_suffix}! 👎🏻👎🏻👎🏻"
        )

    next_game_str = next_game(context)
    if next_game_str:
        final_score_text += f"\n\n{next_game_str}"

    final_score_text += f"\n\n{context.preferred_team.hashtag} | {context.game_hashtag}"

    return final_score_text


def next_game(context: GameContext):
    logger.info("Getting next game and formatting message.")

    full_schedule = schedule.fetch_schedule(context.preferred_team.abbreviation, context.season_id)
    next_game = schedule.fetch_next_game(full_schedule)
    if not next_game:
        return ""

    next_game_starttime = next_game["startTimeUTC"]
    next_game_time_local = otherutils.convert_utc_to_localteam_dt(next_game_starttime, context.preferred_team.timezone)
    next_game_string = datetime.strftime(next_game_time_local, "%A %B %d @ %I:%M%p")

    away_team = next_game["awayTeam"]
    away_team_abbrev = away_team["abbrev"]
    away_team_name = away_team["placeName"]["default"] + " " + away_team["commonName"]["default"]
    home_team = next_game["homeTeam"]
    home_team_abbrev = home_team["abbrev"]
    home_team_name = home_team["placeName"]["default"] + " " + home_team["commonName"]["default"]

    next_opponent = home_team_name if away_team_abbrev == context.preferred_team.abbreviation else away_team_name

    next_game_venue = next_game["venue"]["default"]
    next_game_text = f"Next Game: {next_game_string} vs. {next_opponent} (at {next_game_venue})!"

    return next_game_text


def three_stars(context: GameContext):
    logger.info("Getting the three stars of the game.")

    landing_data = schedule.fetch_landing(context.game_id)
    three_stars = landing_data.get("summary", {}).get("threeStars")

    if not three_stars:
        logger.info("3-stars have not yet posted - try again in next iteration.")
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


def team_stats_chart(context: GameContext) -> Tuple[str, str]:
    """
    Sends the final team stats chart when the game is over.
    """
    right_rail_data = schedule.fetch_rightrail(context.game_id)
    team_stats_data = right_rail_data.get("teamGameStats")
    if not team_stats_data:
        return None, None

    chart_path = charts.teamstats_chart(context, team_stats_data, ingame=True)
    chart_message = "Team Game"


def infer_goalie_result_from_boxscore(
    context: GameContext,
) -> Tuple[Optional[int], bool]:
    """
    Infer the *preferred* team's winning goalie and shutout status
    using only our own game data.

    Assumptions (v1):
      - We only care about milestones for the preferred team’s goalie.
      - If the preferred team didn't win, we don't award a win.
      - If the other team scored 0, we treat it as a shutout.
      - The winning goalie is whoever you have stored as
        `context.preferred_starting_goalie_id`.

    You can later make this smarter (e.g., track which goalies actually played).
    """

    box_score = schedule.fetch_boxscore(context.game_id)
    player_stats = box_score.get("playerByGameStats", {})
    preferred_key = f"{context.preferred_homeaway}Team"

    team_goalies = player_stats.get(preferred_key, {}).get("goalies", [])
    if not team_goalies:
        logger.warning(
            "infer_goalie_result_from_boxscore: no goalies found for %s in boxscore",
            preferred_key,
        )
        return None, False

    # 1) Try to find the goalie with decision == "W"
    winning_goalie = next(
        (g for g in team_goalies if g.get("decision") == "W"),
        None,
    )

    # 2) Fallback: if no explicit decision, use the starter
    if winning_goalie is None:
        winning_goalie = next(
            (g for g in team_goalies if g.get("starter") is True),
            None,
        )

    if winning_goalie is None:
        logger.warning("Could not identify winning/starting goalie for preferred team.")
        return None, False

    goalie_id = winning_goalie.get("playerId")

    # Shutout logic:
    #   - Opponent score is 0
    #   - This goalie has goalsAgainst == 0
    other_score = context.other_team.score
    goals_against = winning_goalie.get("goalsAgainst", 0)
    was_shutout = (other_score == 0) and (goals_against == 0)

    logger.info(
        "Goalie result from boxscore: goalie_id=%s, decision=%s, GA=%s, " "opp_score=%s, was_shutout=%s",
        goalie_id,
        winning_goalie.get("decision"),
        goals_against,
        other_score,
        was_shutout,
    )

    return goalie_id, was_shutout


def generate_final_milestones_post(context: GameContext) -> Optional[str]:
    """
    Build a post-game milestones post from any hits discovered during the game.

    This is meant for:
      - goal milestones hit during the game (from GoalEvent.handle_event)
      - goalie wins / shutouts applied after the game goes FINAL
    and uses `context.final_socials.milestone_hits` as the source of truth.
    """
    service = context.milestone_service
    hits: list[MilestoneHit] = getattr(context.final_socials, "milestone_hits", []) or []

    if service is None or not hits:
        return None

    # ID -> player name
    def resolve_name(player_id: int) -> str:
        # combined_roster is {player_id: "Name"} in your code
        return context.combined_roster.get(player_id, str(player_id))

    team_name = context.preferred_team.full_name if context.preferred_team is not None else "Tonight's game"

    lines: list[str] = []
    lines.append(f"Post-game milestones for {team_name} 🎉🏒")
    lines.append("")
    lines.append("Tonight’s milestones:")

    for hit in hits:
        name = resolve_name(hit.player_id)
        lines.append(f"• {name} — {hit.label}")

    lines.append("")
    lines.append(f"{context.preferred_team.hashtag} | {context.game_hashtag}")

    return "\n".join(lines)
