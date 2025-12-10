#!/usr/bin/env python
"""
Milestone Digest Script

Scans milestone JSON files for a given date and posts a consolidated
milestone thread to X / Bluesky using the existing SocialPublisher.

Behavior:
- Intro post goes only to platforms that have at least one milestone URL.
- Replies are per-platform:
    * X reply only if that team has an X URL
    * Bluesky reply only if that team has a Bluesky URL
- If no platform has any URLs, the digest is skipped entirely.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from socials.publisher import SocialPublisher
from utils.config import load_config

logger = logging.getLogger("milestone_digest")


# ---------------------------------------------------------------------------
# Intro variants
# ---------------------------------------------------------------------------

INTRO_VARIANTS: List[str] = [
    "Tonight’s slate has a bunch of milestone watches 👀🏒\n"
    "Here’s a consolidated look from all active game bots:\n\n"
    "#hockeygamebot",
    "Player milestones on deck tonight — goals, assists, games played and more.\n"
    "Here’s your daily roundup from the game bots:\n\n"
    "#hockeygamebot",
    "Milestone vibes tonight across the league ✨\n"
    "Here’s the full list of who’s closing in on big career numbers:\n\n"
    "#hockeygamebot",
    "Quick milestone check for tonight’s action 🚨\n"
    "Below are today’s milestone posts from each game bot:\n\n"
    "#hockeygamebot",
    "If you like player milestones, tonight’s a good one 👀\n"
    "Here’s the consolidated thread from all running bots:\n\n"
    "#hockeygamebot",
    "Career milestones approaching all over the league tonight 🔔\n"
    "Here’s your daily milestone roundup:\n\n"
    "#hockeygamebot",
    "Before puck drop, here’s a look at who can hit big milestones tonight 👇\n"
    "Collected from all active game bots:\n\n"
    "#hockeygamebot",
    "Milestone watch is *loaded* tonight.\n"
    "Here’s a combined thread of every team with something on the line:\n\n"
    "#hockeygamebot",
    "Tonight’s milestone tracker is live — goals, games played, and more on the horizon.\n"
    "Here’s everything in one place:\n\n"
    "#hockeygamebot",
    "Lots of career markers in reach tonight 🏒📈\n"
    "Here’s the consolidated milestone report from today’s bots:\n\n"
    "#hockeygamebot",
    "A fresh batch of milestone watches for tonight’s games 👇\n"
    "Here’s every team with players close to something big:\n\n"
    "#hockeygamebot",
    "Heading into tonight’s games, here are your milestone storylines to watch 🔍\n"
    "Collected from all currently running game bots:\n\n"
    "#hockeygamebot",
    "Tonight features several players knocking on the door of major milestones.\n"
    "Here’s your daily digest thread:\n\n"
    "#hockeygamebot",
    "Ready for tonight? Here are the milestone chases worth keeping an eye on 👀👇\n"
    "Full breakdown from all game bots:\n\n"
    "#hockeygamebot",
    "A lot of milestone heat in tonight’s matchups.\n"
    "Here’s a combined look at everything from around the league:\n\n"
    "#hockeygamebot",
    "Let’s kick off the night with a check on who’s approaching big career numbers.\n"
    "Here’s today’s milestone roundup:\n\n"
    "#hockeygamebot",
    "Daily Milestone Digest is here 🔔🏒\n"
    "Below is everything the game bots are tracking for tonight:\n\n"
    "#hockeygamebot",
    "Some fun milestone opportunities tonight — here’s the full consolidated list:\n"
    "(Collected automatically from all active bots)\n\n"
    "#hockeygamebot",
]


def _choose_intro() -> str:
    return random.choice(INTRO_VARIANTS)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_milestone_entries(milestones_dir: str | Path, date_str: str) -> List[Dict[str, Any]]:
    """
    Load all milestone JSON files for the given date.

    Expected layout:
        <milestones_dir>/<YYYY-MM-DD>/*.json
    """
    base = Path(milestones_dir)
    day_dir = base / date_str

    if not day_dir.exists() or not day_dir.is_dir():
        logger.info("Milestones directory %s does not exist; nothing to do.", day_dir)
        return []

    entries: List[Dict[str, Any]] = []
    for path in sorted(day_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            entries.append(data)
        except Exception:
            logger.exception("Failed to load milestone file: %s", path)

    return entries


def _scan_platform_availability(entries: List[Dict[str, Any]]) -> Tuple[bool, bool]:
    """
    Look across all milestone entries and determine whether we have at least one
    usable URL for X and/or Bluesky.

    Returns:
        (has_x, has_bluesky)
    """
    has_x = False
    has_bluesky = False

    for entry in entries:
        platform_posts: Dict[str, Dict[str, Any]] = entry.get("platform_posts") or {}

        x_post = platform_posts.get("x")
        if x_post:
            x_url = x_post.get("url") or x_post.get("uri")
            if x_url:
                has_x = True

        bsky_post = platform_posts.get("bluesky")
        if bsky_post:
            bsky_url = bsky_post.get("url") or bsky_post.get("uri")
            if bsky_url:
                has_bluesky = True

        if has_x and has_bluesky:
            break

    return has_x, has_bluesky


def _build_team_lines_for_entry(entry: Dict[str, Any]) -> Dict[str, str]:
    """
    Build per-platform reply lines for a single team entry.

    Returns a mapping of:
        { "x": "...", "bluesky": "..." }

    Only includes a platform if we have a URL for that platform in platform_posts.
    """
    team_abbrev = (entry.get("team_abbrev") or "").upper()
    hashtags = entry.get("hashtags") or []
    primary_hashtag = hashtags[0] if hashtags else (f"#{team_abbrev}" if team_abbrev else "#NHL")

    platform_posts: Dict[str, Dict[str, Any]] = entry.get("platform_posts") or {}

    lines: Dict[str, str] = {}

    # X: only if we have an X URL
    x_post = platform_posts.get("x")
    if x_post:
        x_url = x_post.get("url") or x_post.get("uri")
        if x_url:
            lines["x"] = f"{primary_hashtag} — milestone post: {x_url}"

    # Bluesky: only if we have a Bluesky URL
    bsky_post = platform_posts.get("bluesky")
    if bsky_post:
        bsky_url = bsky_post.get("url") or bsky_post.get("uri")
        if bsky_url:
            lines["bluesky"] = f"{primary_hashtag} — milestone post: {bsky_url}"

    return lines


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Post consolidated milestone digest thread.")
    parser.add_argument(
        "--config",
        required=True,
        help="Path to digest YAML config (e.g. config/config-hgb-digest.yaml)",
    )
    parser.add_argument(
        "--date",
        help="Date to process in YYYY-MM-DD format (defaults to today in local time).",
    )
    parser.add_argument(
        "--nosocial",
        action="store_true",
        help="Do not actually post to social platforms; log what would be posted.",
    )
    return parser.parse_args()


def _setup_logging() -> None:
    # Simple logging setup; you can swap this to utils.others.setup_logging if desired.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    _setup_logging()
    args = _parse_args()

    # Load configuration
    config = load_config(args.config)
    script_cfg = config.get("script", {}) or {}

    # Resolve date
    if args.date:
        date_str = args.date
    else:
        date_str = datetime.now().date().isoformat()

    milestones_dir = script_cfg.get("milestones_dir", "data/milestones")

    # Determine mode (env overrides YAML)
    env_mode = os.getenv("HOCKEYBOT_MODE")
    yaml_mode = script_cfg.get("mode") or "prod"
    mode = (env_mode or yaml_mode or "prod").lower()
    if mode not in ("prod", "debug"):
        mode = "prod"

    # Determine nosocial: CLI flag OR YAML
    yaml_nosocial = bool(script_cfg.get("nosocial", False))
    nosocial = bool(args.nosocial or yaml_nosocial)

    # Initialize SocialPublisher (correct signature)
    publisher = SocialPublisher(
        config=config,
        mode=mode,
        nosocial=nosocial,
    )

    # Load all milestone entries for this date
    entries = load_milestone_entries(milestones_dir, date_str)
    if not entries:
        logger.info("No milestone entries found for %s — nothing to do.", date_str)
        return

    # Scan which platforms actually have at least one URL
    has_x, has_bluesky = _scan_platform_availability(entries)

    platforms_for_intro: List[str] = []
    if has_x:
        platforms_for_intro.append("x")
    if has_bluesky:
        platforms_for_intro.append("bluesky")

    if not platforms_for_intro:
        logger.info(
            "No platforms have milestone URLs for %s — skipping entire digest run.",
            date_str,
        )
        return

    # Choose a random intro variant
    intro_msg = _choose_intro()

    logger.info(
        "Posting milestone digest for %s with %d team entries (intro platforms=%s).",
        date_str,
        len(entries),
        platforms_for_intro,
    )

    # Post intro only to platforms that actually have at least one URL
    intro_post_refs = publisher.post(
        message=intro_msg,
        event_type="milestone_digest",
        platforms=platforms_for_intro,
    )

    # Store the parent tweet per platform so we can build a continuous thread
    current_parent_refs = {platform: intro_post_refs[platform] for platform in platforms_for_intro}

    # We want to thread replies under the intro on each platform where it exists.
    # SocialPublisher.post returns dict[str, PostRef]
    # We'll pass the appropriate PostRef as reply_to for each platform.
    for entry in entries:
        per_platform_lines = _build_team_lines_for_entry(entry)

        if not per_platform_lines:
            logger.info(
                "Skipping digest reply for %s — no platform-specific URLs found.",
                entry.get("team_abbrev"),
            )
            continue

        for platform, line in per_platform_lines.items():
            parent_ref = current_parent_refs.get(platform)
            if not parent_ref:
                logger.info(
                    "No intro PostRef for %s on %s; skipping reply.",
                    entry.get("team_abbrev"),
                    platform,
                )
                continue

            logger.info(
                "Posting milestone digest reply for %s on %s: %s",
                entry.get("team_abbrev"),
                platform,
                line,
            )
            new_ref = publisher.reply(
                message=line,
                event_type="milestone_digest",
                reply_to=parent_ref,
                platforms=[platform],
            )

            # new_ref is a dict: {"x": PostRef(...)}
            # store the returned post ref as the new parent_ref for that platform
            if isinstance(new_ref, dict) and platform in new_ref:
                current_parent_refs[platform] = new_ref[platform]


if __name__ == "__main__":
    main()
