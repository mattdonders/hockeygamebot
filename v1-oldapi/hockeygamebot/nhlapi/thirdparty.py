"""
This module contains functions related to gathering information
from non NHL APIs & websites (ex - lineups, officials, etc).
"""

import logging
from datetime import datetime, timedelta

import lxml
import requests
from bs4 import BeautifulSoup
from dateutil.parser import parse
from fake_useragent import UserAgent
from requests.adapters import HTTPAdapter

from hockeygamebot.helpers import arguments, utils
from hockeygamebot.models.sessions import SessionFactory
from hockeygamebot.models.team import Team
from hockeygamebot.models.game import Game


def thirdparty_request(url, headers=None):
    """Handles all third-party requests / URL calls.

    Args:
        url: URL of the website to call
        headers: Optional headers (ex - fake User Agent)

    Returns:
        response: response from the website (requests.get)
    """

    sf = SessionFactory()
    session = sf.get()

    retries = HTTPAdapter(max_retries=3)
    session.mount("https://", retries)
    session.mount("http://", retries)

    # Setup a Fake User Agent (simulates a real visit)
    # ua = UserAgent(cache=False)
    # ua_header = {"User-Agent": str(ua.chrome)}
    ua_header = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.77 Safari/537.36"
    }
    if headers:
        headers.update(ua_header)
    else:
        headers = ua_header
    # headers = ua_header if not headers else headers
    # headers = headers.update(ua_header)
    # print(headers)

    try:
        logging.info("Sending Third Party URL Request - %s", url)
        response = session.get(url, headers=headers, timeout=5)
        return response
    except requests.ConnectionError as ce:
        logging.error(ce)
        return None
    except requests.RequestException as re:
        logging.error(re)
        return None


def bs4_parse(content):
    """Instead of speficying lxml every time, we define this function and pass
        any content that requires scraping to it.

    Args:
        content: A response from the requests library

    Returns:
        A souped response
    """
    try:
        return BeautifulSoup(content, "lxml")
    except TypeError as e:
        logging.error(e)
        return None


def nst_abbreviation(team_name: str) -> str:
    """Returns the 3-character team abbreviation used in Shift Charts & therefore by most other
        third party stats sites (ex - N.J instead of NJD).

    Args:
        team_name: NHL Team Name

    Returns:
        nss_team: 3-character team abbreviation used at NSS
    """

    team_name = team_name.replace("é", "e")
    nss_teams = {
        "Anaheim Ducks": "ANA",
        "Arizona Coyotes": "ARI",
        "Boston Bruins": "BOS",
        "Buffalo Sabres": "BUF",
        "Carolina Hurricanes": "CAR",
        "Columbus Blue Jackets": "CBJ",
        "Calgary Flames": "CGY",
        "Chicago Blackhawks": "CHI",
        "Colorado Avalanche": "COL",
        "Dallas Stars": "DAL",
        "Detroit Red Wings": "DET",
        "Edmonton Oilers": "EDM",
        "Florida Panthers": "FLA",
        "Los Angeles Kings": "L.A",
        "Minnesota Wild": "MIN",
        "Montreal Canadiens": "MTL",
        "New Jersey Devils": "N.J",
        "Nashville Predators": "NSH",
        "New York Islanders": "NYI",
        "New York Rangers": "NYR",
        "Ottawa Senators": "OTT",
        "Philadelphia Flyers": "PHI",
        "Pittsburgh Penguins": "PIT",
        "San Jose Sharks": "S.J",
        "Seattle Kraken": "SEA",
        "St. Louis Blues": "STL",
        "Tampa Bay Lightning": "T.B",
        "Toronto Maple Leafs": "TOR",
        "Vancouver Canucks": "VAN",
        "Vegas Golden Knights": "VGK",
        "Winnipeg Jets": "WPG",
        "Washington Capitals": "WSH",
    }
    return nss_teams[team_name]


def get_nst_stat(list, index):
    if list[index].text == "-":
        return "N/A"
    try:
        return list[index].text
    except ValueError:
        return "N/A"


