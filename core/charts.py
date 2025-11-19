import logging
import os

import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
from matplotlib import rcParams

import utils.others as otherutils
from core import schedule
from core.models.game_context import GameContext
from definitions import IMAGES_DIR
from utils.team_details import TEAM_DETAILS

logger = logging.getLogger(__name__)


def format_pp_text(goals: int, opps: int) -> str:
    """Return formatted Power Play text like '2/3 (66.7%)'."""
    if opps == 0:
        return "0/0 (0%)"
    pct = (goals / opps) * 100
    return f"{goals}/{opps} ({pct:.1f}%)"


def _parse_pp_pair(value) -> tuple[int, int]:
    """
    Parse a 'goals/opps' string like '2/3' into (goals, opps).
    Returns (0, 0) on any failure.
    """
    if not isinstance(value, str):
        return 0, 0
    try:
        goals_str, opps_str = value.split("/")
        return int(goals_str.strip()), int(opps_str.strip())
    except Exception:
        return 0, 0


def teamstats_conversion(team_game_stats: dict):
    """
    Converts pre-game team stats data into a in-game format for one function processing.
    """

    away_team = team_game_stats["awayTeam"]
    home_team = team_game_stats["homeTeam"]

    formatted_data = []
    for key in away_team.keys():
        if not key.endswith("Rank"):  # Exclude rank keys from main loop
            rank_key = key + "Rank"
            formatted_data.append(
                {
                    "category": key,
                    "awayValue": away_team[key],
                    "homeValue": home_team[key],
                    "awayRank": away_team.get(rank_key, None),
                    "homeRank": home_team.get(rank_key, None),
                }
            )
    return formatted_data


