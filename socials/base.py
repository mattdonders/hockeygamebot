# socials/base.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from socials.types import PostRef


@dataclass
class SocialPost:
    """
    A single outbound post payload.

    - Provide either `local_image` (file path) or `image_url` (already hosted).
    - Threading is handled by passing a PostRef separately to the client's `post()`
      as `reply_to_ref` (do NOT put platform IDs in here).
    """

    text: str | None = None
    local_image: Path | None = None  # local file path (e.g., "./charts/shotmap.png")
    image_url: str | None = None  # already-hosted URL (e.g., B2/GitHub CDN)
    alt_text: str | None = None  # image alt/description (if any)


class SocialClient(Protocol):
    """
    All platform adapters (Bluesky, Threads, etc.) implement this.

    MUST:
      - Create the post on the target platform
      - Thread it under `reply_to_ref` if provided (when valid for that platform)
      - Return a PostRef that uniquely identifies the created post
    """

    def post(self, post: SocialPost, reply_to_ref: PostRef | None = None) -> PostRef: ...
