"""
Functions that create images or non-NST charts (via Matplotlib).
"""

import logging
import os
from enum import Enum

import matplotlib.pyplot as plt
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from hockeygamebot.definitions import IMAGES_PATH, PROJECT_ROOT
from hockeygamebot.helpers import arguments, utils
from hockeygamebot.models.game import Game
from hockeygamebot.models.gameevent import GoalEvent
from hockeygamebot.nhlapi import schedule, thirdparty
from hockeygamebot.models.gametype import GameType


class Backgrounds:
    """Paths to background images & files used in the imaging module."""

    PREGAME = os.path.join(IMAGES_PATH, "BG2019-Gameday-Pregame.png")
    STATS = os.path.join(IMAGES_PATH, "BG2019-Gameday-ScoreReport.png")


class Colors:
    """Specifies commonly used colors."""

    WHITE = (255, 255, 255)
    GRAY = (128, 128, 128)
    BLACK = (0, 0, 0)


class FontFiles:
    """Paths to font files used in the imaging module."""

    BITTER_REGULAR = os.path.join(PROJECT_ROOT, "resources/fonts/Bitter-Regular.ttf")
    BITTER_BOLD = os.path.join(PROJECT_ROOT, "resources/fonts/Bitter-Bold.ttf")


class FontSizes:
    """Font sizes used in the imaging module."""

    TITLE = 80
    DETAIL_LARGE = 56
    DETAIL_SMALL = 50
    RECORD = 38
    STREAK = 30
    GAMENUMBER = 40
    PRESEASON = 28
    STAT_TITLE = 19
    STAT_VALUE = 25
    SCORE = 75
    GOAL_SCORER = 14
    ASST_SCORER = 14
    NO_GOAL_TEXT = 30

    GS_VALUES = 20
    GS_TABLE_HEADERS = 20


class Constants:
    """Constant chart-based values."""

    SIMILAR_THRESHOLD = 6
    CHART_START_X = 35
    CHART_WIDTH = 690
    # CHART_END_X = 725
    CHART_END_X = CHART_START_X + CHART_WIDTH
    CHART_GOAL_SEPARATOR = 40

    GOALBOX_START_X = CHART_END_X + CHART_GOAL_SEPARATOR
    GOALBOX_START_Y = 200
    GOALBOX_TEAM_H = 25
    GOALBOX_W = 400
    GOALBOX_H = 220
    GOALBOX_SEPARATOR = 15


class StatTypes(Enum):
    """Stat types used in our stat-bar image type."""

    SHOTS = 0
    BLOCKED_SHOTS = 1
    HITS = 2
    POWER_PLAYS = 3
    PENALTY_MINS = 4
    FACEOFF_PCT = 5


def luminance(pixel):
    """Calculates the luminance of an (R,G,B) color."""
    return 0.299 * pixel[0] + 0.587 * pixel[1] + 0.114 * pixel[2]


def is_similar(pixel_a, pixel_b, threshold):
    """Takes two (R, G, B) colors and determines if they are similar."""
    difference = abs(luminance(pixel_a) - luminance(pixel_b))
    return difference < threshold


def both_team_colors_compared(first_team_name, second_team_name, threshold=None):
    """Takes two team names and determins if the colors are the same or similar.
        Retruns a dictionary of pref_team & other_team colors.

    Args:
        pref_team_name: Preferred Team Name
        other_team_name: Other Team Name

    Returns:
        colors_dict: Dictionary of final team colors
    """
    first_colors = team_colors(first_team_name)
    second_colors = team_colors(second_team_name)

    first_primary_bg = first_colors["primary"]["bg"]
    second_primary_bg = second_colors["primary"]["bg"]

    # Check if the primary team colors are the same or similar
    threshold = threshold if threshold else Constants.SIMILAR_THRESHOLD
    similar_colors = is_similar(first_primary_bg, second_primary_bg, threshold)

    # Build the returning dictionary
    colors_dict = {"first": first_colors["primary"]}
    colors_dict["second"] = second_colors["secondary"] if similar_colors else second_colors["primary"]
    return colors_dict


