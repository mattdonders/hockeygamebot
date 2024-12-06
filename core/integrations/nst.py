import logging
import os
from typing import Optional
from urllib.parse import urlencode

from matplotlib import pyplot as plt, rcParams
import pandas as pd

from core.integrations import api
from core.models.game_context import GameContext
from utils.team_details import get_team_details_by_name
import utils.others as otherutils
from definitions import IMAGES_DIR


def get_nst_report_url(context: GameContext, full: bool = False) -> Optional[str]:
    """
    Generate the Natural Stat Trick (NST) report URL for a given NHL game.

    Args:
        game: An NHL Game object containing relevant game details. Expected attributes:
              - season (e.g., "20242025")
              - game_id_gametype_shortid (e.g., "02")
              - game_id_shortid (e.g., "1234")
        full (bool): Whether to return the full report URL. Defaults to False.

    Returns:
        Optional[str]: The NST report URL for the game, or None if the URL cannot be constructed.
    """

    base_url = "https://www.naturalstattrick.com"

    # Validate the `game` object has the required attributes
    required_attrs = ["season", "game_type", "game_shortid"]
    if not all(hasattr(context, attr) for attr in required_attrs):
        logging.error(f"GameContext is missing required attributes: {required_attrs}")
        return None

    # Construct query parameters
    try:
        query_params = {
            "season": context.season_id,
            "view": "full" if full else "limited",
            "game": f"{context.game_type}{context.game_shortid}",
        }
        # Generate the full URL
        nst_rpt_url = f"{base_url}/game.php?{urlencode(query_params)}"
        return nst_rpt_url
    except Exception as e:
        logging.error(f"Failed to construct NST URL: {e}")
        return None


def team_season_rank(df: pd.DataFrame, stat, team_name):
    """Takes a dataframe, a stat & a team name and finds the "rank" of that team in the DataFrame."""

    # Sort the dataframe and find the team index
    # Add 1 because a Dataframe is 0-index
    sorted_df = df.sort_values(stat, ascending=False).reset_index(drop=True)
    rank = sorted_df.index[sorted_df["Team"] == team_name].tolist()[0] + 1
    return rank


