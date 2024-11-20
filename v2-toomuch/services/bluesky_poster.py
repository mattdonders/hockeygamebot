# services/bluesky_poster.py

from atproto import Client, client_utils
import re


class BlueskyPoster:
    def __init__(self, account, password):
        self.client = Client()
        self.account = account
        self.password = password

    def login(self):
        self.client.login(self.account, self.password)

    def post(self, content):
        # Initialize TextBuilder
        text_builder = client_utils.TextBuilder()

        # Find the first hashtag in the content
        hashtag_match = re.search(r"#(\w+)", content)
        if hashtag_match:
            start, end = hashtag_match.span()
            hashtag = hashtag_match.group(0)  # e.g., #NJDevils

            # Add text before the hashtag
            text_builder.text(content[:start])

            # Add the hashtag with tag formatting
            text_builder.tag(hashtag, hashtag[1:])  # hashtag[1:] removes the '#'

            # Add remaining text after the hashtag
            text_builder.text(content[end:])
        else:
            # No hashtag found, so just add the entire content as text
            text_builder.text(content)

        # Send the post with formatted content
        self.client.send_post(text_builder)
