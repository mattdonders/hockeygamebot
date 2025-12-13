# socials/x_rate_limiter.py
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# -------------------------------
# Public helper (unchanged API)
# -------------------------------


def build_x_limit_warning(
    enabled_platforms: set[str],
    bluesky_handle: str | None = None,
) -> str:
    """
    Build a platform-aware warning message when the X daily limit is hit.

    - If Bluesky enabled → mention Bluesky (and handle if available)
    - If other platforms enabled → mention them generically
    - If X is the only platform → generic “see you tomorrow” message
    """
    # NOTE: Keep this text consistent with your bot voice; tweak if desired.
    has_bsky = "bluesky" in enabled_platforms or "bsky" in enabled_platforms
    other_platforms = sorted(p for p in enabled_platforms if p not in {"x", "twitter"})

    lines: list[str] = []
    lines.append("Due to daily posting limits on X, this bot has to stop posting updates early today.")
    lines.append("")
    if has_bsky:
        if bluesky_handle:
            lines.append(f"We’ll keep posting on Bluesky: {bluesky_handle}")
        else:
            lines.append("We’ll keep posting on Bluesky.")
        if other_platforms:
            # Avoid listing "x" itself; we already said X is blocked.
            others = ", ".join(p for p in other_platforms if p not in {"bluesky", "bsky"})
            if others:
                lines.append(f"We’ll also keep posting on: {others}")
    else:
        if other_platforms:
            others = ", ".join(other_platforms)
            lines.append(f"We’ll keep posting on: {others}")

    lines.append("")
    lines.append("We’ll be back with updates once our posting limit clears.")
    return "\n".join(lines)


# -------------------------------
# Rolling-window limiter
# -------------------------------


@dataclass(frozen=True)
class XLimitState:
    posts: list[int]  # epoch seconds for successful POST /2/tweets (includes warning tweet)
    warning_sent: bool  # whether we already sent the warning tweet for the *current* rolling window state
    warning_post_ts: int  # epoch seconds; when we last successfully posted the warning tweet (0 if never)
    disabled_until: int  # epoch seconds; if > now, do not attempt posting to X
    last_429_at: int  # epoch seconds; last time we saw a 429 (for debugging)
    last_reset_hint: int  # epoch seconds; best-known reset time from headers (for debugging)