def nst_linetool(game: Game, team: Team):
    """Scrapes Natural Stat Trick's Limited Report to get advanced stats for forward lines
        and defensive pairings.

        #TODO: Defensive Pairings are manually calc'd & retrieved.
               https://twitter.com/Sammich_BLT/status/1154007222634065920?s=20

    Args:
        game (game): An NHL Game Event game object.
        team (Team): A NHL Game Event team object.

    Returns:
        TBD
    """

    urls = utils.load_urls()
    nst_base = urls["endpoints"]["nst"]

    nst_rpt_url = (
        f"{nst_base}/game.php?season={game.season}&view=limited"
        f"&game={game.game_id_gametype_shortid}{game.game_id_shortid}"
    )

    logging.info("Requesting & souping the Natural Stat Trick limited report.")
    resp = thirdparty_request(nst_rpt_url)
    soup = bs4_parse(resp.content)

    # Find the Forward Lines label & then the corresponding 5v5 table on the soup'd page
    nst_abrv = nst_abbreviation(team_name=team.team_name)
    nst_abrv_nopd = nst_abrv.replace(".", "")

    # fwd_lines_header = f'{team.short_name} - Forward Lines'
    fwd_lines_label = soup.find("label", {"for": f"{nst_abrv_nopd}fltg"})
    fwd_lines = fwd_lines_label.parent
    fwd_lines_5v5 = fwd_lines.find("div", class_="t5v5 datadiv").find("tbody")
    fwd_lines_5v5_rows = fwd_lines_5v5.find_all("tr")

    for idx, line in enumerate(fwd_lines_5v5_rows):
        line_stats = list()
        line = line.find_all("td")
        line_players = "-".join([" ".join(x.text.split()[1:]) for x in line][0:3])
        line_toi = float(line[3].text)
        line_toi_mm = int(line_toi)
        line_toi_ss = (line_toi * 60) % 60
        line_toi_mmss = "%02d:%02d" % (line_toi_mm, line_toi_ss)
        line_cf_pct = get_nst_stat(line, 6)
        line_cfpct_rel = get_nst_stat(line, 7)
        line_gf_pct = get_nst_stat(line, 18)
        line_scf_pct = get_nst_stat(line, 22)
        line_hdcf_pct = get_nst_stat(line, 26)
        line_stats.extend(
            [
                line_players,
                line_toi_mmss,
                line_cf_pct,
                line_cfpct_rel,
                line_gf_pct,
                line_scf_pct,
                line_hdcf_pct,
            ]
        )

        if idx == 0:
            # Headers (Centered)
            print(
                "{: ^25s} {: ^10s} {: ^10s} {: ^10s} {: ^10s} {: ^10s} {: ^10s}".format(
                    "Players", "TOI", "CF%", "CF% REL", "GF%", "SCF%", "HDCF%"
                )
            )
            # Dashes (not very readable, but I'm lazy)
            print("-" * 25 + " " + " ".join([("-" * 10)] * 6))

        print("{:25s} {:^10s} {:^10s} {:^10s} {:^10s} {:^10s} {:^10s}".format(*line_stats))

    # print(f"{line_players} ({line_toi_mmss}) \t CF% {line_cf_pct} \t CF% REL {line_cfpct_rel} \t "
    #         f"GF% {line_gf_pct} \t SCF% {line_scf_pct} \t HDCF% {line_hdcf_pct}")


