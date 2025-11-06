# socials/threads_client.py
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import requests

from socials.types import PostRef
from socials.utils import sanitize_for_threads
from utils.image_hosting import get_public_url

from .base import SocialClient, SocialPost

THREADS_BASE = "https://graph.threads.net/v1.0"


@dataclass
class ThreadsConfig:
    access_token: str


class ThreadsClient(SocialClient):
    """
    Threads adapter using Graph Threads API.

    - Text-only posts: /me/threads with media_type=TEXT and auto_publish_text=true
      (no container/publish step; this is fastest & most reliable for text)
    - Image posts: create container (/me/threads) with media_type=IMAGE, image_url
      then publish (/me/threads_publish) with retry/backoff until the container is ready.
    - Multi-image: not supported as a single post; we emulate a 'carousel' by
      posting the first image, then replying with additional images in a thread.
    """

    def __init__(self, cfg: ThreadsConfig, root_cfg: dict):
        self.token = cfg.access_token
        self.root_cfg = root_cfg  # needed for image hosting (B2/GitHub/etc.)

    # ---------------------------
    # Low-level Graph endpoints
    # ---------------------------
    def _create_text(self, text: str, auto_publish: bool = True, reply_to_id: str | None = None):
        data = {
            "text": text,
            "media_type": "TEXT",
            "auto_publish_text": "true" if auto_publish else "false",
        }
        if reply_to_id:
            data["reply_to_id"] = reply_to_id
        r = requests.post(
            f"{THREADS_BASE}/me/threads",
            params={"access_token": self.token},
            data=data,
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def _create_image(
        self,
        text: str | None,
        image_url: str,
        alt_text: str | None,
        reply_to_id: str | None = None,
    ):
        data = {"media_type": "IMAGE", "image_url": image_url}
        if text:
            data["text"] = text
        if alt_text:
            data["alt_text"] = alt_text
        if reply_to_id:
            data["reply_to_id"] = reply_to_id
        r = requests.post(
            f"{THREADS_BASE}/me/threads",
            params={"access_token": self.token},
            data=data,
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def _publish(self, creation_id: str):
        r = requests.post(
            f"{THREADS_BASE}/me/threads_publish",
            params={"access_token": self.token, "creation_id": creation_id},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    # Robust publish: retry on 400 "container not ready"
    def _publish_with_retry(self, creation_id: str, max_attempts: int = 8, base_delay: float = 0.6):
        attempt = 1
        last_err = None
        while attempt <= max_attempts:
            try:
                return self._publish(creation_id)
            except requests.HTTPError as e:
                # 400 usually means "not ready" — wait and retry
                if e.response is not None and e.response.status_code == 400:
                    last_err = e
                    time.sleep(base_delay * attempt)  # linear-ish backoff
                    attempt += 1
                    continue
                # any other HTTP error, just bubble up
                raise
        # if we exhausted retries, raise the last 400
        if last_err:
            raise last_err
        raise RuntimeError("Failed to publish Threads media: unknown error")

    # ---------------------------
    # Helpers
    # ---------------------------
    def _ensure_hosted_url(self, path_or_url: str) -> str:
        """
        If it's a local path, host it and return the public URL.
        Otherwise return the input (already-hosted URL).
        """
        p = Path(path_or_url)
        if p.exists():
            return get_public_url(self.root_cfg, p)
        return path_or_url

    def _collect_images(self, post: SocialPost) -> list[str]:
        """
        Collect all images associated with the post as hosted URLs.
        Supports:
          - post.image_url (str), post.images (List[str] of URLs)
          - post.local_image (str path), post.local_images (List[str] of paths)
        """
        urls: list[str] = []
        # Hosted first
        if getattr(post, "image_url", None):
            urls.append(str(post.image_url))
        if getattr(post, "images", None):
            urls.extend([str(u) for u in post.images])

        # Local(s) -> host & add
        if getattr(post, "local_image", None):
            urls.append(self._ensure_hosted_url(str(post.local_image)))
        if getattr(post, "local_images", None):
            urls.extend([self._ensure_hosted_url(str(p)) for p in post.local_images])

        # De-dup while keeping order
        seen = set()
        deduped = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                deduped.append(u)
        return deduped

    # ---------------------------
    # SocialClient API
    # ---------------------------
    def post(self, post: SocialPost, reply_to_ref: PostRef | None = None) -> PostRef:
        """
        Create a Threads post (text or image[s]). Returns a PostRef.
        If reply_to_ref is provided (and platform==threads), reply in that thread.
        """
        reply_to_id = reply_to_ref.id if (reply_to_ref and reply_to_ref.platform == "threads") else None

        # Sanitize text for Threads (emoji tags etc.)
        text = sanitize_for_threads(post.text or "")

        image_urls = self._collect_images(post)

        # --- TEXT ONLY --------------------------------------------------------
        if not image_urls:
            created = self._create_text(text, auto_publish=True, reply_to_id=reply_to_id)
            return PostRef(platform="threads", id=str(created.get("id")), published=True, raw=created)

        # --- SINGLE IMAGE -----------------------------------------------------
        if len(image_urls) == 1:
            created = self._create_image(text, image_urls[0], getattr(post, "alt_text", None), reply_to_id)
            pub = self._publish_with_retry(created["id"])
            published_id = pub.get("id") or created.get("id")
            return PostRef(
                platform="threads",
                id=str(published_id),
                published=True,
                raw={"created": created, "publish": pub},
            )

        # --- MULTI-IMAGE (carousel workaround via threaded replies) -----------
        # 1) Root with first image + text
        created_root = self._create_image(text, image_urls[0], getattr(post, "alt_text", None), reply_to_id)
        pub_root = self._publish_with_retry(created_root["id"])
        parent_id = pub_root.get("id") or created_root.get("id")
        last_ref = PostRef(
            platform="threads",
            id=str(parent_id),
            published=True,
            raw={"created": created_root, "publish": pub_root},
        )

        # 2) Reply for each additional image; keep threading
        for u in image_urls[1:]:
            created_child = self._create_image(
                None, u, getattr(post, "alt_text", None), reply_to_id=last_ref.id
            )
            pub_child = self._publish_with_retry(created_child["id"])
            child_id = pub_child.get("id") or created_child.get("id")
            last_ref = PostRef(
                platform="threads",
                id=str(child_id),
                published=True,
                raw={"created": created_child, "publish": pub_child},
            )

        return last_ref
