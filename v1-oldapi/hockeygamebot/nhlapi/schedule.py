"""
Functions pertaining to the NHL schedule (via API).
"""

# pylint: disable=redefined-builtin

import logging
import time
from datetime import datetime, timedelta
from dateutil.parser import parse

from hockeygamebot.helpers import arguments, process
from hockeygamebot.nhlapi import api, roster


def get_team_id(team_name):
    """Passes team name to NHL API and returns team ID.

    Args:
        team_name: Valid NHL team name.

    Returns:
        team_id: NHL Team ID
    """

    team_name = team_name.lower()
    endpoint = "/teams"
    response = api.nhl_api(endpoint)

    if not response:
        raise ConnectionError("An invalid response was returned from the NHL Teams API.")

    teams_json = response.json()
    teams = teams_json["teams"]

    team_id = None
    for team in teams:
        if team["name"].lower() == team_name:
            team_id = team["id"]
            break

    if not team_id:
        raise ValueError("{} is not a valid NHL team. Check your configuraiton file!".format(team_name))

    return team_id


def is_game_today(team_id, date):
    """Queries the NHL Schedule API to determine if there is a game today.

    Args:
        team_id (int) - The unique identifier of the team (from get_team function).

    Returns:
        (bool, games_info)
        bool - True if game today, False if not.
        games_info (dict) - A dictionary from the Schedule API that describes game information.
    """
    args = arguments.get_arguments()

    url = "/schedule?teamId={id}&expand=" "schedule.broadcasts,schedule.teams&date={date:%Y-%m-%d}".format(
        id=team_id, date=date
    )

    response = api.nhl_api(url)
    if response:
        schedule = response.json()
        games_total = schedule["totalItems"]
    else:
        return False, None

    if games_total == 1:
        games_info = schedule["dates"][0]["games"][0]
        return True, games_info

    if games_total == 2:
        if args.split is False:
            logging.info("Split Squad - spawning a second process to pick up second game.")
            game_index = 0
            process.spawn_another_process()
            time.sleep(10)
        else:
            game_index = 1
            logging.info("Split Squad - this is the process to pick up second game (sleep 5 seconds).")
            time.sleep(5)

        games_info = schedule["dates"][0]["games"][game_index]
        return True, games_info

    date_string = date.date() if args.date else "today"
    logging.info("There are no games scheduled for %s, SAD!", date_string)
    return False, schedule


def was_game_yesterday(team_id, date):
    """Determines if there was a game yesterday.

    Args:
        team_id (int) - The unique identifier of the team (from get_team function).

    Returns:
        (bool, games_info)
        bool - True if game today, False if not.
        games_info (dict) - A dictionary from the Schedule API that describes game information.
    """

    prev_game_date, prev_game = get_previous_game(team_id)
    yesterday = date - timedelta(days=1)
    prev_game_date_dt = parse(prev_game_date)

    prev_game_yesterday = bool(prev_game_date_dt.date() == yesterday.date())
    return prev_game_yesterday, prev_game


def get_broadcasts(resp):
    """Parses an NHL schedule response to get broadcast information.

    Args:
        resp: JSON response from NHL Schedule API call.

    Returns:
        broadcasts: Dictionary of home & away broadcasts.
    """
    broadcasts = {}

    # Set defaults in case one team doesn't have a broadcast yet
    # broadcasts["home"] = "TBD"
    # broadcasts["away"] = "TBD"

    try:
        resp_broadcasts = resp["broadcasts"]
        for broadcast in resp_broadcasts:
            broadcast_team = broadcast["type"]
            if broadcast_team == "national":
                broadcasts["away"] = broadcast["name"]
                broadcasts["home"] = broadcast["name"]
                break
            else:
                broadcast_channel = broadcast["name"]
                broadcasts[broadcast_team] = broadcast_channel
    except KeyError:
        logging.warning("Broadcasts not available - setting them to TBD.")
        broadcasts["home"] = "TBD"
        broadcasts["away"] = "TBD"

    return broadcasts


