# services/bluesky_poster.py

import logging
from atproto import Client, client_utils, models
import re


class BlueskyClient:
    def __init__(self, account, password, nosocial):
        self.client = Client()
        self.account = account
        self.password = password
        self.nosocial = nosocial

    def login(self):
        self.client.login(self.account, self.password)

    def post(self, message, reply_root=None, reply_post=None):
        if self.nosocial:
            logging.info(f"[NOSOCIAL] {message}")
            return

        # Initialize TextBuilder
        text_builder = client_utils.TextBuilder()

        # Extract all hashtags
        hashtags = re.findall(r"#(\w+)", message)
        remaining_message = message

        for hashtag in hashtags:
            # Find the position of the current hashtag in the message
            match = re.search(rf"#{hashtag}", remaining_message)
            if match:
                start, end = match.span()

                # Add text before the hashtag
                text_builder.text(remaining_message[:start])

                # Add the hashtag with tag formatting
                text_builder.tag(f"#{hashtag}", hashtag)  # Strip '#' for tag formatting

                # Update the remaining message to exclude the processed part
                remaining_message = remaining_message[end:]

        # Add any remaining text after the last hashtag
        text_builder.text(remaining_message)

        # Send the post with formatted message
        if reply_root and reply_post:
            parent = models.create_strong_ref(reply_post)
            root = models.create_strong_ref(reply_root)
            reply_model = models.AppBskyFeedPost.ReplyRef(parent=parent, root=root)
            post_response = self.client.send_post(text_builder, reply_to=reply_model)
        else:
            post_response = self.client.send_post(text_builder)

        return post_response
