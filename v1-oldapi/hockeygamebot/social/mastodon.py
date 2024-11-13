import logging
import requests
from hockeygamebot.helpers import arguments, utils
from hockeygamebot.models.hashtag import Hashtag

from mastodon import Mastodon


def send_post(text, video=None, media=None, reply=None, hashtags=None, team_hashtag=None, game_hashtag=None):
    """Generatic Mastodon Function that sends posts to the game bot account."""

    logging.info("[MASTODON] %s (Media: %s, Reply: %s)", text, media, reply)
    args = arguments.get_arguments()

    mastodon_config = utils.load_config()["mastodon"]
    mastodon_instance = mastodon_config["instance"]
    mastodon_user = mastodon_config["username"]
    mastodon_token = mastodon_config["token"]

    mastodon_api = Mastodon(access_token=mastodon_token, api_base_url=mastodon_instance)

    if args.notweets:
        logging.info("%s", text)
        return f"{mastodon_instance}/@{mastodon_user}"

    if game_hashtag:
        text = f"{text}\n\n{Hashtag.game_hashtag}"

    try:
        status = mastodon_api.status_post(status=text)
        return status.id

    except Exception as e:
        logging.error("Failed to send Mastodon Post : %s", text)
        logging.error(e)
        return None