def get_next_game(today_game_date: datetime, team_id: int) -> dict:
    """Takes today's game date & the team ID to get the next game from the NHL API endpoint.

    Args:
        today_game_date (datetime) - The date of today's game.
        team_id (int) - The unique identifier of the team (from get_team function).

    Returns:
        next_game (dict) - Dictionary of next game attributes.
    """

    game_date = today_game_date.strftime("%Y-%m-%d")
    tomorrow = (today_game_date + timedelta(days=1)).strftime("%Y-%m-%d")
    end_date = (today_game_date + timedelta(days=365)).strftime("%Y-%m-%d")

    logging.info("Checking the schedule API endpoint for the next game.")
    url = f"schedule?teamId={team_id}&startDate={game_date}&endDate={end_date}"

    response = api.nhl_api(url)
    if not response:
        return None

    next_game_json = response.json()
    next_game = next_game_json.get("dates")[1].get("games")[0]

    return next_game


def get_previous_game(team_id: int) -> dict:
    """Takes a team ID & gets the previous game from the schedule API modified endpoint.

    Args:
        team_id (int) - The unique identifier of the team (from get_team function).

    Returns:
        date (string) - Date of last game
        next_game (dict) - Dictionary of previous game attributes.
    """

    logging.info("Checking the schedule API endpoint for the previous game.")
    url = f"teams/{team_id}?expand=team.schedule.previous"

    response = api.nhl_api(url)
    if not response:
        return None

    prev_game_json = response.json()
    prev_game_sched = prev_game_json.get("teams")[0].get("previousGameSchedule")
    prev_game_date = prev_game_sched.get("dates")[0].get("date")
    prev_game = prev_game_sched.get("dates")[0].get("games")[0]

    return prev_game_date, prev_game


def get_number_games(season: str, team_id: int, game_type_code: str = "R") -> dict:
    """Queries the NHL Schedule API to how many games are in this season.
        This is particularly important in the 2020-2021 shortened season.

    Args:
        season (str) - The 8-digit season code (ex: 20202021).
        team_id (int) - The unique identifier of the team (from get_team function).

    Returns:
        num_games (int) - The number of games played in the regular season.
    """
    args = arguments.get_arguments()

    endpoint = f"/schedule?teamId={team_id}&season={season}&gameType={game_type_code}"
    response = api.nhl_api(endpoint)

    if response:
        schedule = response.json()
        games_total = schedule["totalItems"]
        return games_total

    # If no valid response, just return default number of games (82)
    return 82