def team_colors(team_name):
    """Accepts a team name and returns the background color & text color.

    Args:
        team_name: Full name of the NHL Team

    Returns:
        dict: Dictionary of primary & secondary colors
    """

    team_colors_dict = {
        "Anaheim Ducks": {
            "primary": {"bg": (252, 76, 2), "text": (255, 255, 255)},
            "secondary": {"bg": (162, 170, 173), "text": (0, 0, 0)},
        },
        "Arizona Coyotes": {
            "primary": {"bg": (134, 38, 51), "text": (255, 255, 255)},
            "secondary": {"bg": (221, 203, 164), "text": (0, 0, 0)},
        },
        "Boston Bruins": {
            "primary": {"bg": (255, 184, 28), "text": (255, 255, 255)},
            "secondary": {"bg": (0, 0, 0), "text": (255, 255, 255)},
        },
        "Buffalo Sabres": {
            "primary": {"bg": (4, 30, 66), "text": (255, 255, 255)},
            "secondary": {"bg": (162, 170, 173), "text": (0, 0, 0)},
        },
        "Calgary Flames": {
            "primary": {"bg": (200, 16, 46), "text": (255, 255, 255)},
            "secondary": {"bg": (241, 190, 72), "text": (0, 0, 0)},
        },
        "Carolina Hurricanes": {
            "primary": {"bg": (200, 16, 46), "text": (255, 255, 255)},
            "secondary": {"bg": (162, 170, 173), "text": (0, 0, 0)},
        },
        "Chicago Blackhawks": {
            "primary": {"bg": (204, 138, 0), "text": (255, 255, 255)},
            "secondary": {"bg": (255, 209, 0), "text": (0, 0, 0)},
        },
        "Colorado Avalanche": {
            "primary": {"bg": (111, 38, 61), "text": (255, 255, 255)},
            "secondary": {"bg": (35, 97, 146), "text": (0, 0, 0)},
        },
        "Columbus Blue Jackets": {
            "primary": {"bg": (4, 30, 66), "text": (255, 255, 255)},
            "secondary": {"bg": (200, 16, 46), "text": (255, 255, 255)},
        },
        "Dallas Stars": {
            "primary": {"bg": (0, 99, 65), "text": (255, 255, 255)},
            "secondary": {"bg": (138, 141, 143), "text": (0, 0, 0)},
        },
        "Detroit Red Wings": {
            "primary": {"bg": (200, 16, 46), "text": (255, 255, 255)},
            "secondary": {"bg": (0, 0, 0), "text": (255, 255, 255)},
        },
        "Edmonton Oilers": {
            "primary": {"bg": (207, 69, 32), "text": (255, 255, 255)},
            "secondary": {"bg": (0, 32, 91), "text": (0, 0, 0)},
        },
        "Florida Panthers": {
            "primary": {"bg": (4, 30, 66), "text": (255, 255, 255)},
            "secondary": {"bg": (185, 151, 91), "text": (0, 0, 0)},
        },
        "Los Angeles Kings": {
            "primary": {"bg": (162, 170, 173), "text": (255, 255, 255)},
            "secondary": {"bg": (0, 0, 0), "text": (255, 255, 255)},
        },
        "Minnesota Wild": {
            "primary": {"bg": (21, 71, 52), "text": (255, 255, 255)},
            "secondary": {"bg": (166, 25, 46), "text": (0, 0, 0)},
        },
        "Montréal Canadiens": {
            "primary": {"bg": (166, 25, 46), "text": (255, 255, 255)},
            "secondary": {"bg": (0, 30, 98), "text": (255, 255, 255)},
        },
        "Nashville Predators": {
            "primary": {"bg": (255, 184, 28), "text": (255, 255, 255)},
            "secondary": {"bg": (4, 30, 66), "text": (0, 0, 0)},
        },
        "New Jersey Devils": {
            "primary": {"bg": (200, 16, 46), "text": (255, 255, 255)},
            "secondary": {"bg": (0, 0, 0), "text": (255, 255, 255)},
        },
        "New York Islanders": {
            "primary": {"bg": (252, 76, 2), "text": (255, 255, 255)},
            "secondary": {"bg": (0, 48, 135), "text": (0, 0, 0)},
        },
        "New York Rangers": {
            "primary": {"bg": (0, 51, 160), "text": (255, 255, 255)},
            "secondary": {"bg": (200, 16, 46), "text": (0, 0, 0)},
        },
        "Ottawa Senators": {
            "primary": {"bg": (198, 146, 20), "text": (255, 255, 255)},
            "secondary": {"bg": (200, 16, 46), "text": (0, 0, 0)},
        },
        "Philadelphia Flyers": {
            "primary": {"bg": (250, 70, 22), "text": (255, 255, 255)},
            "secondary": {"bg": (0, 0, 0), "text": (255, 255, 255)},
        },
        "Pittsburgh Penguins": {
            "primary": {"bg": (255, 184, 28), "text": (255, 255, 255)},
            "secondary": {"bg": (0, 0, 0), "text": (255, 255, 255)},
        },
        "San Jose Sharks": {
            "primary": {"bg": (0, 98, 114), "text": (255, 255, 255)},
            "secondary": {"bg": (229, 114, 0), "text": (0, 0, 0)},
        },
        "Seattle Kraken": {
            "primary": {"bg": (53, 84, 100), "text": (255, 255, 255)},
            # "primary": {"bg": (153, 217, 217), "text": (0, 0, 0)},
            "secondary": {"bg": (0, 22, 40), "text": (255, 255, 255)},
        },
        "St. Louis Blues": {
            "primary": {"bg": (0, 48, 135), "text": (255, 255, 255)},
            "secondary": {"bg": (4, 30, 66), "text": (0, 0, 0)},
        },
        "Tampa Bay Lightning": {
            "primary": {"bg": (0, 32, 91), "text": (255, 255, 255)},
            "secondary": {"bg": (0, 0, 0), "text": (255, 255, 255)},
        },
        "Toronto Maple Leafs": {
            "primary": {"bg": (0, 32, 91), "text": (255, 255, 255)},
            "secondary": {"bg": (0, 0, 0), "text": (255, 255, 255)},
        },
        "Vancouver Canucks": {
            "primary": {"bg": (0, 32, 91), "text": (255, 255, 255)},
            "secondary": {"bg": (151, 153, 155), "text": (0, 0, 0)},
        },
        "Vegas Golden Knights": {
            "primary": {"bg": (180, 151, 90), "text": (255, 255, 255)},
            "secondary": {"bg": (51, 63, 66), "text": (0, 0, 0)},
        },
        "Washington Capitals": {
            "primary": {"bg": (166, 25, 46), "text": (255, 255, 255)},
            "secondary": {"bg": (4, 30, 66), "text": (255, 255, 255)},
        },
        "Winnipeg Jets": {
            "primary": {"bg": (4, 30, 66), "text": (255, 255, 255)},
            "secondary": {"bg": (200, 16, 46), "text": (0, 0, 0)},
        },
    }

    return team_colors_dict[team_name]


