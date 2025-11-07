import logging
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
from matplotlib import rcParams

import utils.others as otherutils
from core import schedule
from core.models.game_context import GameContext
from definitions import IMAGES_DIR
from utils.team_details import TEAM_DETAILS


def generate_split_barchart(context: GameContext, game_title, stats):
    """Generate a stacked bar chart to compare team stats.

    Args:
        context: The GameContext object containing team information.
        game_title: Title for the chart.
        overview_stats: Dictionary containing stats for both teams.
        selected_stats: List of keys from `overview_stats` to include in the chart.

    Returns:
        The saved file path of the chart.

    """
    # Extract team details and colors
    preferred_team = context.preferred_team.full_name
    other_team = context.other_team_name

    pref_hex_color = TEAM_DETAILS.get(context.preferred_team_abbreviation, {}).get("primary_color", "#0000FF")
    other_hex_color = TEAM_DETAILS.get(context.other_team_abbreviation, {}).get("primary_color", "#FF0000")
    pref_color = [x / 255 for x in otherutils.hex_to_rgb(pref_hex_color)]
    other_color = [x / 255 for x in otherutils.hex_to_rgb(other_hex_color)]

    # Normalize stats to percentages
    percentage_stats = {}
    for stat in stats["home"]:
        home_value = stats["home"][stat]
        away_value = stats["away"][stat]
        total = home_value + away_value
        if total > 0:
            percentage_stats[stat] = {
                "home": round((home_value / total) * 100, 1),
                "away": round((away_value / total) * 100, 1),
            }
        else:
            # If total is 0, both percentages are 0
            percentage_stats[stat] = {"home": 0, "away": 0}

    df_percentage = pd.DataFrame(percentage_stats).T.iloc[::-1]
    df_values = pd.DataFrame(stats).iloc[::-1]

    # Check if the DataFrame is empty
    if df_percentage.empty:
        logging.error("generate_percentage_split_barchart: DataFrame is empty. No data to plot.")
        return None

    overview_fig, ax1 = plt.subplots(1, 1, figsize=(10, 5))
    df_percentage.plot(
        kind="barh",
        stacked=True,
        ax=ax1,
        color=[pref_color, other_color],
    )

    # ax1.grid(False, which="major", axis="x", color="#cccccc")
    # ax1.grid(False)
    # ax1.spines["bottom"].set_visible(False)
    # ax1.set_axisbelow(False)
    plt.tick_params(
        axis="x",  # changes apply to the x-axis
        which="both",  # both major and minor ticks are affected
        bottom=False,  # ticks along the bottom edge are off
        labelbottom=False,
    )  # labels along the bottom edge are off

    ax1.set(frame_on=False)
    ax1.legend(
        [preferred_team, other_team],
        bbox_to_anchor=(0.5, -0.2),
        loc="lower center",
        ncol=2,
        frameon=False,
    )

    temp_title = f"Game Stats: {context.preferred_team.full_name} vs. {context.other_team_name}"
    ax1.title.set_text(temp_title)

    for i, v in enumerate(df_percentage["home"].values):
        if v > 0:
            ax1.text(
                float(v) - 2,
                i,
                df_values["home"][i],
                va="center",
                ha="right",
                color="white",
                fontweight="bold",
            )

    for i, v in enumerate(df_values["away"].values):
        if v > 0:
            ax1.text(
                100 - 2,
                i,
                df_values["away"][i],
                va="center",
                ha="right",
                color="white",
                fontweight="bold",
            )

    file_path = f"{game_title.replace(' ', '_')}_percentage_split_chart.png"
    overview_fig.savefig(file_path, bbox_inches="tight")
    plt.close(overview_fig)
    return file_path

    # Plot the percentage split bar chart
    overview_fig, ax1 = plt.subplots(figsize=(10, 5))
    try:
        df_percentage.plot(
            kind="barh",
            stacked=True,
            ax=ax1,
            color=[pref_color, other_color],
        )

        # Formatting and labels
        ax1.grid(True, which="major", axis="x", color="#cccccc")
        ax1.set_axisbelow(True)
        ax1.set(frame_on=False)
        ax1.legend(
            [preferred_team, other_team],
            bbox_to_anchor=(0.5, -0.2),
            loc="lower center",
            ncol=2,
            frameon=False,
        )
        ax1.title.set_text(f"{game_title}\nPercentage Split of Team Stats\nData Source: Custom")

        # Add percentages as text on the bars
        for index, row in df_percentage.iterrows():
            ax1.text(
                row["home"] / 2,
                index,
                f"{row['home']}%",
                va="center",
                ha="center",
                color="white",
                fontweight="bold",
            )
            ax1.text(
                100 - row["away"] / 2,
                index,
                f"{row['away']}%",
                va="center",
                ha="center",
                color="white",
                fontweight="bold",
            )

        # Save the figure
        file_path = f"{game_title.replace(' ', '_')}_percentage_split_chart.png"
        overview_fig.savefig(file_path, bbox_inches="tight")
        plt.close(overview_fig)
        return file_path

    except Exception as e:
        logging.exception(f"generate_percentage_split_barchart: Failed to generate chart. Error: {e}")
        plt.close(overview_fig)
        return None


