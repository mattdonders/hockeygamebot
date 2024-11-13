"""
A social media wrapper function that handles routing messages to all other defined
social networks in our configuration file.
"""
import logging

from PIL import Image  # Used for debugging images (notweets)

from hockeygamebot.helpers import arguments, utils
from hockeygamebot.helpers.config import config
from hockeygamebot.models.globalgame import GlobalGame
from hockeygamebot.social import discord, slack, twitter


@utils.check_social_timeout
def send(msg, **kwargs):
    """The handler function that takes a message and a set of key-value arguments
        to be routed to social media functions.

    Args:
        message: The main message to be sent to all social media sites.
        # TODO: **kwargs

    Returns:
        None
    """
    # If for some reason, message is None (or False), just exit the function.
    if not msg:
        return

    if GlobalGame.game and GlobalGame.game.other_team.team_name == "Washington Capitals":
        msg = msg.lower()

    args = arguments.get_arguments()
    social_config = config.socials

    # Initialize a return dictionary
    return_dict = {"twitter": None, "discord": None, "slack": None}

    if args.notweets:
        logging.info("[SOCIAL] %s", msg)
        if kwargs.get("media"):
            media = kwargs.get("media")
            if isinstance(media, list):
                for single_image in media:
                    Image.open(single_image).show()
            else:
                Image.open(media).show()
            # kwargs.get("media").show()
        return return_dict

    if social_config["twitter"]:
        # tweet_id = twitter.send_tweet(
        #     msg, media=kwargs.get("media"), reply=kwargs.get("reply"), hashtag=kwargs.get("hashtag")
        # )
        team_hashtag = kwargs.get("team_hashtag")
        game_hashtag = kwargs.get("game_hashtag")
        tweet_id = twitter.send_tweet(
            msg,
            media=kwargs.get("media"),
            video=kwargs.get("video"),
            reply=kwargs.get("reply"),
            hashtags=kwargs.get("hashtags"),
            team_hashtag=kwargs.get("team_hashtag"),
            game_hashtag=kwargs.get("game_hashtag"),
        )
        return_dict["twitter"] = tweet_id

    if social_config["discord"]:
        msg = kwargs.get("discord_msg", msg)
        discord.send_discord(
            msg,
            embed=kwargs.get("discord_embed"),
            title=kwargs.get("discord_title"),
            color=kwargs.get("discord_color"),
            media=kwargs.get("media"),
        )

    if social_config["slack"]:
        pass

    return return_dict