def rgb_to_hex(value1, value2=None, value3=None, discord=False):
    """
    Convert RGB value (as three numbers each ranges from 0 to 255) to hex format.
    """

    if isinstance(value1, (list, tuple)):
        rgb = value1
        value1 = rgb[0]
        value2 = rgb[1]
        value3 = rgb[2]

    for value in (value1, value2, value3):
        if not 0 <= value <= 255:
            raise ValueError("Value each slider must be ranges from 0 to 255")

    hex_string = "#{0:02X}{1:02X}{2:02X}".format(value1, value2, value3)
    if discord:
        hex_string = hex_string.replace("#", "")
        return int(hex_string, 16)

    return hex_string


def discord_color(team_name):
    """Takes a team name and returns a base-16 string for Discord embeds."""

    team_color = team_colors(team_name)["primary"]["bg"]
    discord_color = rgb_to_hex(team_color, discord=True)
    return discord_color


def center_text(draw, left, top, width, text, color, font, vertical=False, height=None):
    """Draws text (at least) horizontally centered in a specified width. Can also
        center vertically if specified.

    Args:
        draw: Current PIL draw Object
        left: left coordinate (x) of the bounding box
        top: top coordinate (y) of the bounding box
        width: width of the bounding box
        text: text to draw
        color: color to draw the text in
        font: ImageFont instance

        vertical: align vertically
        height: height of the box to align vertically

    Returns:
        None
    """

    # Get text size (string length & font)
    w, h = draw.textsize(text, font)
    left_new = left + ((width - w) / 2)

    if not vertical:
        coords_new = (left_new, top)
        # Draw the text with the new coordinates
        draw.text(coords_new, text, fill=color, font=font, align="center")
    else:
        _, offset_y = font.getoffset(text)
        top_new = top + ((height - h - offset_y) / 2)
        coords_new = (left_new, top_new)
        # Draw the text with the new coordinates
        draw.text(coords_new, text, fill=color, font=font, align="center")


def valign_center_text(draw, left, top, height, text, color, font):
    """Draws text centered in the vertical orientation in a specified height.

    Args:
        draw: Current PIL draw Object
        left: left coordinate (x) of the bounding box
        top: top coordinate (y) of the bounding box
        width: width of the bounding box
        text: text to draw
        color: color to draw the text in
        font: ImageFont instance

    Returns:
        None
    """

    # Get text size (string length & font)
    _, h = draw.textsize(text, font)

    # Get offset & new coordinates
    _, offset_y = font.getoffset(text)
    top_new = top + ((height - h - offset_y) / 2)
    coords_new = (left, top_new)

    # Draw the text with the new coordinates
    draw.text(coords_new, text, color, font, align="center")


