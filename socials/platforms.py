# socials/platforms.py

"""
Centralized platform group constants.

These are *logical* groupings, not tied to config. The SocialPublisher
will still only post to platforms that are actually enabled/configured.
"""

from typing import List

# Single-platform groups
X_PLATFORMS: List[str] = ["x"]

# Non-X platforms – your “full firehose” group
NON_X_PLATFORMS: List[str] = ["bluesky", "threads", "telegram", "mastodon"]

# Convenience superset (optional, but handy later)
ALL_PLATFORMS: List[str] = NON_X_PLATFORMS + X_PLATFORMS

# NEW: where we *prefer* GIF vs MP4 for goal “GIF” events.
GIF_PLATFORMS = {"x"}  # animated GIF UX is good
VIDEO_PLATFORMS = {"bluesky", "threads", "telegram"}  # use MP4 instead of GIF
