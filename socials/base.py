# socials/base.py
from __future__ import annotations

from dataclasses import dataclass
from os import PathLike
from typing import Protocol

from socials.types import PostRef


@dataclass
class SocialPost:
    """A single outbound post payload.

    - Provide either `local_image` (file path) or `image_url` (already hosted).
    - Threading is handled by passing a PostRef separately to the client's `post()`
      as `reply_to_ref` (do NOT put platform IDs in here).
    """

    # Required/typical
    text: str | None = None

    # Hosted image(s)
    image_url: str | None = None  # single hosted URL
    images: list[str] | None = None  # multiple hosted URLs

    # Local image(s) (paths - your client will host/resolve)
    local_image: str | PathLike[str] | None = None  # single local path
    local_images: list[str] | PathLike[str] | None = None  # multiple local paths

    # Accessibility
    alt_text: str | None = None


class SocialClient(Protocol):
    """All platform adapters (Bluesky, Threads, etc.) implement this.

    MUST:
      - Create the post on the target platform
      - Thread it under `reply_to_ref` if provided (when valid for that platform)
      - Return a PostRef that uniquely identifies the created post
    """

    def post(self, post: SocialPost, reply_to_ref: PostRef | None = None) -> PostRef: ...