def intermission_chart(context: GameContext):
    right_rail = schedule.fetch_rightrail(context.game_id)
    team_game_stats = right_rail.get("teamGameStats")

    if not team_game_stats:
        return

    team_game_stats_formatted = {"home": {}, "away": {}}
    stats_to_keep = ["sog", "pim", "hits", "blockedShots", "giveaways", "takeaways"]

    for stat in team_game_stats:
        if stat["category"] not in stats_to_keep:
            continue
        category = stat["category"]
        team_game_stats_formatted["home"][category] = stat["homeValue"]
        team_game_stats_formatted["away"][category] = stat["awayValue"]

    generate_split_barchart(context, "TBD", team_game_stats_formatted)


def teamstats_conversion(team_game_stats: dict):
    """Converts pre-game team stats data into a in-game format for one function processing."""
    away_team = team_game_stats["awayTeam"]
    home_team = team_game_stats["homeTeam"]

    formatted_data = []
    for key in away_team:
        if not key.endswith("Rank"):  # Exclude rank keys from main loop
            rank_key = key + "Rank"
            formatted_data.append(
                {
                    "category": key,
                    "awayValue": away_team[key],
                    "homeValue": home_team[key],
                    "awayRank": away_team.get(rank_key, None),
                    "homeRank": home_team.get(rank_key, None),
                },
            )
    return formatted_data


