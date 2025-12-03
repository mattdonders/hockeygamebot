# core/milestones.py
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

import requests

from utils.http import get_json

logger = logging.getLogger(__name__)

STATS_API_BASE = "https://api.nhle.com/stats/rest/en"


@dataclass
class PlayerCareerSnapshot:
    """
    Baseline career stats as of BEFORE this game.

    We use these to compute "career after this event" by adding
    per-game deltas as PBP events come in.
    """

    player_id: int
    games_played: int
    goals: int
    assists: int
    points: int
    pp_goals: int
    pp_points: int
    is_goalie: bool = False
    wins: int = 0
    shutouts: int = 0


@dataclass
class PlayerMilestoneState:
    """
    Live mutable state for a player during a single game, built on
    top of the baseline career snapshot.
    """

    baseline: PlayerCareerSnapshot
    games_played: int
    goals: int
    assists: int
    points: int
    pp_goals: int
    pp_points: int
    wins: int
    shutouts: int

    @classmethod
    def from_snapshot(cls, snap: PlayerCareerSnapshot) -> "PlayerMilestoneState":
        return cls(
            baseline=snap,
            games_played=snap.games_played,  # NOTE: this won't change during the game
            goals=snap.goals,
            assists=snap.assists,
            points=snap.points,
            pp_goals=snap.pp_goals,
            pp_points=snap.pp_points,
            wins=snap.wins,
            shutouts=snap.shutouts,
        )


@dataclass
class MilestoneHit:
    """
    Represents a single milestone event, e.g. "100th NHL point".
    """

    player_id: int
    stat: str  # "goals", "assists", "points", "pp_goals", "pp_points"
    value: int  # 100
    label: str  # "100th NHL point"


@dataclass
class MilestoneWatch:
    """
    Upcoming milestone: e.g. '2 goals away from 100th NHL goal'.
    """

    player_id: int
    stat: str  # "goals", "assists", "points", "pp_goals", "pp_points", "games_played"
    current: int  # current career total (baseline)
    target: int  # next milestone threshold
    remaining: int  # target - current
    label: str  # human label, e.g. "2 goals away from 100th NHL goal"


