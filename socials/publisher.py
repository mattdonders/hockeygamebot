# socials/publisher.py
from __future__ import annotations

import inspect
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Union
from uuid import uuid4

import yaml

from socials.types import PostRef

from .base import SocialPost
from .bluesky_client import BlueskyClient, BlueskyConfig
from .threads_client import ThreadsClient, ThreadsConfig
from .x_client import XClient, XConfig

logger = logging.getLogger(__name__)


class SocialPublisher:
    """
    Platform-agnostic publisher.

    - post(): fire-and-forget (doesn't affect per-platform reply anchors)
    - reply(): replies to last known PostRef per platform (or a supplied PostRef/state)
               and advances the anchors (and state, if provided)
    - post_and_seed(): post() and remember the returned PostRef(s) as new reply anchors;
                       also seeds a provided state with roots/parents
    """

    def __init__(
        self,
        config: Union[dict, str, Path],  # accept dict or path to YAML
        mode: Optional[str] = None,  # "prod" | "debug" (overrides YAML)
        nosocial: Optional[bool] = None,  # override YAML script.nosocial
        monitor: Optional[object] = None,  # optional status monitor
    ):
        # Load config if a path/str was provided
        if isinstance(config, (str, Path)):
            with open(config, "r", encoding="utf-8") as f:
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

        # Bluesky
        self._bsky = None
        if self.socials.get("bluesky", False):
            bc = self.cfg["bluesky"][self.mode]
            self._bsky = BlueskyClient(
                BlueskyConfig(
                    handle=bc["handle"],
                    app_password=bc["app_password"],
                    service_url=bc.get("service_url"),
                )
            )

        # Threads
        self._thr = None
        if self.socials.get("threads", False):
            tc = self.cfg["threads"][self.mode]
            self._thr = ThreadsClient(
                ThreadsConfig(access_token=tc["access_token"]),
                root_cfg=self.cfg,  # used for image hosting by Threads client
            )

        # X / Twitter
        self._x = None
        if self.socials.get("x", False) or self.socials.get("twitter", False):
            xc = self.cfg["x"][self.mode]
            self._x = XClient(
                XConfig(
                    consumer_key=xc["consumer_key"],
                    consumer_secret=xc["consumer_secret"],
                    access_token=xc["access_token"],
                    access_token_secret=xc["access_token_secret"],
                )
            )

        # Registry of active platforms
        self._platforms: dict[str, object] = {}
        if self._bsky:
            self._platforms["bluesky"] = self._bsky
        if self._thr:
            self._platforms["threads"] = self._thr
        if self._x:
            self._platforms["x"] = self._x

        # Per-platform “last reply anchor”
        self._last: Dict[str, PostRef] = {}

    # ---------- lifecycle ----------
    def login_all(self) -> None:
        """Login/session-restore across enabled clients. Safe to call unconditionally."""
        for name, client in self._platforms.items():
            if hasattr(client, "login_or_restore"):
                try:
                    client.login_or_restore()
                except Exception as e:
                    logger.exception("Login/restore failed for %s: %s", name, e)

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
        """
        Create a new post on 1+ platforms. Does NOT update reply anchors.
        'state' is accepted for API symmetry but not used here.
        """
        # NOSOCIAL centrally
        if self.nosocial:
            targets = self._resolve_targets(platforms)
            results: dict[str, PostRef] = {}

            for name in targets:
                # Per-platform logging
                if message:
                    preview = message.strip().replace("\n", " ")[:180]
                    logger.info("[NOSOCIAL] (%s) Would post → %s", name, preview)
                    logger.debug("[NOSOCIAL-FULL] (%s)\n%s", name, message)
                else:
                    logger.info("[NOSOCIAL] (%s) Would post an image-only update.", name)

                results[name] = PostRef(platform=name, id=f"nosocial-{uuid4()}")

            # Keep the monitor behavior
            self._log_nosocial_preview(message)
            return results

        targets = self._resolve_targets(platforms)
        results: dict[str, PostRef] = {}

        # Normalize media into local vs hosted lists without losing items
        local_paths: list[str] = []
        hosted_urls: list[str] = []
        if isinstance(media, list):
            for m in media:
                if isinstance(m, str) and m.startswith(("http://", "https://")):
                    hosted_urls.append(m)
                elif m:
                    local_paths.append(str(m))
        elif isinstance(media, str):
            if media.startswith(("http://", "https://")):
                hosted_urls.append(media)
            else:
                local_paths.append(media)

        for name, client in self._iter_clients(targets):
            rp = reply_parent if (reply_parent and reply_parent.platform == name) else None
            sp = SocialPost(
                text=message,
                # singletons stay compatible; lists enable multi-image
                local_image=Path(local_paths[0]) if len(local_paths) == 1 else None,
                image_url=hosted_urls[0] if (len(hosted_urls) == 1 and not local_paths) else None,
                local_images=[Path(p) for p in local_paths] if len(local_paths) > 1 else None,
                images=hosted_urls if len(hosted_urls) > 1 or (hosted_urls and local_paths) else None,
                alt_text=alt_text,
            )
            ref: PostRef = client.post(sp, reply_to_ref=rp)
            if ref:
                results[name] = ref

        return results

    def reply(
        self,
        message: str,
        media: str | list[str] | None = None,
        platforms: str | Iterable[str] = "enabled",
        reply_to: PostRef | None = None,
        alt_text: str | None = None,
        state: Any | None = None,  # NEW: use/advance per-platform parents from state
    ) -> dict[str, PostRef]:
        """
        Reply to the current anchor (publisher's _last or provided state) or to an explicit PostRef.
        Advances both the publisher anchors and 'state' parents if provided.
        """
        if self.nosocial:
            targets = self._resolve_targets(platforms)
            results: dict[str, PostRef] = {}

            for name in targets:
                # Per-platform logging
                if message:
                    preview = message.strip().replace("\n", " ")[:180]
                    logger.info("[NOSOCIAL] (%s) Would reply → %s", name, preview)
                    logger.debug("[NOSOCIAL-FULL] (%s)\n%s", name, message)
                else:
                    logger.info("[NOSOCIAL] (%s) Would reply with image-only update.", name)

                results[name] = PostRef(platform=name, id=f"nosocial-{uuid4()}")

            # Keep monitor behavior unchanged
            self._log_nosocial_preview(message)
            return results

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

            # normalize media like in post()
            local_paths: list[str] = []
            hosted_urls: list[str] = []
            if isinstance(media, list):
                for m in media:
                    if isinstance(m, str) and m.startswith(("http://", "https://")):
                        hosted_urls.append(m)
                    elif m:
                        local_paths.append(str(m))
            elif isinstance(media, str):
                if media.startswith(("http://", "https://")):
                    hosted_urls.append(media)
                elif media:
                    local_paths.append(media)
            sp = SocialPost(
                text=message,
                local_image=Path(local_paths[0]) if len(local_paths) == 1 else None,
                image_url=hosted_urls[0] if (len(hosted_urls) == 1 and not local_paths) else None,
                local_images=[Path(p) for p in local_paths] if len(local_paths) > 1 else None,
                images=hosted_urls if len(hosted_urls) > 1 or (hosted_urls and local_paths) else None,
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
        """
        post() and store returned PostRef(s) as new per-platform reply anchors.
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
        """
        Seed both root and parent for each platform in 'state'.
        We try a few shapes to maximize compatibility:
          - state.set_root(platform, ref)  (your helper, if present)
          - setattr(state, f"{platform}_root", ref) / f"{platform}_parent"
        """
        for platform, ref in results.items():
            # prefer a helper if present
            if hasattr(state, "set_root") and callable(getattr(state, "set_root")):
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
        """
        Read the current per-platform parent from 'state'.
        Looks for {platform}_parent (e.g., bluesky_parent / threads_parent).
        """
        attr = f"{platform}_parent"
        return getattr(state, attr, None)

    def _set_state_parent(self, state: Any, platform: str, ref: PostRef) -> None:
        """
        Advance the per-platform parent in 'state' after a reply.
        """
        attr = f"{platform}_parent"
        if hasattr(state, attr):
            setattr(state, attr, ref)

    def restore_roots_from_cache(
        self,
        roots: Dict[str, Dict[str, str]],
        state: Any | None = None,
    ) -> None:
        """
        Restore per-platform reply anchors and optional state roots/parents
        from cached PostRef data.

        'roots' is expected to look like:
        {
            "bluesky": {"platform": "bluesky", "id": "..."},
            "threads": {"platform": "threads", "id": "..."},
        }
        """
        if not roots:
            return

        for platform, info in roots.items():
            post_id = info.get("id")
            if not post_id:
                continue

            ref = PostRef(platform=platform, id=post_id)

            # Restore internal anchor so future .reply() calls thread correctly
            self._last[platform] = ref

            if state is not None:
                # Try to seed <platform>_root and <platform>_parent on the StartOfGameSocial state
                root_attr = f"{platform}_root"
                parent_attr = f"{platform}_parent"

                if hasattr(state, root_attr):
                    setattr(state, root_attr, ref)
                if hasattr(state, parent_attr):
                    setattr(state, parent_attr, ref)

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
        # Keep monitor behavior the same
        mon = getattr(self, "monitor", None)
        if mon and hasattr(mon, "record_social_post"):
            try:
                import inspect

                sig = inspect.signature(mon.record_social_post)
                kwargs = {}
                if "message" in sig.parameters and message:
                    kwargs["message"] = message
                mon.record_social_post(**kwargs)
            except Exception as e:
                logger.warning("Monitor record failed in NOSOCIAL: %s", e)
