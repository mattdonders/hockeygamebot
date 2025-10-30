import logging
from pathlib import Path
import re
import typing as t

import httpx
from atproto import Client, client_utils, models
from PIL import Image

_META_PATTERN = re.compile(r'<meta property="og:.*?>')
_CONTENT_PATTERN = re.compile(r'<meta[^>]+content="([^"]+)"')


def _find_tag(og_tags: t.List[str], search_tag: str) -> t.Optional[str]:
    for tag in og_tags:
        if search_tag in tag:
            return tag

    return None


def _get_tag_content(tag: str) -> t.Optional[str]:
    match = _CONTENT_PATTERN.match(tag)
    if match:
        return match.group(1)

    return None


def _get_og_tag_value(og_tags: t.List[str], tag_name: str) -> t.Optional[str]:
    tag = _find_tag(og_tags, tag_name)
    if tag:
        return _get_tag_content(tag)

    return None


def get_og_tags(url: str) -> t.Tuple[t.Optional[str], t.Optional[str], t.Optional[str]]:
    response = httpx.get(url)
    response.raise_for_status()

    og_tags = _META_PATTERN.findall(response.text)

    og_image = _get_og_tag_value(og_tags, "og:image")
    og_title = _get_og_tag_value(og_tags, "og:title")
    og_description = _get_og_tag_value(og_tags, "og:description")

    return og_image, og_title, og_description


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

    def _send_post(self, text_builder, media=None, reply_to=None, embed=None):
        """
        Send a post with optional media or a reply reference.

        :param text_builder: The text content to be posted.
        :param media: None, a single path string, or a list of path strings representing images.
        :param reply_to: Optional reference to another post (e.g., a CID).
        :param embed: Optional embed data.
        """
        if media is None:
            # No media: just send a standard post
            return self.client.send_post(text_builder, reply_to=reply_to, embed=embed)

        # If media is a list of multiple images
        if isinstance(media, list):
            images = [Path(path).read_bytes() for path in media]
            return self.client.send_images(text_builder, images=images, reply_to=reply_to)

        # Otherwise, we have a single image
        # Extract dimensions for aspect ratio
        with Image.open(media) as img:
            width, height = img.size

        aspect_ratio = models.AppBskyEmbedDefs.AspectRatio(height=height, width=width)
        image_data = Path(media).read_bytes()

        return self.client.send_image(
            text_builder, image=image_data, reply_to=reply_to, image_alt="", image_aspect_ratio=aspect_ratio
        )

    def post(self, message: str, link=None, reply_root=None, reply_parent=None, media=None):
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
            # Track social post in monitor (even in nosocial mode for testing)
            if hasattr(self, 'monitor') and self.monitor:
                self.monitor.record_social_post()
            return

        # Initialize TextBuilder & External Embed
        text_builder = client_utils.TextBuilder()
        embed_external = None
        reply_model = None

        # Build a list of matches (hashtags and URLs)
        matches = []

        # Find hashtags
        for match in re.finditer(r"#(\w+)", message):
            matches.append(
                {"type": "hashtag", "start": match.start(), "end": match.end(), "value": match.group()}
            )

        # Find URLs
        for match in re.finditer(r"(https?://\S+)", message):
            matches.append(
                {"type": "link", "start": match.start(), "end": match.end(), "value": match.group()}
            )

        # Sort matches by their start position
        matches = sorted(matches, key=lambda x: x["start"])
        logging.debug(f"Bluesky Text Builder Matches: {matches}")

        # Process the message based on matches
        last_pos = 0  # Tracks the end of the last processed segment
        for match in matches:
            # Add text before the match
            if match["start"] > last_pos:
                text_builder.text(message[last_pos : match["start"]])

            # Add the match as a tag or link
            if match["type"] == "hashtag":
                text_builder.tag(match["value"], match["value"][1:])  # Strip '#' for tag
            elif match["type"] == "link":
                text_builder.link(match["value"], match["value"])  # Add as clickable link

            # Update the last processed position
            last_pos = match["end"]

        # Add any remaining text after the last match
        if last_pos < len(message):
            text_builder.text(message[last_pos:])

        # Debugging TextBuilder facets
        if hasattr(text_builder, "_facets"):
            for i, facet in enumerate(text_builder._facets):
                logging.debug(f"Facet {i}: {facet}")

        # If Link is True, Add External Embed
        if link:
            img_url, title, description = get_og_tags(link)
            if title and description:
                thumb_blob = None
                if img_url:
                    # Download image from og:image url and upload it as a blob
                    img_data = httpx.get(img_url).content
                    thumb_blob = self.client.upload_blob(img_data).blob

                    # AppBskyEmbedExternal is the same as "link card" in the app
                    embed_external = models.AppBskyEmbedExternal.Main(
                        external=models.AppBskyEmbedExternal.External(
                            title=title, description=description, uri=link, thumb=thumb_blob
                        )
                    )

        # # Send the post with formatted message
        # if reply_root and reply_parent:
        #     parent = models.create_strong_ref(reply_parent)
        #     root = models.create_strong_ref(reply_root)
        #     reply_model = models.AppBskyFeedPost.ReplyRef(parent=parent, root=root)
        #     post_response = self.client.send_post(text_builder, reply_to=reply_model, embed=embed_external)
        # else:
        #     if media:
        #         media = media if isinstance(media, list) else [media]
        #         images = []

        #         for path in media:
        #             with open(path, "rb") as f:
        #                 images.append(f.read())

        #         post_response = self.client.send_images(text_builder, images=images)
        #     else:
        #         post_respo[open(path, "rb").read() for path in media]
        # return post_response

        if reply_root and reply_parent:
            parent = models.create_strong_ref(reply_parent)
            root = models.create_strong_ref(reply_root)
            reply_model = models.AppBskyFeedPost.ReplyRef(parent=parent, root=root)

        # Send the Post w/ Formatted Message & Properties
        post_response = self._send_post(text_builder, media=media, reply_to=reply_model, embed=embed_external)

        # Track social post in monitor
        if hasattr(self, 'monitor') and self.monitor:
            self.monitor.record_social_post()

        return post_response