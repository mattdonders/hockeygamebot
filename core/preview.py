from datetime import datetime, timezone
import logging
import time

import requests

from core import schedule
from core.models.game_context import GameContext
from utils.others import categorize_broadcasts, clock_emoji, convert_utc_to_localteam
from utils.team_details import TEAM_DETAILS
from core.schedule import fetch_schedule

logger = logging.getLogger(__name__)

def sleep_until_game_start(start_time_utc):
    """
    Sleep until the game starts based on the provided UTC start time.
    """
    now = datetime.now(timezone.utc)
    start_time = datetime.strptime(start_time_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    time_diff = (start_time - now).total_seconds()

    if time_diff > 0:
        logger.info(f"Sleeping for {time_diff:.2f} seconds until game start at {start_time}.")
        time.sleep(time_diff)
    else:
        logger.warning("Game start time is in the past, but not live yet - sleep for 30s.")
        time.sleep(30)


def preview_sleep_calculator(context: GameContext):
    """
    Auto sleep-time calculator for FUT or PRE game states.

    IMPORTANT: Always sleeps for at least 5 seconds to prevent busy loops
    that can hammer the NHL API and cause rate limit errors.
    """
    # MINIMUM SLEEP TIME - prevents busy loop when game time approaches
    MIN_SLEEP_TIME = 10  # seconds

    preview_sleep_time = context.config["script"]["preview_sleep_time"]
    preview_sleep_mins = int(preview_sleep_time / 60)

    # Scenario 1: Game Time Passed, but not LIVE yet
    if context.game_time_countdown < 0:
        logger.warning(
            "Game start time is in the past (%s seconds ago), but not live yet - sleep for 30s.",
            abs(context.game_time_countdown)
        )
        time.sleep(30)
        return

    # Scenario 2: All Pre-Game Posts Sent - sleep until game time (with minimum)
    if context.preview_socials.all_pregame_sent:
        # CRITICAL FIX: Always sleep at least MIN_SLEEP_TIME seconds
        actual_sleep_time = max(context.game_time_countdown, MIN_SLEEP_TIME)
        preview_sleep_mins = int(actual_sleep_time / 60)

        if context.game_time_countdown < MIN_SLEEP_TIME:
            logger.info(
                "All pre-game messages sent. Game starts in %s seconds - sleeping for minimum %s seconds to avoid API spam.",
                int(context.game_time_countdown),
                MIN_SLEEP_TIME
            )
        else:
            logger.info(
                "All pre-game messages sent. Sleeping until game time (~%s minutes).",
                preview_sleep_mins
            )

        time.sleep(actual_sleep_time)
        return

    # Scenario 3: Pre-Game Posts NOT Sent, but preview_sleep_time is longer than game_time_countdown
    if preview_sleep_time > context.game_time_countdown:
        # CRITICAL FIX: Always sleep at least MIN_SLEEP_TIME seconds
        actual_sleep_time = max(context.game_time_countdown, MIN_SLEEP_TIME)

        if context.game_time_countdown < MIN_SLEEP_TIME:
            logger.info(
                "Not all pre-game messages sent, but game starts in %s seconds - sleeping for minimum %s seconds to avoid API spam.",
                int(context.game_time_countdown),
                MIN_SLEEP_TIME
            )
        else:
            logger.info(
                "Preview sleep time is greater than game countdown - sleeping until game time (~%s seconds).",
                int(context.game_time_countdown)
            )

        time.sleep(actual_sleep_time)
        return

    # Scenario 4: FALLBACK - Not all pre-game messages sent and we have time
    logger.info(
        "Not all pre-game messages are sent, sleeping for %s minutes & will try again.",
        preview_sleep_mins
    )
    time.sleep(preview_sleep_time)


def format_future_game_post(game, context: GameContext):
    """
    Format a social media post for a future game preview.
    """
    away_team = f"{game['awayTeam']['placeName']['default']} {game['awayTeam']['commonName']['default']}"
    home_team = f"{game['homeTeam']['placeName']['default']} {game['homeTeam']['commonName']['default']}"
    venue = game["venue"]["default"]
    start_time_utc = game["startTimeUTC"]
    broadcasts = game.get("tvBroadcasts", [])

    # Convert game time to Eastern Time
    game_time_local = convert_utc_to_localteam(start_time_utc, context.preferred_team.timezone)

    # Generate clock emoji
    clock = clock_emoji(game_time_local)

    # Categorize broadcasts
    local_broadcasts, national_broadcasts = categorize_broadcasts(broadcasts)

    # Generate the message
    broadcast_info = ", ".join(local_broadcasts + national_broadcasts)
    post = (
        f"Tune in {context.game_time_of_day} when the {home_team} take on the {away_team} at {venue}.\n\n"
        f"{clock} {game_time_local}\n"
        f"📺 {broadcast_info}\n"
        f"#️⃣ {context.preferred_team.hashtag} | {context.game_hashtag}"
    )

    return post


def calculate_season_series(
    schedule, preferred_team_abbreviation, opposing_team_abbreviation, season_id, last_season=False
):
    """
    Calculate the season series record between the preferred team and the opposing team.

    Args:
        schedule (dict): The full schedule data from the API.
        preferred_team_abbreviation (str): The abbreviation of the preferred team.
        opposing_team_abbreviation (str): The abbreviation of the opposing team.
        season_id (str): The current season ID.

    Returns:
        str: A formatted season series record string.
    """
    season_id = str(season_id)
    preferred_record = {"wins": 0, "losses": 0, "ot": 0}
    team_games = []

    for game in schedule.get("games", []):
        # Skip games that haven't been played yet
        if game["gameState"] in ["FUT", "PREVIEW"]:
            continue

        # Check if the opposing team matches either home or away
        home_team = game["homeTeam"]["abbrev"]
        away_team = game["awayTeam"]["abbrev"]
        if opposing_team_abbreviation not in [home_team, away_team]:
            continue

        # Add the game to the team_games list
        team_games.append(game)

        # Determine if the preferred team is home or away
        if home_team == preferred_team_abbreviation:
            preferred_score = game["homeTeam"]["score"]
            opposing_score = game["awayTeam"]["score"]
        elif away_team == preferred_team_abbreviation:
            preferred_score = game["awayTeam"]["score"]
            opposing_score = game["homeTeam"]["score"]
        else:
            continue

        # Determine if the game went to overtime
        extra_time = game["gameOutcome"]["lastPeriodType"] != "REG"

        # Update record based on scores
        if preferred_score > opposing_score:
            preferred_record["wins"] += 1
        elif preferred_score < opposing_score:
            if extra_time:
                preferred_record["ot"] += 1  # OT loss
            else:
                preferred_record["losses"] += 1

    # Check if no games were found and fallback to last season
    if len(team_games) == 0:
        last_season_id = str(int(season_id[:4]) - 1) + str(int(season_id[4:]) - 1)
        logger.info(f"No games found for the current season. Checking last season: {last_season_id}.")
        last_season_schedule = fetch_schedule(preferred_team_abbreviation, last_season_id)
        return calculate_season_series(
            last_season_schedule,
            preferred_team_abbreviation,
            opposing_team_abbreviation,
            last_season_id,
            last_season=True,
        )

    # Format the record string
    record_str = f"{preferred_record['wins']}-{preferred_record['losses']}-{preferred_record['ot']}"
    logger.info(
        f"Calculated season series record for {preferred_team_abbreviation} vs {opposing_team_abbreviation}: {record_str}"
    )

    # Calculate last season flag on return
    return record_str, last_season


def format_season_series_post(
    schedule, preferred_team_abbreviation, opposing_team_abbreviation, context: GameContext
):
    """
    Format a social media post with the season series record.

    Args:
        schedule (dict): The full schedule data from the API.
        preferred_team_abbreviation (str): The abbreviation of the preferred team.
        opposing_team_abbreviation (str): The abbreviation of the opposing team.

    Returns:
        str: A formatted post with the season series record.
    """
    season_id = context.season_id
    record, last_season = calculate_season_series(
        schedule, preferred_team_abbreviation, opposing_team_abbreviation, season_id
    )

    if last_season:
        return (
            f"This is the first meeting of the season between the two teams. "
            f"Last season the {context.preferred_team.full_name} were {record} "
            f"against the {context.other_team.full_name}.\n\n"
            f"{context.preferred_team.hashtag} | {context.game_hashtag}"
        )
    else:
        return (
            f"This season, the {context.preferred_team.full_name} are {record} "
            f"against the {context.other_team.full_name}.\n\n"
            f"{context.preferred_team.hashtag} | {context.game_hashtag}"
        )


def generate_referees_post(context: GameContext):
    """
    Generate a social media post highlighting the referees for the game.
    """
    logger.info("Attempting to fetch officials from NHL Gamecenter site now to generate preview post.")

    right_rail = schedule.fetch_rightrail(context.game_id)
    game_info = right_rail["gameInfo"]
    referees = game_info.get("referees")
    linesmen = game_info.get("linesmen")

    if referees and linesmen:
        r_string = "\n".join([f"R: {r['default']}" for r in referees])
        l_string = "\n".join([f"R: {l['default']}" for l in linesmen])
        officials_string = (
            f"The officials for {context.game_time_of_day}'s game are:\n\n{r_string}\n{l_string}"
        )
        return officials_string

    return None


def generate_goalies_post(game):
    """
    Generate a social media post previewing the starting goalies.
    """
    # Implement goalie data logic
    pass


def generate_team_stats_chart(context):
    pass