def hockeyref_goalie_against_team(goalie, opponent):
    """Scrapes Hockey Reference for starting goalies for the night.

    Args:
        goalie: The name of the goalie we want to look up.
        opponent: The team we want to check the above goalie's stats for

    Returns:
        goalie_stats_split: A string of goalie stats split versus opponent
    """

    urls = utils.load_urls()
    hockeyref_base = urls["endpoints"]["hockeyref_base"]

    # Form the Hockey Reference specific player name format
    goalie_name_orig = goalie
    goalie_name = goalie.lower()
    goalie_first_name = goalie_name.split()[0]
    goalie_last_name = goalie_name.split()[1]
    goalie_hockeyref_name = f"{goalie_last_name[0:5]}{goalie_first_name[0:2]}01"

    logging.info("Trying to get goalie split information for %s against the %s.", goalie, opponent)
    hockeyref_url = f"{hockeyref_base}/{goalie_last_name[0]}/{goalie_hockeyref_name}/splits"
    resp = thirdparty_request(hockeyref_url)

    # If we get a bad response from the function above, return False
    if resp is None:
        return False

    soup = bs4_parse(resp.content)
    if soup is None:
        return False

    hr_player_info = soup.find("div", attrs={"itemtype": "https://schema.org/Person"})
    hr_player_info_attr = hr_player_info.find_all("p")
    hr_name = soup.find("h1", attrs={"itemprop": "name"}).text.strip()

    for attr in hr_player_info_attr:
        if "Position:" in attr.text:
            hr_position_goalie = bool("Position: G" in attr.text.rstrip())
            break

    # If the goalie name doesn't match exactly or the player position is not goalie, try Player 02
    if hr_name.lower() != goalie_name_orig.lower() or not hr_position_goalie:
        logging.warning("%s is not who we are looking for, or is not a goalie - trying 02.", hr_name)
        goalie_hockeyref_name = f"{goalie_last_name[0:5]}{goalie_first_name[0:2]}02"
        hockeyref_url = f"{hockeyref_base}/{goalie_last_name[0]}/{goalie_hockeyref_name}/splits"
        resp = thirdparty_request(hockeyref_url)
        soup = bs4_parse(resp.content)

    split_rows = soup.find("table", {"id": "splits"}).find("tbody").find_all("tr")
    for row in split_rows:
        cells = row.find_all("td")
        team_row = row.find("td", attrs={"data-stat": "split_value"})
        team_name = team_row.text if team_row is not None else "None"

        if team_name == opponent:
            wins = cells[2].text
            loss = cells[3].text
            ot = cells[4].text
            sv_percent = cells[8].text
            gaa = cells[9].text
            shutout = cells[10].text

            goalie_stats_split = "{}-{}-{} W-L | {} GAA | 0{} SV% | {} SO".format(
                wins, loss, ot, gaa, sv_percent, shutout
            )
            return goalie_stats_split

    goalie_no_stats = "None (First Game)"
    return goalie_no_stats


def dailyfaceoff_lines_parser(lines, soup):
    """A sub-function of the dailyfaceoff_lines(...) that takes a BS4 Soup
        and parses it to break it down by individual player & position.

    Args:
        lines: Existing lines dictionary (append)
        soup: A valid souped response

    Return:
        lines: Modified lines dictionary
    """

    for player in soup:
        try:
            soup_position = player["id"]
            line = soup_position[-1]
            position = soup_position[0:-1]
            player_position = f"{line}{position}"
            name = player.find("a").text

            # Add player & position to existing lines dictionary
            lines[player_position] = name
        except KeyError:
            pass  # This is a valid exception - not a player.

    return lines


