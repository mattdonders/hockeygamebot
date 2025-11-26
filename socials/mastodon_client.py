from __future__ import annotations

import logging
import mimetypes
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

import requests

from socials.types import PostRef

from .base import SocialClient, SocialPost

logger = logging.getLogger(__name__)

Visibility = Literal["public", "unlisted", "private", "direct"]


@dataclass
class MastodonConfig:
    base_url: str
    access_token: str
    visibility: Visibility = "unlisted"


class MastodonClient(SocialClient):
    """
    Mastodon client compatible with SocialPublisher.

    - Text posts.
    - Image posts via media upload (api/v2/media).
    - Image-only posts allowed (status text optional when media present).
    """

    def __init__(self, config: MastodonConfig) -> None:
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.config.access_token}",
                "User-Agent": "hockeygamebot/1.0",
            }
        )

    def login_or_restore(self) -> None:
        """No-op for Mastodon – tokens are long-lived."""
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

        # Deduplicate while preserving order
        unique: list[Path] = []
        seen: set[Path] = set()
        for p in paths:
            if p not in seen:
                seen.add(p)
                unique.append(p)

        return unique

    def _wait_for_media_ready(
        self,
        media_id: str,
        timeout: float = 10.0,
        poll_interval: float = 0.5,
    ) -> bool:
        """
        Poll Mastodon until media has finished processing (or we time out).

        Returns True if ready, False if it errors or times out.
        """
        status_url = f"{self.base_url}/api/v1/media/{media_id}"
        deadline = time.monotonic() + timeout

        logger.info("Mastodon: waiting for media %s to finish processing", media_id)

        while time.monotonic() < deadline:
            try:
                resp = self.session.get(status_url, timeout=10)
            except Exception:
                logger.exception("MastodonClient._wait_for_media_ready failed for %s", media_id)
                return False

            if resp.status_code >= 300:
                logger.warning(
                    "Mastodon media status failed for %s: status=%s body=%s",
                    media_id,
                    resp.status_code,
                    resp.text,
                )
                return False

            js = resp.json()
            url = js.get("url")
            preview = js.get("preview_url")

            logger.debug(
                "Mastodon media %s poll: url=%r preview_url=%r",
                media_id,
                url,
                preview,
            )

            # For images/GIFs, url or preview_url becomes non-null when ready.
            if url or preview:
                logger.info("Mastodon: media %s reported ready", media_id)
                return True

            time.sleep(poll_interval)

        logger.warning(
            "Mastodon media %s not ready after %.1fs; giving up.",
            media_id,
            timeout,
        )
        return False

    def _upload_media(self, path: Path) -> Optional[str]:
        """
        Upload a single image/GIF to Mastodon and return media_id, or None on failure.

        Also waits until Mastodon reports the media as 'ready' before returning,
        and then sleeps a little extra for safety (GIFs can be slow to process).
        """
        url = f"{self.base_url}/api/v2/media"

        mime_type, _ = mimetypes.guess_type(path.name)
        if not mime_type:
            mime_type = "application/octet-stream"

        try:
            with path.open("rb") as f:
                files = {"file": (path.name, f, mime_type)}
                resp = self.session.post(url, files=files, timeout=60)

            if resp.status_code >= 300:
                logger.warning(
                    "Mastodon media upload failed for %s: status=%s body=%s",
                    path,
                    resp.status_code,
                    resp.text,
                )
                return None

            js = resp.json()
            media_id = js.get("id")
            if not media_id:
                logger.warning("Mastodon media upload returned no id for %s", path)
                return None

            media_id = str(media_id)
            logger.info("Mastodon: uploaded media %s for %s", media_id, path)

            # Wait for processing to complete
            if not self._wait_for_media_ready(media_id):
                logger.warning("Mastodon media %s never became ready; skipping.", media_id)
                return None

            # Extra buffer – some instances still need a beat after reporting ready
            logger.info("Mastodon: media %s ready, sleeping extra 2s before posting", media_id)
            time.sleep(2.0)

            return media_id
        except Exception:
            logger.exception("MastodonClient._upload_media raised exception for %s", path)
            return None

    # ---- public API -------------------------------------------------------

    def post(
        self,
        post: SocialPost,
        reply_to_ref: Optional[PostRef] = None,
    ) -> Optional[PostRef]:
        """
        Create a Mastodon status.

        Behavior:
        - If text and/or local images are present, we post.
        - If neither text nor images are present, we skip.
        - For now, we SKIP posts whose media is a GIF, because some instances
          never accept GIF attachments as 'finished processing' in time.
        """
        text = (post.text or "").strip() if post.text else ""
        local_images = self._extract_local_images(post)

        if not text and not local_images:
            logger.warning("MastodonClient.post called with no text and no images; skipping.")
            return None

        # --- GIF detection: skip goal GIFs on Mastodon for now -------------
        for img_path in local_images:
            try:
                if img_path.suffix.lower() == ".gif":
                    logger.info(
                        "MastodonClient: skipping GIF media post; instance keeps "
                        "returning 'not finished processing' for GIFs. text=%r",
                        text[:80],
                    )
                    return None
            except AttributeError:
                if Path(img_path).suffix.lower() == ".gif":
                    logger.info(
                        "MastodonClient: skipping GIF media post; instance keeps "
                        "returning 'not finished processing' for GIFs. text=%r",
                        text[:80],
                    )
                    return None

        # -------------------------------------------------------------------
        # Existing behavior for non-GIF posts
        # -------------------------------------------------------------------
        # Upload local images (if any) and collect media_ids
        media_ids: list[str] = []
        for img_path in local_images:
            media_id = self._upload_media(img_path)
            if media_id:
                media_ids.append(media_id)

        status_url = f"{self.base_url}/api/v1/statuses"
        data: dict[str, object] = {
            "visibility": self.config.visibility,
        }

        if text:
            data["status"] = text

        if reply_to_ref and reply_to_ref.id:
            data["in_reply_to_id"] = reply_to_ref.id

        if media_ids:
            # requests will encode list values correctly for media_ids[]
            data["media_ids[]"] = media_ids

        # Simple, single-shot status POST (since GIFs are already filtered out)
        try:
            resp = self.session.post(status_url, data=data, timeout=15)
            if resp.status_code >= 300:
                logger.warning(
                    "Mastodon post_status failed: status=%s body=%s",
                    resp.status_code,
                    resp.text,
                )
                return None

            js = resp.json()
            status_id = js.get("id")
            if not status_id:
                return None

            return PostRef(platform="mastodon", id=str(status_id))
        except Exception:
            logger.exception("MastodonClient.post raised exception")
            return None
