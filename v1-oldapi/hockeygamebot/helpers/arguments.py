"""
This module deals with parsing of command line arguments
or environment variables (if using Docker containers).
"""

# Disable global statement warnings as we use it for "singletone" Arguments
# pylint: disable=global-statement

import argparse
import os
import sys

import pytz

# from hockeygamebot.definitions import CONFIG_PATH

# Set global ARGS to None until parsed
CONSOLE_ARGS = None


def _parse_local_arguments(sysargs):
    """
    Parses arguments passed into the python script on the command line.command

    Input:
    None

    Output:
    args - argument Namespace
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--notweets", help="log tweets to console instead of Twitter", action="store_true"
    )
    parser.add_argument("--console", help="log to console instead of file", action="store_true")
    parser.add_argument("--debug", help="print debug log items", action="store_true")
    parser.add_argument("--team", help="override team in configuration", action="store")
    parser.add_argument("--debugtweets", help="send tweets from debug account", action="store_true")
    parser.add_argument("--debugsocial", help="use debug social accounts", action="store_true")
    parser.add_argument("--localdata", help="use local data instead of API", action="store_true")
    parser.add_argument(
        "--overridelines", help="override lines if None are returned", action="store_true"
    )
    parser.add_argument(
        "--yesterday", help="get yesterday game on the schedule", action="store_true"
    )
    parser.add_argument("--date", help="override game date", action="store")
    parser.add_argument("--split", help="split squad game index", action="store_true")
    parser.add_argument("--docker", help="running in a docker container", action="store_true")
    parser.add_argument("--discord", help="Send messages to discord channel", action="store_true")
    parser.add_argument(
        "--config", help="Overrides the config.yaml with another filename.", action="store"
    )
    parser.add_argument("-v", help="Increased verbosity.", action="store_true")
    arguments = parser.parse_args() if sysargs is None else parser.parse_args(sysargs)
    return arguments


def _parse_env_variables(args):
    """
    For when running via Docker, parse Environment variables.
    Environment variables replace command line arguments.

    Args:
        args - argument Namespace

    Returns:
        None
    """

    if "ARGS_NOTWEETS" in os.environ and os.environ["ARGS_NOTWEETS"] == "TRUE":
        args.notweets = True

    if "ARGS_DEBUG" in os.environ and os.environ["ARGS_DEBUG"] == "TRUE":
        args.debug = True

    if "ARGS_TEAM" in os.environ:
        args.team = os.environ["ARGS_TEAM"]

    if "ARGS_DEBUGSOCIAL" in os.environ and os.environ["ARGS_DEBUGSOCIAL"] == "TRUE":
        args.debugsocial = True

    if "ARGS_DATE" in os.environ:
        args.date = os.environ["ARGS_DATE"]


def parse_arguments(sysargs=None):
    """Executes local argument parsing and then checks for Docker arguments.

    Args:
        None

    Returns:
        args: Arguments Namespace
    """
    args = _parse_local_arguments(sysargs)

    # If running in Docker, parse environment variables (instead of arguments)
    # And set args.console to True to make `docker logs` easier to use
    if args.docker:
        # Check if a config file exists (needs to be manually copied via docker run command)
        DOCKER_CONFIG = "/app/hockeygamebot/config/config.yaml"
        if not os.path.exists(DOCKER_CONFIG):
            print(
                "[ERROR] Docker requires a configuration file to be passed into the `docker run` command."
            )
            print(
                "[ERROR] Sample: docker run -v /local/path/to/config.yaml:/app/hockeygamebot/config/config.yaml mattdonders/nhl-twitter-bot:latest"
            )
            sys.exit()

        # Force console argument & parse the remainder of the environment variables
        args.console = True
        _parse_env_variables(args)

    global CONSOLE_ARGS
    CONSOLE_ARGS = args
    # return args
    return CONSOLE_ARGS


def get_arguments():
    global CONSOLE_ARGS
    if CONSOLE_ARGS is None:
        parse_arguments()
    return CONSOLE_ARGS


# optional: delete function after use to prevent calling from other place
# del _parse_arguments