class XRateLimiter:
    """
    Enforces a rolling 24-hour window locally.

    - Tracks successful tweet create timestamps (epoch seconds) in `posts[]`.
    - Rolling count is posts in the last 24 hours.
    - Supports a "content stop" threshold (e.g., 15) and a hard ceiling (e.g., 17).
    - When a 429 occurs, you can set disabled_until to stop attempts until reset.
    """

    WINDOW_SECONDS = 24 * 60 * 60

    def __init__(
        self,
        state_path: str | Path,
        daily_limit: int = 17,  # hard cap (Free tier)
        content_limit: int = 15,  # your “stop content” threshold
    ):
        self.state_path = Path(state_path)
        self.daily_limit = int(daily_limit)
        self.content_limit = int(content_limit)

        self._state: XLimitState = self._load_state()
        self._prune_and_save_if_needed()

    # ---------- Internals ----------

    @staticmethod
    def _now() -> int:
        return int(time.time())

    def _load_state(self) -> XLimitState:
        if not self.state_path.exists():
            return XLimitState(
                posts=[],
                warning_sent=False,
                warning_post_ts=0,
                disabled_until=0,
                last_429_at=0,
                last_reset_hint=0,
            )

        try:
            raw = json.loads(self.state_path.read_text())
        except Exception:
            # Corrupt file → fail safe: disable X for 15 minutes so we don’t spam retries
            return XLimitState(
                posts=[],
                warning_sent=False,
                warning_post_ts=0,
                disabled_until=self._now() + 15 * 60,
                last_429_at=self._now(),
                last_reset_hint=0,
            )

        # Legacy format support: {"day": "...", "count": N, "warning_sent": bool}
        if isinstance(raw, dict) and "posts" not in raw and "count" in raw:
            count = int(raw.get("count", 0) or 0)
            warning_sent = bool(raw.get("warning_sent", False))

            # Conservative migration: assume those posts happened within the last 24 hours.
            # We backfill timestamps spaced 60s apart ending “now”.
            now = self._now()
            backfilled = [now - (i * 60) for i in range(count)][::-1]

            return XLimitState(
                posts=backfilled,
                warning_sent=warning_sent,
                warning_post_ts=0,
                disabled_until=0,
                last_429_at=0,
                last_reset_hint=0,
            )

        posts = [int(x) for x in (raw.get("posts") or []) if isinstance(x, (int, float, str))]
        posts = [int(x) for x in posts]

        return XLimitState(
            posts=posts,
            warning_sent=bool(raw.get("warning_sent", False)),
            warning_post_ts=int(raw.get("warning_post_ts", 0) or 0),
            disabled_until=int(raw.get("disabled_until", 0) or 0),
            last_429_at=int(raw.get("last_429_at", 0) or 0),
            last_reset_hint=int(raw.get("last_reset_hint", 0) or 0),
        )

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "posts": self._state.posts,
            "warning_sent": self._state.warning_sent,
            "disabled_until": self._state.disabled_until,
            "last_429_at": self._state.last_429_at,
            "last_reset_hint": self._state.last_reset_hint,
        }
        self.state_path.write_text(json.dumps(payload, indent=2, sort_keys=True))

    def _prune_posts(self) -> bool:
        """Prune anything older than the rolling window. Returns True if it changed."""
        now = self._now()
        cutoff = now - self.WINDOW_SECONDS
        before = len(self._state.posts)
        kept = [ts for ts in self._state.posts if ts >= cutoff]
        changed = len(kept) != before
        if changed:
            # If the window moved, allow a warning again when we re-approach the content limit.
            # (Otherwise a warning sent yesterday could block warning today even after posts fall out.)
            # We only reset warning_sent when pruning actually changes the window.
            # Only clear warning_sent if the last warning is outside the rolling window.
            warning_in_window = self._state.warning_post_ts >= cutoff if self._state.warning_post_ts else False
            self._state = XLimitState(
                posts=kept,
                warning_sent=(True if warning_in_window else False),
                warning_post_ts=(self._state.warning_post_ts if warning_in_window else 0),
                disabled_until=self._state.disabled_until,
                last_429_at=self._state.last_429_at,
                last_reset_hint=self._state.last_reset_hint,
            )
        return changed

    def _prune_and_save_if_needed(self) -> None:
        changed = self._prune_posts()
        if changed:
            self._save_state()

    # ---------- Public API used by Publisher ----------

    def mark_warning_sent(self):
        """Mark warning as sent without incrementing the post counter."""
        now = self._now()
        self._state.warning_sent = True
        self._state.warning_post_ts = now
        self._save_state()

    def get_state(self) -> dict[str, Any]:
        """Useful for dashboards/monitors."""
        self._prune_and_save_if_needed()
        now = self._now()
        rolling_count = self.get_rolling_count()
        return {
            "rolling_count": rolling_count,
            "content_limit": self.content_limit,
            "daily_limit": self.daily_limit,
            "warning_sent": self._state.warning_sent,
            "warning_post_ts": self._state.warning_post_ts,
            "disabled_until": self._state.disabled_until,
            "disabled_for_seconds": max(0, self._state.disabled_until - now),
            "last_429_at": self._state.last_429_at,
            "last_reset_hint": self._state.last_reset_hint,
        }

    def get_rolling_count(self) -> int:
        self._prune_and_save_if_needed()
        return len(self._state.posts)

    def can_post_regular(self) -> bool:
        """
        Whether we should include X in normal posting targets.
        - False if disabled_until is active (recent 429)
        - False if we reached content_limit (your early stop)
        """
        self._prune_and_save_if_needed()
        now = self._now()

        if self._state.disabled_until and now < self._state.disabled_until:
            return False

        return self.get_rolling_count() < self.content_limit

    def should_send_warning(self) -> bool:
        """
        Whether we should send the one-time warning tweet and then drop X from targets.
        """
        self._prune_and_save_if_needed()
        now = self._now()

        if self._state.disabled_until and now < self._state.disabled_until:
            return False

        count = self.get_rolling_count()
        if self._state.warning_sent:
            return False

        # Extra guard: never send two warnings inside the same rolling window,
        # even if warning_sent gets toggled for any reason.
        if self._state.warning_post_ts and (now - self._state.warning_post_ts) < self.WINDOW_SECONDS:
            return False

        # send warning once when we hit content_limit
        return count >= self.content_limit and count < self.daily_limit

    def record_post(self, is_warning: bool = False, ts: int | None = None) -> None:
        """
        Record a successful tweet create (POST /2/tweets).
        Call this only when X actually returned success (ref is not None).
        """
        self._prune_and_save_if_needed()
        now = int(ts) if ts is not None else self._now()

        posts = list(self._state.posts)
        posts.append(now)

        self._state = XLimitState(
            posts=posts,
            warning_sent=(True if is_warning else self._state.warning_sent),
            warning_post_ts=(now if is_warning else self._state.warning_post_ts),
            disabled_until=self._state.disabled_until,
            last_429_at=self._state.last_429_at,
            last_reset_hint=self._state.last_reset_hint,
        )
        self._save_state()

    def record_rate_limited(self, reset_epoch: int | None = None) -> None:
        """
        Call this when X returns 429 for POST /2/tweets.
        This disables X until reset_epoch (if provided), otherwise uses a conservative fallback.
        """
        self._prune_and_save_if_needed()
        now = self._now()

        # Fallback: assume it’s at least a 15-minute bucket if we can’t read anything.
        fallback = now + 15 * 60
        disabled_until = int(reset_epoch) if reset_epoch else fallback

        # Guard against weird values (past timestamps)
        if disabled_until < now:
            disabled_until = fallback

        self._state = XLimitState(
            posts=self._state.posts,
            warning_sent=self._state.warning_sent,
            warning_post_ts=self._state.warning_post_ts,
            disabled_until=disabled_until,
            last_429_at=now,
            last_reset_hint=disabled_until,
        )
        self._save_state()

    # Optional helper for seeding/migration tooling
    def seed_posts(self, timestamps: list[int], warning_sent: bool = False) -> None:
        """
        Overwrite the stored posts with the provided timestamps (epoch seconds).
        Useful for seeding from known tweet times.
        """
        timestamps = sorted(int(t) for t in timestamps)
        self._state = XLimitState(
            posts=timestamps,
            warning_sent=warning_sent,
            warning_post_ts=0,
            disabled_until=0,
            last_429_at=0,
            last_reset_hint=0,
        )
        self._prune_and_save_if_needed()
        self._save_state()
