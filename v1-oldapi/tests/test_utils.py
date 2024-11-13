""" Tests for 'utils.py' module. """

import pytest

from hockeygamebot.helpers import utils


def test_load_config():
    assert utils.load_config()["endpoints"]["nhl_base"] == "https://statsapi.web.nhl.com"