def pregame_image(game: Game):
    """Generates the pre-game image that is sent to social media platforms at the first
        run of the hockeygamebot script per day.

    Args:
        game: Current Game object

    Returns:
        bg: Finished Image instance
    """

    # Fonts used within the pregame image
    FONT_TITLE = ImageFont.truetype(FontFiles.BITTER_BOLD, FontSizes.TITLE)
    FONT_RECORD = ImageFont.truetype(FontFiles.BITTER_BOLD, FontSizes.RECORD)
    FONT_STREAK = ImageFont.truetype(FontFiles.BITTER_BOLD, FontSizes.STREAK)
    FONT_DETAIL_LARGE = ImageFont.truetype(FontFiles.BITTER_BOLD, FontSizes.DETAIL_LARGE)
    FONT_DETAIL_SMALL = ImageFont.truetype(FontFiles.BITTER_BOLD, FontSizes.DETAIL_SMALL)
    FONT_GAMENUMBER = ImageFont.truetype(FontFiles.BITTER_BOLD, FontSizes.GAMENUMBER * 3)
    FONT_BOT_TAG = ImageFont.truetype(FontFiles.BITTER_BOLD, FontSizes.GAMENUMBER * 2)

    # Pre-game specific constant values (incl coordinates)
    HEADER_TEXT = "PRE-GAME MATCHUP"
    LOGO_Y = 150
    COORDS_HOME_X = 245
    COORDS_AWAY_X = 650
    COORDS_HOME_LOGO = (COORDS_HOME_X, LOGO_Y)
    COORDS_AWAY_LOGO = (COORDS_AWAY_X, LOGO_Y)
    COORDS_GAME_NUM = (-90, 80)
    COORDS_BOT_TAG = (910, 330)
    TEAM_RECORD_Y = LOGO_Y + 200
    TEAM_STREAK_Y = TEAM_RECORD_Y + FontSizes.RECORD + 10

    # Generate records, venue & other strings
    # If this is the first team, game then no streak
    if GameType(game.game_type) == GameType.PLAYOFFS:
        home_pts = ""
        home_record_str = game.home_team.playoff_series_record
        home_streak_last10 = ""

        away_pts = ""
        away_record_str = game.away_team.playoff_series_record
        away_streak_last10 = ""

        playoff_info = Game.playoff_info
        round_number = playoff_info["round"]["number"]
        game_number = playoff_info["currentGame"]["seriesSummary"]["gameNumber"]
        text_gamenumber = f"RD#{round_number} / GM#{game_number}"
    else:
        home_pts = game.home_team.points
        home_record_str = f"{home_pts} PTS • {game.home_team.current_record}"
        home_streak_last10 = (
            f"{game.home_team.streak} • LAST 10: {game.home_team.last_ten}"
            if game.home_team.games > 0
            else ""
        )

        away_pts = game.away_team.points
        away_record_str = f"{away_pts} PTS • {game.away_team.current_record}"
        away_streak_last10 = (
            f"{game.away_team.streak} • LAST 10: {game.away_team.last_ten}"
            if game.away_team.games > 0
            else ""
        )

        num_games = schedule.get_number_games(
            season=game.season, team_id=game.preferred_team.team_id, game_type_code=game.game_type
        )
        text_gamenumber = (
            "PRESEASON" if game.game_type == "PR" else f"{game.preferred_team.games + 1} OF {num_games}"
        )

    text_datetime = f"{game.game_date_short} • {game.game_time_local}"
    text_hashtags = (
        f"{utils.team_hashtag(game.preferred_team.team_name, game.game_type)} • {game.game_hashtag}"
    )

    bg = Image.open(Backgrounds.PREGAME)
    bg_w, bg_h = bg.size

    away_team = game.away_team.team_name.replace(" ", "")
    home_team = game.home_team.team_name.replace(" ", "")
    away_logo = Image.open(os.path.join(PROJECT_ROOT, f"resources/logos/{away_team}.png"))
    home_logo = Image.open(os.path.join(PROJECT_ROOT, f"resources/logos/{home_team}.png"))

    # Paste the home / away logos with the mask the same as the image
    bg.paste(away_logo, COORDS_AWAY_LOGO, away_logo)
    bg.paste(home_logo, COORDS_HOME_LOGO, home_logo)

    # Generates a 'draw' object that we use to draw on top of the image
    draw = ImageDraw.Draw(bg)

    # Draw text items on the background now
    # fmt: off
    center_text(
        draw=draw, left=0, top=0, width=bg_w, text=HEADER_TEXT, color=Colors.WHITE, font=FONT_TITLE
    )

    center_text(
        draw=draw, left=COORDS_HOME_X, top=TEAM_RECORD_Y, width=300,
        text=home_record_str, color=Colors.WHITE, font=FONT_RECORD
    )

    center_text(
        draw=draw, left=COORDS_HOME_X, top=TEAM_STREAK_Y, width=300,
        text=home_streak_last10, color=Colors.WHITE, font=FONT_STREAK
    )

    center_text(
        draw=draw, left=COORDS_AWAY_X, top=TEAM_RECORD_Y, width=300,
        text=away_record_str, color=Colors.WHITE, font=FONT_RECORD
    )

    center_text(
        draw=draw, left=COORDS_AWAY_X, top=TEAM_STREAK_Y, width=300,
        text=away_streak_last10, color=Colors.WHITE, font=FONT_STREAK
    )

    center_text(
        draw=draw, left=0, top=480, width=bg_w,
        text=text_datetime, color=Colors.WHITE, font=FONT_DETAIL_LARGE,
    )

    center_text(
        draw=draw, left=0, top=540, width=bg_w,
        text=game.venue.upper(), color=Colors.WHITE, font=FONT_DETAIL_LARGE,
    )

    center_text(
        draw=draw, left=0, top=600, width=bg_w,
        text=text_hashtags, color=Colors.WHITE, font=FONT_DETAIL_SMALL,
    )
    # fmt: on

    # Create a new image to put the game number & cleanly rotate it
    txt = Image.new("L", (900, 900))
    d = ImageDraw.Draw(txt)
    center_text(
        draw=d,
        left=0,
        top=0,
        width=900,
        text=text_gamenumber,
        color=255,
        font=FONT_GAMENUMBER,
    )
    w = txt.rotate(315, expand=True, resample=Image.BICUBIC)
    w_resize = w.resize((300, 300), Image.ANTIALIAS)
    bg.paste(w_resize, COORDS_GAME_NUM, w_resize)

    # Create a new image to put the game bot handle & cleanly rotate it
    args = arguments.get_arguments()
    twitterenv = "debug" if args.debugsocial else "prod"
    twitter_config = utils.load_config()["twitter"][twitterenv]
    twitter_handle = twitter_config["handle"]

    txt = Image.new("L", (900, 900))
    d = ImageDraw.Draw(txt)
    center_text(
        draw=d,
        left=0,
        top=0,
        width=900,
        text=f"@{twitter_handle}",
        color=255,
        font=FONT_BOT_TAG,
    )
    w = txt.rotate(315, expand=True, resample=Image.BICUBIC)
    w_resize = w.resize((300, 300), Image.ANTIALIAS)
    bg.paste(w_resize, COORDS_BOT_TAG, w_resize)

    return bg


