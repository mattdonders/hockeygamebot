# socials/x_client.py
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

import tweepy

from socials.types import PostRef

from .base import SocialClient, SocialPost


@dataclass
class XConfig:
    consumer_key: str
    consumer_secret: str
    access_token: str
    access_token_secret: str


class XClient(SocialClient):
    """
    Minimal X (Twitter) client:

    - Uses v1.1 API for media upload (photos).
    - Uses v2 API (`Client.create_tweet`) for posting.
    - Implements the SocialClient protocol so it plugs into SocialPublisher.
    """

    def __init__(self, cfg: XConfig):
        self.cfg = cfg

        # v1.1 API for media upload
        auth = tweepy.OAuth1UserHandler(
            cfg.consumer_key,
            cfg.consumer_secret,
            cfg.access_token,
            cfg.access_token_secret,
        )
        self.api_v1 = tweepy.API(auth)

        # v2 client for tweeting
        self.client_v2 = tweepy.Client(
            consumer_key=cfg.consumer_key,
            consumer_secret=cfg.consumer_secret,
            access_token=cfg.access_token,
            access_token_secret=cfg.access_token_secret,
        )

        # Cache username for building URLs (nice but non-critical)
        try:
            me = self.client_v2.get_me().data
            self.username = me.username
        except Exception as exc:  # pragma: no cover
            logging.warning("XClient: failed to resolve username: %s", exc)
            self.username = None

    def login_or_restore(self) -> None:
        """
        For interface symmetry with Bluesky/Threads.
        Nothing to restore for X as we use static tokens.
        """
        return

    def _upload_media(self, paths: Iterable[Path]) -> List[str]:
        media_ids: List[str] = []
        for p in paths:
            try:
                media = self.api_v1.media_upload(filename=str(p))
                # media_id_string works across Tweepy versions
                media_ids.append(str(getattr(media, "media_id_string", media.media_id)))
            except Exception as exc:
                logging.exception("XClient: failed to upload media %s: %s", p, exc)
        return media_ids

    def post(self, post: SocialPost, reply_to_ref: Optional[PostRef] = None) -> Optional[PostRef]:
        """
        Post a tweet with optional media and threading.
        1. Upload media (if any) via v1.1 API.
        2. Post tweet via v2 API.
        3. Return PostRef for created tweet, or None on failure.

        NOTE: This method treats duplicate-content and rate-limit errors as
        soft failures: it logs and returns None instead of raising so the
        publisher can continue posting to other platforms.
        """
        image_paths: List[Path] = []
        if post.local_images:
            image_paths.extend(post.local_images)
        elif post.local_image:
            image_paths.append(post.local_image)

        # X-specific: You can have up to 4 images OR 1 GIF per tweet.
        # If any GIFs are present, prefer a single GIF and ignore everything else.
        if image_paths:
            gif_paths = [p for p in image_paths if p.suffix.lower() == ".gif"]
            if gif_paths:
                chosen = gif_paths[0]
                if len(gif_paths) > 1 or len(image_paths) > 1:
                    logging.warning(
                        "XClient: multiple media provided including GIF; using only GIF %s for this tweet.",
                        chosen,
                    )
                image_paths = [chosen]

        media_ids: List[str] | None = None
        if image_paths:
            media_ids = self._upload_media(image_paths) or None

        # Optional: apply alt text to all media if provided
        if media_ids and getattr(post, "alt_text", None):
            for mid in media_ids:
                try:
                    # Tweepy v1.1 helper for media alt text
                    self.api_v1.create_media_metadata(
                        media_id=mid,
                        alt_text=post.alt_text,
                    )
                except Exception as exc:
                    logging.exception(
                        "XClient: failed to set alt text for media %s: %s",
                        mid,
                        exc,
                    )

        kwargs: dict = {"text": post.text or ""}
        if media_ids:
            kwargs["media_ids"] = media_ids
        if reply_to_ref and reply_to_ref.id:
            kwargs["in_reply_to_tweet_id"] = reply_to_ref.id

        try:
            resp = self.client_v2.create_tweet(**kwargs)
        except Exception as exc:
            msg = str(exc)
            lower = msg.lower()

            if "duplicate" in lower and "content" in lower:
                logging.warning(
                    "XClient: duplicate tweet blocked by X (soft-fail): %s",
                    msg,
                )
                return None

            if "429" in lower or "too many requests" in lower:
                logging.warning(
                    "XClient: rate limited when calling create_tweet (soft-fail): %s",
                    msg,
                )
                return None

            logging.exception("XClient: create_tweet failed: %s", exc)
            return None

        data = getattr(resp, "data", {}) or {}
        tweet_id = str(data.get("id") or "")
        if not tweet_id:
            logging.warning("XClient: create_tweet returned no id: %r", resp)
            return None

        url = None
        if self.username:
            url = f"https://x.com/{self.username}/status/{tweet_id}"

        return PostRef(
            platform="x",
            id=tweet_id,
            uri=url,
            published=True,
            raw=data,
        )
