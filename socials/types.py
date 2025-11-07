# socials/types.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PostRef:
    """Normalized reference to a published (or staged) social post across platforms.

    platform:  "bluesky" | "threads" | "x" | "unknown"
    id:        canonical id for the platform (e.g., Threads post/creation id, Bluesky URI)
    uri:       Bluesky URI if available (useful for replies)
    cid:       Bluesky CID if available
    published: whether the post is publicly visible yet
    raw:       original dict returned by the platform adapter (debugging/forensics)
    """

    platform: str
    id: str
    uri: str | None = None
    cid: str | None = None
    published: bool = True
    raw: dict[str, Any] | None = None