def generate_stats_bar(draw, stat, pref_value, other_value, pref_color, other_color):
    """Used in conjunction with the stats_image function to draw the label & the actual
        value bars of each stat from the boxscore for each preferred & other teams.

    Args:
        draw: Current PIL draw Object
        stat: boxscore stat name (used for special coordinate cases)
        pref_value: value of the stat for the preferred team
        other_value: value of the stat for the other team
        pref_color: color of the value bar for the preferred team
        other_color: color of the value bar for the other team

    Returns:
        None (just draws a rectangle)
    """
    # Fonts used within the stats bar
    FONT_STAT_TITLE = ImageFont.truetype(FontFiles.BITTER_BOLD, FontSizes.STAT_TITLE)
    FONT_STAT_VALUE = ImageFont.truetype(FontFiles.BITTER_BOLD, FontSizes.STAT_VALUE)

    # Pre-game specific constant values (incl coordinates)
    STAT_TITLE_WIDTH = 240
    STAT_VALUE_SPACING = 15
    TOTAL_BAR_WIDTH = 445
    BAR_START_X = 278  # Arbitrary start number based on text label size
    BAR_END_X = 722
    CHART_START_X = 35
    CHART_START_Y = 150
    CHART_RECT_H = 55
    CHART_SEPARATOR = 35

    logging.info("Drawing stat bar for %s", stat)

    # Iterate over each possible type of passed stat
    if stat == StatTypes.SHOTS:
        stat_total = pref_value + other_value
        stat_title = f"SHOTS: {stat_total}"
    elif stat == StatTypes.BLOCKED_SHOTS:
        stat_total = pref_value + other_value
        stat_title = f"BLOCKED SHOTS: {stat_total}"
    elif stat == StatTypes.HITS:
        stat_total = pref_value + other_value
        stat_title = f"HITS: {stat_total}"
    elif stat == StatTypes.FACEOFF_PCT:
        stat_total = pref_value + other_value
        stat_title = f"FACEOFF %"
    elif stat == StatTypes.PENALTY_MINS:
        stat_total = pref_value + other_value
        stat_title = f"PENALTY MINUTES: {stat_total:.0f}"
    elif stat == StatTypes.POWER_PLAYS:
        pref_pp, pref_ppg = pref_value
        other_pp, other_ppg = other_value
        power_play_pref = f"{int(pref_ppg)} / {int(pref_pp)}"
        power_play_other = f"{int(other_ppg)} / {int(other_pp)}"
        pref_value = pref_pp
        other_value = other_pp
        stat_total = pref_pp + other_pp
        stat_title = f"POWER PLAYS: {int(stat_total)}"

    # fmt: off
    # Draws the stat label for the stat bar
    chart_top_y = CHART_START_Y + (stat.value * CHART_RECT_H) + (stat.value * CHART_SEPARATOR)
    center_text(
        draw=draw, left=CHART_START_X, top=chart_top_y, width=STAT_TITLE_WIDTH, text=stat_title,
        color=Colors.BLACK, font=FONT_STAT_TITLE, vertical=True, height=CHART_RECT_H,
    )

    # Draws the actual stat bar for both teams (proportioned correctly to the stat)
    # And also draws the stat value within the bar itself
    if stat_total == 0:
        stat_bar_pref_end_x = BAR_START_X + int(0.5 * TOTAL_BAR_WIDTH)
    else:
        stat_bar_pref_end_x = BAR_START_X + int((pref_value / stat_total) * TOTAL_BAR_WIDTH)

    draw.rectangle(
        ((BAR_START_X, chart_top_y), (stat_bar_pref_end_x, chart_top_y + CHART_RECT_H)),
        fill=pref_color['bg'], outline=(255, 255, 255), width=2
    )

    draw.rectangle(
        ((stat_bar_pref_end_x, chart_top_y), (BAR_END_X, chart_top_y + CHART_RECT_H)),
        fill=other_color['bg'], outline=(255, 255, 255), width=2
    )

    if pref_value > 0:
        # If Power Play stats are being printed, re-assign the stat value text
        pref_value = power_play_pref if stat == StatTypes.POWER_PLAYS else pref_value
        valign_center_text(
            draw=draw, left=(BAR_START_X + STAT_VALUE_SPACING), top=chart_top_y,
            height=CHART_RECT_H, text=str(pref_value), color=pref_color['text'], font=FONT_STAT_VALUE
        )

    if other_value > 0:
        # If Power Play stats are being printed, re-assign the stat value text
        other_value = power_play_other if stat == StatTypes.POWER_PLAYS else other_value
        valign_center_text(
            draw=draw, left=(stat_bar_pref_end_x + STAT_VALUE_SPACING), top=chart_top_y,
            height=CHART_RECT_H, text=str(other_value), color=other_color['text'], font=FONT_STAT_VALUE
        )

    # fmt: on


def draw_goal_text(
    draw,
    pref_other,
    number,
    goal,
    assist_p,
    assist_s,
    strength,
    period,
    time,
    team_color,
):
    """Draws goal text (scorer & assists in the goals box).

    Args:
        TBD

    Returns:
        None
    """

    FONT_GOAL = ImageFont.truetype(FontFiles.BITTER_BOLD, FontSizes.GOAL_SCORER)
    FONT_TIME = ImageFont.truetype(FontFiles.BITTER_BOLD, FontSizes.GOAL_SCORER)
    FONT_ASST = ImageFont.truetype(FontFiles.BITTER_REGULAR, FontSizes.ASST_SCORER)

    # Instantiate shorter namespace for Constants
    c = Constants

    # Setup Goal Iterator (for spacing)
    goal_iter = number

    LEFT_OFFSET = 7
    HEIGHT = 35
    LEFT = c.GOALBOX_START_X + LEFT_OFFSET
    TOP = (
        c.GOALBOX_START_Y + c.GOALBOX_TEAM_H
        if pref_other == "pref"
        else c.GOALBOX_START_Y + c.GOALBOX_H + c.GOALBOX_SEPARATOR + c.GOALBOX_TEAM_H
    )

    # Draw Goal Scorer Text (Bold) & then get font size (to offset assists)
    TOP = TOP + (goal_iter * (10 + FontSizes.GOAL_SCORER))
    goal_text = f"{goal} - {strength}" if strength != "EVEN" else goal
    valign_center_text(
        draw=draw,
        left=LEFT,
        top=TOP,
        height=HEIGHT,
        text=goal_text,
        color=Colors.BLACK,
        font=FONT_GOAL,
    )
    goal_w, _ = draw.textsize(goal_text, FONT_GOAL)

    # Generate assists texts (or unassisted) via list comprehension
    assist_p = " ".join(assist_p.split()[1:]) if assist_p else assist_p
    assist_s = " ".join(assist_s.split()[1:]) if assist_s else assist_s
    assists = [assist_p, assist_s]
    assists = [i for i in assists if i]
    assist_text = "Unassisted" if not assists else ", ".join(assists)
    assist_text = f"({assist_text})"

    # Draw assists text (non-bold) * then get font size (to offset time)
    valign_center_text(
        draw,
        LEFT + goal_w + 5,
        TOP,
        height=HEIGHT,
        text=assist_text,
        color=Colors.BLACK,
        font=FONT_ASST,
    )
    asst_w, _ = draw.textsize(assist_text, FONT_ASST)

    # Generate time / period text & draw it
    time_period_text = f"[{time} / {period}]" if number < 7 else f"[{time} / {period}]   & MORE!"
    valign_center_text(
        draw,
        LEFT + goal_w + asst_w + 15,
        TOP,
        height=HEIGHT,
        text=time_period_text,
        color=team_color,
        font=FONT_TIME,
    )


