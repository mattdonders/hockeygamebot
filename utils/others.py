import logging
from datetime import datetime, timezone

import pytz
from utils.team_details import TEAM_DETAILS


from pytz import timezone as pytz_timezone


def setup_logging(config, console=False, debug=False):
    """
    Sets up the logging configuration based on provided settings.

    Args:
        config (dict): The configuration dictionary containing script settings.
        console (bool): If True, log to console instead of a file.
        debug (bool): If True, set the logging level to DEBUG; otherwise, INFO.
    """
    log_file_name = config["script"]["log_file_name"] + "-" + datetime.now().strftime("%Y%m%d%H%M%S") + ".log"
    logger_level = logging.DEBUG if debug else logging.INFO

    # Configure logging
    logging.basicConfig(
        level=logger_level,
        datefmt="%Y-%m-%d %H:%M:%S",
        # format="%(asctime)s - %(levelname)s - %(message)s",
        format="%(asctime)s - %(module)s.%(funcName)s (%(lineno)d) - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler() if console else logging.FileHandler(log_file_name)],
    )
    logging.info("Logging initialized.")
    if console:
        logging.info("Logging to console.")
    else:
        logging.info(f"Logging to file: {log_file_name}")


def log_startup_info(args, config):
    """
    Log startup information, including arguments and configuration details.

    Args:
        args (Namespace): The parsed arguments.
        config (dict): The configuration dictionary.
    """
    logging.info("#" * 80)
    logging.info("New instance of the Hockey Game Bot started.")
    logging.info("TIME: %s", datetime.now())
    logging.info("Startup Parameters:")

    # Log all argument values dynamically
    for arg, value in vars(args).items():
        logging.info(f"  ARG - {arg}: {value}")

    # Log social media flags
    logging.info("Social Media Configurations:")
    socials_config = config.get("socials", {})
    for platform, enabled in socials_config.items():
        logging.info(f"  SOCIAL - {platform}: {enabled}")

    logging.info("#" * 80)


def ordinal(n):
    """
    Convert an integer to its ordinal representation.
    E.g., 1 -> '1st', 2 -> '2nd', etc.
    """
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    if n % 10 == 1:
        return f"{n}st"
    if n % 10 == 2:
        return f"{n}nd"
    if n % 10 == 3:
        return f"{n}rd"
    return f"{n}th"


def get_player_name(player_id, roster):
    """
    Retrieve a player's name using their ID from the roster.
    """
    # return roster.get(player_id, "Unknown Player")
    return roster.get(player_id)


def convert_utc_to_eastern(utc_time):
    """
    Convert a UTC time string to Eastern Time.
    """
    utc = datetime.strptime(utc_time, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    eastern = utc.astimezone(pytz_timezone("US/Eastern"))
    return eastern.strftime("%I:%M %p")  # Format as 12-hour time with AM/PM


def convert_utc_to_localteam(utc_time_str, team_abbreviation):
    """
    Convert a UTC time string to the local time zone of the specified team.

    Args:
        utc_time_str (str): Time in UTC, e.g., "2024-11-20T19:30:00Z".
        team_abbreviation (str): The team's abbreviation, e.g., "NJD".

    Returns:
        str: Local time formatted as "HH:MM AM/PM".
    """
    # Get the team's time zone from TEAM_DETAILS
    team_timezone = pytz.timezone(TEAM_DETAILS[team_abbreviation]["timezone"])

    # Parse the UTC time string
    utc_time = datetime.strptime(utc_time_str, "%Y-%m-%dT%H:%M:%SZ")
    utc_time = pytz.utc.localize(utc_time)

    # Convert to the team's local time
    local_time = utc_time.astimezone(team_timezone)

    # Format the local time as "HH:MM AM/PM"
    return local_time.strftime("%I:%M %p")


def categorize_broadcasts(broadcasts):
    """
    Categorize broadcasts into local and national based on the market code.
    Local: Market Code = 'H' (Home) or 'A' (Away)
    National: All others
    """
    local_broadcasts = []
    national_broadcasts = []

    for broadcast in broadcasts:
        if broadcast["market"] in ["H", "A"]:
            local_broadcasts.append(broadcast["network"])
        else:
            national_broadcasts.append(broadcast["network"])

    return local_broadcasts, national_broadcasts


def clock_emoji(time):
    """
    Accepts a time in 12-hour or 24-hour format with minutes (:00 or :30)
    and returns the corresponding clock emoji.

    Args:
        time: Time in the format 'HH:MM' (12-hour or 24-hour format)

    Returns:
        str: Clock emoji.
    """

    # Remove AM/PM if present
    time = time.split(" ")[0]

    # Dictionary mapping hour-minute tuples to their respective clock emojis
    # fmt: off
    clock_emojis = {
        (0, 0): "🕛", (0, 30): "🕧",
        (1, 0): "🕐", (1, 30): "🕜",
        (2, 0): "🕑", (2, 30): "🕝",
        (3, 0): "🕒", (3, 30): "🕞",
        (4, 0): "🕓", (4, 30): "🕟",
        (5, 0): "🕔", (5, 30): "🕠",
        (6, 0): "🕕", (6, 30): "🕡",
        (7, 0): "🕖", (7, 30): "🕢",
        (8, 0): "🕗", (8, 30): "🕣",
        (9, 0): "🕘", (9, 30): "🕤",
        (10, 0): "🕙", (10, 30): "🕥",
        (11, 0): "🕚", (11, 30): "🕦",
    }
    # fmt: on

    # Extract hour and minutes from time, adjusting for 24-hour format
    hour, minutes = map(int, time.split(":"))
    hour %= 12  # Convert to 12-hour format if it's in 24-hour format

    return clock_emojis.get((hour, minutes), "🕛")  # Default to 🕛 if time is invalid
