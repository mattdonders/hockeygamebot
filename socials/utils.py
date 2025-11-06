# socials/utils.py
from __future__ import annotations

import re

from socials.types import PostRef


def seed_roots_from_results(social_state, results: dict[str, PostRef]) -> None:
    """
    Seed per-platform thread roots/parents from a platform->PostRef map.
    Works for any platform names present in `results`.
    """
    for platform, ref in results.items():
        # social_state must implement set_root(platform, PostRef)
        social_state.set_root(platform, ref)


def any_posted(results: dict[str, PostRef]) -> bool:
    """True if at least one platform returned a PostRef."""
    return bool(results)


def update_parents_from_results(preview_socials, results: dict[str, PostRef]) -> None:
    """Advance per-platform parents after a reply."""
    if "bluesky" in results:
        preview_socials.bluesky_parent = results["bluesky"]
    if "threads" in results:
        preview_socials.threads_parent = results["threads"]


KEYCAP_VARIANTS = [
    "\ufe0f",  # VARIATION SELECTOR-16
    "\u20e3",  # COMBINING ENCLOSING KEYCAP
]
# Some keyboards insert the keycap emoji as a single glyph; catch common forms.
KEYCAP_HASH = "#\ufe0f\u20e3"  # "#️⃣"


def sanitize_for_threads(text: str) -> str:
    if not text:
        return text
    # 1) Convert keycap hash emoji to plain hash
    text = text.replace(KEYCAP_HASH, "#")
    # 2) Remove stray variation selectors after '#'
    text = re.sub(r"#\ufe0f", "#", text)
    # 3) Collapse accidental spaces between # and tag
    text = re.sub(r"#\s+([A-Za-z0-9_]+)", r"#\1", text)
    return text
