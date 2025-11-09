# utils/http.py
from __future__ import annotations

import logging
import random
import threading
import time
from typing import Any, Dict, Optional

import requests

log = logging.getLogger(__name__)

# ===== Tunables (can be moved to config.yaml later) =====
MAX_TOTAL_RETRIES = 7  # total attempts per request
BASE_BACKOFF = 0.75  # seconds (exponential, with jitter)
MAX_BACKOFF = 60.0  # cap a single sleep
TIMEOUT = 15.0  # per request timeout

# Per-endpoint rate caps (requests/sec). Keys are arbitrary labels you pass in.
RATE_LIMITS = {
    "play_by_play": 0.6,  # ~1 req / 1.6s
    "scoreboard": 0.4,  # ~1 req / 2.5s
    "roster": 0.1,  # ~1 req / 10s (rarely needed)
    "schedule": 0.1,  # ~1 req / 10s
}

# Circuit breaker: if we see this many consecutive 429s on a key, pause that key
CB_TRIP_THRESHOLD = 3
CB_COOLDOWN_SECONDS = 180.0  # 3 minutes


# ===== Simple token-bucket rate limiter per key =====
class _RateLimiter:
    def __init__(self, rate_per_sec: float):
        self.tokens = 1.0
        self.rate = float(rate_per_sec)
        self.capacity = 1.0
        self.last = time.monotonic()
        self.lock = threading.Lock()

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last
            self.last = now
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            if self.tokens < 1.0:
                need = 1.0 - self.tokens
                sleep_for = need / self.rate if self.rate > 0 else 1.0
                time.sleep(sleep_for)
                # refill after sleep
                now2 = time.monotonic()
                elapsed2 = now2 - self.last
                self.last = now2
                self.tokens = min(self.capacity, self.tokens + elapsed2 * self.rate)
            self.tokens -= 1.0


# ===== Circuit breaker per key =====
class _Circuit:
    def __init__(self):
        self.consecutive_429 = 0
        self.open_until = 0.0


_rate_limiters: Dict[str, _RateLimiter] = {}
_circuits: Dict[str, _Circuit] = {}
_global_lock = threading.Lock()

_session = requests.Session()
_session.headers.update({"User-Agent": "HockeyGameBot/1.0 (+https://github.com/mattdonders/hockeygamebot)"})


def _limiter_for(key: str) -> _RateLimiter:
    with _global_lock:
        if key not in _rate_limiters:
            rate = RATE_LIMITS.get(key, 0.5)  # default ~1/2s
            _rate_limiters[key] = _RateLimiter(rate)
        return _rate_limiters[key]


def _circuit_for(key: str) -> _Circuit:
    with _global_lock:
        if key not in _circuits:
            _circuits[key] = _Circuit()
        return _circuits[key]


def _sleep_with_jitter(attempt: int, retry_after: Optional[str]) -> None:
    if retry_after:
        try:
            secs = min(MAX_BACKOFF, float(retry_after))
        except ValueError:
            secs = 0.0
    else:
        secs = min(MAX_BACKOFF, BASE_BACKOFF * (2 ** (attempt - 1)))
        secs += random.uniform(0, secs * 0.25)
    secs = max(0.5, secs)
    time.sleep(secs)


def get_json(
    url: str,
    *,
    key: str = "default",
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = TIMEOUT,
) -> Dict[str, Any]:
    """
    GET JSON with:
      - token-bucket rate limit per 'key'
      - Retry-After + exponential backoff w/ jitter
      - circuit breaker on repeated 429s (pauses that key)
    """
    lim = _limiter_for(key)
    circ = _circuit_for(key)

    # Circuit open?
    now = time.monotonic()
    if circ.open_until > now:
        remaining = circ.open_until - now
        log.warning("Circuit OPEN for key=%s, sleeping %.1fs", key, remaining)
        time.sleep(remaining)

    for attempt in range(1, MAX_TOTAL_RETRIES + 1):
        # Respect rate limit
        lim.wait()

        resp = _session.get(url, params=params, headers=headers, timeout=timeout)

        if 200 <= resp.status_code < 300:
            circ.consecutive_429 = 0
            try:
                return resp.json()
            except ValueError as e:
                raise RuntimeError(f"Invalid JSON from {url}: {e}") from e

        if resp.status_code == 429:
            circ.consecutive_429 += 1
            retry_after = resp.headers.get("Retry-After")
            log.warning(
                "429 for key=%s (attempt %d/%d). Retry-After=%s, consecutive=%d",
                key,
                attempt,
                MAX_TOTAL_RETRIES,
                retry_after,
                circ.consecutive_429,
            )
            if circ.consecutive_429 >= CB_TRIP_THRESHOLD:
                circ.open_until = time.monotonic() + CB_COOLDOWN_SECONDS
                log.error("Circuit TRIPPED for key=%s, pausing %.0fs", key, CB_COOLDOWN_SECONDS)
                time.sleep(CB_COOLDOWN_SECONDS)
                # after cooldown, continue loop (attempt increases)
            if attempt == MAX_TOTAL_RETRIES:
                resp.raise_for_status()
            _sleep_with_jitter(attempt, retry_after)
            continue

        if 500 <= resp.status_code < 600:
            log.warning("5xx %d for key=%s (attempt %d/%d)", resp.status_code, key, attempt, MAX_TOTAL_RETRIES)
            if attempt == MAX_TOTAL_RETRIES:
                resp.raise_for_status()
            _sleep_with_jitter(attempt, resp.headers.get("Retry-After"))
            continue

        # Other errors: fail fast
        resp.raise_for_status()

    raise RuntimeError(f"Exhausted retries for {url}")
