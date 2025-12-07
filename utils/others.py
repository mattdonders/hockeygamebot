import logging
import os
from datetime import datetime, timezone

import pytz
from pytz import timezone as pytz_timezone

from definitions import LOGS_DIR

logger = logging.getLogger(__name__)


class ColoredFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[38;5;244m",  # gray
        "INFO": "\033[38;5;120m",  # soft mint green
        "WARNING": "\033[38;5;221m",  # warm yellow
        "ERROR": "\033[38;5;196m",  # bright red
        "CRITICAL": "\033[1;38;5;196;48;5;232m",  # bold bright red on dark bg
    }
    RESET = "\033[0m"

    def format(self, record):
        level = record.levelname
        if level in self.COLORS:
            record.levelname = f"{self.COLORS[level]}{level}{self.RESET}"
        return super().format(record)


def setup_logging(config, console=False, debug=False):
    """
    Sets up the logging configuration based on provided settings.

    Args:
        config (dict): The configuration dictionary containing script settings.
        console (bool): If True, log to console instead of a file.
        debug (bool): If True, set the logging level to DEBUG; otherwise, INFO.
    """
    # Generate log file name
    log_file_name_base = config["script"]["log_file_name"]
    log_file_name_time = datetime.now().strftime("%Y%m%d%H%M%S")
    log_file_name_full = f"{log_file_name_base}-{log_file_name_time}.log"
    log_file_path = os.path.join(LOGS_DIR, log_file_name_full)

    # Ensure the logs directory exists
    os.makedirs(LOGS_DIR, exist_ok=True)

    # Define logger level
    logger_level = logging.DEBUG if debug else logging.INFO

    # Define logging format
    log_format = "%(asctime)s [%(name)s.%(funcName)s:%(lineno)d] %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Configure logging handlers
    handlers = []

    if console:
        handler = logging.StreamHandler()
        handler.setFormatter(ColoredFormatter(log_format, datefmt=date_format))
        handlers.append(handler)
    else:
        handler = logging.FileHandler(log_file_path)
        handler.setFormatter(logging.Formatter(log_format, date_format))
        handlers.append(handler)

    # Set up the logging configuration
    logging.basicConfig(
        level=logger_level,
        format=log_format,
        datefmt=date_format,
        handlers=handlers,
    )

    # Log initialization messages
    logger.info("Logging initialized.")
    if console:
        logger.info("Logging to console.")
    else:
        logger.info(f"Logging to file: {log_file_path}")


def log_startup_info(args, config):
    """
    Log startup information, including arguments and configuration details.

    Args:
        args (Namespace): The parsed arguments.
        config (dict): The configuration dictionary.
    """
    logger.info("#" * 80)
    logger.info("New instance of the Hockey Game Bot started.")
    logger.info("TIME: %s", datetime.now())
    logger.info("Startup Parameters:")

    # Log all argument values dynamically
    for arg, value in vars(args).items():
        logger.info(f"  ARG - {arg}: {value}")

    # Log social media flags
    logger.info("Social Media Configurations:")
    socials_config = config.get("socials", {})
    for platform, enabled in socials_config.items():
        logger.info(f"  SOCIAL - {platform}: {enabled}")

    logger.info("#" * 80)


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


def convert_utc_to_localteam(utc_time_str, team_timezone):
    """
    Convert a UTC time string to the local time zone of the specified team.

    Args:
        utc_time_str (str): Time in UTC, e.g., "2024-11-20T19:30:00Z".
        team_abbreviation (str): The team's abbreviation, e.g., "NJD".

    Returns:
        str: Local time formatted as "HH:MM AM/PM".
    """
    # Convert to the team's local time
    local_time = convert_utc_to_localteam_dt(utc_time_str, team_timezone)

    # Format the local time as "HH:MM AM/PM"
    return local_time.strftime("%I:%M %p")


def convert_utc_to_localteam_dt(utc_time_str, team_timezone):
    """
    Convert a UTC time string to the local time zone of the specified team.

    Args:
        utc_time_str (str): Time in UTC, e.g., "2024-11-20T19:30:00Z".
        team_abbreviation (str): The team's abbreviation, e.g., "NJD".

    Returns:
        str: Local time formatted as "HH:MM AM/PM".
    """

    # Parse the UTC time string
    utc_time = datetime.strptime(utc_time_str, "%Y-%m-%dT%H:%M:%SZ")
    utc_time = pytz.utc.localize(utc_time)

    # Convert to the team's local time
    local_time = utc_time.astimezone(pytz.timezone(team_timezone))

    # Format the local time as "HH:MM AM/PM"
    return local_time


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


def replace_ids_with_names(details, roster):
    """
    Replace fields ending with 'Id' in the details dictionary with their corresponding 'Name' fields,
    excluding fields ending in 'TeamId'.
    """
    for key, value in list(details.items()):  # Use list() to avoid runtime modification issues
        if key.endswith("Id") and not key.endswith("TeamId") and isinstance(value, int):
            player_name = roster.get(value, "Unknown Player")
            details[key.replace("Id", "Name")] = player_name
    return details


def hex_to_rgb(hex_color):
    """
    Convert HEX color to RGB.

    Args:
        hex_color (str): Color in HEX format, e.g., "#FF0000".

    Returns:
        tuple: RGB color as a tuple of three integers, e.g., (255, 0, 0).
    """
    hex_color = hex_color.lstrip("#")  # Remove the '#' character
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def safe_remove(item, collection):
    """Safely remove an item from a collection, if it exists."""
    if item in collection:
        collection.remove(item)


def normalize_venue_name(name: str | None) -> str | None:
    """
    Prevents Twitter/X from auto-linking domain-like substrings in venue names
    by replacing all periods with a Unicode dot (U+2024).

    This is safe because we only ever call this on NHL venue names, which
    don't use '.' for anything meaningful except sponsor domains
    (e.g., 'Crypto.com Arena').
    """
    if not name:
        return name

    return name.replace(".", "\u2024")
