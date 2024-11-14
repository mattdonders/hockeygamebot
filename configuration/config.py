# config.py

import os

import yaml

from paths import CONFIG_PATH


def load_config():
    """Loads the configuration YAML file and returns a dictionary."""
    with open(CONFIG_PATH, "r") as ymlfile:
        config = yaml.load(ymlfile, Loader=yaml.FullLoader)
    return config


# Load the configuration at the module level so it can be imported elsewhere
config = load_config()
