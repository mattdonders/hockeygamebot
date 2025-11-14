# social_state.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

from socials.types import PostRef

logger = logging.getLogger(__name__)

@dataclass
class StartOfGameSocial:
    """
    Tracks start-of-game (preview) posting state, content, and threading refs.
    Keep per-platform root/parent so you can thread independently.
    """

    # --- Per-platform thread anchors ---
    bluesky_root: Optional[PostRef] = None
    bluesky_parent: Optional[PostRef] = None
    threads_root: Optional[PostRef] = None
    threads_parent: Optional[PostRef] = None

    # --- Optional bookkeeping flags/metadata you already track ---
    did_season_series: bool = False
    did_team_stats: bool = False
    did_officials: bool = False

    # --- Your existing message content + sent flags ---
    core_msg: Optional[str] = None
    core_sent: bool = False

    season_series_msg: Optional[str] = None
    season_series_sent: bool = False

    team_stats_sent: bool = False

    goalies_pref_msg: Optional[str] = None
    goalies_pref_sent: bool = False
    goalies_other_msg: Optional[str] = None
    goalies_other_sent: bool = False

    officials_msg: Optional[str] = None
    officials_sent: bool = False

    pref_lines_msg: Optional[str] = None
    pref_lines_sent: bool = False
    pref_lines_resent: bool = False

    other_lines_msg: Optional[str] = None
    other_lines_sent: bool = False
    other_lines_resent: bool = False

    # This is for starting lineups
    starters_msg: Optional[str] = None
    starters_sent: bool = False

    # --- Misc debug / last responses ---
    last_payloads: Dict[str, Any] = field(default_factory=dict)

    # --- convenience helpers ---
    def set_root(self, platform: str, ref: PostRef) -> None:
        if platform == "bluesky":
            self.bluesky_root = ref
            self.bluesky_parent = ref
        elif platform == "threads":
            self.threads_root = ref
            self.threads_parent = ref

    def set_reply_parent(self, platform: str, ref: PostRef) -> None:
        if platform == "bluesky":
            self.bluesky_parent = ref
        elif platform == "threads":
            self.threads_parent = ref

    def get_parent(self, platform: str) -> Optional[PostRef]:
        if platform == "bluesky":
            return self.bluesky_parent
        if platform == "threads":
            return self.threads_parent
        return None

    def as_dict(self) -> Dict[str, Optional[Dict[str, Any]]]:
        """Serialize minimal thread anchors for persistence/logging."""

        def to_min(ref: Optional[PostRef]):
            if not ref:
                return None
            return {
                "platform": ref.platform,
                "id": ref.id,
                "uri": ref.uri,
                "cid": ref.cid,
                "published": ref.published,
            }

        return {
            "bluesky_root": to_min(self.bluesky_root),
            "bluesky_parent": to_min(self.bluesky_parent),
            "threads_root": to_min(self.threads_root),
            "threads_parent": to_min(self.threads_parent),
        }

    @property
    def all_pregame_sent(self) -> bool:
        """
        Returns True when the core preview set is posted.
        Tweak the checklist as you see fit.
        """
        pregame_checks = ("core_sent", "season_series_sent", "officials_sent")
        status = {attr: getattr(self, attr) for attr in pregame_checks}
        if not all(status.values()):
            logger.info("Pregame Socials Status: %s", status)
        return all(status.values())


@dataclass
class EndOfGameSocial:
    """
    Tracks end-of-game (final) posting state, content, and threading refs.
    """

    # --- Per-platform thread anchors ---
    bluesky_root: Optional[PostRef] = None
    bluesky_parent: Optional[PostRef] = None
    threads_root: Optional[PostRef] = None
    threads_parent: Optional[PostRef] = None

    # --- Final posting switches you had ---
    did_final_score: bool = False
    did_three_stars: bool = False
    did_team_stats: bool = False

    # --- Retry / diagnostics ---
    retry_count: int = 0
    last_payloads: Dict[str, Any] = field(default_factory=dict)

    # --- Scraped values you cache to avoid re-scraping ---
    hsc_homegs: Optional[str] = None
    hsc_awaygs: Optional[str] = None

    # --- Messages + sent flags you already track ---
    final_score_msg: Optional[str] = None
    final_score_sent: bool = False

    three_stars_msg: Optional[str] = None
    three_stars_sent: bool = False

    nst_linetool_msg: Optional[str] = None
    nst_linetool_sent: bool = False

    hsc_msg: Optional[str] = None
    hsc_sent: bool = False

    shotmap_retweet: bool = False

    team_stats_sent: bool = False

    # --- convenience helpers ---
    def set_root(self, platform: str, ref: PostRef) -> None:
        if platform == "bluesky":
            self.bluesky_root = ref
            self.bluesky_parent = ref
        elif platform == "threads":
            self.threads_root = ref
            self.threads_parent = ref

    def set_reply_parent(self, platform: str, ref: PostRef) -> None:
        if platform == "bluesky":
            self.bluesky_parent = ref
        elif platform == "threads":
            self.threads_parent = ref

    def get_parent(self, platform: str) -> Optional[PostRef]:
        if platform == "bluesky":
            return self.bluesky_parent
        if platform == "threads":
            return self.threads_parent
        return None

    def as_dict(self) -> Dict[str, Optional[Dict[str, Any]]]:
        def to_min(ref: Optional[PostRef]):
            if not ref:
                return None
            return {
                "platform": ref.platform,
                "id": ref.id,
                "uri": ref.uri,
                "cid": ref.cid,
                "published": ref.published,
            }

        return {
            "bluesky_root": to_min(self.bluesky_root),
            "bluesky_parent": to_min(self.bluesky_parent),
            "threads_root": to_min(self.threads_root),
            "threads_parent": to_min(self.threads_parent),
        }

    @property
    def all_social_sent(self) -> bool:
        """Returns True / False depending on if all final socials were sent."""
        # Consider only *_sent booleans
        sent_flags = [v for k, v in self.__dict__.items() if k.endswith("_sent")]
        return all(sent_flags)

    @property
    def retries_exceeded(self) -> bool:
        """Returns True if the number of retries (3 = default) has been exceeded."""
        return self.retry_count >= 3
