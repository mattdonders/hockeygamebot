from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

from socials.types import PostRef

from .base import SocialClient, SocialPost

logger = logging.getLogger(__name__)


@dataclass
class TelegramConfig:
    bot_token: str
    chat_id: str  # channel id (e.g. "-1003396036547")


class TelegramClient(SocialClient):
    """
    Telegram channel client compatible with SocialPublisher.

    - Text posts via sendMessage.
    - Image posts via sendPhoto (uses first local image if multiple are present).
    - Supports image-only or text+image (caption).
    """

    def __init__(self, config: TelegramConfig) -> None:
        self.config = config
        self.base_url = f"https://api.telegram.org/bot{self.config.bot_token}"

    def login_or_restore(self) -> None:
        """No-op for Telegram bots (no session to restore)."""
        return

    # ---- internal helpers -------------------------------------------------

    def _extract_local_images(self, post: SocialPost) -> list[Path]:
        """
        Collect local image Paths from SocialPost.

        We prioritize:
        - post.local_images (iterable of Paths/str)
        - post.local_image (single Path/str)
        Only existing files are kept.
        """
        paths: list[Path] = []

        local_images = getattr(post, "local_images", None) or []
        for p in local_images:
            try:
                path = Path(p)
                if path.exists():
                    paths.append(path)
            except TypeError:
                continue

        single = getattr(post, "local_image", None)
        if single:
            try:
                path = Path(single)
                if path.exists():
                    paths.append(path)
            except TypeError:
                pass

        # Deduplicate
        unique: list[Path] = []
        seen: set[Path] = set()
        for p in paths:
            if p not in seen:
                seen.add(p)
                unique.append(p)

        return unique

    def _send_message(
        self,
        text: str,
        reply_to_ref: Optional[PostRef],
    ) -> Optional[PostRef]:
        """
        Send a plain text message to the channel.
        """
        payload: dict[str, object] = {
            "chat_id": self.config.chat_id,
            "text": text,
            "disable_notification": False,
        }

        if reply_to_ref and reply_to_ref.id:
            try:
                payload["reply_to_message_id"] = int(reply_to_ref.id)
            except ValueError:
                pass

        try:
            resp = requests.post(
                f"{self.base_url}/sendMessage",
                json=payload,
                timeout=10,
            )
            if resp.status_code != 200:
                logger.warning(
                    "Telegram sendMessage failed: status=%s body=%s",
                    resp.status_code,
                    resp.text,
                )
                return None

            data = resp.json()
            msg = data.get("result") or {}
            message_id = msg.get("message_id")
            if message_id is None:
                return None

            return PostRef(platform="telegram", id=str(message_id))
        except Exception:
            logger.exception("TelegramClient._send_message raised exception")
            return None

    def _send_photo(
        self,
        image_path: Path,
        caption: str | None,
        reply_to_ref: Optional[PostRef],
    ) -> Optional[PostRef]:
        """
        Send a photo to the channel, optionally with caption.
        """
        payload: dict[str, object] = {
            "chat_id": self.config.chat_id,
            "disable_notification": False,
        }

        if caption:
            # Telegram caption limit is 1024 characters
            payload["caption"] = caption[:1024]

        if reply_to_ref and reply_to_ref.id:
            try:
                payload["reply_to_message_id"] = int(reply_to_ref.id)
            except ValueError:
                pass

        try:
            with image_path.open("rb") as f:
                files = {"photo": (image_path.name, f)}
                resp = requests.post(
                    f"{self.base_url}/sendPhoto",
                    data=payload,
                    files=files,
                    timeout=20,
                )

            if resp.status_code != 200:
                logger.warning(
                    "Telegram sendPhoto failed: status=%s body=%s",
                    resp.status_code,
                    resp.text,
                )
                return None

            data = resp.json()
            msg = data.get("result") or {}
            message_id = msg.get("message_id")
            if message_id is None:
                return None

            return PostRef(platform="telegram", id=str(message_id))
        except Exception:
            logger.exception("TelegramClient._send_photo raised exception for %s", image_path)
            return None

    def _send_animation(
        self,
        image_path: Path,
        caption: str | None,
        reply_to_ref: Optional[PostRef],
    ) -> Optional[PostRef]:
        """
        Send an animated GIF/video to the channel as an animation.
        """
        payload: dict[str, object] = {
            "chat_id": self.config.chat_id,
            "disable_notification": False,
        }

        if caption:
            # Telegram caption limit is 1024 characters
            payload["caption"] = caption[:1024]

        if reply_to_ref and reply_to_ref.id:
            try:
                payload["reply_to_message_id"] = int(reply_to_ref.id)
            except ValueError:
                pass

        try:
            with image_path.open("rb") as f:
                files = {"animation": f}
                resp = requests.post(
                    f"{self.base_url}/sendAnimation",
                    data=payload,
                    files=files,
                    timeout=20,
                )

            if resp.status_code != 200:
                logger.warning(
                    "Telegram sendAnimation failed: status=%s body=%s",
                    resp.status_code,
                    resp.text,
                )
                return None

            data = resp.json()
            msg = data.get("result") or {}
            message_id = msg.get("message_id")
            if message_id is None:
                return None

            return PostRef(platform="telegram", id=str(message_id))
        except Exception:
            logger.exception("TelegramClient._send_animation raised exception for %s", image_path)
            return None

    # ---- public API -------------------------------------------------------
    def post(
        self,
        post: SocialPost,
        reply_to_ref: Optional[PostRef] = None,
    ) -> Optional[PostRef]:
        """
        Post text and optional image/animation to Telegram.

        - If we have a local GIF -> sendAnimation
        - If we have another image -> sendPhoto
        - Otherwise -> plain text message
        """
        text = (post.text or "").strip() if post.text else ""
        local_images = self._extract_local_images(post)

        if not text and not local_images:
            logger.warning("TelegramClient.post called with no text and no images; skipping.")
            return None

        if local_images:
            primary_image = local_images[0]

            suffix = primary_image.suffix.lower()

            # Treat GIFs *and* short MP4-style clips as Telegram animations.
            # Telegram's sendAnimation supports both GIF and silent video,
            # and displays them as looping "GIF-like" animations.
            if suffix in {".gif", ".mp4", ".m4v", ".webm"}:
                return self._send_animation(
                    primary_image,
                    caption=text or None,
                    reply_to_ref=reply_to_ref,
                )

            # Otherwise treat as a regular photo
            return self._send_photo(
                primary_image,
                caption=text or None,
                reply_to_ref=reply_to_ref,
            )

        # Otherwise, text-only
        return self._send_message(text, reply_to_ref=reply_to_ref)
