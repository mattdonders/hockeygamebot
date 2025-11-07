# socials/publisher.py
from __future__ import annotations

import inspect
import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import yaml

from socials.types import PostRef

from .base import SocialPost
from .bluesky_client import BlueskyClient, BlueskyConfig
from .threads_client import ThreadsClient, ThreadsConfig


@runtime_checkable
class SocialClient(Protocol):
    def post(self, post: SocialPost, reply_to_ref: PostRef | None = None) -> PostRef: ...


class SocialPublisher:
    """Platform-agnostic publisher.

    - post(): fire-and-forget (doesn't affect per-platform reply anchors)
    - reply(): replies to last known PostRef per platform (or a supplied PostRef/state)
               and advances the anchors (and state, if provided)
    - post_and_seed(): post() and remember the returned PostRef(s) as new reply anchors;
                       also seeds a provided state with roots/parents
    """

    def __init__(
        self,
        config: dict | str | Path,  # accept dict or path to YAML
        mode: str | None = None,  # "prod" | "debug" (overrides YAML)
        nosocial: bool | None = None,  # override YAML script.nosocial
        monitor: object | None = None,  # optional status monitor
    ):
        # Load config if a path/str was provided
        if isinstance(config, (str, Path)):
            cfg_path = Path(config)
            with cfg_path.open(encoding="utf-8") as f:
                self.cfg: dict = yaml.safe_load(f)
        else:
            self.cfg = dict(config)

        # Resolve mode / nosocial
        cfg_script = self.cfg.get("script", {}) or {}
        self.mode = (mode or cfg_script.get("mode") or "prod").lower()
        if self.mode not in ("prod", "debug"):
            self.mode = "prod"

        cfg_nosocial = bool(cfg_script.get("nosocial", False))
        self.nosocial = cfg_nosocial if nosocial is None else bool(nosocial)

        self.monitor = monitor
        self.socials = self.cfg.get("socials", {}) or {}

        # Instantiate enabled clients
        self._bsky = None
        if self.socials.get("bluesky", False):
            bc = self.cfg["bluesky"][self.mode]
            self._bsky = BlueskyClient(
                BlueskyConfig(
                    handle=bc["handle"],
                    app_password=bc["app_password"],
                    service_url=bc.get("service_url"),
                ),
            )

        self._thr = None
        if self.socials.get("threads", False):
            tc = self.cfg["threads"][self.mode]
            self._thr = ThreadsClient(
                ThreadsConfig(access_token=tc["access_token"]),
                root_cfg=self.cfg,  # used for image hosting by Threads client
            )

        # Registry of active platforms
        self._platforms: dict[str, SocialClient] = {}
        if self._bsky:
            self._platforms["bluesky"] = self._bsky
        if self._thr:
            self._platforms["threads"] = self._thr

        # Per-platform “last reply anchor”
        self._last: dict[str, PostRef] = {}

    # ---------- lifecycle ----------
    def login_all(self) -> None:
        """Login/session-restore across enabled clients. Safe to call unconditionally."""
        for name, client in self._platforms.items():
            if hasattr(client, "login_or_restore"):
                try:
                    client.login_or_restore()  # type: ignore[attr-defined]
                except Exception as e:
                    logging.exception("Login/restore failed for %s: %s", name, e)

    # ---------- high-level API ----------
    def post(
        self,
        message: str | None = None,
        media: str | list[str] | None = None,
        reply_root: PostRef | None = None,  # kept for backward compat (unused by adapters)
        reply_parent: PostRef | None = None,  # if provided, used only when platform matches
        platforms: str | Iterable[str] = "enabled",
        alt_text: str | None = None,
        state: Any | None = None,  # accepted but intentionally ignored in post()
    ) -> dict[str, PostRef]:
        """Create a new post on 1+ platforms. Does NOT update reply anchors.
        'state' is accepted for API symmetry but not used here.
        """
        # NOSOCIAL centrally
        if self.nosocial:
            self._log_nosocial_preview(message)
            return {}

        targets = self._resolve_targets(platforms)
        results: dict[str, PostRef] = {}

        media_path: str | None = None
        if isinstance(media, list):
            media_path = media[0] if media else None
        elif isinstance(media, str):
            media_path = media

        for name, client in self._iter_clients(targets):
            rp = reply_parent if (reply_parent and reply_parent.platform == name) else None
            sp = SocialPost(
                text=message,
                local_image=(
                    Path(media_path)
                    if (media_path and not str(media_path).startswith(("http://", "https://")))
                    else None
                ),
                image_url=(
                    media_path if (media_path and str(media_path).startswith(("http://", "https://"))) else None
                ),
                alt_text=alt_text,
            )
            ref: PostRef = client.post(sp, reply_to_ref=rp)
            if ref:
                results[name] = ref

        return results

    def reply(
        self,
        message: str,
        media: str | None = None,
        platforms: str | Iterable[str] = "enabled",
        reply_to: PostRef | None = None,
        alt_text: str | None = None,
        state: Any | None = None,  # NEW: use/advance per-platform parents from state
    ) -> dict[str, PostRef]:
        """Reply to the current anchor (publisher's _last or provided state) or to an explicit PostRef.
        Advances both the publisher anchors and 'state' parents if provided.
        """
        if self.nosocial:
            self._log_nosocial_preview(message)
            return {}

        targets = self._resolve_targets(platforms)
        results: dict[str, PostRef] = {}

        for name, client in self._iter_clients(targets):
            # Determine the reply parent precedence:
            # 1) explicit reply_to (must match platform)
            # 2) parent from state (if available)
            # 3) publisher's last anchor
            parent = None
            if reply_to and reply_to.platform == name:
                parent = reply_to
            elif state is not None:
                parent = self._get_state_parent(state, name)
            if parent is None:
                parent = self._last.get(name)

            sp = SocialPost(
                text=message,
                local_image=(Path(media) if media and not str(media).startswith(("http://", "https://")) else None),
                image_url=(media if media and str(media).startswith(("http://", "https://")) else None),
                alt_text=alt_text,
            )
            ref: PostRef = client.post(sp, reply_to_ref=parent)
            if ref:
                results[name] = ref
                # advance publisher anchor and (optionally) state parent
                self._last[name] = ref
                if state is not None:
                    self._set_state_parent(state, name, ref)

        return results

    def post_and_seed(
        self,
        message: str,
        media: str | None = None,
        platforms: str | Iterable[str] = "enabled",
        alt_text: str | None = None,
        state: Any | None = None,  # NEW: also seed state roots/parents
    ) -> dict[str, PostRef]:
        """post() and store returned PostRef(s) as new per-platform reply anchors.
        If 'state' is provided, it seeds both roots and parents per platform.
        """
        results = self.post(message=message, media=media, platforms=platforms, alt_text=alt_text)
        for name, ref in results.items():
            self._last[name] = ref
        if state is not None:
            self._seed_state(state, results)
        return results

    # ---------- helpers: anchors & state ----------
    def set_anchor(self, platform: str, ref: PostRef) -> None:
        """Manually set/override the reply anchor for a platform."""
        self._last[platform] = ref

    def get_anchor(self, platform: str) -> PostRef | None:
        return self._last.get(platform)

    # --- state wiring (works with your StartOfGameSocial or similar) ---
    def _seed_state(self, state: Any, results: dict[str, PostRef]) -> None:
        """Seed both root and parent for each platform in 'state'.
        We try a few shapes to maximize compatibility:
          - state.set_root(platform, ref)  (your helper, if present)
          - setattr(state, f"{platform}_root", ref) / f"{platform}_parent"
        """
        for platform, ref in results.items():
            # prefer a helper if present
            if hasattr(state, "set_root") and callable(state.set_root):
                try:
                    state.set_root(platform, ref)
                    continue
                except Exception:
                    pass
            # fallback to attrs like bluesky_root / bluesky_parent
            root_attr = f"{platform}_root"
            parent_attr = f"{platform}_parent"
            if hasattr(state, root_attr):
                setattr(state, root_attr, ref)
            if hasattr(state, parent_attr):
                setattr(state, parent_attr, ref)

    def _get_state_parent(self, state: Any, platform: str) -> PostRef | None:
        """Read the current per-platform parent from 'state'.
        Looks for {platform}_parent (e.g., bluesky_parent / threads_parent).
        """
        attr = f"{platform}_parent"
        return getattr(state, attr, None)

    def _set_state_parent(self, state: Any, platform: str, ref: PostRef) -> None:
        """Advance the per-platform parent in 'state' after a reply."""
        attr = f"{platform}_parent"
        if hasattr(state, attr):
            setattr(state, attr, ref)

    # ---------- target resolution & iteration ----------
    def _resolve_targets(self, platforms: str | Iterable[str]) -> list[str]:
        if isinstance(platforms, str):
            if platforms == "enabled":
                return list(self._platforms.keys())
            return [p for p in [platforms] if p in self._platforms]
        return [p for p in platforms if p in self._platforms]

    def _iter_clients(self, targets: Iterable[str]):
        for name in targets:
            client = self._platforms.get(name)
            if client:
                yield name, client

    # ---------- NOSOCIAL logging ----------
    def _log_nosocial_preview(self, message: str | None) -> None:
        if message:
            preview = message.strip().replace("\n", " ")[:180]
            logging.info(f"[NOSOCIAL] Would post → {preview}")
            logging.debug(f"[NOSOCIAL-FULL]\n{message}")
        else:
            logging.info("[NOSOCIAL] Would post an image-only update.")
        # Call monitor without guessing parameters
        mon = getattr(self, "monitor", None)
        if mon and hasattr(mon, "record_social_post"):
            try:
                # Introspect to avoid arg mismatches
                sig = inspect.signature(mon.record_social_post)
                kwargs = {}
                # Only pass kwargs that the monitor method actually accepts
                if "message" in sig.parameters and message:
                    kwargs["message"] = message
                mon.record_social_post(**kwargs)
            except Exception as e:
                logging.warning("Monitor record failed in NOSOCIAL: %s", e)
