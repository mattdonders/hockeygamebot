"""
This module contains all functions pertaining spawning a second process of the Game bot.
This is mainly used for split squad games.
"""

import logging
import os
import sys
from subprocess import Popen

from hockeygamebot.definitions import PROJECT_ROOT
from hockeygamebot.helpers import arguments


def spawn_another_process():
    """Spawns a second process of the hockeygamebot (for split squad games)."""
    args = arguments.get_arguments()

    if args.date is not None:
        python_exec = sys.executable
        script_path = os.path.join(PROJECT_ROOT, "app.py")
        spawn_args = " ".join(sys.argv[1:])
        full_exec = [
            "{python} {script} --split {args}".format(
                python=python_exec, script=script_path, args=spawn_args
            )
        ]

        logging.debug("Spawning Process: %s", full_exec)
        Popen(full_exec, shell=True)
    else:
        python_exec = sys.executable
        script_path = os.path.join(PROJECT_ROOT, "app.py")
        spawn_args = " ".join(sys.argv[1:])
        full_exec = [
            "{python} {script} --split {args}".format(
                python=python_exec, script=script_path, args=spawn_args
            )
        ]
        logging.debug("Spawning Process: %s", full_exec)
        # Popen(["nohup python3 " + dirname + "/hockey_twitter_bot.py --split &"], shell=True)
        Popen(full_exec, shell=True)
