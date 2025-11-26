import logging
from pathlib import Path
from typing import Optional

from core.gifs.edge_renderer import load_sprites_json, render_frames

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RINK_BG = PROJECT_ROOT / "resources" / "rink_bg.png"
DEFAULT_LOGO_DIR = PROJECT_ROOT / "resources" / "logos"
DEFAULT_GIF_ROOT = PROJECT_ROOT / "output" / "goal_gifs"


def clean_frame(frame):
    """
    Remove invalid/malformed player entries from a raw frame dict.
    A valid player entry must have non-empty playerId and numeric x,y coords.
    """
    cleaned = dict(frame)  # shallow copy
    cleaned_on_ice = {}

    for pid, pdata in frame.get("onIce", {}).items():
        x = pdata.get("x")
        y = pdata.get("y")
        player_id = pdata.get("playerId")

        # Filter conditions for invalid players
        if (
            not player_id  # empty string, None, 0, etc
            or x is None
            or y is None
            or not isinstance(x, (int, float))
            or not isinstance(y, (int, float))
        ):
            continue  # skip this bad player

        cleaned_on_ice[pid] = pdata

    cleaned["onIce"] = cleaned_on_ice
    return cleaned


def generate_goal_gif_from_edge(
    *,
    season: str,
    game_id: str,
    event_id: str,
    home_abbr: str,
    away_abbr: str,
    goal_sweater: Optional[str],
    goal_player_id: Optional[int],
    width: int = 1200,
    fps: int = 18,
    playback_speed: float = 0.9,
    trail_length: int = 1,
    interp_extra_frames: int = 1,
    flip_vertical: bool = True,
    marker_scale: float = 1.8,
    rink_bg_path: Optional[Path] = None,
    logo_dir: Optional[Path] = None,
    gif_root: Optional[Path] = None,
    sprites_json_path: Optional[Path] = None,
) -> Optional[Path]:
    """High-level helper for GoalEvent to build a GIF for a single goal."""
    try:
        gif_root = gif_root or DEFAULT_GIF_ROOT
        season_dir = gif_root / season
        game_dir = season_dir / str(game_id)
        game_dir.mkdir(parents=True, exist_ok=True)

        out_path = game_dir / f"goal_{game_id}_ev{event_id}.gif"
        if out_path.exists():
            logger.debug("Reusing existing goal GIF: %s", out_path)
            return out_path

        rink_bg = rink_bg_path or DEFAULT_RINK_BG
        logos = logo_dir or DEFAULT_LOGO_DIR

        if not rink_bg.exists():
            logger.error("Rink background not found at %s", rink_bg)
            return None

        # Suppply sprites JSON directly if given (for testing), else load from EDGE
        if sprites_json_path is not None:
            frames = load_sprites_json(
                json_path=str(sprites_json_path),
                season=None,
                game_id=None,
                event_id=None,
            )
        else:
            frames = load_sprites_json(
                json_path=None,
                season=season,
                game_id=game_id,
                event_id=event_id,
            )

        # Cleanup Frames w/o Coordinates or PlayerIDs
        frames = [f for f in frames if "onIce" in f and isinstance(f["onIce"], dict)]
        # frames = [clean_frame(f) for f in frames if isinstance(f, dict)]

        if not frames:
            logger.error(
                "No frames returned by load_sprites_json() " "for season=%s game=%s event=%s",
                season,
                game_id,
                event_id,
            )
            return None

        logger.info(
            "Loaded %d sprite frame(s) for season=%s game=%s event=%s",
            len(frames),
            season,
            game_id,
            event_id,
        )

        logger.info(
            "Rendering goal GIF for season=%s game=%s event=%s -> %s",
            season,
            game_id,
            event_id,
            out_path,
        )

        render_frames(
            frames=frames,
            output_path=out_path,
            rink_bg_path=str(rink_bg),
            target_width=width,
            trail_length=trail_length,
            fps=fps,
            playback_speed=playback_speed,
            interp_extra_frames=interp_extra_frames,
            flip_vertical=flip_vertical,
            home_abbr=home_abbr,
            away_abbr=away_abbr,
            season=season,
            logo_dir=str(logos),
            marker_scale=marker_scale,
            goal_sweater=goal_sweater,
            goal_player_id=goal_player_id,
        )

        return out_path

    except Exception:
        logger.exception(
            "Failed to generate goal GIF for season=%s game=%s event=%s",
            season,
            game_id,
            event_id,
        )
        return None
