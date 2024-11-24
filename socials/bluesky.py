import logging
from atproto import Client, client_utils, models
import re


class BlueskyClient:
    """
    A client for managing interactions with Bluesky, including authentication and posting.

    The `BlueskyClient` encapsulates the functionality required to log in and post messages
    to Bluesky. It supports formatted messages with hashtag tagging and handles optional
    replies to existing posts.

    Attributes:
        client (Client): An instance of the Bluesky `atproto.Client` for API interactions.
        account (str): The Bluesky account username or handle.
        password (str): The password for the Bluesky account.
        nosocial (bool): A flag to disable posting to Bluesky, useful for debugging purposes.

    Methods:
        login():
            Authenticates the client with the provided account credentials.

        post(message, reply_root=None, reply_post=None):
            Sends a formatted post to Bluesky with optional reply references.

    Example Usage:
        # Initialize and authenticate the client
        bluesky_client = BlueskyClient(account="username", password="password", nosocial=False)
        bluesky_client.login()

        # Post a simple message
        response = bluesky_client.post("Hello, Bluesky! #Update")

        # Post a reply to an existing post
        response = bluesky_client.post(
            "This is a reply! #Response",
            reply_root=existing_root_post,
            reply_post=existing_parent_post
        )
    """

    def __init__(self, account, password, nosocial):
        """
        Initializes the `BlueskyClient` with account credentials and debug mode settings.

        Args:
            account (str): The Bluesky account username or handle.
            password (str): The password for the Bluesky account.
            nosocial (bool): If True, disables posting to Bluesky and logs the message instead.
        """
        self.client = Client()
        self.account = account
        self.password = password
        self.nosocial = nosocial

    def login(self):
        """
        Authenticates the client using the provided account credentials.

        Raises:
            Exception: If login fails due to invalid credentials or other errors.
        """
        self.client.login(self.account, self.password)

    def post(self, message: str, reply_root=None, reply_post=None):
        """
        Sends a formatted post to Bluesky with optional reply references.

        The post method supports hashtag tagging, which formats hashtags into Bluesky's
        rich text tagging format. Messages are sent as top-level posts or as replies if
        `reply_root` and `reply_post` are provided.

        Args:
            message (str): The message content to post. Hashtags (e.g., `#tag`) will be
                automatically formatted and tagged.
            reply_root: (Optional) The root post reference for a reply thread.
            reply_post: (Optional) The direct parent post reference for the reply.

        Returns:
            dict: The response from the Bluesky API if the post is successful.
            None: If `nosocial` is True, the message is logged instead of being posted.

        Example Usage:
            # Post a standalone message
            response = bluesky_client.post("Hello, Bluesky! #Update")

            # Post a reply to a specific post
            response = bluesky_client.post(
                "This is a reply! #Response",
                reply_root=root_post_ref,
                reply_post=parent_post_ref
            )
        """
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