def stats_image(game: Game, game_end: bool, boxscore: dict):
    """Generates the intermission & final image that contains bar chart starts & goal scorers.
        This is sent to social media platforms at each PERIOD_END & GAME_END event.

    Args:
        game: Current Game object
        boxscore: Boxscore of the game (for stats & goal scorers)

    Returns:
        bg: Finished Image instance
    """

    # Fonts used within the stats image
    FONT_TITLE = ImageFont.truetype(FontFiles.BITTER_BOLD, FontSizes.TITLE)
    FONT_RECORD = ImageFont.truetype(FontFiles.BITTER_BOLD, FontSizes.RECORD)
    FONT_DETAIL_LARGE = ImageFont.truetype(FontFiles.BITTER_BOLD, FontSizes.DETAIL_LARGE)
    FONT_DETAIL_SMALL = ImageFont.truetype(FontFiles.BITTER_BOLD, FontSizes.DETAIL_SMALL)
    FONT_GAMENUMBER = ImageFont.truetype(FontFiles.BITTER_BOLD, FontSizes.GAMENUMBER * 3)
    FONT_SCORE = ImageFont.truetype(FontFiles.BITTER_BOLD, FontSizes.SCORE)
    FONT_STAT_TITLE = ImageFont.truetype(FontFiles.BITTER_BOLD, FontSizes.STAT_TITLE)
    FONT_NO_GOAL = ImageFont.truetype(FontFiles.BITTER_BOLD, FontSizes.NO_GOAL_TEXT)

    # Pre-game specific constant values (incl coordinates)
    HEADER_TEXT = "END OF GAME RECAP!" if game_end else "INTERMISSION REPORT!"
    LOGO_Y = 110
    COORDS_PREF_X = 775
    COORDS_OTHER_X = 975
    LOGO_SCORE_SPACING = 50
    COORDS_PREF_LOGO = (COORDS_PREF_X, LOGO_Y)
    COORDS_OTHER_LOGO = (COORDS_OTHER_X, LOGO_Y)

    CHART_START_X = 35
    CHART_END_X = 725
    CHART_START_Y = 150
    CHART_RECT_H = 55
    CHART_SEPARATOR = 35
    CHART_GOAL_SEPARATOR = 40
    GOAL_START_Y = 200
    GOAL_SCORER_BOX_W = 400
    GOAL_SCORER_BOX_H = 220
    GOAL_SCORER_BOX_TEAM_H = 25
    GOAL_SCORE_BOX_W = 100
    GOAL_SCORER_BOX_SEPARATOR = 15

    # Setup Colors (via functions)
    colors_dict = both_team_colors_compared(game.preferred_team.team_name, game.other_team.team_name)
    pref_colors = colors_dict["first"]
    other_colors = colors_dict["second"]

    logging.debug("Pref Colors - %s // Other Colors - %s", pref_colors, other_colors)

    # Load background & pasted resized logos
    bg = Image.open(Backgrounds.STATS)
    bg_w, bg_h = bg.size

    pref_team = game.preferred_team.team_name.replace(" ", "")
    other_team = game.other_team.team_name.replace(" ", "")
    pref_logo = Image.open(os.path.join(PROJECT_ROOT, f"resources/logos/{pref_team}.png"))
    other_logo = Image.open(os.path.join(PROJECT_ROOT, f"resources/logos/{other_team}.png"))

    # Resize & paste the home / away logos with the mask the same as the image
    # TODO: Convert losing team to black & white (code snippet below)
    LOGO_RESIZE = (120, 120)
    pref_logo.thumbnail(LOGO_RESIZE, Image.ANTIALIAS)
    other_logo.thumbnail(LOGO_RESIZE, Image.ANTIALIAS)
    bg.paste(pref_logo, COORDS_PREF_LOGO, pref_logo)
    bg.paste(other_logo, COORDS_OTHER_LOGO, other_logo)

    # if game.preferred_team.score > game.other_team.score:
    #     bg.paste(pref_logo, COORDS_PREF_LOGO, pref_logo)
    #     bg.paste(other_logo.convert('LA'), COORDS_OTHER_LOGO, other_logo)
    # else:
    #     bg.paste(pref_logo.convert('LA'), COORDS_PREF_LOGO, pref_logo)
    #     bg.paste(other_logo, COORDS_OTHER_LOGO, other_logo)

    # Generates a 'draw' object that we use to draw on top of the image
    draw = ImageDraw.Draw(bg)

    center_text(
        draw=draw,
        left=0,
        top=0,
        width=bg_w,
        text=HEADER_TEXT,
        color=Colors.WHITE,
        font=FONT_TITLE,
    )

    # Draw the scores on the image
    # fmt:off
    center_text(
        draw=draw, left=COORDS_PREF_X + LOGO_SCORE_SPACING, top=LOGO_Y, width=190,
        text=str(game.preferred_team.score), color=Colors.WHITE, font=FONT_SCORE, vertical=True, height=FontSizes.SCORE
    )
    center_text(
        draw=draw, left=COORDS_OTHER_X + LOGO_SCORE_SPACING, top=LOGO_Y, width=190,
        text=str(game.other_team.score), color=Colors.WHITE, font=FONT_SCORE, vertical=True, height=FontSizes.SCORE
    )
    # fmt: on

    # Draw the boxes where Goal Scorers information goes
    draw.rectangle(
        (
            (725 + CHART_GOAL_SEPARATOR, GOAL_START_Y),
            (
                725 + CHART_GOAL_SEPARATOR + GOAL_SCORER_BOX_W,
                GOAL_START_Y + GOAL_SCORER_BOX_H,
            ),
        ),
        fill=(255, 255, 255),
    )
    draw.rectangle(
        (
            (725 + CHART_GOAL_SEPARATOR, GOAL_START_Y),
            (
                725 + CHART_GOAL_SEPARATOR + GOAL_SCORER_BOX_W,
                GOAL_START_Y + GOAL_SCORER_BOX_TEAM_H,
            ),
        ),
        fill=pref_colors["bg"],
    )
    draw.rectangle(
        (
            (
                725 + CHART_GOAL_SEPARATOR,
                GOAL_START_Y + GOAL_SCORER_BOX_SEPARATOR + GOAL_SCORER_BOX_H,
            ),
            (
                725 + CHART_GOAL_SEPARATOR + GOAL_SCORER_BOX_W,
                GOAL_START_Y + 2 * GOAL_SCORER_BOX_H + GOAL_SCORER_BOX_SEPARATOR,
            ),
        ),
        fill=(255, 255, 255),
    )
    draw.rectangle(
        (
            (
                725 + CHART_GOAL_SEPARATOR,
                GOAL_START_Y + GOAL_SCORER_BOX_SEPARATOR + GOAL_SCORER_BOX_H,
            ),
            (
                725 + CHART_GOAL_SEPARATOR + GOAL_SCORER_BOX_W,
                GOAL_START_Y + GOAL_SCORER_BOX_H + GOAL_SCORER_BOX_SEPARATOR + GOAL_SCORER_BOX_TEAM_H,
            ),
        ),
        fill=other_colors["bg"],
    )

    # fmt: off
    center_text(
        draw=draw, left=725 + CHART_GOAL_SEPARATOR, top=GOAL_START_Y, width=GOAL_SCORER_BOX_W,
        text=f"{game.preferred_team.tri_code} GOALS", color=pref_colors["text"], font=FONT_STAT_TITLE,
        vertical=True, height=GOAL_SCORER_BOX_TEAM_H,
    )
    center_text(
        draw=draw, left=725 + CHART_GOAL_SEPARATOR, top=GOAL_START_Y + GOAL_SCORER_BOX_SEPARATOR + GOAL_SCORER_BOX_H,
        width=GOAL_SCORER_BOX_W, text=f"{game.other_team.tri_code} GOALS", color=other_colors["text"],
        font=FONT_STAT_TITLE, vertical=True, height=GOAL_SCORER_BOX_TEAM_H)
    # fmt: on

    # Draw the stats base chart rectangles
    for i in range(6):
        CHART_TOP_Y = CHART_START_Y + (i * CHART_RECT_H) + (i * CHART_SEPARATOR)
        CHART_BOTTOM_Y = CHART_START_Y + ((i + 1) * CHART_RECT_H) + (i * CHART_SEPARATOR)
        draw.rectangle(
            ((CHART_START_X, CHART_TOP_Y), (CHART_END_X, CHART_BOTTOM_Y)),
            fill=Colors.WHITE,
        )

    # Get the boxscores for each team (via the homeaway variable)
    boxscore_pref = boxscore["teams"][game.preferred_team.home_away]
    boxscore_other = boxscore["teams"][game.other_team.home_away]
    preferred_stats = boxscore_pref["teamStats"]["teamSkaterStats"]
    other_stats = boxscore_other["teamStats"]["teamSkaterStats"]

    # fmt: off
    # Generate each stats bar via the function & box score
    # Shots, Blocked, Hits & FO% are always there with no logic necessary
    generate_stats_bar(
        draw=draw, stat=StatTypes.SHOTS, pref_value=preferred_stats["shots"],
        other_value=other_stats["shots"], pref_color=pref_colors, other_color=other_colors
    )

    generate_stats_bar(
        draw=draw, stat=StatTypes.BLOCKED_SHOTS, pref_value=preferred_stats["blocked"],
        other_value=other_stats["blocked"], pref_color=pref_colors, other_color=other_colors
    )

    generate_stats_bar(
        draw=draw, stat=StatTypes.HITS, pref_value=preferred_stats["hits"],
        other_value=other_stats["hits"], pref_color=pref_colors, other_color=other_colors
    )

    generate_stats_bar(
        draw=draw, stat=StatTypes.FACEOFF_PCT, pref_value=float(preferred_stats["faceOffWinPercentage"]),
        other_value=float(other_stats["faceOffWinPercentage"]), pref_color=pref_colors, other_color=other_colors
    )

    generate_stats_bar(
        draw=draw, stat=StatTypes.PENALTY_MINS, pref_value=preferred_stats["pim"],
        other_value=other_stats["pim"], pref_color=pref_colors, other_color=other_colors
    )

    # Power Plays takes a tuple instead of single values (opporunities & goals)
    pref_pp = (preferred_stats["powerPlayOpportunities"], preferred_stats["powerPlayGoals"])
    other_pp = (other_stats["powerPlayOpportunities"], other_stats["powerPlayGoals"])
    generate_stats_bar(
        draw=draw, stat=StatTypes.POWER_PLAYS, pref_value=pref_pp,
        other_value=other_pp, pref_color=pref_colors, other_color=other_colors
    )

    # Loop through preferred goals (unless there are none)
    if not game.pref_goals:
        center_text(
            draw, Constants.GOALBOX_START_X, top=Constants.GOALBOX_START_Y, width=Constants.GOALBOX_W,
            text="NO GOALS!", color=Colors.GRAY, font=FONT_NO_GOAL, vertical=True, height=Constants.GOALBOX_H,
        )

    for idx, goal in enumerate(game.pref_goals):
        logging.info("Parsing GoalEvent ID: %s, IDX: %s.", goal.event_id, goal.event_idx)

        period = goal.period_ordinal
        time = goal.period_time_remain_str
        strength = goal.strength_code
        goal_scorer = goal.scorer_name
        assist_primary = goal.primary_name
        assist_secondary = goal.secondary_name

        draw_goal_text(
            draw=draw, pref_other="pref", number=idx, goal=goal_scorer, assist_p=assist_primary,
            assist_s=assist_secondary, strength=strength, period=period, time=time, team_color=pref_colors["bg"],
        )

    # Loop through other goals (unless there are none)
    if not game.other_goals:
        TOP = Constants.GOALBOX_START_Y + Constants.GOALBOX_H + Constants.GOALBOX_SEPARATOR
        center_text(
            draw, Constants.GOALBOX_START_X, top=TOP, width=Constants.GOALBOX_W,
            text="NO GOALS!", color=Colors.GRAY, font=FONT_NO_GOAL, vertical=True, height=Constants.GOALBOX_H,
        )

    for idx, goal in enumerate(game.other_goals):
        period = goal.period_ordinal
        time = goal.period_time_remain_str
        strength = goal.strength_code
        goal_scorer = goal.scorer_name
        assist_primary = goal.primary_name
        assist_secondary = goal.secondary_name

        draw_goal_text(
            draw=draw, pref_other="other", number=idx, goal=goal_scorer, assist_p=assist_primary,
            assist_s=assist_secondary, strength=strength, period=period, time=time, team_color=other_colors["bg"],
        )
    # fmt: on

    # bg.show()
    return bg


