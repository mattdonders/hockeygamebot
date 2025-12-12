# utils/http.py
from __future__ import annotations

import hashlib  # NEW: Used for creating stable cache keys
import json  # NEW: Used for serializing/deserializing data to/from Redis
import logging
import random
import threading
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import requests

log = logging.getLogger(__name__)

# Conditional Redis Import
try:
    import redis

    _HAS_REDIS = True
except ImportError:
    _HAS_REDIS = False

# Global Cache Variables (Good to Define at Top of File)
_cache_enabled: bool = False
_cache_ttl_seconds: int = 5
_redis_client: Optional["redis.Redis"] = None  # type: ignore[name-defined]

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


# ----------------------------------------------------------------------------------------


# =======================================================
# 💡 NEW: HTTP Client and Cache Initialization
# =======================================================


def init_http_client(config: Dict[str, Any]) -> None:
    """
    Initializes global HTTP client settings, including optional cache.
    Reads ENABLE_SHARED_CACHE, REDIS_HOST/PORT, and API_CACHE_TTL_SECONDS from config.
    """
    global _cache_enabled
    global _redis_client
    global _cache_ttl_seconds

    script_config = config.get("script", {})

    # 1. Set the TTL based on config
    _cache_ttl_seconds = script_config.get("API_CACHE_TTL_SECONDS", 5)

    # 2. Check if caching is enabled in config
    if script_config.get("ENABLE_SHARED_CACHE", False):

        # 3. Check if the Redis library is installed
        if not _HAS_REDIS:
            log.error("Config requested shared cache, but 'redis-py' is not installed. Caching disabled.")
            _cache_enabled = False
            return

        # 4. Try to connect to the Redis server
        try:
            redis_host = script_config.get("REDIS_HOST", "localhost")
            redis_port = script_config.get("REDIS_PORT", 6379)
            redis_db = script_config.get("REDIS_DB", 0)

            _redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                socket_timeout=5,
                decode_responses=True,  # Returns strings/None, not bytes
            )

            _redis_client.ping()  # Verify connectivity
            _cache_enabled = True
            log.info(
                "Shared Redis cache ENABLED at %s:%s (DB:%s). TTL: %ss.",
                redis_host,
                redis_port,
                redis_db,
                _cache_ttl_seconds,
            )

        except redis.exceptions.ConnectionError as e:
            # Server is not running or accessible
            log.error("Failed to connect to Redis at %s:%s. Shared caching disabled: %s", redis_host, redis_port, e)
            _cache_enabled = False
    else:
        # 5. Caching disabled by configuration
        _cache_enabled = False
        log.info("Shared caching is DISABLED in configuration.")


def _create_cache_key(url: str, params: Optional[Dict[str, Any]] = None) -> str:
    """Creates a stable, unique cache key based on the request URL and params."""
    if params:
        # Sort params to ensure key is consistent regardless of parameter order
        # urlencode safely converts params into a query string
        query_string = urlencode(sorted(params.items()))
        full_url = f"{url}?{query_string}"
    else:
        full_url = url

    # Use SHA-256 hash of the full URL for the key (safe, fixed length)
    return "hgb:" + hashlib.sha256(full_url.encode("utf-8")).hexdigest()


def _get_json_direct(
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

        resp = None
        try:
            resp = _session.get(url, params=params, headers=headers, timeout=timeout)
        except requests.exceptions.ConnectionError as e:
            # Handle low-level socket/connection errors (RemoteDisconnected, Timeout, etc.)
            log.warning(
                "ConnectionError (%s) for key=%s (attempt %d/%d)",
                type(e).__name__,
                key,
                attempt,
                MAX_TOTAL_RETRIES,
            )

            if attempt == MAX_TOTAL_RETRIES:
                log.error("Exhausted retries for ConnectionError on %s", url)
                raise  # Re-raise on final attempt

            _sleep_with_jitter(attempt, None)
            continue

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


# =======================================================
# 🚀 NEW PUBLIC ENTRY POINT (cache wrapper)
# =======================================================


def get_json(
    url: str,
    *,
    key: str = "default",
    params: Optional[Dict[str, Any]] = None,
    timeout: float = TIMEOUT,
    ttl_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Main public function to fetch JSON data.
    Uses shared Redis cache if enabled, otherwise calls API directly.
    """
    if not _cache_enabled:
        # If cache is disabled or failed to connect, call the robust API fetcher directly
        return _get_json_direct(url, key=key, params=params)

    # --- Cache Enabled Logic ---
    cache_key = _create_cache_key(url, params)

    # 1. Check Cache
    try:
        # Use Redis Client
        cached_json_str = _redis_client.get(cache_key)
        if cached_json_str:
            log.debug("Cache HIT for key=%s", key)
            return json.loads(cached_json_str)
        log.debug("Cache MISS for key=%s", key)
    except Exception as e:
        log.warning("Redis read failed (%s). Falling through to direct API call.", type(e).__name__)
        # Proceed to fetch from API

    # 2. Cache Miss: Call the robust API fetcher
    api_data = _get_json_direct(url, key=key, params=params)

    # 3. Store Result in Cache
    try:
        json_str = json.dumps(api_data)

        # Determine which TTL to use:
        # If ttl_seconds is provided (e.g., 5 for PBP), use it.
        # Otherwise, fall back to the global default TTL (_cache_ttl_seconds).
        ttl_to_use = ttl_seconds if ttl_seconds is not None else _cache_ttl_seconds

        # SET key, value, EXPIRE (ex) TTL
        _redis_client.set(cache_key, json_str, ex=ttl_to_use)
        log.debug("Cache SET for key=%s, TTL=%ss", key, ttl_to_use)
    except Exception as e:
        log.warning("Redis write failed (%s). Data was not cached.", type(e).__name__)

    return api_data
