""" Tests for 'helpers.arguments' module. """

# pylint: disable=protected-access

import json
import logging
import os
import sys
from datetime import datetime

import pytest
import responses

from hockeygamebot.helpers import arguments, utils


def test_invalid_arguments():
    with pytest.raises(SystemExit):
        assert arguments.parse_arguments(["--invalidargument"])
        assert arguments.parse_arguments(["", "--invalidargument"])
        assert arguments.parse_arguments(["", "--invalidkey", "value"])


def test_no_arguments():
    args = arguments.parse_arguments([])
    default_args = [
        args.console,
        args.date,
        args.debugsocial,
        args.discord,
        args.docker,
        args.localdata,
        args.notweets,
        args.overridelines,
        args.split,
        args.team,
        args.yesterday,
    ]
    assert not any(default_args)


def test_console_argument():
    args = arguments.parse_arguments(["--console"])
    assert args.console


def test_valid_date():
    dt = datetime(2019, 10, 4, 0, 0)
    args = arguments.parse_arguments(["--date", "2019-10-04"])
    date = utils.date_parser(args.date)

    assert args.date
    assert date == dt


def test_invalid_date():
    args = arguments.parse_arguments(["--date", "2019-42-69"])
    with pytest.raises(ValueError):
        assert utils.date_parser(args.date)


def test_debug_logging():
    args = arguments.parse_arguments(["--debug"])
    utils.setup_logging()
    assert logging.getLogger().getEffectiveLevel() == logging.DEBUG


def test_default_logging():
    arguments.parse_arguments([])
    utils.setup_logging()
    assert logging.getLogger().getEffectiveLevel() == logging.INFO
