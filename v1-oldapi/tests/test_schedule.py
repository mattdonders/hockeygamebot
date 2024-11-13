""" Tests for 'nhlapi.schedule' module. """

import json
import os
import responses

from hockeygamebot.helpers import utils
from hockeygamebot.nhlapi import schedule
from hockeygamebot.definitions import TESTS_RESOURCES_PATH


@responses.activate
def test_schedule_no_game():
    """Performs a test to verify an empty schedule is parsed correctly."""
    config = utils.load_config()
    date = utils.date_parser("2019-06-27")
    resp_file = os.path.join(TESTS_RESOURCES_PATH, "schedule_no_games.json")
    with open(resp_file, encoding="utf-8") as json_file:
        json_response = json.load(json_file)

    url = "https://statsapi.web.nhl.com/api/v1/schedule"

    responses.add(
        responses.GET,
        url,
        json=json_response,
        match_querystring=False,
        content_type="application/json",
    )

    game_today, game_info = schedule.is_game_today(1, date)

    assert not game_today
    assert game_info == json_response


@responses.activate
def test_schedule_one_game():
    """Performs a test to verify a schedule with 1 game is parsed correctly."""
    config = utils.load_config()
    date = utils.date_parser("2019-10-04")
    resp_file = os.path.join(TESTS_RESOURCES_PATH, "schedule_one_game.json")
    with open(resp_file, encoding="utf-8") as json_file:
        json_response = json.load(json_file)

    url = "https://statsapi.web.nhl.com/api/v1/schedule"
    responses.add(
        responses.GET,
        url,
        json=json_response,
        match_querystring=False,
        content_type="application/json",
    )

    game_today, game_info = schedule.is_game_today(1, date)
    assert game_today
    assert game_info == json_response["dates"][0]["games"][0]
