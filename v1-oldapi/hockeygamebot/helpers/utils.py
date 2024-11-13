"""
This module contains all utility functions such as
log management & other miscellaneous.
"""

import functools
import logging
import math
import os
import shutil
import time
from datetime import datetime, timezone

import dateutil.parser
import requests
import yaml

from hockeygamebot.definitions import CONFIG_PATH, IMAGES_PATH, LOGS_PATH, URLS_PATH
from hockeygamebot.helpers import arguments
from hockeygamebot.models.gametype import GameType


# Social Media Decorator
def check_social_timeout(func):
    """A function decorate used within the GameEvent module to determine
    if we should send this event to social media. This can only wrap
    functions that have an attribute of a GameEvent.

    """

    @functools.wraps(func)
    def wrapper_social_timeout(*args, **kwargs):
        parsed_args = arguments.get_arguments()
        config = load_config()

        # If notweets is specified, always run the social methods
        if parsed_args.notweets:
            return func(*args, **kwargs)

        # Check for a force-send flag & if not False, force the message through
        if kwargs.get("force_send"):
            return func(*args, **kwargs)

        try:
            event = kwargs.get("event")
            event_time = dateutil.parser.parse(event.date_time)
            timeout = config["script"]["event_timeout"]
            utcnow = datetime.now(timezone.utc)
            time_since_event = (utcnow - event_time).total_seconds()
            if time_since_event < timeout:
                return func(*args, **kwargs)
            else:
                logging.info(
                    "Event #%s (%s) occurred %s second(s) in the past - older than our social timeout.",
                    event.event_idx,
                    event.event_type,
                    time_since_event,
                )
                # return False
                return {"twitter": None, "discord": None, "slack": None}
        except Exception as e:
            logging.warning("Timeout function should contain an event key:value. %s", e)
            return func(*args, **kwargs)

    return wrapper_social_timeout


def load_config():
    """Loads the configuration yaml file and returns a yaml object / dictionary..

    Args:
        None

    Returns:
        A yaml (dictionary) object.
    """

    with open(CONFIG_PATH) as ymlfile:
        config = yaml.load(ymlfile, Loader=yaml.FullLoader)

    return config


def load_urls():
    """Loads the URLs yaml file and returns a yaml object / dictionary..

    Args:
        None

    Returns:
        A yaml (dictionary) object.
    """

    with open(URLS_PATH) as ymlfile:
        urls = yaml.load(ymlfile, Loader=yaml.FullLoader)

    return urls


def setup_logging():
    """Configures application logging and prints the first three log lines."""
    # pylint: disable=line-too-long
    # logger = logging.getLogger(__name__)

    # Create logs directory if not present
    if not os.path.exists(LOGS_PATH):
        os.makedirs(LOGS_PATH)

    args = arguments.get_arguments()

    # Reset root handler to default so BasicConfig is respected
    root = logging.getLogger()
    if root.handlers:
        for handler in root.handlers:
            root.removeHandler(handler)

    log_file_name = datetime.now().strftime(load_config()["script"]["log_file_name"] + "-%Y%m%d%H%M%S.log")
    log_file = os.path.join(LOGS_PATH, log_file_name)
    if args.console and args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            datefmt="%Y-%m-%d %H:%M:%S",
            format="%(asctime)s - %(module)s.%(funcName)s (%(lineno)d) - %(levelname)s - %(message)s",
        )

    elif args.console:
        logging.basicConfig(
            level=logging.INFO,
            datefmt="%Y-%m-%d %H:%M:%S",
            format="%(asctime)s - %(module)s.%(funcName)s (%(lineno)d) - %(levelname)s - %(message)s",
        )
    else:
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            datefmt="%Y-%m-%d %H:%M:%S",
            format="%(asctime)s - %(module)s.%(funcName)s (%(lineno)d) - %(levelname)s - %(message)s",
        )

    # Reset logging level (outside of Basic Config)
    logger = logging.getLogger()
    logger_level = logging.DEBUG if args.debug else logging.INFO
    logger.setLevel(logger_level)


