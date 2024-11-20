# services/social_media_service.py

import logging
from services.bluesky_poster import BlueskyPoster


class SocialMediaService:
    def __init__(self, config, env, nosocial=False):
        self.config = config
        self.nosocial = nosocial
        self.bluesky_enabled = self.config["socials"]["bluesky"] and not self.nosocial
        self.bluesky_poster = None

        if self.bluesky_enabled:
            bs_config = config.get("bluesky", {}).get(env, {})
            account = bs_config.get("account")
            password = bs_config.get("password")
            self.bluesky_poster = BlueskyPoster(account, password)

        # self.threads_enabled = self.config["socials"]["threads"]

    def post_update(self, content):
        if self.nosocial:
            # Log the content instead of posting
            logging.info("[NOSOCIAL]: \n%s", content)
        if self.bluesky_enabled and self.bluesky_poster:
            self.bluesky_poster.login()
            self.bluesky_poster.post(content)
