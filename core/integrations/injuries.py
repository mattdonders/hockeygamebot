# integrations/injuries.py

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import pandas as pd
import requests

from utils.retry import retry

logger = logging.getLogger(__name__)


# -----------------------
# Data model
# -----------------------


@dataclass
class InjuryRecord:
    source: str
    player: str  # "First Last"
    team: str  # e.g. "NJD"
    status: Optional[str]
    detail: Optional[str]
    raw: Dict[str, Any]


# -----------------------
# HTTP helpers
# -----------------------

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.google.com/",
    "Connection": "keep-alive",
}


def make_requests_session() -> requests.Session:
    """Plain requests session with browser-y headers."""
    s = requests.Session()
    s.headers.update(DEFAULT_HEADERS)
    return s


def fetch_and_cache_html(
    session: requests.Session,
    url: str,
    cache_dir: Path,
    cache_key: str,
    *,
    force: bool = False,
) -> str:
    """
    Fetch HTML from URL, cache it, and return the text.

    If cache exists and force=False, we load from disk instead.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{cache_key}.html"

    if cache_path.exists() and not force:
        logger.info("Injuries: loading cached HTML from %s", cache_path)
        return cache_path.read_text(encoding="utf-8")

    logger.info("Injuries: fetching %s (%s)", url, cache_key)
    resp = session.get(url, timeout=15)
    resp.raise_for_status()

    cache_path.write_text(resp.text, encoding="utf-8")
    logger.info(
        "Injuries: saved HTML to %s (status=%s, len=%d)",
        cache_path,
        resp.status_code,
        len(resp.text),
    )
    return resp.text


# -----------------------
# Hockey-Reference parsing
# -----------------------


def _normalize_name(name: str) -> str:
    """
    Normalized name for matching. Very simple for now:
    lowercase, strip whitespace.
    """
    return " ".join(name.strip().lower().split())


def parse_hockey_reference_injuries_html(
    html: str,
    team_abbr: str,
) -> List[InjuryRecord]:
    """
    Parse Hockey-Reference team injury page HTML into a list of InjuryRecord.

    URL shape:
      https://www.hockey-reference.com/teams/NJD/2026_injuries.html
    """
    logger.info("Injuries: parsing Hockey-Reference injuries for %s", team_abbr)

    tables = pd.read_html(StringIO(html))
    if not tables:
        logger.warning("Injuries: no tables found in Hockey-Reference HTML")
        return []

    injury_table = None
    for idx, df in enumerate(tables):
        cols = set(df.columns.astype(str))
        if {"Player", "Date of Injury"} <= cols:
            injury_table = df
            logger.info(
                "Injuries: using Hockey-Reference table #%d with columns: %s",
                idx,
                list(cols),
            )
            break

    if injury_table is None:
        logger.warning("Injuries: no suitable injury table found on Hockey-Reference")
        return []

    injury_table = injury_table.fillna("")
    injuries: List[InjuryRecord] = []

    for _, row in injury_table.iterrows():
        row_dict = row.to_dict()
        player_name = str(row_dict.get("Player", "")).strip()
        if not player_name:
            continue

        injuries.append(
            InjuryRecord(
                source="hockey-reference",
                player=player_name,
                team=team_abbr,
                status=None,  # If you later want status, you can parse from Injury Type / Note
                detail=None,
                raw=row_dict,
            )
        )

    logger.info("Injuries: Hockey-Reference returned %d injuries", len(injuries))
    return injuries


@retry(max_attempts=3, delay=2.0, exceptions=(requests.RequestException,))
def get_team_injuries_from_hockey_reference(
    team_abbr: str,
    season_year: int,
    *,
    cache_root: Path,
    session: Optional[requests.Session] = None,
    max_age_hours: int = 3,
) -> List[InjuryRecord]:
    """
    High-level API: fetch + parse injuries for a single team+season.

    season_year is the season-ending year, e.g. 2026 for 2025-26.
    """
    if session is None:
        session = make_requests_session()

    cache_dir = cache_root / "injuries"
    url = f"https://www.hockey-reference.com/teams/{team_abbr}/{season_year}_injuries.html"
    cache_key = f"hockeyref_{team_abbr}_{season_year}"
    cache_path = cache_dir / f"{cache_key}.html"

    use_cache = False
    if cache_path.exists():
        age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
        if age < timedelta(hours=max_age_hours):
            use_cache = True

    if not use_cache:
        logger.info("Fetching %s (%s)", url, cache_key)
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=15)
        resp.raise_for_status()
        cache_path.write_text(resp.text, encoding="utf-8")
        logger.info(
            "Saved HTML to %s (status=%s, len=%d)",
            cache_path,
            resp.status_code,
            len(resp.text),
        )
    else:
        logger.info(
            "Using cached HTML from %s (age %.1f hours)",
            cache_path,
            age.total_seconds() / 3600.0,
        )

    html = cache_path.read_text(encoding="utf-8")
    return parse_hockey_reference_injuries_html(html, team_abbr)


# -----------------------
# Helpers for the bot
# -----------------------


def build_injured_name_set(injuries: List[InjuryRecord]) -> Set[str]:
    """
    Convert a list of InjuryRecord into a set of normalized player names.

    Use this to quickly filter players in milestone watches.
    """
    return {_normalize_name(injury.player) for injury in injuries}


def is_player_injured(
    player_name: str,
    injured_names: Set[str],
) -> bool:
    """
    Check if a given roster name is in the injured set (by normalized name).
    """
    if not player_name:
        return False
    return _normalize_name(player_name) in injured_names