def ordinal(n):
    """Converts an integer into its ordinal equivalent.

    Args:
        n: number to convert

    Returns:
        nth: ordinal respresentation of passed integer
    """
    nth = "%d%s" % (n, "tsnrhtdd"[(n // 10 % 10 != 1) * (n % 10 < 4) * n % 10 :: 4])
    return nth


def date_parser(date):
    """Converts a string in Y-m-d format to datetime object.

    Args:
        date: a string in Y-m-d format

    Returns:
        date_dt: the passed in date as a datetime object
    """

    try:
        date_dt = datetime.strptime(date, "%Y-%m-%d")
        return date_dt
    except ValueError as e:
        logging.error("Invalid override date - exiting.")
        logging.error(e)
        raise e


def clock_emoji(time):
    """
    Accepts an hour (in 12 or 24 hour format) and returns the correct clock emoji.

    Args:
        time: 12 or 24 hour format time (:00 or :30)

    Returns:
        clock: corresponding clock emoji.
    """

    hour_emojis = {
        "0": "🕛",
        "1": "🕐",
        "2": "🕑",
        "3": "🕒",
        "4": "🕓",
        "5": "🕔",
        "6": "🕕",
        "7": "🕖",
        "8": "🕗",
        "9": "🕘",
        "10": "🕙",
        "11": "🕚",
    }

    half_emojis = {
        "0": "🕧",
        "1": "🕜",
        "2": "🕝",
        "3": "🕞",
        "4": "🕟",
        "5": "🕠",
        "6": "🕡",
        "7": "🕢",
        "8": "🕣",
        "9": "🕤",
        "10": "🕥",
        "11": "🕦",
    }

    # Split up the time to get the hours & minutes sections
    time_split = time.split(":")
    hour = int(time_split[0])
    minutes = time_split[1].split(" ")[0]

    # We need to adjust the hour if we use 24 hour-time.
    hour = 12 - hour if hour > 11 else hour
    clock = half_emojis[str(hour)] if int(minutes) == 30 else hour_emojis[str(hour)]
    return clock


def team_hashtag(team, game_type=None):
    """Generates a team hashtag from a team name & game type.

    UPDATED: 2019-09-30 (NHL Updated Hashtags)

    Args:
        team: full team name
        game_type: Game type text

    Returns:
        hashtag: team specific hashtag
    """

    team_hashtags = {
        "Anaheim Ducks": "#FlyTogether",
        "Arizona Coyotes": "#Yotes",
        "Boston Bruins": "#NHLBruins",
        "Buffalo Sabres": "#LetsGoBuffalo",
        "Calgary Flames": "#Flames",
        "Carolina Hurricanes": "#LetsGoCanes",
        "Chicago Blackhawks": "#Blackhawks",
        "Colorado Avalanche": "#GoAvsGo",
        "Columbus Blue Jackets": "#CBJ",
        "Dallas Stars": "#GoStars",
        "Detroit Red Wings": "#LGRW",
        "Edmonton Oilers": "#LetsGoOilers",
        "Florida Panthers": "#FLAPanthers",
        "Los Angeles Kings": "#GoKingsGo",
        "Minnesota Wild": "#MNWild",
        "Montréal Canadiens": "#GoHabsGo",
        "Montreal Canadiens": "#GoHabsGo",
        "Nashville Predators": "#Preds",
        "New Jersey Devils": "#NJDevils",
        "New York Islanders": "#Isles",
        "New York Rangers": "#NYR",
        "Ottawa Senators": "#GoSensGo",
        "Philadelphia Flyers": "#AnytimeAnywhere",
        "Pittsburgh Penguins": "#LetsGoPens",
        "San Jose Sharks": "#SJSharks",
        "Seattle Kraken": "#SeaKraken",
        "St. Louis Blues": "#STLBlues",
        "Tampa Bay Lightning": "#GoBolts",
        "Toronto Maple Leafs": "#LeafsForever",
        "Vancouver Canucks": "#Canucks",
        "Vegas Golden Knights": "#VegasBorn",
        "Washington Capitals": "#ALLCAPS",
        "Winnipeg Jets": "#GoJetsGo",
    }

    team_hashtags_playoffs = {
        "Anaheim Ducks": "#FlyTogether",
        "Arizona Coyotes": "#Yotes",
        "Boston Bruins": "#NHLBruins",
        "Buffalo Sabres": "#LetsGoBuffalo",
        "Calgary Flames": "#Flames",
        "Carolina Hurricanes": "#LetsGoCanes",
        "Chicago Blackhawks": "#Blackhawks",
        "Colorado Avalanche": "#GoAvsGo",
        "Columbus Blue Jackets": "#CBJ",
        "Dallas Stars": "#GoStars",
        "Detroit Red Wings": "#LGRW",
        "Edmonton Oilers": "#LetsGoOilers",
        "Florida Panthers": "#FLAPanthers",
        "Los Angeles Kings": "#GoKingsGo",
        "Minnesota Wild": "#MNWild",
        "Montréal Canadiens": "#GoHabsGo",
        "Montreal Canadiens": "#GoHabsGo",
        "Nashville Predators": "#Preds",
        "New Jersey Devils": "#NJDevils",
        "New York Islanders": "#Isles",
        "New York Rangers": "#PlayLikeANewYorker",
        "Ottawa Senators": "#GoSensGo",
        "Philadelphia Flyers": "#AnytimeAnywhere",
        "Pittsburgh Penguins": "#LetsGoPens",
        "San Jose Sharks": "#SJSharks",
        "St. Louis Blues": "#STLBlues",
        "Tampa Bay Lightning": "#GoBolts",
        "Toronto Maple Leafs": "#LeafsForever",
        "Vancouver Canucks": "#Canucks",
        "Vegas Golden Knights": "#VegasBorn",
        "Washington Capitals": "#ALLCAPS",
        "Winnipeg Jets": "#GoJetsGo",
    }

    # if GameType(game_type) == GameType.PLAYOFFS:
    #     return team_hashtags_playoffs[team]
    # else:
    #     return team_hashtags[team]

    return team_hashtags.get(team)


def calculate_shot_distance(x: int, y: int) -> str:
    """Takes a (x,y) shot coordinate and calculates the distance to the net.

    Args:
        x: x-coordinate of the shot
        y: y-coordiante of the shot

    Returns:
        shot_text: shot distance with unit
    """

    x = abs(x)

    shot_dist = math.ceil(math.hypot(x - 89, y))
    shot_unit = "foot" if shot_dist == 1 else "feet"
    shot_text = f"{shot_dist} {shot_unit}"
    return shot_text


def determine_event_zone(x: int, y: int, period: int, homeaway: str) -> str:
    # Neutral Zone is 50 feet wide (from -25 to 25)
    if abs(x) < 25:
        return ("N", "neutral")

    # Even numbered periods, need their coordinates flipped
    x = x * -1 if period % 2 == 0 else x
    y = y * -1 if period % 2 == 0 else y

    if homeaway == "away":
        zone = ("O", "offensive") if x > 25 else ("D", "defensive")
    elif homeaway == "home":
        zone = ("O", "offensive") if x < -25 else ("D", "defensive")
    else:
        zone = (None, None)

    return zone


def time_remain_converter(time: str) -> str:
    """Takes a time remaining string and determines if its less than 1 minute.

    Args:
        time: time remaining in the period

    Returns:
        time_new: possibly modified time string
    """
    try:
        minutes = time.split(":")[0]
        seconds = time.split(":")[1]

        time_new = f"{seconds} seconds" if minutes == "00" else time
        return time_new
    except Exception as e:
        logging.warning("The value %s cannot be converted to seconds. %s", time, e)
        return "0 seconds"


# def localdata_simulator(directory, game, sleep):
#     """ Takes a directory of json livefeed files & simulates a live game.

#     Args:
#         directory: directory of live feed json files
#         game: current game object
#         sleep: time in seconds to sleep between each parsing event

#     Returns:
#         data: livefeed response (similar to API response)
#     """

#     for file in os.listdir(directory):
#         filename = os.fsdecode(file)
#         if filename.endswith(".json"):
#             feed_json = os.path.join(directory, filename)
#             with open(feed_json) as json_file:
#                 data = json.load(json_file)
#             live.live_loop(livefeed=data, game=game)
#             game.update_game(data)
#             time.sleep(sleep)


def from_mmss(time_input):
    """ Converts a timestamp in MM:SS format to an integer for comparison. """
    try:
        m, s = time_input.split(":")
        output = int(m) * 60 + int(s)
        return output
    except Exception as e:
        logging.warning("The value %s cannot be converted to seconds. %s", time_input, e)
        return 0


def to_mmss(time_input):
    """ Converts a time based integer (in seconds) to MM:SS format. """
    return time.strftime("%M:%S", time.gmtime(time_input))


def download_file(url):
    """ Downloads a remote file to the IMAGES_PATH/temp directory. """
    local_filename = url.split("/")[-1]
    local_path = os.path.join(IMAGES_PATH, "temp", local_filename)

    logging.info("Downloading file & storing into filename - %s.", local_filename)
    with requests.get(url, stream=True) as r:
        with open(local_path, "wb") as f:
            shutil.copyfileobj(r.raw, f)

    return local_path


def empty_images_temp():
    """ Empties the temporary image directory after the bot is done running."""
    temp_path = os.path.join(IMAGES_PATH, "temp")
    temp_images = os.listdir(temp_path)
    logging.info("Emptying the TEMP images directory - %s.", temp_path)

    for item in temp_images:
        if item.endswith(".png"):
            os.remove(os.path.join(temp_path, item))

        if item.endswith(".mp4"):
            os.remove(os.path.join(temp_path, item))