def hockeystatcards_charts(game: Game, home_gs: dict, away_gs: dict):
    """Generates two charts of each team's GameScore (with their average & breakout status).
        This is sent to social media platforms at the end of each game.

    Args:
        game: Current Game object
        home_gs: Home Team Game Score dictionary
        away_gs: Away Team Game Score dictionary

    Returns:
        gs_charts: Two file paths to GameScore charts
    """

    # Intialize an empty list to hold our completed file paths
    gs_charts = list()

    # Loop over both the home & away gamescore dictionaries to plot the charts
    for idx, gs in enumerate((home_gs, away_gs)):
        # Setup Team Name & Proper Colors
        team_name = game.home_team.team_name if idx == 0 else game.away_team.team_name
        color = rgb_to_hex(team_colors(team_name).get("primary").get("bg"))

        logging.info("Generating the %s Game Score Chart.", team_name)

        gs_df = pd.DataFrame(gs)
        gs_df.columns = map(str.lower, gs_df.columns)
        gs_df = gs_df[["player", "toi", "gamescore", "hero", "gsavg"]]
        gs_df["gamescore"] = pd.to_numeric(gs_df["gamescore"])
        gs_df["gsavg"] = pd.to_numeric(gs_df["gsavg"])
        gs_df = gs_df.sort_values(by=["gamescore"], ascending=False)
        gs_df.set_index("player", drop=True, inplace=True)
        gs_df = gs_df.iloc[::-1]

        gs_fig, ax = plt.subplots(1, 1, figsize=(10, 8))
        bars = gs_df[["gamescore"]].astype(float).plot.barh(ax=ax, color=color)
        bars = bars.patches
        heros = gs_df["hero"]
        for bar, hero in zip(bars, heros):
            if hero:
                bar.set_hatch("///")

        ax.plot(
            gs_df[["gsavg"]].astype(float).gsavg.values,
            gs_df[["gsavg"]].astype(float).index.values,
            # marker="H",
            marker="X",
            linestyle="",
            color="#AAAAAA",
        )

        ax.grid(True, which="major", axis="x", color="#cccccc")
        ax.grid(True, which="major", axis="y", color="#cccccc", linestyle="dotted")
        ax.set_axisbelow(True)
        ax.set(frame_on=False)
        ax.set_ylabel("")
        ax.set_xlabel("")
        ax.legend().remove()
        ax.legend(
            ["Player's Season Average GameScore"],
            bbox_to_anchor=(0.5, -0.15),
            loc="lower center",
            ncol=1,
            frameon=False,
        )

        ax.title.set_text(
            f"{team_name} GameScore - {game.game_date_short}\n"
            f"Data Courtesy: Cole Palmer (@hockeystatcards) & Natural Stat Trick\n"
            f"GameScore Formula: Dom Luszczyszyn (@domluszczyszyn)\n"
        )

        gs_fig.text(
            0.5,
            -0.04,
            "Hatched (///) Pattern Indicates Breakout Game.\n"
            "A breakout game is ~1.5X the standard deviation from the player's mean GameScore.",
            horizontalalignment="center",
            fontsize=8,
        )

        gs_chart_path = os.path.join(IMAGES_PATH, "temp", f"hsc_gamescore-{game.game_id_shortid}-{idx}.png")
        logging.info("Image Path: %s", gs_chart_path)
        gs_fig.savefig(gs_chart_path, bbox_inches="tight")

        # Add the overview image path to our list
        gs_charts.append(gs_chart_path)

    return gs_charts