def dailyfaceoff_lines(game, team):
    """Parse Daily Faceoff lines page to get lines dictionary.
       Used for pre-game tweets & advanced stats.

    Args:
        game (game): An NHL Game Event game object.
        team (Team): A NHL Game Event team object.

    Returns:
        Dictionary: confirmed, forwards, defense, powerplay
    """

    # Instantiate blank dictionaries
    return_dict = dict()
    fwd_lines = dict()
    def_lines = dict()
    lines = dict()

    urls = utils.load_urls()
    df_linecombos_url = urls["endpoints"]["df_line_combos"]

    # Setup a Fake User Agent (simulates a real visit)
    # ua = UserAgent(cache=False)
    # ua_header = {"User-Agent": str(ua.chrome)}
    ua_header = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.77 Safari/537.36"
    }

    df_team_encoded = team.team_name.replace(" ", "-").replace("é", "e").replace(".", "").lower()
    df_lines_url = df_linecombos_url.replace("TEAMNAME", df_team_encoded)

    logging.info("Requesting & souping the Daily Faceoff lines page.")
    resp = thirdparty_request(df_lines_url, headers=ua_header)
    soup = bs4_parse(resp.content)

    # Grab the last update line from Daily Faceoff
    # If Update Time != Game Date, return not confirmed
    soup_update = soup.find("div", class_="team-line-combination-last-updated")
    last_update = last_update = [x for x in soup_update.text.split("\n") if x][0]
    last_update_cleaned = last_update.strip().split(": ")[1].replace("@", "")
    last_update_date = parse(last_update_cleaned)
    game_day = parse(game.game_date_local)

    confirmed = bool(last_update_date.date() == game_day.date())
    return_dict["confirmed"] = confirmed
    if not confirmed:
        return return_dict

    # If the lines are confirmed (updated today) then parse & return
    combos = soup.find("div", class_="team-line-combination-wrap")
    soup_forwards = combos.find("table", {"id": "forwards"}).find("tbody").find_all("td")
    soup_defense = combos.find("table", {"id": "defense"}).find("tbody").find_all("td")

    # fwd_lines = dailyfaceoff_lines_parser(lines, soup_forwards)
    # def_lines = dailyfaceoff_lines_parser(lines, soup_defense)
    fwd_lines = dailyfaceoff_lines_parser(fwd_lines, soup_forwards)
    def_lines = dailyfaceoff_lines_parser(def_lines, soup_defense)

    # dict1.update(dict2) merges the two dictionaries together
    # res = {**dict1, **dict2}
    all_lines = {**fwd_lines, **def_lines}

    # Put the lines in the return dictionary
    # And set the property on the team object
    return_dict["fwd"] = fwd_lines
    return_dict["def"] = def_lines
    return_dict["lines"] = all_lines

    # Now create the forward & defense strings
    # Iterate over the forwards dictionary & take into account 11/7 lineups
    fwd_line_string = list()
    fwd_all_list = list()

    fwd_num = len(fwd_lines.items())
    for idx, (_, player) in enumerate(fwd_lines.items()):
        last_name = " ".join(player.split()[1:])
        fwd_line_string.append(last_name)
        if len(fwd_line_string) == 3 or (idx + 1) == fwd_num:
            fwd_line_string = " - ".join(fwd_line_string)
            fwd_all_list.append(fwd_line_string)
            fwd_line_string = list()

    # Iterate over the defense dictionary & take into account 11/7 lineups
    def_line_string = list()
    def_all_list = list()

    def_num = len(def_lines.items())
    for idx, (_, player) in enumerate(def_lines.items()):
        last_name = " ".join(player.split()[1:])
        def_line_string.append(last_name)
        if len(def_line_string) == 2 or (idx + 1) == def_num:
            def_line_string = " - ".join(def_line_string)
            def_all_list.append(def_line_string)
            def_line_string = list()

    # Combine the 'all-strings' separated by new lines
    fwd_all_string = "\n".join(fwd_all_list)
    def_all_string = "\n".join(def_all_list)
    return_dict["fwd_string"] = fwd_all_string
    return_dict["def_string"] = def_all_string

    team.lines = all_lines

    return return_dict