def generate_team_season_charts(team_name, situation, lastgames=None):
    """
    Generate team season charts using data from Natural Stat Trick.

    Args:
        team_name (str): The name of the team to generate charts for.
        situation (str): The game situation (e.g., "5v5", "PP").
        lastgames (int, optional): Number of last games to filter data. Defaults to None.

    Returns:
        pd.DataFrame: DataFrame containing the team and league-average statistics.
    """

    # Set the custom font (you'll need the font file)
    # rcParams["font.family"] = "sans-serif"
    # rcParams["font.sans-serif"] = ["Inter", "Arial", "sans-serif"]

    # Construct the Natural Stat Trick URL based on the situation and number of games
    base_url = "https://www.naturalstattrick.com"
    last_games_mod = "" if not lastgames else f"&gp={lastgames}&gpf=c"
    nst_team_url = f"{base_url}/teamtable.php?sit={situation}{last_games_mod}"

    # Fetch the HTML content from the URL
    resp = api.thirdparty_request(nst_team_url)
    soup = api.bs4_parse(resp.content)

    # Extract the team table and convert it to a Pandas DataFrame
    teams = soup.find("table", id="teams")
    teams_df = pd.read_html(str(teams), index_col=0)[0]

    # Before calculating the average, store a copy of the dataframe for rankings
    df_rank = teams_df.copy()

    # Add League Average as an extra row (using numeric_only=True)
    # & Reset the index to handle the new row properly
    teams_df.loc["avg"] = teams_df.mean(numeric_only=True)
    # teams_df.reset_index(drop=True, inplace=True)

    # Rename the last row as "Average"
    teams_df.iloc[-1, teams_df.columns.get_loc("Team")] = "Average"

    # Print the resulting DataFrame for debugging purposes
    # print(teams_df)

    # Create two dataframes (for the two halves) of the report card
    pref_df = teams_df.loc[teams_df["Team"].isin([team_name, "Average"])]
    pref_df_no_against = pref_df[["Point %", "xGF", "GF", "SH%", "SV%", "PDO", "HDSH%", "HDSV%"]]
    pref_df = pref_df[["CF%", "SCF%", "HDCF%", "xGF%", "GF%"]]

    # Transpose them to make them easier to work with in the correct form
    pref_df_T = pref_df.T
    pref_df_no_against = pref_df_no_against.T

    # Manipulate the data frames to drop & rename columns for named access
    pref_df_T["FOR"] = pref_df_T.iloc[:, 0]
    pref_df_T.drop(pref_df_T.columns[0], axis=1, inplace=True)
    pref_df_T.drop("avg", axis=1, inplace=True)
    pref_df_no_against["FOR"] = pref_df_no_against.iloc[:, 0]
    pref_df_no_against.drop(pref_df_no_against.columns[0], axis=1, inplace=True)

    # Perform DataFrame data clean up
    # Convert the "Against Column to 100-value" to make sure each row totals 100
    # Convert PDO & Point % to full percentage values
    pref_df_T["AGAINST"] = pref_df_T.apply(lambda row: 100 - row.FOR, axis=1)
    pref_df_no_against["FOR"]["Point %"] = pref_df_no_against["FOR"]["Point %"] * 100
    pref_df_no_against["FOR"]["PDO"] = pref_df_no_against["FOR"]["PDO"] * 100
    pref_df_no_against["avg"]["Point %"] = pref_df_no_against["avg"]["Point %"] * 100
    pref_df_no_against["avg"]["PDO"] = pref_df_no_against["avg"]["PDO"] * 100

    # Reverse the Order of the DataFrame rows to make the graph look cleaner
    pref_df_T = pref_df_T.iloc[::-1]
    pref_df_no_against = pref_df_no_against.iloc[::-1]

    team_details = get_team_details_by_name(team_name)
    team_color_bg = team_details["primary_color"]
    team_color_text = team_details["primary_text_color"]

    # For each index value of the dataframe, add the rank to that index
    # We transpose twice because volumns are easier to work with
    ranked_columns = list()
    pref_df_T = pref_df_T.T
    for col in pref_df_T.columns:
        stat_rank = otherutils.ordinal(team_season_rank(df_rank, col, team_name))
        ranked_col = f"{col} ({stat_rank})"
        ranked_columns.append(ranked_col)
    pref_df_T.columns = ranked_columns
    pref_df_T = pref_df_T.T

    ranked_columns = list()
    pref_df_no_against = pref_df_no_against.T
    for col in pref_df_no_against.columns:
        stat_rank = otherutils.ordinal(team_season_rank(df_rank, col, team_name))
        ranked_col = f"{col} ({stat_rank})"
        ranked_columns.append(ranked_col)
    pref_df_no_against.columns = ranked_columns
    pref_df_no_against = pref_df_no_against.T

    # Create the figure that we will plot the two separate graphs on
    overview_fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 10))

    # Plot the top (no against) bar graph & the leage average line graph
    pref_df_no_against[["FOR"]].plot.barh(ax=ax1, color=team_color_bg)

    ax1.plot(
        pref_df_no_against[["avg"]].avg.values,
        pref_df_no_against[["avg"]].index.values,
        # marker="H",
        marker="X",
        linestyle="",
        color="#AAAAAA",
    )

    # Plot the bottom (split bar graph) in the team & a gray color for the opposition
    pref_df_T.plot(kind="barh", stacked=True, ax=ax2, color=[team_color_bg, "#AAAAAA"])

    # Clean up the plots (fixes axes, legends, etc)
    ax1.legend().remove()
    ax1.legend(["League Average"], bbox_to_anchor=(0.5, -0.2), loc="lower center", ncol=1, frameon=False)

    ax2.legend(
        [team_name, "Opponents"],
        bbox_to_anchor=(0.5, -0.2),
        loc="lower center",
        ncol=2,
        frameon=False,
    )

    for ax in [ax1, ax2]:
        ax.grid(True, which="major", axis="x", color="#cccccc")
        ax.set_axisbelow(True)
        ax.set(frame_on=False)

    # Add the Figure Title
    last_games_title = "Season Stats" if not lastgames else f"Last {lastgames} Games"
    sit_label = "5v5 (SVA)" if situation == "sva" else "All Situations"

    ax1.title.set_text(f"{team_name} {last_games_title} - {sit_label}\nData Courtesy: Natural Stat Trick")

    # Draw the text labels on each of the corresponding bars
    # The top graph values are centered in the bar so it doesn't conflict with the average marker
    for i, v in enumerate(pref_df_no_against["FOR"].values):
        ax1.text(
            float(v) / 2,
            i,
            str(round(v, 2)),
            va="center",
            ha="center",
            color=team_color_text,
            fontweight="bold",
        )

    for i, v in enumerate(pref_df_T["FOR"].values):
        ax2.text(
            float(v) - 2,
            i,
            str(round(v, 2)),
            va="center",
            ha="right",
            color=team_color_text,
            fontweight="bold",
        )

    for i, v in enumerate(pref_df_T["AGAINST"].values):
        ax2.text(
            100 - 2, i, str(round(v, 2)), va="center", ha="right", color=team_color_text, fontweight="bold"
        )

    last_games_file = "" if not lastgames else f"-last{lastgames}"
    overview_fig_path = os.path.join(
        IMAGES_DIR, f"allcharts-yesterday-team-season-{situation}{last_games_file}.png"
    )
    overview_fig.savefig(overview_fig_path, bbox_inches="tight")
    return overview_fig_path