class MilestoneService:
    """
    High-level API:

        service = MilestoneService(thresholds, session)
        service.preload_for_roster(player_ids)
        hits = service.handle_goal_event(...)

    This service is designed to be instantiated per GameContext.
    """

    def __init__(
        self,
        thresholds: Dict[str, List[int]],
        session: Optional[requests.Session] = None,
        snapshot_cache_path: Optional[Path] = None,
    ) -> None:
        """
        :param thresholds: mapping of stat -> list of career totals that are milestones, e.g.:

            {
                "goals": [1, 10, 50, 100, 200, 300],
                "assists": [50, 100, 200, 300],
                "points": [100, 300, 500, 1000],
                "pp_goals": [10, 25, 50],
                "pp_points": [20, 50, 100],
            }

        :param session: optional shared requests.Session
        """
        self.watch_margins: Dict[str, int] = thresholds.get("watch_margins", {})
        self.thresholds = {k: v for k, v in thresholds.items() if k != "watch_margins"}
        self.session = session or requests.Session()

        # Baseline career values from stats API (immutable).
        self._snapshots: Dict[int, PlayerCareerSnapshot] = {}

        # Per-game mutable state (baseline + game deltas).
        self._state: Dict[int, PlayerMilestoneState] = {}

        # Per-game baseline snapshot cache (loaded from / written to disk)
        self._snapshot_cache: Dict[int, PlayerCareerSnapshot] = {}
        self._snapshot_cache_path: Optional[Path] = snapshot_cache_path
        self._snapshot_cache_dirty: bool = False

        self._load_snapshot_cache()

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #

    def preload_for_roster(self, player_ids: Iterable[int]) -> None:
        """
        Optionally warm the cache for all skaters on the roster.

        You can call this at pregame using the full-game roster list.
        """
        for pid in player_ids:
            try:
                self._ensure_state(pid)
            except Exception:
                # Don't break the bot if stats API fails for one player.
                logger.exception("Failed to preload career snapshot for player_id=%s", pid)

    def handle_goal_event(
        self,
        scoring_player_id: Optional[int],
        primary_assist_id: Optional[int],
        secondary_assist_id: Optional[int],
        is_power_play: bool,
    ) -> List[MilestoneHit]:
        """
        Given a goal PBP event, update per-player career counters for
        this game and return any MilestoneHit instances that triggered.

        Call this once per goal event from GoalEvent.parse().
        """
        hits: List[MilestoneHit] = []

        # Scorer
        if scoring_player_id:
            hits.extend(self._apply_goal(scoring_player_id, is_power_play))

        # Primary assist
        if primary_assist_id:
            hits.extend(self._apply_assist(primary_assist_id, is_power_play))

        # Secondary assist
        if secondary_assist_id:
            hits.extend(self._apply_assist(secondary_assist_id, is_power_play))

        return hits

    def handle_postgame_goalie_milestones(
        self,
        goalie_id: int,
        *,
        won: bool,
        got_shutout: bool,
    ) -> List[MilestoneHit]:
        """
        Apply post-game goalie milestones (wins, shutouts) for a single goalie.

        This is intended to be called once, after the game goes FINAL, once we
        know who got the decision and whether it was a shutout.
        """
        hits: List[MilestoneHit] = []

        state = self._ensure_state(goalie_id)

        # Wins
        if won:
            state.wins += 1
            hits.extend(self._check_stat(goalie_id, "wins", state.wins))

        # Shutouts
        if got_shutout:
            state.shutouts += 1
            hits.extend(self._check_stat(goalie_id, "shutouts", state.shutouts))

        return hits

    def handle_scoring_change(
        self,
        new_scorer_ids: Iterable[int],
        new_assist_ids: Iterable[int],
        is_power_play: bool,
    ) -> List[MilestoneHit]:
        """Apply milestone accounting for *newly credited* players on a scoring change.

        This method is intentionally simpler than `handle_goal_event`:
        callers are expected to pre-filter the IDs so that each player only
        appears once per underlying goal across all revisions.

        :param new_scorer_ids: iterable of player IDs newly credited with a goal
        :param new_assist_ids: iterable of player IDs newly credited with an assist
        :param is_power_play: whether the goal is a power-play goal for milestone
                              purposes (callers may keep this ``False`` if PP
                              milestones are disabled).
        """
        hits: List[MilestoneHit] = []

        for pid in new_scorer_ids or []:
            hits.extend(self._apply_goal(pid, is_power_play))

        for pid in new_assist_ids or []:
            hits.extend(self._apply_assist(pid, is_power_play))

        return hits

    def format_hits(
        self,
        hits: List[MilestoneHit],
        player_name_resolver: Callable[[int], str],
    ) -> str:
        """
        Convert one or more MilestoneHit objects into a short text prefix
        to prepend to your unified goal message.

        Example output:
            "🎉 300th NHL point for Jack Hughes! 🎉"
        """
        if not hits:
            return ""

        # Sort by "importance": points > goals > assists > pp_points > pp_goals
        priority_order = ["games_played", "points", "goals", "assists", "pp_points", "pp_goals"]

        hits_sorted = sorted(
            hits,
            key=lambda h: priority_order.index(h.stat) if h.stat in priority_order else len(priority_order),
        )

        # For v1, just show the most important milestone.
        hit = hits_sorted[0]
        name = player_name_resolver(hit.player_id)

        # Use our own label if present; otherwise build a generic string.
        label = (
            hit.label or f"{hit.value}{self._ordinal_suffix(hit.value)} NHL {hit.stat.replace('_', ' ').rstrip('s')}"
        )

        return f"🎉 {label} for {name}! 🎉"

    def get_pregame_milestones_for_roster(
        self,
        player_ids: Iterable[int],
        player_name_resolver: Callable[[int], str],
    ) -> tuple[list[MilestoneHit], list[MilestoneWatch]]:
        """
        Convenience helper for pregame:
        - compute games-played *hits* for this roster
        - compute all stat *watches* for this roster
        """
        hits: list[MilestoneHit] = []

        for pid in player_ids:
            try:
                hit = self.check_games_played_milestone(pid)
            except Exception:
                logger.exception(
                    "MilestoneService: error while checking games-played milestone "
                    "for player_id=%s; skipping this player.",
                    pid,
                )
                continue

            if hit:
                hits.append(hit)

        watches = self.get_milestone_watches_for_roster(player_ids, player_name_resolver=player_name_resolver)

        return hits, watches

    def check_games_played_milestone(self, player_id: int) -> Optional[MilestoneHit]:
        """
        Check if tonight's game is a games-played milestone for this player.

        We treat 'current game number' as baseline.games_played + 1,
        assuming we fetched career stats BEFORE this game starts.
        """
        thresholds = self.thresholds.get("games_played", [])
        if not thresholds:
            return None

        state = self._ensure_state(player_id)
        baseline_gp = state.baseline.games_played
        current_game_number = baseline_gp + 1

        if current_game_number in thresholds:
            label = f"{current_game_number}{self._ordinal_suffix(current_game_number)} NHL Game"
            return MilestoneHit(
                player_id=player_id,
                stat="games_played",
                value=current_game_number,
                label=label,
            )
        return None

    def get_milestone_watches_for_roster(
        self,
        player_ids: Iterable[int],
        player_name_resolver: Callable[[int], str],
    ) -> List[MilestoneWatch]:
        """
        Return a list of upcoming milestones for players on this roster,
        based on the configured watch_window thresholds.
        """
        watches: List[MilestoneWatch] = []

        for pid in player_ids:
            try:
                state = self._ensure_state(pid)
            except Exception:
                logger.exception(
                    "Failed to ensure milestone state for player_id=%s while building milestone watch",
                    pid,
                )
                continue

            watches.extend(self._compute_watches_for_player(pid, state, player_name_resolver))

        # Do NOT enforce max_watches here; just sort by closeness.
        watches = sorted(watches, key=lambda w: w.remaining)
        return watches

    def log_roster_baselines(
        self,
        player_ids: Iterable[int],
        player_name_resolver: Callable[[int], str],
    ) -> None:
        """
        Convenience helper: log each player's baseline career snapshot
        at DEBUG level so you can verify that stats are wired correctly.

        Call this once after preload_for_roster during pre-game setup.
        """
        for pid in player_ids:
            try:
                state = self._ensure_state(pid)
            except Exception:
                logger.exception("Failed to ensure milestone state for player_id=%s", pid)
                continue

            snap = state.baseline
            name = player_name_resolver(pid)

            position = "GOALIE" if snap.is_goalie else "SKATER"

            logger.info(
                "Milestone baseline for %s (%s): GP=%d, G=%d, A=%d, P=%d, PP G=%d, PP P=%d, W=%d, SO=%d, POS=%s",
                name,
                pid,
                snap.games_played,
                snap.goals,
                snap.assists,
                snap.points,
                snap.pp_goals,
                snap.pp_points,
                snap.wins,
                snap.shutouts,
                position,
            )

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #

    def _load_snapshot_cache(self) -> None:
        """Load per-game baseline snapshots from disk if present."""
        path = self._snapshot_cache_path
        if not path or not path.exists():
            return

        try:
            with path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            logger.exception("Failed to load milestone snapshot cache from %s", path)
            return

        players = payload.get("players", {})
        loaded = 0

        for pid_str, data in players.items():
            try:
                pid = int(pid_str)
                snap = PlayerCareerSnapshot(**data)
                self._snapshot_cache[pid] = snap
                loaded += 1
            except Exception:
                logger.exception("Failed to parse milestone snapshot for player_id=%s", pid_str)

        logger.info(
            "Loaded %d milestone snapshots from %s",
            loaded,
            path,
        )

    def _save_snapshot_cache(self) -> None:
        """Write per-game baseline snapshots to disk if there were new ones."""
        logger.info("Saving milestone snapshot cache...")
        path = self._snapshot_cache_path
        if not path or not self._snapshot_cache_dirty:
            return

        payload = {
            "schema_version": 1,
            "players": {str(pid): asdict(snap) for pid, snap in self._snapshot_cache.items()},
        }

        tmp = path.with_suffix(".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, sort_keys=True)
            tmp.replace(path)
            logger.info(
                "Wrote %d milestone snapshots to %s",
                len(self._snapshot_cache),
                path,
            )
            self._snapshot_cache_dirty = False
        except Exception:
            logger.exception("Failed to write milestone snapshot cache to %s", path)

    def flush_snapshot_cache(self) -> None:
        """Call this at convenient times (after preload, before shutdown)."""
        logger.info("Flushing milestone snapshot cache to disk...")
        self._save_snapshot_cache()

    def _ensure_state(self, player_id: int) -> PlayerMilestoneState:
        """
        Ensure we have PlayerMilestoneState for this player: fetch baseline
        from stats API if not already cached.
        """
        if player_id in self._state:
            return self._state[player_id]

        snap = self._snapshot_cache.get(player_id)
        if snap is None:
            # Not cached for this game yet → hit stats API
            snap = self._fetch_career_snapshot(player_id)
            self._snapshot_cache[player_id] = snap
            self._snapshot_cache_dirty = True

        state = PlayerMilestoneState.from_snapshot(snap)
        self._state[player_id] = state
        return state

    def _fetch_career_snapshot(self, player_id: int) -> PlayerCareerSnapshot:
        """
        Fetch career totals from NHL stats API (regular-season only).
        This uses the skater career summary endpoint:

            /stats/rest/en/skater/summary
              ?isAggregate=true
              &reportType=career
              &isGame=false
              &cayenneExp=playerId=<id>

        - First try skater career summary.
        - If no row is returned, fall back to goalie career summary.
        """
        url = f"{STATS_API_BASE}/skater/summary"
        params = {
            "isAggregate": "true",
            "reportType": "career",
            "isGame": "false",
            "cayenneExp": f"playerId={player_id} and gameTypeId=2",
        }

        logger.debug("Fetching career snapshot from stats API for player_id=%s", player_id)

        data = get_json(url, key="nhl_stats_skater", params=params, timeout=5)
        rows = data.get("data", [])

        if rows:
            row = rows[0]
            return PlayerCareerSnapshot(
                player_id=player_id,
                games_played=int(row.get("gamesPlayed", 0) or 0),
                goals=int(row.get("goals", 0) or 0),
                assists=int(row.get("assists", 0) or 0),
                points=int(row.get("points", 0) or 0),
                pp_goals=int(row.get("ppGoals", 0) or 0),
                pp_points=int(row.get("ppPoints", 0) or 0),
                is_goalie=False,
                wins=0,
                shutouts=0,
            )

        logger.info(
            "No skater career row in stats API for player_id=%s; trying goalie career summary",
            player_id,
        )

        # ---- Fall back to goalie career stats ----
        goalie_url = f"{STATS_API_BASE}/goalie/summary"
        goalie_params = {
            "isAggregate": "true",
            "reportType": "career",
            "isGame": "false",
            "cayenneExp": f"playerId={player_id} and gameTypeId=2",
        }

        data = get_json(goalie_url, key="nhl_stats_goalie", params=goalie_params, timeout=5)
        rows = data.get("data", [])

        if rows:
            row = rows[0]
            # Goalie endpoint doesn't have goals/assists/points/PP stuff,
            # so we just set those to 0 and use gamesPlayed for GP milestones.
            games_played = int(row.get("gamesPlayed", 0) or 0)

            logger.debug(
                "Fetched goalie career snapshot for player_id=%s: GP=%d",
                player_id,
                games_played,
            )

            return PlayerCareerSnapshot(
                player_id=player_id,
                games_played=games_played,
                goals=int(row.get("goals", 0) or 0),
                assists=0,
                points=int(row.get("points", 0) or 0),
                pp_goals=0,
                pp_points=0,
                is_goalie=True,
                wins=int(row.get("wins", 0) or 0),
                shutouts=int(row.get("shutouts", 0) or 0),
            )

        # ---- Nothing returned: weird edge case ----
        logger.warning(
            "No skater or goalie career row in stats API for player_id=%s; " "using zero baseline",
            player_id,
        )
        return PlayerCareerSnapshot(
            player_id=player_id,
            games_played=0,
            goals=0,
            assists=0,
            points=0,
            pp_goals=0,
            pp_points=0,
            is_goalie=False,
        )

    def _apply_goal(self, player_id: int, is_power_play: bool) -> List[MilestoneHit]:
        state = self._ensure_state(player_id)

        state.goals += 1
        state.points += 1
        if is_power_play:
            state.pp_goals += 1
            state.pp_points += 1

        hits: List[MilestoneHit] = []

        # Only stats affected by a goal
        hits.extend(self._check_stat(player_id, "goals", state.goals))
        hits.extend(self._check_stat(player_id, "points", state.points))
        if is_power_play:
            hits.extend(self._check_stat(player_id, "pp_goals", state.pp_goals))
            hits.extend(self._check_stat(player_id, "pp_points", state.pp_points))

        return hits

    def _apply_assist(self, player_id: int, is_power_play: bool) -> List[MilestoneHit]:
        state = self._ensure_state(player_id)

        state.assists += 1
        state.points += 1
        if is_power_play:
            state.pp_points += 1

        hits: List[MilestoneHit] = []

        # Only stats affected by an assist
        hits.extend(self._check_stat(player_id, "assists", state.assists))
        hits.extend(self._check_stat(player_id, "points", state.points))
        if is_power_play:
            hits.extend(self._check_stat(player_id, "pp_points", state.pp_points))

        return hits

    def _check_all_stats(
        self,
        player_id: int,
        state: PlayerMilestoneState,
    ) -> List[MilestoneHit]:
        hits: List[MilestoneHit] = []

        hits.extend(self._check_stat(player_id, "goals", state.goals))
        hits.extend(self._check_stat(player_id, "assists", state.assists))
        hits.extend(self._check_stat(player_id, "points", state.points))
        hits.extend(self._check_stat(player_id, "pp_goals", state.pp_goals))
        hits.extend(self._check_stat(player_id, "pp_points", state.pp_points))

        return hits

    def _check_stat(
        self,
        player_id: int,
        stat: str,
        value: int,
    ) -> List[MilestoneHit]:
        thresholds = self.thresholds.get(stat, [])
        if value in thresholds:
            # You can customize these labels further if you want.
            human_name = stat.replace("_", " ").rstrip("s")  # "pp_goal", "point"
            label = f"{value}{self._ordinal_suffix(value)} NHL {human_name.title()}"
            return [
                MilestoneHit(
                    player_id=player_id,
                    stat=stat,
                    value=value,
                    label=label,
                )
            ]
        return []

    def _compute_watches_for_player(
        self,
        player_id: int,
        state: PlayerMilestoneState,
        player_name_resolver: Callable[[int], str],
    ) -> List[MilestoneWatch]:
        watches: List[MilestoneWatch] = []

        # Stats we care about for “watch” purposes
        stats = ["games_played", "goals", "assists", "points", "pp_goals", "pp_points"]

        for stat in stats:
            thresholds = self.thresholds.get(stat)
            if not thresholds:
                continue

            window = self.watch_margins.get(stat, 0)
            if window <= 0:
                continue

            # Use baseline for pre-game “career so far”
            current = getattr(state.baseline, stat)
            if current == 0:
                continue

            # Find the NEXT milestone strictly above the current total
            upcoming = [t for t in thresholds if t > current]
            if not upcoming:
                continue

            target = min(upcoming)
            remaining = target - current
            if remaining <= 0 or remaining > window:
                continue

            name = player_name_resolver(player_id)
            # Nice human label, e.g. "2 goals away from 100th NHL goal"
            human_stat = stat.replace("_", " ").rstrip("s")  # "goal", "assist", "point"
            label = f"{remaining} away from {target}{self._ordinal_suffix(target)} NHL {human_stat.title()}"

            watches.append(
                MilestoneWatch(
                    player_id=player_id,
                    stat=stat,
                    current=current,
                    target=target,
                    remaining=remaining,
                    label=label,
                )
            )

        return watches

    @staticmethod
    def _ordinal_suffix(n: int) -> str:
        # 1st, 2nd, 3rd, 4th, 11th, 12th, 13th...
        if 10 <= (n % 100) <= 20:
            return "th"
        last = n % 10
        return {1: "st", 2: "nd", 3: "rd"}.get(last, "th")
