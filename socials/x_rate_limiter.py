import json
from datetime import datetime, timezone
from pathlib import Path


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

    base = "Due to daily posting limits on X, this bot has to stop posting updates early today.\n\n"

    # Remove X itself — we care about *other* active channels
    non_x = {p for p in enabled_platforms if p != "x"}

    # ----- Case A: Bluesky enabled -----
    if "bluesky" in non_x:
        pretty_others = sorted(non_x - {"bluesky"})

        if bluesky_handle:
            bsky_part = f"Bluesky at {bluesky_handle}"
        else:
            bsky_part = "Bluesky"

        if pretty_others:
            # Example: "Threads, Telegram"
            others_str = ", ".join(name.capitalize() for name in pretty_others)
            return base + f"Live game coverage will continue on {bsky_part} and our other channels ({others_str})."
        else:
            return base + f"Live game coverage will continue on {bsky_part} for the rest of the game."

    # ----- Case B: Other platforms enabled (no Bluesky) -----
    if non_x:
        pretty = ", ".join(name.capitalize() for name in sorted(non_x))
        return base + f"Live game coverage will continue on our other channels: {pretty}."

    # ----- Case C: Only X is enabled -----
    return base + "We’ll be back with updates tomorrow once our daily limit resets."


class XRateLimiter:
    """
    Manages Twitter/X daily post limits per bot.

    Each Twitter account gets its own JSON file:
        data/cache/twitter_limits/<TEAM>.json

    Structure:
        {
            "day": "YYYY-MM-DD",   # UTC day
            "count": 0,            # posts sent today (UTC)
            "warning_sent": false  # has the early-stop tweet been sent?
        }
    """

    DAILY_LIMIT = 17  # X hard limit
    CONTENT_LIMIT = 15  # at 15, we begin warning + shutting down

    def __init__(self, team_slug: str, base_cache_dir: Path):
        """
        team_slug: "njd", "pit", etc.
        base_cache_dir: typically Path("data/cache")
        """
        self.slug = team_slug.lower()

        # Directory: data/cache/twitter_limits
        self.limit_dir = base_cache_dir / "twitter_limits"
        self.limit_dir.mkdir(parents=True, exist_ok=True)

        # File: data/cache/twitter_limits/NJD.json
        self.file_path = self.limit_dir / f"{self.slug}.json"

        self._state = self._load_state()

    # -------------------------------
    # Internal state helpers
    # -------------------------------

    def _load_state(self):
        """Load the JSON file or initialize a new state."""
        if self.file_path.exists():
            try:
                return json.loads(self.file_path.read_text())
            except Exception:
                pass  # corrupt file → reinitialize below

        today = datetime.now(timezone.utc).date().isoformat()
        return {"day": today, "count": 0, "warning_sent": False}

    def _save_state(self):
        """Persist the updated state."""
        self.file_path.write_text(json.dumps(self._state, indent=2))

    def _maybe_rotate_day(self):
        """Reset counters if we've crossed a UTC day boundary."""
        now_utc = datetime.now(timezone.utc).date().isoformat()
        stored_day = self._state.get("day")

        if stored_day != now_utc:
            # Twitter quota resets → we reset as well
            self._state = {
                "day": now_utc,
                "count": 0,
                "warning_sent": False,
            }
            self._save_state()

    # -------------------------------
    # Public API
    # -------------------------------

    def can_post_regular(self) -> bool:
        """
        True → allowed to send a normal event post to X.
        False → do NOT send (but may still send the warning post).
        """
        self._maybe_rotate_day()
        if self._state["warning_sent"]:
            return False
        return self._state["count"] < self.CONTENT_LIMIT

    def should_send_warning(self) -> bool:
        """
        Determines whether it is time to send the *one* early-stop warning tweet.

        Conditions:
        - We are at or above CONTENT_LIMIT (15 posts)
        - warning_sent is still False
        - We have NOT exceeded the hard limit (17)
        """
        self._maybe_rotate_day()

        count = self._state["count"]

        return count >= self.CONTENT_LIMIT and not self._state["warning_sent"] and count < self.DAILY_LIMIT

    def record_post(self, is_warning: bool = False):
        """
        Called AFTER a successful X post.
        Increments count and optionally marks warning_sent.
        """
        self._maybe_rotate_day()

        self._state["count"] += 1

        if is_warning:
            self._state["warning_sent"] = True

        self._save_state()

    def get_state(self) -> dict:
        """
        Public accessor used by StatusMonitor to snapshot the current
        X rate-limit state for the dashboard.

        Returns a shallow copy so callers can't mutate internal state.
        """
        self._maybe_rotate_day()
        return dict(self._state)


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Debug / simulate XRateLimiter usage.")
    parser.add_argument("--team", required=True, help="Team slug (real or fake).")
    parser.add_argument("--cache-dir", default="data/cache", help="Directory for cache.")
    parser.add_argument("--steps", type=int, default=18, help="Number of attempts.")
    parser.add_argument(
        "--show-warning",
        action="store_true",
        default=True,
        help="Print the X daily-limit warning message.",
    )
    args = parser.parse_args()

    # WARN if using a real NHL abbreviation
    # fmt: off
    real_abbrevs = {
        "ana","ari","bos","buf","cgy","car","cbj","chi","col","dal",
        "det","edm","fla","lak","min","mtl","njd","nsh","nyi","nyr",
        "ott","phi","pit","sea","sjs","stl","tbl","tor","van","vgk",
        "wpg","wsh","uta"
    }
    # fmt: on

    if args.team.lower() in real_abbrevs:
        print(
            f"⚠️  WARNING: '{args.team}' looks like a real team slug.\n"
            "    Running the simulator will overwrite the real bot's rate-limit file!\n"
            "    Use a fake slug instead, e.g. '--team njd_test' or '--team sim_njd'.\n"
        )
        exit(1)

    limiter = XRateLimiter(
        team_slug=args.team.lower(),
        base_cache_dir=Path(args.cache_dir),
    )

    print(f"Initial state for {args.team}: {limiter._state}")

    for i in range(1, args.steps + 1):
        label = f"[SIM {i:02d}]"

        if limiter.should_send_warning():
            print(f"{label} should_send_warning=True → recording WARNING post")
            limiter.record_post(is_warning=True)

            if args.show_warning:
                # Simulate the platforms your real bot would have
                enabled_platforms = {"x", "bluesky"}  # OR use whatever you want to test
                fake_handle = "@debug.hockeygamebot.com"

                print("\n--- Warning Message Preview ---")
                print(
                    build_x_limit_warning(
                        enabled_platforms=enabled_platforms,
                        bluesky_handle=fake_handle,
                    )
                )
                print("--- End Preview ---\n")
            continue

        if limiter.can_post_regular():
            print(f"{label} can_post_regular=True → recording regular post")
            limiter.record_post()
        else:
            print(f"{label} X posting disabled for today (count={limiter._state.get('count')}).")

    print(f"Final state for {args.team}: {limiter._state}")