def scouting_the_refs(game, pref_team):
    """Scrapes Scouting the Refs for referee information for the night.

    Args:
        game: Game Object
        pref_team (Team): Preferred team object.

    Returns:
        Tuple: dictionary {goalie string, goalie confirmed}
    """

    def calculate_total_games(ref_info):
        # Takes a referee dictionary & returns number of total games (centralizes logic)
        career_games_str = ref_info.get("careergames", "0")
        if "|" in career_games_str:
            total_games = sum([int(x) for x in career_games_str.split(" | ")])
        else:
            total_games = sum([int(x) for x in career_games_str.split(" / ")])
        return total_games

    # Initialized return dictionary
    return_dict = dict()
    return_dict["confirmed"] = False

    urls = utils.load_urls()
    refs_url = urls["endpoints"]["scouting_refs"]
    logging.info("Getting officials information from Scouting the Refs!")
    response = thirdparty_request(refs_url).json()

    # If we get a bad response from the function above, return False
    if response is None:
        return False

    for post in response:
        categories = post.get("categories")
        post_date = parse(post.get("date"))
        posted_today = bool(post_date.date() == datetime.today().date())
        post_title = post.get("title").get("rendered")
        if (921 in categories and posted_today) or (
            posted_today and "NHL Referees and Linesmen" in post_title
        ):
            # if 921 in categories:     # This line is uncommented for testing on non-game days
            content = post.get("content").get("rendered")
            soup = bs4_parse(content)
            break
    else:
        logging.warning("BS4 result is empty - either no posts found or bad scraping.")
        return return_dict

    # TESTING: This section gets commented out when needed for testing.
    # soup = BeautifulSoup(
    #     requests.get(
    #         "https://scoutingtherefs.com/2019/04/25706/tonights-nhl-referees-and-linesmen-4-6-19/"
    #     ).content,
    #     "lxml",
    # )

    # If we get some bad soup, return False
    if soup is None:
        logging.warning("BS4 result is empty - either no posts found or bad scraping.")
        return return_dict

    games = soup.find_all("h1")
    for game in games:
        if pref_team.team_name in game.text:
            game_details = game.find_next("table")
            break
    else:
        logging.warning("No game details found - your team is probably not playing today.")
        return return_dict

    return_referees = list()
    return_linesmen = list()

    # This Section uses List Comprehension & Indeces to Keep Track of Row Values
    idx_ref = next(
        i for i, x in enumerate(game_details.find_all("tr")) if x.text.lower().strip() == "referees"
    )
    idx_ref_names = idx_ref + 1

    idx_line = next(
        i for i, x in enumerate(game_details.find_all("tr")) if x.text.lower().strip() == "linesmen"
    )
    idx_line_names = idx_line + 1

    idx_season_gms = [i for i, x in enumerate(game_details.find_all("tr")) if "22-23" in x.text.lower()]
    idx_season_gms_ref = idx_season_gms[0]
    idx_season_gms_line = idx_season_gms[1]

    idx_career_gms = [
        i for i, x in enumerate(game_details.find_all("tr")) if "career games" in x.text.lower()
    ]
    idx_career_gms_ref = idx_career_gms[0]
    idx_career_gms_line = idx_career_gms[1]

    idx_penalty_gm = next(i for i, x in enumerate(game_details.find_all("tr")) if "penl/gm" in x.text.lower())

    refs = game_details.find_all("tr")[idx_ref_names].find_all("td")
    refs_season_games = game_details.find_all("tr")[idx_season_gms_ref].find_all("td")
    refs_career_games = game_details.find_all("tr")[idx_career_gms_ref].find_all("td")
    refs_penalty_game = game_details.find_all("tr")[idx_penalty_gm].find_all("td")
    for i, ref in enumerate(refs):
        ref_name = ref.text.strip()
        ref_season_games = refs_season_games[i].text
        ref_career_games = refs_career_games[i].text
        ref_penalty_game = refs_penalty_game[i].text.split(" (")[0]
        if ref_name:
            ref_dict = dict()
            ref_dict["name"] = ref_name
            ref_dict["seasongames"] = ref_season_games
            ref_dict["careergames"] = ref_career_games
            ref_dict["penaltygame"] = ref_penalty_game
            ref_dict["totalgames"] = calculate_total_games(ref_dict)
            print(ref_dict)
            return_referees.append(ref_dict)

    linesmen = game_details.find_all("tr")[idx_line_names].find_all("td")
    linesmen_season_games = game_details.find_all("tr")[idx_season_gms_line].find_all("td")
    linesmen_career_games = game_details.find_all("tr")[idx_career_gms_line].find_all("td")
    for i, linesman in enumerate(linesmen):
        linesman_name = linesman.text.strip()
        linesman_season_games = linesmen_season_games[i].text
        linesman_career_games = linesmen_career_games[i].text
        if linesman_name:
            linesman_dict = dict()
            linesman_dict["name"] = linesman_name
            linesman_dict["seasongames"] = linesman_season_games
            linesman_dict["careergames"] = linesman_career_games
            linesman_dict["totalgames"] = calculate_total_games(linesman_dict)
            print(linesman_dict)
            return_linesmen.append(linesman_dict)

    return_dict["referees"] = return_referees
    return_dict["linesmen"] = return_linesmen
    return_dict["confirmed"] = False if not bool(return_dict) else True
    logging.debug("Scouting the Refs - %s", return_dict)
    return return_dict


