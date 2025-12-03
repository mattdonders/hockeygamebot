# core/events/event_cache.py
from __future__ import annotations

import json
import os
import tempfile
import time
from typing import Any, Dict, Optional, Set

CACHE_SCHEMA_VERSION = 1


class GameCache:
    """
    Restart-safe cache for per-game event processing.

    Each game gets its own JSON file:
      {root_dir}/{season_id}/{game_id}-{team_abbrev}.json

    Tracks:
      - processed_event_ids: eventIds we've already handled (to avoid reposting)
      - last_sort_order: highest sortOrder seen (fast gate)
      - goal_snapshots: optional dict for per-goal change detection (future-proof)
      - team_abbrev: preferred team abbreviation (for human-friendly inspection)
    """

    def __init__(
        self,
        root_dir: str,
        season_id: str,
        game_id: str,
        team_abbrev: str,
    ):
        self.root_dir = root_dir
        self.season_id = str(season_id)
        self.game_id = str(game_id)
        self.team_abbrev = str(team_abbrev)

        self.dirpath = os.path.join(self.root_dir, self.season_id)
        self.filepath = os.path.join(self.dirpath, f"{self.game_id}-{self.team_abbrev.lower()}.json")

        self.processed_event_ids: Set[str] = set()
        self.last_sort_order: Optional[int] = None
        self.goal_snapshots: Dict[str, Any] = {}

        self.pregame_posts: Dict[str, Any] = {"sent": {}, "root_refs": {}}

        self.meta: Dict[str, Any] = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "created_ts": int(time.time()),
            "updated_ts": int(time.time()),
        }

    def to_dict(self) -> dict:
        """
        Return a JSON-serializable snapshot of the cache.

        This is used both for persisting to disk and for exposing cache
        state on the monitoring dashboard.
        """
        return {
            "schema_version": CACHE_SCHEMA_VERSION,
            "season_id": self.season_id,
            "game_id": self.game_id,
            "team_abbrev": self.team_abbrev,
            "processed_event_ids": sorted(self.processed_event_ids),
            "last_sort_order": self.last_sort_order,
            "goal_snapshots": self.goal_snapshots,
            "meta": self.meta,
        }

    # ---------- public ----------

    def load(self) -> None:
        os.makedirs(self.dirpath, exist_ok=True)
        if not os.path.exists(self.filepath):
            return
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            # Corrupt cache? Start clean.
            return

        if data.get("schema_version") != CACHE_SCHEMA_VERSION:
            # If you bump schema, add a migration here; for now just read what we can.
            pass

        self.processed_event_ids = set(map(str, data.get("processed_event_ids", [])))
        self.last_sort_order = data.get("last_sort_order")
        self.goal_snapshots = data.get("goal_snapshots", {})
        self.team_abbrev = data.get("team_abbrev") or self.team_abbrev
        self.meta.update({k: v for k, v in data.get("meta", {}).items() if k != "schema_version"})
        self.meta["schema_version"] = CACHE_SCHEMA_VERSION

        sent = (data.get("pregame_posts") or {}).get("sent") or {}
        roots = (data.get("pregame_posts") or {}).get("root_refs") or {}
        self.pregame_posts = {"sent": dict(sent), "root_refs": dict(roots)}

    def save(self) -> None:
        self.meta["updated_ts"] = int(time.time())
        payload = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "game_id": self.game_id,  # NEW
            "season_id": self.season_id,  # NEW
            "team_abbrev": self.team_abbrev,
            "processed_event_ids": sorted(self.processed_event_ids),
            "last_sort_order": self.last_sort_order,
            "goal_snapshots": self.goal_snapshots,
            "meta": self.meta,
            "pregame_posts": self.pregame_posts,
        }

        os.makedirs(self.dirpath, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=f".{self.game_id}.", suffix=".json.tmp", dir=self.dirpath)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
            os.replace(tmp, self.filepath)  # atomic on POSIX
        finally:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass

    def has_seen(self, event_id: Any) -> bool:
        return str(event_id) in self.processed_event_ids

    def mark_seen(self, event_id: Any, sort_order: Optional[int]) -> None:
        self.processed_event_ids.add(str(event_id))
        if isinstance(sort_order, int):
            self.last_sort_order = max(self.last_sort_order or sort_order, sort_order)

    # Optional helpers (future-proof)
    def set_goal_snapshot(self, event_id: Any, snapshot: Dict[str, Any]) -> None:
        self.goal_snapshots[str(event_id)] = snapshot

    def get_goal_snapshot(self, event_id: Any) -> Optional[Dict[str, Any]]:
        return self.goal_snapshots.get(str(event_id))

    # ----------------------------------------------------------------------
    # Goal posting helpers (restart-safe)
    # These extend your existing "goal_snapshots" structure.
    # ----------------------------------------------------------------------

    def was_goal_posted(self, event_id: Any) -> bool:
        """
        Return True if this goal's *initial* post has already been sent.
        """
        snap = self.goal_snapshots.get(str(event_id), {})
        if not isinstance(snap, dict):
            return False
        return bool(snap.get("posted", False))

    def mark_goal_posted(
        self,
        event_id: Any,
        *,
        team_abbrev: Optional[str] = None,
        sort_order: Optional[int] = None,
    ) -> None:
        """
        Mark a goal as initially posted in this game.
        Does not overwrite existing highlight fields.
        """
        k = str(event_id)
        snap = self.goal_snapshots.setdefault(k, {})
        snap["posted"] = True

        if team_abbrev:
            snap["team_abbrev"] = team_abbrev
        if sort_order is not None:
            snap["sort_order"] = int(sort_order)

        self.save()

    def update_goal_snapshot(self, event_id: Any, **fields) -> None:
        """
        Upsert arbitrary fields (e.g., highlight URLs) for a goal.
        Safe to call repeatedly.
        """
        k = str(event_id)
        snap = self.goal_snapshots.setdefault(k, {})
        snap.update(fields)
        self.save()

    # ---------- pre-game socials helpers ----------

    def mark_pregame_sent(self, kind: str, refs: Optional[Dict[str, Any]] = None) -> None:
        """
        Record that a pre-game social of 'kind' has been sent, and optionally
        persist per-platform PostRef IDs as the shared thread roots.
        'refs' is expected to be a dict[str, PostRef].
        """
        sent = self.pregame_posts.setdefault("sent", {})
        roots = self.pregame_posts.setdefault("root_refs", {})

        sent[kind] = True

        if refs:
            for platform, ref in refs.items():
                # Defensive: only look for the fields we care about
                roots[platform] = {
                    "platform": getattr(ref, "platform", platform),
                    "id": getattr(ref, "id", None),
                }

    def is_pregame_sent(self, kind: str) -> bool:
        return bool(self.pregame_posts.get("sent", {}).get(kind, False))

    def get_pregame_root_refs(self) -> Dict[str, Dict[str, str]]:
        """
        Returns the stored per-platform thread roots:
        { "bluesky": {"platform": "bluesky", "id": "..."}, ... }
        """
        return self.pregame_posts.get("root_refs", {}) or {}