def season_series(game_id, pref_team, other_team, last_season=False):
    """Generates season series, points leader & TOI leader.

    Args:
        game_id
        pref_team:
        other_team:

    Returns:
        Tuple: (season_series_str, points_leader_str, toi_leader_str)
        season_series_str: Season Series (w/ records)
        points_leader_str: Points Leader(s)
        toi_leader_str: TOI Leader(s)
    """

    # Init empty dictionaries and lists
    games_against = list()
    pref_toi = dict()
    pref_goals = dict()
    pref_assists = dict()
    pref_points = dict()
    pref_record = {"wins": 0, "losses": 0, "ot": 0}
    roster_player = True

    # If this is the first game of the season, we can set the 'last_season' flag to enable the
    # season series function to check last year's season series between the two teams.
    if not last_season:
        season_start = str(game_id)[0:4]
        season_end = str(int(season_start) + 1)
        yesterday = datetime.now() - timedelta(days=1)
        # yesterday = datetime.now() + timedelta(days=50)
        # schedule_url = (
        #     f"/schedule?teamId={pref_team.team_id}"
        #     f"&expand=schedule.broadcasts,schedule.teams&startDate="
        #     f"{season_start}-08-01&endDate={yesterday:%Y-%m-%d}"
        # )
        schedule_url = (
            f"/schedule?teamId={pref_team.team_id}"
            f"&expand=schedule.broadcasts,schedule.teams"
            f"&season={season_start}{season_end}"
        )
    else:
        season_start = int(str(game_id)[0:4]) - 1
        season_end = str(int(season_start) + 1)
        yesterday = datetime.now() - timedelta(days=1)
        # yesterday = datetime.now() + timedelta(days=50)
        # schedule_url = (
        #     f"/schedule?teamId={pref_team.team_id}"
        #     f"&expand=schedule.broadcasts,schedule.teams&startDate="
        #     f"{season_start}-08-01&endDate={season_end}-06-01"
        # )
        schedule_url = (
            f"/schedule?teamId={pref_team.team_id}"
            f"&expand=schedule.broadcasts,schedule.teams"
            f"&season={season_start}{season_end}"
        )

    schedule = api.nhl_api(schedule_url).json()
    dates = schedule["dates"]

    # Loop through scheduled to get previously played games against
    for date in dates:
        game = date["games"][0]
        game_type = game["gameType"]
        game_id = game["gamePk"]
        game_team_home = game["teams"]["home"]["team"]["name"]
        game_team_away = game["teams"]["away"]["team"]["name"]
        teams = [game_team_away, game_team_home]
        game_status = game["status"]["abstractGameState"]
        if game_type == "R" and game_status == "Final" and other_team.team_name in teams:
            game_feed = f"/game/{game_id}/feed/live"
            games_against.append(game_feed)

    # If the two teams haven't played yet, just exit this function
    if not games_against:
        return None, None, None

    # Loop through newly created games_against list to get each stats
    for feed in games_against:
        game = api.nhl_api(feed).json()
        game_data = game["gameData"]
        home_team_name = game_data["teams"]["home"]["name"]
        pref_homeaway = "home" if home_team_name == pref_team.team_name else "away"
        other_homeaway = "away" if home_team_name == pref_team.team_name else "home"

        # Get season series
        end_period = game["liveData"]["linescore"]["currentPeriod"]
        extra_time = True if end_period > 3 else False
        pref_score = game["liveData"]["linescore"]["teams"][pref_homeaway]["goals"]
        other_score = game["liveData"]["linescore"]["teams"][other_homeaway]["goals"]
        if pref_score > other_score:
            pref_record["wins"] += 1
        elif other_score > pref_score and extra_time:
            pref_record["ot"] += 1
        else:
            pref_record["losses"] += 1

        season_series_str = f"Series: {pref_record['wins']}-" f"{pref_record['losses']}-{pref_record['ot']}"

        # Get stats leaders
        # pref_teamstats = game["liveData"]["boxscore"]["teams"][pref_homeaway]["teamStats"]
        pref_playerstats = game["liveData"]["boxscore"]["teams"][pref_homeaway]["players"]
        for id, player in pref_playerstats.items():
            try:
                # Calculate TOI
                player_toi_str = player["stats"]["skaterStats"]["timeOnIce"]
                player_toi_minutes = int(player_toi_str.split(":")[0])
                player_toi_seconds = int(player_toi_str.split(":")[1])
                player_toi = (player_toi_minutes * 60) + player_toi_seconds
                pref_toi[id] = pref_toi.get(id, 0) + player_toi

                # Point Totals
                player_goal_str = player["stats"]["skaterStats"]["goals"]
                pref_goals[id] = pref_goals.get(id, 0) + int(player_goal_str)
                player_assist_str = player["stats"]["skaterStats"]["assists"]
                pref_assists[id] = pref_assists.get(id, 0) + int(player_assist_str)
                player_points = int(player_goal_str) + int(player_assist_str)
                pref_points[id] = pref_points.get(id, 0) + int(player_points)

            except KeyError:
                pass

    # Calculate Stats Leaders
    sorted_toi = sorted(pref_toi.values(), reverse=True)
    leader_toi = sorted_toi[0]

    sorted_points = sorted(pref_points.values(), reverse=True)
    leader_points = sorted_points[0]

    # Get TOI leader
    for id in pref_toi.keys():
        if pref_toi[id] == leader_toi:
            player_name = roster.player_attr_by_id(pref_team.roster, id, "fullName")
            if player_name is None:
                roster_player = False
                player_id_only = id.replace("ID", "")
                player_name = roster.nonroster_player_attr_by_id(player_id_only, "fullName")
            leader_toi_avg = leader_toi / len(games_against)
            m, s = divmod(leader_toi_avg, 60)
            toi_m = int(m)
            toi_s = int(s)
            toi_s = "0{}".format(toi_s) if toi_s < 10 else toi_s
            toi_avg = "{}:{}".format(toi_m, toi_s)
            player_short_name = f"{player_name[0]}. {' '.join(player_name.split()[1:])}"
            toi_leader_str = "TOI Leader: {} with {} / game.".format(player_short_name, toi_avg)

    # Handle tied points leaders
    point_leaders = list()
    for id in pref_points.keys():
        if pref_points[id] == leader_points:
            point_leaders.append(id)

    if leader_points == 0:
        points_leader_str = "Points Leader: None (all players have 0 points)."

    elif len(point_leaders) == 1:
        leader = point_leaders[0]
        player_name = roster.player_attr_by_id(pref_team.roster, leader, "fullName")
        # If the player is no longer on the team, get their information (change string here?)
        if player_name is None:
            roster_player = False
            player_id_only = leader.replace("ID", "")
            player_name = roster.nonroster_player_attr_by_id(player_id_only, "fullName")
        player_goals = pref_goals[leader]
        player_assists = pref_assists[leader]
        if not roster_player:
            points_leader_str = (
                f"Points Leader: {player_name} with {leader_points} points "
                f"({player_goals}G {player_assists}A) "
            )
        else:
            points_leader_str = "Points Leader: {} with {} ({}G {}A).".format(
                player_name, leader_points, player_goals, player_assists
            )

    elif len(point_leaders) > 3:
        point_leaders_with_attrs = list()
        for leader in point_leaders:
            player_name = roster.player_attr_by_id(pref_team.roster, leader, "fullName")
            if player_name is None:
                player_id_only = leader.replace("ID", "")
                player_name = roster.nonroster_player_attr_by_id(player_id_only, "fullName")
            player_goals = pref_goals[leader]
            player_assists = pref_assists[leader]
            player_short_name = f"{player_name[0]}. {' '.join(player_name.split()[1:])}"
            point_leaders_with_attrs.append(player_short_name)

        point_leaders_joined = ", ".join(point_leaders_with_attrs[0:3])
        leftover_leaders = len(point_leaders) - 3
        points_leader_str = (
            f"Points Leaders: {point_leaders_joined} & {leftover_leaders} others ({leader_points} each)."
        )

    else:
        point_leaders_with_attrs = list()
        for leader in point_leaders:
            player_name = roster.player_attr_by_id(pref_team.roster, leader, "fullName")
            if player_name is None:
                player_id_only = leader.replace("ID", "")
                player_name = roster.nonroster_player_attr_by_id(player_id_only, "fullName")
            player_goals = pref_goals[leader]
            player_assists = pref_assists[leader]
            player_short_name = f"{player_name[0]}. {' '.join(player_name.split()[1:])}"
            player_str = f"{player_short_name} ({player_goals}G {player_assists}A)"
            point_leaders_with_attrs.append(player_str)

        point_leaders_joined = (
            f", ".join(point_leaders_with_attrs[:-1]) + f" & {point_leaders_with_attrs[-1]}"
        )
        points_leader_str = "Points Leaders: {} with {} each.".format(point_leaders_joined, leader_points)

    return season_series_str, points_leader_str, toi_leader_str


def get_playoff_info(pref_team_id, season):
    """Queries the NHL Tournament API to get information about playoff series."""

    url = f"/tournaments/playoffs?expand=round.series,schedule.game.seriesSummary&season={season}"
    response = api.nhl_api(url)

    if not response:
        return False

    playoffs = response.json()
    default_round = playoffs["defaultRound"]
    current_round = [x for x in playoffs["rounds"] if x["code"] == default_round][0]

    current_round_series = current_round["series"]
    for i in current_round_series:
        matchup_teams = i["matchupTeams"]
        for team in matchup_teams:
            if team["team"]["id"] == pref_team_id:
                current_round_series_pref = i
                break

    return current_round_series_pref