def dailyfaceoff_goalies(pref_team, other_team, pref_homeaway, game_date):
    """Scrapes Daily Faceoff for starting goalies for the night.

    Args:
        pref_team (Team): Preferred team object.
        other_team (Team): Other team object.
        pref_homeaway (str): Is preferred team home or away?
        game_date: Game date to add to DF URL

    Returns:
        Tuple: dictionary {goalie string, goalie confirmed}
    """
    return_dict = {}
    urls = utils.load_urls()
    args = arguments.get_arguments()

    df_goalies_url = urls["endpoints"]["df_starting_goalies"]
    df_goalies_url = f"{df_goalies_url}{game_date}"
    df_linecombos_url = urls["endpoints"]["df_line_combos"]

    logging.info("Trying to get starting goalie information via Daily Faceoff.")
    cache_headers = {"cache-control": "max-age=0"}
    resp = thirdparty_request(df_goalies_url, headers=cache_headers)

    # If we get a bad response from the function above, return False
    if resp is None:
        return False

    soup = bs4_parse(resp.content)
    if soup is None:
        return False

    logging.info("Valid response received & souped - parse the Daily Faceoff page!")
    pref_team_name = pref_team.team_name

    games = soup.find_all("div", class_="starting-goalies-card stat-card")
    team_playing_today = any(pref_team_name in game.text for game in games)
    if games and team_playing_today:
        for game in games:
            teams = game.find("h4", class_="top-heading-heavy").text
            # If the preferred team is not in this matchup, skip this loop iteration
            if pref_team_name not in teams:
                continue

            teams_split = teams.split(" at ")
            home_team = teams_split[1]
            away_team = teams_split[0]
            goalies = game.find("div", class_="stat-card-main-contents")

            away_goalie_info = goalies.find("div", class_="away-goalie")
            away_goalie_name = away_goalie_info.find("h4").text.strip()
            away_goalie_confirm = away_goalie_info.find("h5", class_="news-strength")
            away_goalie_confirm = str(away_goalie_confirm.text.strip())
            away_goalie_stats = away_goalie_info.find("p", class_="goalie-record")
            away_goalie_stats_str = " ".join(away_goalie_stats.text.strip().split())

            away_goalie = dict()
            away_goalie["name"] = away_goalie_name
            away_goalie["confirm"] = away_goalie_confirm
            away_goalie["season"] = away_goalie_stats_str

            home_goalie_info = goalies.find("div", class_="home-goalie")
            home_goalie_name = home_goalie_info.find("h4").text.strip()
            home_goalie_confirm = home_goalie_info.find("h5", class_="news-strength")
            home_goalie_confirm = str(home_goalie_confirm.text.strip())
            home_goalie_stats = home_goalie_info.find("p", class_="goalie-record")
            home_goalie_stats_str = " ".join(home_goalie_stats.text.strip().split())

            home_goalie = dict()
            home_goalie["name"] = home_goalie_name
            home_goalie["confirm"] = home_goalie_confirm
            home_goalie["season"] = home_goalie_stats_str

            if pref_homeaway == "home":
                return_dict["pref"] = home_goalie
                return_dict["other"] = away_goalie
                return_dict["pref"]["homeaway"] = "home"
                return_dict["other"]["homeaway"] = "away"
            else:
                return_dict["pref"] = away_goalie
                return_dict["other"] = home_goalie
                return_dict["pref"]["homeaway"] = "away"
                return_dict["other"]["homeaway"] = "home"

            return_dict["home"] = home_goalie
            return_dict["away"] = away_goalie
            return return_dict

    # If there is any issue parsing the Daily Faceoff page, grab a goalie from each team
    else:
        logging.info(
            "There was an issue parsing the Daily Faceoff page, "
            "grabbing a goalie from each individual team's line combinations page."
        )
        pref_team_encoded = pref_team.team_name.replace(" ", "-").replace("é", "e").lower()
        other_team_encoded = other_team.team_name.replace(" ", "-").replace("é", "e").lower()
        df_url_pref = df_linecombos_url.replace("TEAMNAME", pref_team_encoded)
        df_url_other = df_linecombos_url.replace("TEAMNAME", other_team_encoded)

        logging.info("Getting a fallback goalie for the preferred team.")
        resp = thirdparty_request(df_url_pref)
        soup = bs4_parse(resp.content)
        goalie_table = soup.find("table", attrs={"summary": "Goalies"}).find("tbody").find_all("tr")
        pref_goalie_name = goalie_table[0].find_all("td")[0].find("a").text

        logging.info("Getting a fallback goalie for the other team.")
        resp = thirdparty_request(df_url_other)
        soup = bs4_parse(resp.content)
        goalie_table = soup.find("table", attrs={"summary": "Goalies"}).find("tbody").find_all("tr")
        other_goalie_name = goalie_table[0].find_all("td")[0].find("a").text

        return_dict["pref_goalie"] = pref_goalie_name
        return_dict["pref_goalie_confirm"] = "Not Found"
        return_dict["other_goalie"] = other_goalie_name
        return_dict["other_goalie_confirm"] = "Not Found"

        return return_dict

    return True


