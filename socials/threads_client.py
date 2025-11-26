# socials/threads_client.py
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import requests

from socials.types import PostRef
from socials.utils import sanitize_for_threads
from utils.image_hosting import get_public_url

from .base import SocialClient, SocialPost

THREADS_BASE = "https://graph.threads.net/v1.0"

logger = logging.getLogger(__name__)


@dataclass
class ThreadsConfig:
    access_token: str


class ThreadsClient(SocialClient):
    """Threads adapter using Graph Threads API.

    - Text-only posts: /me/threads with media_type=TEXT and auto_publish_text=true.
    - Image posts: IMAGE containers + /me/threads_publish.
    - Multi-image: CAROUSEL container with child IMAGE containers.
    """

    def __init__(self, cfg: ThreadsConfig, root_cfg: dict):
        self.token = cfg.access_token
        self.root_cfg = root_cfg

    # ---------------------------
    # Low-level Graph endpoints
    # ---------------------------
    def _create_text(
        self,
        text: str,
        auto_publish: bool = True,
        reply_to_id: Optional[str] = None,
    ) -> dict:
        data = {
            "text": text,
            "media_type": "TEXT",
            "auto_publish_text": "true" if auto_publish else "false",
        }
        if reply_to_id:
            data["reply_to_id"] = reply_to_id

        logger.info(
            "Threads: creating TEXT post (auto_publish=%s, reply_to_id=%s)",
            auto_publish,
            reply_to_id,
        )
        r = requests.post(
            f"{THREADS_BASE}/me/threads",
            params={"access_token": self.token},
            data=data,
            timeout=30,
        )
        r.raise_for_status()
        res = r.json()
        logger.debug("Threads: TEXT response: %s", res)
        return res

    def _create_image(
        self,
        text: Optional[str],
        image_url: str,
        alt_text: Optional[str],
        reply_to_id: Optional[str] = None,
        *,
        is_carousel_item: bool = False,
    ) -> dict:
        data: dict[str, str] = {
            "media_type": "IMAGE",
            "image_url": image_url,
        }
        if text:
            data["text"] = text
        if alt_text:
            data["alt_text"] = alt_text
        if reply_to_id:
            data["reply_to_id"] = reply_to_id
        if is_carousel_item:
            data["is_carousel_item"] = "true"

        logger.info(
            "Threads: creating IMAGE container (carousel_item=%s, reply_to_id=%s)",
            is_carousel_item,
            reply_to_id,
        )
        r = requests.post(
            f"{THREADS_BASE}/me/threads",
            params={"access_token": self.token},
            data=data,
            timeout=30,
        )
        r.raise_for_status()
        res = r.json()
        logger.debug("Threads: IMAGE response: %s", res)
        return res

    def _create_video(
        self,
        text: Optional[str],
        video_url: str,
        reply_to_id: Optional[str] = None,
    ) -> dict:
        """
        Create a VIDEO container for Threads.

        Threads Graph API:
        - media_type: VIDEO
        - video_url: publicly accessible URL for the video
        - text: optional caption
        - reply_to_id: optional parent post id
        """
        data: dict[str, str] = {
            "media_type": "VIDEO",
            "video_url": video_url,
        }
        if text:
            data["text"] = text
        if reply_to_id:
            data["reply_to_id"] = reply_to_id

        logger.info(
            "Threads: creating VIDEO container (reply_to_id=%s)",
            reply_to_id,
        )
        r = requests.post(
            f"{THREADS_BASE}/me/threads",
            params={"access_token": self.token},
            data=data,
            timeout=30,
        )
        r.raise_for_status()
        res = r.json()
        logger.debug("Threads: VIDEO response: %s", res)
        return res

    def _create_carousel(
        self,
        text: Optional[str],
        children_ids: List[str],
        reply_to_id: Optional[str] = None,
    ) -> dict:
        if len(children_ids) < 2:
            raise ValueError("Carousel must have at least 2 children.")
        if len(children_ids) > 20:
            raise ValueError("Carousel cannot have more than 20 children.")

        data: dict[str, str] = {
            "media_type": "CAROUSEL",
            # Threads wants a comma-separated list of child container IDs
            "children": ",".join(children_ids),
        }
        if text:
            data["text"] = text
        if reply_to_id:
            data["reply_to_id"] = reply_to_id

        logger.info(
            "Threads: creating CAROUSEL container with %d children (reply_to_id=%s)",
            len(children_ids),
            reply_to_id,
        )
        r = requests.post(
            f"{THREADS_BASE}/me/threads",
            params={"access_token": self.token},
            data=data,
            timeout=30,
        )

        # Try to parse JSON either way so we can see error details
        raw_text = r.text
        try:
            res = r.json()
        except ValueError:
            res = None

        if r.status_code >= 400:
            logger.error(
                "Threads: CAROUSEL create failed (%s). Payload=%s Response=%s",
                r.status_code,
                data,
                raw_text,
            )
            r.raise_for_status()

        logger.debug("Threads: CAROUSEL response: %s", res if res is not None else raw_text)
        return res if res is not None else {"raw": raw_text}

    def _publish(self, creation_id: str) -> dict:
        logger.info("Threads: publishing container %s", creation_id)
        r = requests.post(
            f"{THREADS_BASE}/me/threads_publish",
            params={"access_token": self.token, "creation_id": creation_id},
            timeout=30,
        )
        r.raise_for_status()
        res = r.json()
        logger.debug("Threads: publish response for %s: %s", creation_id, res)
        return res

    def _publish_with_retry(
        self,
        creation_id: str,
        max_attempts: int = 10,
        base_delay: float = 2,
    ) -> dict:
        attempt = 1
        last_err: Exception | None = None
        while attempt <= max_attempts:
            try:
                return self._publish(creation_id)
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 400:
                    last_err = e
                    sleep_time = base_delay * attempt
                    logger.warning(
                        "Threads: container %s not ready (attempt %d/%d), sleeping for %s seconds & retrying...",
                        creation_id,
                        attempt,
                        max_attempts,
                        sleep_time,
                    )
                    time.sleep(sleep_time)
                    attempt += 1
                    continue
                # other HTTP error – bubble up
                raise
        if last_err:
            logger.error(
                "Threads: failed to publish container %s after %d attempts",
                creation_id,
                max_attempts,
            )
            raise last_err
        raise RuntimeError("Failed to publish Threads media: unknown error")

    # ---------------------------
    # Helpers
    # ---------------------------
    def _ensure_hosted_url(self, path_or_url: str) -> str:
        p = Path(path_or_url)
        if p.exists():
            hosted = get_public_url(self.root_cfg, p)
            logger.info("Threads: hosted local media %s -> %s", p, hosted)
            return hosted
        return path_or_url

    def _collect_images(self, post: SocialPost) -> List[str]:
        urls: List[str] = []
        if getattr(post, "image_url", None):
            urls.append(str(post.image_url))
        if getattr(post, "images", None):
            urls.extend([str(u) for u in post.images])
        if getattr(post, "local_image", None):
            urls.append(self._ensure_hosted_url(str(post.local_image)))
        if getattr(post, "local_images", None):
            urls.extend([self._ensure_hosted_url(str(p)) for p in post.local_images])

        seen: set[str] = set()
        deduped: List[str] = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                deduped.append(u)
        return deduped

    # ---------------------------
    # SocialClient API
    # ---------------------------

    def post(self, post: SocialPost, reply_to_ref: PostRef | None = None) -> PostRef | None:
        """
        Create a Threads post.

        For now, we SKIP posts whose media is a GIF, because the Threads API
        treats GIFs as static images and that looks broken in the feed.
        """
        # --- GIF detection (local media only for now) ----------------------
        has_gif = False

        if getattr(post, "local_image", None) is not None:
            try:
                if Path(post.local_image).suffix.lower() == ".gif":
                    has_gif = True
            except TypeError:
                # local_image might already be a Path
                if isinstance(post.local_image, Path) and post.local_image.suffix.lower() == ".gif":
                    has_gif = True

        if getattr(post, "local_images", None):
            for img in post.local_images:
                try:
                    suffix = Path(img).suffix.lower()
                except TypeError:
                    suffix = img.suffix.lower() if isinstance(img, Path) else ""
                if suffix == ".gif":
                    has_gif = True
                    break

        if has_gif:
            logger.info(
                "ThreadsClient: skipping GIF media post (GIFs render as static images via API). " "text=%r",
                (post.text or "")[:80],
            )
            return None

        # --- existing behavior ---------------------------------------------
        reply_to_id = reply_to_ref.id if (reply_to_ref and reply_to_ref.platform == "threads") else None

        text = sanitize_for_threads(post.text or "")

        # --- VIDEO detection (local media only) ----------------------------
        video_exts = {".mp4", ".mov", ".m4v", ".webm"}
        video_path: Optional[str] = None

        if getattr(post, "local_image", None) is not None:
            try:
                p = Path(post.local_image)
            except TypeError:
                p = post.local_image if isinstance(post.local_image, Path) else None
            if p is not None and p.suffix.lower() in video_exts:
                video_path = str(p)

        if video_path is None and getattr(post, "local_images", None):
            for media in post.local_images:
                try:
                    p = Path(media)
                except TypeError:
                    p = media if isinstance(media, Path) else None
                if p is not None and p.suffix.lower() in video_exts:
                    video_path = str(p)
                    break

        if video_path is not None:
            video_url = self._ensure_hosted_url(video_path)
            created = self._create_video(
                text=text,
                video_url=video_url,
                reply_to_id=reply_to_id,
            )
            pub = self._publish_with_retry(created["id"])
            published_id = pub.get("id") or created.get("id")
            return PostRef(
                platform="threads",
                id=str(published_id),
                published=True,
                raw={"created": created, "publish": pub},
            )

        image_urls = self._collect_images(post)
        logger.info(
            "Threads: post requested (reply_to_id=%s, images=%d, text_len=%d)",
            reply_to_id,
            len(image_urls),
            len(text),
        )

        # TEXT ONLY
        if not image_urls:
            created = self._create_text(text, auto_publish=True, reply_to_id=reply_to_id)
            return PostRef(
                platform="threads",
                id=str(created.get("id")),
                published=True,
                raw=created,
            )

        # SINGLE IMAGE
        if len(image_urls) == 1:
            created = self._create_image(
                text,
                image_urls[0],
                getattr(post, "alt_text", None),
                reply_to_id=reply_to_id,
                is_carousel_item=False,
            )
            pub = self._publish_with_retry(created["id"])
            published_id = pub.get("id") or created.get("id")
            return PostRef(
                platform="threads",
                id=str(published_id),
                published=True,
                raw={"created": created, "publish": pub},
            )

        # MULTI-IMAGE: CAROUSEL
        alt_text = getattr(post, "alt_text", None)
        child_ids: List[str] = []
        for url in image_urls:
            child = self._create_image(
                text=None,
                image_url=url,
                alt_text=alt_text,
                reply_to_id=None,
                is_carousel_item=True,
            )
            child_ids.append(child["id"])

        created_carousel = self._create_carousel(
            text=text,
            children_ids=child_ids,
            reply_to_id=reply_to_id,
        )
        pub_carousel = self._publish_with_retry(created_carousel["id"])
        carousel_id = pub_carousel.get("id") or created_carousel.get("id")

        return PostRef(
            platform="threads",
            id=str(carousel_id),
            published=True,
            raw={"created": created_carousel, "publish": pub_carousel},
        )
