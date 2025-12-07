# socials/utils.py
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict

from socials.types import PostRef

logger = logging.getLogger(__name__)


def seed_roots_from_results(social_state, results: Dict[str, PostRef]) -> None:
    """
    Seed per-platform thread roots/parents from a platform->PostRef map.
    Works for any platform names present in `results`.
    """
    for platform, ref in results.items():
        # social_state must implement set_root(platform, PostRef)
        social_state.set_root(platform, ref)


def any_posted(results: Dict[str, PostRef]) -> bool:
    """True if at least one platform returned a PostRef."""
    return bool(results)


def update_parents_from_results(preview_socials, results: dict[str, "PostRef"]) -> None:
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


def normalize_post_refs(results) -> list[PostRef]:
    """
    Normalize whatever SocialPublisher returns into a list[PostRef].

    Handles:
      - a single PostRef
      - a single dict-like result (with keys like platform/id/uri/url)
      - a dict mapping platform -> PostRef / dict
      - a list/tuple/set of PostRef / dict
    """
    refs: list[PostRef] = []

    if results is None:
        return refs

    # Normalize to a simple iterable of "items" we can coerce one by one.
    if isinstance(results, (list, tuple, set)):
        items = list(results)
    elif isinstance(results, dict):
        # If this dict looks like a single PostRef-like dict, treat it as one item.
        if any(k in results for k in ("platform", "id", "uri", "url", "cid", "tweet_id", "post_id")):
            items = [results]
        else:
            # Otherwise assume it's a mapping of {platform: obj}
            items = list(results.values())
    else:
        items = [results]

    for obj in items:
        # Already a PostRef
        if isinstance(obj, PostRef):
            # Skip pure placeholders (no id/uri)
            if not obj.id and not getattr(obj, "uri", None):
                continue
            refs.append(obj)
            continue

        # Dict-like result from a client or publisher
        if isinstance(obj, dict):
            platform = obj.get("platform") or "unknown"

            canonical_id = (
                obj.get("id")
                or obj.get("tweet_id")
                or obj.get("post_id")
                or obj.get("container_id")
                or obj.get("uri")
                or obj.get("url")
                or ""
            )

            uri = obj.get("uri") or obj.get("url")

            # If we have neither id nor uri, this is almost certainly a debug/nosocial placeholder.
            if not canonical_id and not uri:
                continue

            try:
                ref = PostRef(
                    platform=str(platform),
                    id=str(canonical_id),
                    uri=uri,
                    cid=obj.get("cid"),
                    published=bool(obj.get("published", True)),
                    raw=obj,
                )
                refs.append(ref)
            except Exception:
                logger.exception("normalize_post_refs: failed to build PostRef from dict: %r", obj)
            continue

        # Anything else we don't understand
        logger.debug("normalize_post_refs: unsupported item type %r (%r)", type(obj), obj)

    return refs


def write_milestones_index(context: "GameContext", milestone_msg: str, post_refs: list[PostRef]) -> None:
    """
    Writes a per-team JSON file describing the milestone pre-game post.

    Layout:
        <milestones_dir>/YYYY-MM-DD/<team-abbrev>-milestones.json

    This is consumed later by the milestone digest script.
    """
    try:
        script_cfg = context.config.get("script", {}) or {}
        base_dir = Path(script_cfg.get("milestones_dir", "data/milestones"))

        if getattr(context, "game_time_local", None) is not None:
            game_date = context.game_time_local.date()
        else:
            game_date = datetime.now().date()
        date_str = game_date.isoformat()

        team = getattr(context, "preferred_team", None)
        team_abbrev = getattr(team, "abbreviation", None) or "unknown"
        team_slug = team_abbrev.lower()
        team_name = getattr(team, "full_name", None) or team_abbrev

        out_dir = base_dir / date_str
        out_dir.mkdir(parents=True, exist_ok=True)

        # Collect hashtags
        hashtags: list[str] = []
        if getattr(team, "hashtag", None):
            hashtags.append(team.hashtag)
        if getattr(context, "game_hashtag", None):
            hashtags.append(context.game_hashtag)

        platform_posts: Dict[str, Dict[str, object]] = {}

        for ref in post_refs:
            if not ref or not getattr(ref, "platform", None):
                continue

            platform = ref.platform
            uri = getattr(ref, "uri", None)
            pid = getattr(ref, "id", None)

            # For now, just trust whatever the client put in `uri` as a usable URL/identifier.
            url = uri

            platform_posts[platform] = {
                "platform": platform,
                "id": pid,
                "uri": uri,
                "url": url,
                "published": bool(getattr(ref, "published", True)),
            }

        out_path = out_dir / f"{team_slug}-milestones.json"

        payload = {
            "team_name": team_name,
            "team_abbrev": team_abbrev,
            "game_id": getattr(context, "game_id", None),
            "date": date_str,
            "milestone_message": milestone_msg,
            "hashtags": hashtags,
            "platform_posts": platform_posts,
        }

        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info("Wrote milestone index file: %s", out_path)

    except Exception:
        logger.exception("Failed writing milestone index JSON")
