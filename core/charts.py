import logging
from matplotlib import pyplot as plt
import pandas as pd
from core import schedule
from core.models.game_context import GameContext
from utils.team_details import TEAM_DETAILS
import utils.others as otherutils


def generate_split_barchart(context: GameContext, game_title, stats):
    """
    Generate a stacked bar chart to compare team stats.

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
    for stat in stats["home"].keys():
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

    print("Stats:", stats)
    print("PCT Stats:", percentage_stats)

    df_percentage = pd.DataFrame(percentage_stats).T.iloc[::-1]
    df_values = pd.DataFrame(stats).iloc[::-1]
    print(df_percentage)
    print(df_values)

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
        logging.error(f"generate_percentage_split_barchart: Failed to generate chart. Error: {e}")
        plt.close(overview_fig)
        return None


def intermission_chart(context: GameContext):
    right_rail = schedule.fetch_rightrail(context.game_id)
    team_game_stats = right_rail.get("teamGameStats")

    if not team_game_stats:
        return None

    team_game_stats_formatted = {"home": {}, "away": {}}
    stats_to_keep = ["sog", "pim", "hits", "blockedShots", "giveaways", "takeaways"]

    for stat in team_game_stats:
        if stat["category"] not in stats_to_keep:
            continue
        category = stat["category"]
        team_game_stats_formatted["home"][category] = stat["homeValue"]
        team_game_stats_formatted["away"][category] = stat["awayValue"]

    file_path = generate_split_barchart(context, "TBD", team_game_stats_formatted)