def teamstats_chart(context: GameContext, team_game_stats: dict, ingame: bool = True, period_label_short: str = None):
    """
    Generate a horizontal stacked bar chart comparing team statistics.
    Supports:
      - Pre-game season stats (ingame=False)
      - Live/post-game stats (ingame=True)
      - Intermission charts with period_label_short ("1st", "2nd", "OT", etc.)

    Returns:
        str: The file path to the saved chart image.
    """

    # Set the custom font (you'll need the font file)
    rcParams["font.family"] = "sans-serif"
    rcParams["font.sans-serif"] = ["Inter", "Arial", "sans-serif"]

    # Pull Out Team Names & Colors from GameContext
    pref_team = context.preferred_team
    pref_team_name = pref_team.full_name
    pref_team_score = pref_team.score
    pref_team_color = pref_team.primary_color
    pref_team_text_color = pref_team.primary_text_color

    other_team = context.other_team
    other_team_name = other_team.full_name
    other_team_score = other_team.score
    other_team_color = other_team.primary_color
    other_team_text_color = other_team.primary_text_color

    game_date_string = context.game_time_local_str
    venue = context.venue

    # Check if Colors are Same & Swap Other Team Color
    if pref_team_color == other_team_color:
        other_team_color = other_team.secondary_color
        other_team_text_color = other_team.secondary_text_color

    # Remove Preferred HomeAway from Context to Shorten Variable Names
    pref_homeaway = context.preferred_homeaway

    if ingame:
        # Implement Period Label in Title if Provided
        if period_label_short:
            # PERIOD / OT / SO INTERMISSION CHARTS
            # Uses your existing Event period-label logic ("1st", "2nd", "OT", "SO")
            pls = period_label_short.upper()

            if pls in ("1ST", "2ND", "3RD"):
                chart_title = f"END OF {pls} PERIOD: Team Game Stats"
            elif pls.endswith("OT"):  # OT, 2OT, 3OT...
                chart_title = f"END OF {pls}: Team Game Stats"
            elif pls == "SO":
                chart_title = "SHOOTOUT STATS"
            else:
                chart_title = "Team Game Stats"
        else:
            # No period label = final post-game chart
            chart_title = "FINAL: Team Game Stats"

        chart_file_prefix = "ingame"
        chart_figsize = (12, 9)
        chart_title_y = 0.94
        chart_subtitle = f"{pref_team_name}: {pref_team_score} / {other_team_name}: {other_team_score}"
        chart_subtitle_y = 0.9
        category_labels = {
            "sog": "SOG",
            "faceoffWinningPctg": "Faceoff %",
            "powerPlayPctg": "Power Play %",
            "pim": "PIM",
            "hits": "Hits",
            "blockedShots": "Blocked Shots",
            "giveaways": "Giveaways",
            "takeaways": "Takeaways",
        }
    else:
        chart_file_prefix = "pregame"
        chart_figsize = (12, 6)
        chart_title = f"Pre-Game: Team Season Stats"
        chart_title_y = 0.96
        chart_subtitle = f"{game_date_string} @ {venue}"
        chart_subtitle_y = 0.9
        team_game_stats = teamstats_conversion(team_game_stats)
        category_labels = {
            "ppPctg": "Power Play %",
            "pkPctg": "Penalty Kill %",
            "faceoffWinningPctg": "Faceoff %",
            "goalsForPerGamePlayed": "Goals For / GP",
            "goalsAgainstPerGamePlayed": "Goals Against / GP",
        }

    # -------------------------------
    # Extract raw PowerPlay row (for goals/opps)
    # -------------------------------
    powerplay_raw = next(
        (s for s in team_game_stats if s.get("category") == "powerPlay"),
        None,
    )

    # -------------------------------
    # Sanitize numeric stats (keep powerPlayPctg, drop powerPlay)
    # -------------------------------
    team_game_stats_numeric = [
        stat
        for stat in team_game_stats
        if stat.get("category") != "powerPlay"  # handled via powerPlayPctg
        and isinstance(stat.get("awayValue"), (int, float))
        and isinstance(stat.get("homeValue"), (int, float))
    ]

    # -------------------------------
    # Preprocess stats
    # -------------------------------
    categories = []
    away_percentages = []
    home_percentages = []
    pp_meta = {}  # index -> dict(goals/opps) for label text

    for stat in team_game_stats_numeric:
        category = stat["category"]
        away_val = stat["awayValue"]
        home_val = stat["homeValue"]

        # Power Play row: use goals/opps from 'powerPlay' string row
        if category == "powerPlayPctg":
            if powerplay_raw:
                away_goals, away_opps = _parse_pp_pair(powerplay_raw.get("awayValue"))
                home_goals, home_opps = _parse_pp_pair(powerplay_raw.get("homeValue"))
            else:
                away_goals = away_opps = home_goals = home_opps = 0

            total_opps = away_opps + home_opps
            if total_opps > 0:
                away_pct = (away_opps / total_opps) * 100
                home_pct = (home_opps / total_opps) * 100
            else:
                # No PP either side: visually even split
                away_pct = home_pct = 50.0

            categories.append(category_labels.get(category, "Power Play"))
            away_percentages.append(away_pct)
            home_percentages.append(home_pct)

            idx = len(categories) - 1
            pp_meta[idx] = {
                "home_goals": home_goals,
                "away_goals": away_goals,
                "home_opps": home_opps,
                "away_opps": away_opps,
            }
            continue

        # Normal stats
        total = away_val + home_val
        if total > 0:
            categories.append(category_labels.get(category, category))
            away_percentages.append((away_val / total) * 100)
            home_percentages.append((home_val / total) * 100)

    # Reverse for top-down ordering
    categories = categories[::-1]
    away_percentages = away_percentages[::-1]
    home_percentages = home_percentages[::-1]
    team_game_stats_numeric = team_game_stats_numeric[::-1]

    # Because we reversed, remap pp_meta indices
    if pp_meta:
        new_pp_meta = {}
        n = len(categories)
        for old_idx, meta in pp_meta.items():
            new_idx = n - 1 - old_idx
            new_pp_meta[new_idx] = meta
        pp_meta = new_pp_meta

    # -------------------------------
    # Y positions
    # -------------------------------
    bar_height = 0.2
    bar_spacing = 0.125
    y = np.arange(len(categories)) * (bar_height + bar_spacing)

    # Preferred team orientation
    if pref_homeaway == "home":
        preferred_percentages = home_percentages
        other_percentages = away_percentages
    else:
        preferred_percentages = away_percentages
        other_percentages = home_percentages

    # -------------------------------
    # Draw base bars (all rows, including Power Play)
    # -------------------------------
    fig, ax = plt.subplots(figsize=chart_figsize)
    bar_gap = 0.5

    ax.barh(
        y,
        preferred_percentages,
        bar_height,
        color=pref_team_color,
        label=pref_team_name,
    )
    ax.barh(
        y,
        other_percentages,
        bar_height,
        left=[p + bar_gap for p in preferred_percentages],
        color=other_team_color,
        label=other_team_name,
    )

    # -------------------------------
    # Annotate rows
    # -------------------------------
    for i, (preferred_val, other_val, total) in enumerate(
        zip(preferred_percentages, other_percentages, team_game_stats_numeric)
    ):
        category = total["category"]

        # ----- POWER PLAY: labels from pp_meta, geometry from percentages -----
        if category == "powerPlayPctg" and i in pp_meta:
            meta = pp_meta[i]
            if pref_homeaway == "home":
                pref_goals = meta["home_goals"]
                pref_opps = meta["home_opps"]
                other_goals = meta["away_goals"]
                other_opps = meta["away_opps"]
            else:
                pref_goals = meta["away_goals"]
                pref_opps = meta["away_opps"]
                other_goals = meta["home_goals"]
                other_opps = meta["home_opps"]

            preferred_label = format_pp_text(pref_goals, pref_opps)
            other_label = format_pp_text(other_goals, other_opps)
        else:
            # ----- Normal categories -----
            preferred_raw = total["homeValue"] if pref_homeaway == "home" else total["awayValue"]
            other_raw = total["awayValue"] if pref_homeaway == "home" else total["homeValue"]

            if category.lower().endswith("pctg"):
                preferred_label = f"{preferred_raw * 100:.2f}%"
                other_label = f"{other_raw * 100:.2f}%"
            else:
                preferred_label = str(preferred_raw) if preferred_raw > 0 else ""
                other_label = str(other_raw) if other_raw > 0 else ""

            preferred_rank = total.get("homeRank") if pref_homeaway == "home" else total.get("awayRank")
            other_rank = total.get("awayRank") if pref_homeaway == "home" else total.get("homeRank")

            if preferred_rank is not None:
                preferred_label += f" ({otherutils.ordinal(preferred_rank)})"
            if other_rank is not None:
                other_label += f" ({otherutils.ordinal(other_rank)})"

        # Category label (centered above both bars)
        total_width = preferred_val + other_val + bar_gap
        ax.text(
            total_width / 2,
            y[i] + bar_height / 2 + 0.01,
            category_labels.get(category, category),
            ha="center",
            va="bottom",
            fontsize=12,
            color="black",
        )

        # Preferred value text
        ax.text(
            preferred_val / 2,
            y[i],
            preferred_label,
            ha="center",
            va="center",
            fontsize=14,
            color=pref_team_text_color,
            fontweight="bold",
        )

        # Other value text
        ax.text(
            preferred_val + bar_gap + (other_val / 2),
            y[i],
            other_label,
            ha="center",
            va="center",
            fontsize=14,
            color=other_team_text_color,
            fontweight="bold",
        )

    # -------------------------------
    # Title / subtitle / styling
    # -------------------------------
    fig.text(
        0.125,
        chart_title_y,
        chart_title,
        ha="left",
        va="top",
        fontsize=24,
        fontweight="bold",
        color="dimgray",
    )
    fig.text(
        0.125,
        chart_subtitle_y,
        chart_subtitle,
        ha="left",
        va="top",
        fontsize=14,
        color="gray",
    )

    plt.subplots_adjust(top=0.85)

    ax.set_yticks([])
    ax.set_yticklabels([])
    ax.set_ylabel(" ")

    ax.set_xticks([])
    ax.set_xticklabels([])

    ax.grid(False)
    ax.set(frame_on=False)

    # Move legend to the bottom
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.06), ncol=2, frameon=False)

    # Remove grid lines
    ax.grid(False)

    # Save the figure
    chart_path = os.path.join(IMAGES_DIR, f"{chart_file_prefix}-teamstatschart.png")
    plt.savefig(chart_path, bbox_inches="tight")
    return chart_path
