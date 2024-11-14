import logging
import logging.config
import os
from datetime import datetime
from paths import LOGS_PATH
from utils import arguments


def setup_logging(config, args):
    """Configures application logging and prints the first three log lines."""
    # pylint: disable=line-too-long
    # logger = logging.getLogger(__name__)

    # Create logs directory if not present
    if not os.path.exists(LOGS_PATH):
        os.makedirs(LOGS_PATH)

    # Reset root handler to default so BasicConfig is respected
    root = logging.getLogger()
    if root.handlers:
        for handler in root.handlers:
            root.removeHandler(handler)

    log_file_name = config["script"]["log_file_name"] + "-" + datetime.now().strftime("%Y%m%d%H%M%S") + ".log"
    log_file = os.path.join(LOGS_PATH, log_file_name)

    # Determine the logging level
    logger_level = logging.DEBUG if args.debug else logging.INFO

    # Create logging configuration dictionary
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,  # Preserve existing loggers
        "formatters": {
            "standard": {
                "format": "%(asctime)s - %(module)s.%(funcName)s (%(lineno)d) - %(levelname)s - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "level": logger_level,
                "class": "logging.StreamHandler",
                "formatter": "standard",
            },
        },
        "loggers": {
            "": {  # Root logger
                "handlers": ["console"],
                "level": logger_level,
                "propagate": True,
            },
        },
    }

    # If not console output, add file handler
    if not args.console:
        logging_config["handlers"]["file"] = {
            "level": logger_level,
            "class": "logging.FileHandler",
            "formatter": "standard",
            "filename": log_file,
            "mode": "a",
        }
        logging_config["loggers"][""]["handlers"] = ["file"]

    # Configure logging
    logging.config.dictConfig(logging_config)


def clock_emoji(time):
    """
    Accepts a time in 12-hour or 24-hour format with minutes (:00 or :30)
    and returns the corresponding clock emoji.

    Args:
        time: Time in the format 'HH:MM' (12-hour or 24-hour format)

    Returns:
        str: Clock emoji.
    """

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