def teamstats_chart(context: GameContext, team_game_stats: dict, ingame: bool = True):
    """Generate a horizontal stacked bar chart comparing team statistics.

    Args:
        context (GameContext): The game context containing team details, including names,
            colors, and preferred home/away designation.
        team_game_stats (dict): Team statistics data. Supports in-game and pre-game formats:
            - In-game: [{"category": "stat_name", "awayValue": value, "homeValue": value}, ...]
            - Pre-game: Converted internally using `teamstats_conversion`.
        ingame (bool, optional): If True, generates an in-game/post-game chart.
            If False, generates a pre-game season stats chart. Defaults to True.

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
        chart_file_prefix = "ingame"
        chart_figsize = (12, 9)
        chart_title = "FINAL: Team Game Stats"
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
        chart_title = "Pre-Game: Team Season Stats"
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

    # Remove Non-Numeric Values from Dictionary
    team_game_stats = [
        item
        for item in team_game_stats
        if isinstance(item.get("awayValue"), (int, float)) and isinstance(item.get("homeValue"), (int, float))
    ]

    # Pre-Process Data
    categories = []
    away_percentages = []
    home_percentages = []

    for stat in team_game_stats:
        category = stat["category"]
        away_value = stat["awayValue"]
        home_value = stat["homeValue"]
        total = away_value + home_value

        # Skip categories with zero total to avoid division by zero
        if total > 0:
            categories.append(category_labels.get(category, category))  # Use custom label
            away_percentages.append((away_value / total) * 100)
            home_percentages.append((home_value / total) * 100)

    # Reverse the order of data for plotting
    categories = categories[::-1]
    away_percentages = away_percentages[::-1]
    home_percentages = home_percentages[::-1]
    team_game_stats = team_game_stats[::-1]

    # Adjust bar spacing
    bar_height = 0.2
    bar_spacing = 0.125  # Increased spacing
    y = np.arange(len(categories)) * (bar_height + bar_spacing)

    # Determine which team is preferred and adjust the plotting order
    if pref_homeaway == "home":
        preferred_percentages = home_percentages
        other_percentages = away_percentages
    else:
        preferred_percentages = away_percentages
        other_percentages = home_percentages

    # Create the figure and axis
    fig, ax = plt.subplots(figsize=chart_figsize)

    # Horizontal stacked bar chart
    bar_gap = 0.5
    ax.barh(y, preferred_percentages, bar_height, label=pref_team_name, color=pref_team_color)
    ax.barh(
        y,
        other_percentages,
        bar_height,
        left=[p + bar_gap for p in preferred_percentages],
        label=other_team_name,
        color=other_team_color,
    )

    # Annotate raw values with rank information
    for i, (preferred, other, total) in enumerate(
        zip(preferred_percentages, other_percentages, team_game_stats, strict=False),
    ):
        preferred_value = total["homeValue"] if pref_homeaway == "home" else total["awayValue"]
        other_value = total["awayValue"] if pref_homeaway == "home" else total["homeValue"]
        preferred_rank = total.get("homeRank") if pref_homeaway == "home" else total.get("awayRank")
        other_rank = total.get("awayRank") if pref_homeaway == "home" else total.get("homeRank")
        category = total["category"]

        # Convert values to percentages for categories ending in 'pctg'
        if category.lower().endswith("pctg"):
            preferred_value = f"{preferred_value * 100:.2f}%"
            other_value = f"{other_value * 100:.2f}%"
        else:
            # Convert non-percentage values to strings
            preferred_value = str(preferred_value) if preferred_value > 0 else ""
            other_value = str(other_value) if other_value > 0 else ""

        # Add rank to the annotation if available, converting to ordinal
        if preferred_rank is not None:
            preferred_value += f" ({otherutils.ordinal(preferred_rank)})"
        if other_rank is not None:
            other_value += f" ({otherutils.ordinal(other_rank)})"

        # Annotate Bar Categories Above Graph
        total_width = preferred + other
        y_offset = bar_height / 2 + 0.01  # Adjust offset to position above the bars
        ax.text(
            total_width / 2,  # Align labels at the start of the x-axis
            y[i] + y_offset,
            category_labels.get(category, category),
            ha="center",
            va="bottom",
            fontsize=12,
            # weight="bold",
            color="black",
        )

        # Annotate Away
        ax.text(
            preferred / 2,
            y[i],
            f"{preferred_value}",
            ha="center",
            va="center",
            color=pref_team_text_color,
            fontweight="bold",
            fontsize=14,
        )

        # Annotate Home
        ax.text(
            preferred + other / 2,
            y[i],
            f"{other_value}",
            ha="center",
            va="center",
            color=other_team_text_color,
            fontweight="bold",
            fontsize=14,
        )

    # Customizations
    # ax.set_xlabel("Percentage (%)", fontsize=12)
    # ax.set_ylabel("Categories", fontsize=12)
    # ax.set_title(chart_title, fontsize=14, fontweight="bold")
    # Add a styled title
    # ax.set_title(
    #     chart_title,
    #     fontsize=20,
    #     fontweight="bold",
    #     color="dimgray",
    #     loc="center",  # Options: "left", "center", "right"
    # )

    # Add the title
    fig.text(
        0.125,
        chart_title_y,  # Y-coordinate for the title
        chart_title,  # Main title
        ha="left",
        va="top",
        fontsize=24,  # Larger font for the main title
        fontweight="bold",
        color="dimgray",
    )

    # Add the subtitle
    fig.text(
        0.125,
        chart_subtitle_y,  # Slightly lower Y-coordinate for the subtitle
        chart_subtitle,  # Subtitle
        ha="left",
        va="top",
        fontsize=14,  # Smaller font for the subtitle
        fontweight="regular",
        color="gray",
    )

    # Adjust the chart to leave more room for the title
    plt.subplots_adjust(top=0.85)  # Push the chart content down

    # if ingame:
    #     ax.set_yticks(y)
    #     ax.set_yticklabels(categories)

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
    chart_path = Path(IMAGES_DIR) / f"{chart_file_prefix}-teamstatschart.png"
    plt.savefig(chart_path, bbox_inches="tight")
    return chart_path
    return chart_path