def hockeystatcard_gamescores(game: Game):
    """Uses the Hockey Stat Cards API to retrieve gamescores for the current game.
        Returns two lists of game scores - one for the home team and one for the away team.

    Args:
        game (Game): Current Game object.

    Returns:
        gamescores (tuple):  (home_gs, away_gs)
    """

    urls = utils.load_urls()
    hsc_base = urls["endpoints"]["hockey_stat_cards"]

    hsc_season = f"{game.season[2:4]}{game.season[6:8]}"
    hsc_gametype = "ps" if game.game_id_gametype_shortid == "1" else "rs"
    hsc_nst_num = int(f"{game.game_id_gametype_id}{game.game_id_shortid}")
    hsc_game_num = None

    hsc_games_url = f"{hsc_base}/get-games?date={game.game_date_local}&y={hsc_season}&s={hsc_gametype}"
    resp = thirdparty_request(hsc_games_url)

    # If we get a bad response from the function above, return False
    if resp is None:
        return False

    hsc_games_json = resp.json()
    hsc_games = hsc_games_json["gameList"]

    for hsc_game in hsc_games:
        if hsc_nst_num == hsc_game["nstnum"]:
            hsc_game_num = hsc_game["gamenum"]
            logging.info("Hockey Stat Cards valid game found - HSC Game #%s", hsc_game_num)
            break

    # If we don't have a valid Hockey Stat Cards game number, return False
    if not hsc_game_num:
        return False

    hsc_gs_url = f"{hsc_base}/get-gamescore-card/{hsc_game_num}?date={game.game_date_local}&y={hsc_season}&s={hsc_gametype}"
    resp = thirdparty_request(hsc_gs_url)

    # If we get a bad response from the function above, return False
    if resp is None:
        return False

    home_team = game.home_team.team_name
    home_abbrev = nst_abbreviation(team_name=home_team).replace(".", "")
    # home_abbrev = game.home_team.tri_code
    away_team = game.away_team.team_name
    away_abbrev = nst_abbreviation(team_name=away_team).replace(".", "")
    # away_abbrev = game.away_team.tri_code

    hsc_gs = resp.json()
    home_gs = list()
    away_gs = list()
    # all_player_data = hsc_gs['playerData'] + hsc_gs['goalieData']
    all_player_data = hsc_gs["playerData"]

    # home_gs = [
    #     x for x in all_player_data if x["team"] == home_abbrev or home_team.replace(" ", "_") in x["src"]
    # ]
    # away_gs = [
    #     x for x in all_player_data if x["team"] == away_abbrev or away_team.replace(" ", "_") in x["src"]
    # ]

    home_gs = [x for x in all_player_data if x["team"] == home_abbrev]
    away_gs = [x for x in all_player_data if x["team"] == away_abbrev]

    # This [:5] returns the top 5 values only - leave this out and return all for better functionality.
    # home_gs_sorted = sorted(home_gs, key = lambda i: i['GameScore'], reverse=True)[:5]
    # away_gs_sorted = sorted(away_gs, key = lambda i: i['GameScore'], reverse=True)[:5]
    home_gs_sorted = sorted(home_gs, key=lambda i: i["GameScore"], reverse=True)
    away_gs_sorted = sorted(away_gs, key=lambda i: i["GameScore"], reverse=True)

    game_scores = (home_gs_sorted, away_gs_sorted)
    return game_scores
