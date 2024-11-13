"""
This module contains a single Configuration class used for read-only once.
"""

# pylint: disable=too-few-public-methods

import yaml

from hockeygamebot.definitions import CONFIG_PATH


class _Config:
    """ A configuration class that converts the YAML configuration file into
        class attributes (one level deep).

    Args:
        None

    Returns:
        config object consisting of attributes & then sub-dictionaries
    """

    def __init__(self):
        with open(CONFIG_PATH) as ymlfile:
            _config = yaml.load(ymlfile, Loader=yaml.FullLoader)

        for k, v in _config.items():
            setattr(self, k, v)


config = _Config()
