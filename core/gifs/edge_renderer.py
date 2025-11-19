#!/usr/bin/env python3
"""
goal_sprite_gif_bg.py

Render NHL EDGE sprites JSON into an animated GIF using a pre-rendered
rink background image (e.g. rink_bg.png). The script does NOT draw any
rink lines/creases/circles itself – it only draws:

- players (circles + sweater numbers)
- puck + trail
- center-ice logo
- team abbreviations on the boards
- optional double-ring highlight for the goal scorer
"""

import argparse
import io
import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Rink coordinate system (EDGE)
# ----------------------------------------------------------------------
RINK_X_MIN = 0.0
RINK_X_MAX = 2400.0
RINK_Y_MIN = 0.0
RINK_Y_MAX = 1020.0
RINK_X_RANGE = RINK_X_MAX - RINK_X_MIN
RINK_Y_RANGE = RINK_Y_MAX - RINK_Y_MIN

# Player / puck sizing
BASE_PLAYER_RADIUS_FACTOR = 0.018  # was 0.018 – slightly bigger now
# BASE_PUCK_RADIUS_FACTOR = 0.0075
BASE_PUCK_RADIUS_FACTOR = 0.0085  # slightly bigger puck

# Team colors for outlines/text; extend as needed
TEAM_COLORS: Dict[str, str] = {
    "NJD": "#CE1126",
    "CHI": "#CF0A2C",
    "CAR": "#CC0000",
}

# FONTS
BASE_DIR = Path(__file__).resolve().parents[2]
FONT_DIR = BASE_DIR / "resources"
INTER_REGULAR = FONT_DIR / "Inter-Regular.ttf"  # or "Inter.ttf"
logger.debug("BASE_DIR: %s", BASE_DIR)
logger.debug("FONT_DIR: %s", FONT_DIR)
logger.debug("INTER_REGULAR: %s", INTER_REGULAR)


# ----------------------------------------------------------------------
# Data loading
# ----------------------------------------------------------------------

EDGE_HTTP_HEADERS = {
    # Reasonable modern desktop UA – doesn't need to be exact
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    # NHL site is the natural referer for these sprite requests
    "Referer": "https://www.nhl.com/",
}


def load_sprites_json(
    json_path: Optional[str],
    season: Optional[str],
    game_id: Optional[str],
    event_id: Optional[str],
) -> List[Dict[str, Any]]:
    """
    Load sprites JSON either from a local file or from the EDGE sprites API.
    """
    if json_path:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)

    if not (season and game_id and event_id):
        raise SystemExit("Either --json or (--season, --game, --event) must be provided.")

    url = f"https://wsr.nhle.com/sprites/{season}/{game_id}/ev{event_id}.json"
    logger.info("Fetching sprites JSON from %s", url)
    try:
        resp = requests.get(url, headers=EDGE_HTTP_HEADERS, timeout=15)
    except Exception as e:
        logger.warning("Request to %s failed: %s", url, e)
        raise

    if resp.status_code == 403:
        # More helpful than a raw HTTPError
        logging.warning(
            "ERROR: 403 Forbidden when fetching sprites JSON from %s. "
            "The NHL sprites endpoint may not exist for this event, "
            "might require browser-like headers or may be temporarily blocked.",
            url,
        )
        resp.raise_for_status()

    resp.raise_for_status()
    return resp.json()


# ----------------------------------------------------------------------
# Coordinate transforms
# ----------------------------------------------------------------------
def build_transform_for_dimensions(
    width: int,
    height: int,
) -> Tuple[Callable[[float], int], Callable[[float], int]]:
    """
    Build transform functions from EDGE world coordinates to pixel coordinates,
    given the actual background width/height in pixels.
    """

    def tx(x: float) -> int:
        frac = (x - RINK_X_MIN) / RINK_X_RANGE
        px = int(frac * width)
        return max(0, min(width - 1, px))

    def ty(y: float) -> int:
        # y increases upward in EDGE, downward in image → invert
        frac = (y - RINK_Y_MIN) / RINK_Y_RANGE
        py = int((1.0 - frac) * height)
        return max(0, min(height - 1, py))

    return tx, ty


# ----------------------------------------------------------------------
# Logo + text helpers
# ----------------------------------------------------------------------
def fetch_team_logo_image(
    team_abbr: str,
    season: Optional[str],
    max_size: int,
    logo_dir: Optional[str] = None,
) -> Optional[Image.Image]:
    """
    Try to load a team logo from a local PNG first.
    Optionally fall back to NHL SVG via cairosvg if available.
    """
    # Prefer local PNG in logo_dir
    if logo_dir:
        logo_path = Path(logo_dir) / f"{team_abbr}.png"
        if logo_path.exists():
            try:
                logo = Image.open(logo_path).convert("RGBA")
                logo.thumbnail((max_size, max_size), Image.LANCZOS)
                logging.info("Using local logo: %s", logo_path)
                return logo
            except Exception as exc:
                logging.warning("Failed to load local logo %s: %s", logo_path, exc)

    # Optional SVG fallback (only if cairosvg is installed and season provided)
    if not season:
        return None

    try:
        import cairosvg  # type: ignore
    except ImportError:
        return None

    url = f"https://assets.nhle.com/logos/nhl/svg/{team_abbr}_light.svg?season={season}"
    try:
        logging.info("Fetching SVG logo from %s", url)
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
    except Exception as exc:
        logging.error("Failed to fetch logo SVG for %s: %s", team_abbr, exc)
        return None

    try:
        png_bytes = cairosvg.svg2png(
            bytestring=resp.content,
            output_width=max_size,
            output_height=max_size,
        )
        logo = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        return logo
    except Exception as exc:
        logging.warning("Failed to convert SVG to PNG for %s: %s", team_abbr, exc)
        return None


def draw_rotated_text(
    base_img: Image.Image,
    text: str,
    center: Tuple[int, int],
    angle: float,
    font: ImageFont.FreeTypeFont,
    fill: str,
) -> None:
    """
    Draw rotated text at a given center using a minimal bounding box layer.

    This avoids Pillow auto-scaling issues and allows large font sizes.
    """
    # Measure text size for minimal layer
    bbox = font.getbbox(text)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]

    # Create minimal layer
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.text((-bbox[0], -bbox[1]), text, font=font, fill=fill)

    # Rotate the small text layer
    rotated = layer.rotate(angle, expand=True)

    # Compute top-left so rotated center aligns at desired center
    rx, ry = rotated.size
    x = center[0] - rx // 2
    y = center[1] - ry // 2

    # Composite onto main image
    base_img.alpha_composite(rotated, (x, y))


# ----------------------------------------------------------------------
# Rink base (background image + logo + abbreviations)
# ----------------------------------------------------------------------
def draw_rink_base(
    rink_bg_path: str,
    target_width: Optional[int],
    home_abbr: Optional[str],
    away_abbr: Optional[str],
    season: Optional[str],
    logo_dir: Optional[str],
) -> Tuple[Image.Image, Callable[[float], int], Callable[[float], int]]:
    """
    Load the rink background image (rink_bg.png), optionally resize it to a
    target width (keeping aspect ratio), then overlay:

    - center-ice logo (home_abbr)
    - vertical team abbreviations on left/right boards

    Returns:
        (base_image, tx, ty)
    """
    bg = Image.open(rink_bg_path).convert("RGBA")
    orig_w, orig_h = bg.size

    if target_width is not None and target_width > 0:
        scale = target_width / float(orig_w)
        new_w = int(orig_w * scale)
        new_h = int(orig_h * scale)
        bg = bg.resize((new_w, new_h), Image.LANCZOS)
        width, height = new_w, new_h
    else:
        width, height = orig_w, orig_h

    img = bg.copy()  # we'll draw on top of this

    # Build transforms for these dimensions
    tx_func, ty_func = build_transform_for_dimensions(width, height)

    # Center-ice logo
    center_x = width // 2
    center_y = height // 2
    if home_abbr:
        max_logo_size = int(min(width, height) * 0.30)
        logo = fetch_team_logo_image(home_abbr, season, max_logo_size, logo_dir=logo_dir)
        if logo is not None:
            lx = center_x - logo.width // 2
            ly = center_y - logo.height // 2
            img.alpha_composite(logo, (lx, ly))

    # --- Team abbreviations on the boards ---
    try:
        # Big text – roughly NHL visualizer scale
        font_size = int(height * 0.05)
        abbr_font = ImageFont.truetype(str(INTER_REGULAR), size=font_size)
    except Exception:
        logger.warning("Failed to load Inter font; using default font for sweater numbers.")
        abbr_font = ImageFont.load_default()

    # HOME team on the LEFT boards (rotate 90°)
    if home_abbr:
        text = home_abbr.upper()
        color = TEAM_COLORS.get(text, "red")
        cx = int(width * 0.02)  # small inset from left edge
        cy = height // 2
        draw_rotated_text(img, text, (cx, cy), 90, abbr_font, color)

    # AWAY team on the RIGHT boards (rotate 270°)
    if away_abbr:
        text = away_abbr.upper()
        color = TEAM_COLORS.get(text, "red")
        cx = width - int(width * 0.02)
        cy = height // 2
        draw_rotated_text(img, text, (cx, cy), 270, abbr_font, color)

    return img, tx_func, ty_func


# ----------------------------------------------------------------------
# Frame interpolation
# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
# Frame interpolation
# ----------------------------------------------------------------------
def interpolate_frames(
    frames: List[Dict[str, Any]],
    extra_frames: int,
    puck_only: bool = True,
) -> List[Dict[str, Any]]:
    """
    Insert interpolated frames between each pair of frames.

    This version uses a Catmull–Rom spline for x/y to create smooth,
    NHL-like motion. It only interpolates objects that appear in BOTH
    frames A and B (stable identity via playerId or 'puck'), and falls
    back to the original positions when identity changes.

    extra_frames:
        number of additional synthetic frames between each original pair.
        0  -> original sequence
        1  -> A, A-B mid, B, B-C mid, C, ...
    """
    if extra_frames <= 0 or len(frames) < 2:
        return frames

    def catmull_rom(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
        """Catmull–Rom spline interpolation for a single coordinate."""
        t2 = t * t
        t3 = t2 * t
        return 0.5 * (
            (2.0 * p1)
            + (-p0 + p2) * t
            + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
            + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3
        )

    def build_obj_map(frame: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """
        Build a map keyed by logical identity:

        - 'puck' for the puck (no playerId)
        - f'player_{playerId}' for skaters
        """
        mapping: Dict[str, Dict[str, Any]] = {}
        for obj in frame.get("onIce", {}).values():
            pid = obj.get("playerId")
            if pid:
                key = f"player_{pid}"
            else:
                key = "puck"
            mapping[key] = obj
        return mapping

    result: List[Dict[str, Any]] = []

    n = len(frames)
    for idx in range(n - 1):
        a = frames[idx]
        b = frames[idx + 1]
        result.append(a)

        # Neighbour frames for spline endpoints
        prev_frame = frames[idx - 1] if idx > 0 else a
        next_frame = frames[idx + 2] if (idx + 2) < n else b

        map_prev = build_obj_map(prev_frame)
        map_a = build_obj_map(a)
        map_b = build_obj_map(b)
        map_next = build_obj_map(next_frame)

        # Only interpolate identities that exist in BOTH A and B
        stable_keys = set(map_a.keys()) & set(map_b.keys())

        if puck_only:
            # Restrict to smoothing only the puck, if present.
            if "puck" in stable_keys:
                stable_keys = {"puck"}
            else:
                stable_keys = set()

        for step in range(1, extra_frames + 1):
            t = step / float(extra_frames + 1)

            # Start from a copy of frame A (including its onIce structure)
            new_frame = dict(a)
            new_onice: Dict[str, Any] = {}
            for k, obj_a in a.get("onIce", {}).items():
                obj = dict(obj_a)  # copy

                pid = obj_a.get("playerId")
                track_key = f"player_{pid}" if pid else "puck"

                if track_key in stable_keys:
                    # Build spline control points from neighbouring frames.
                    p0 = map_prev.get(track_key, map_a[track_key])
                    p1 = map_a[track_key]
                    p2 = map_b[track_key]
                    p3 = map_next.get(track_key, map_b[track_key])

                    x0, y0 = float(p0["x"]), float(p0["y"])
                    x1, y1 = float(p1["x"]), float(p1["y"])
                    x2, y2 = float(p2["x"]), float(p2["y"])
                    x3, y3 = float(p3["x"]), float(p3["y"])

                    obj["x"] = catmull_rom(x0, x1, x2, x3, t)
                    obj["y"] = catmull_rom(y0, y1, y2, y3, t)
                    # (all other fields, e.g. playerId/teamAbbrev, stay as in A)

                # Otherwise: identity changed → keep A's position (no morph)
                new_onice[k] = obj

            new_frame["onIce"] = new_onice
            result.append(new_frame)

    result.append(frames[-1])
    return result


# ----------------------------------------------------------------------
# Frame rendering
# ----------------------------------------------------------------------
def render_frames(
    frames: List[Dict[str, Any]],
    output_path: Path,
    rink_bg_path: str,
    target_width: Optional[int] = None,
    trail_length: int = 30,
    fps: int = 12,
    playback_speed: float = 1.0,
    interp_extra_frames: int = 0,
    flip_vertical: bool = False,
    home_abbr: Optional[str] = None,
    away_abbr: Optional[str] = None,
    season: Optional[str] = None,
    logo_dir: Optional[str] = None,
    marker_scale: float = 1.8,
    goal_sweater: Optional[str] = None,
    goal_player_id: Optional[int] = None,
) -> None:
    """
    Render an animated GIF from EDGE sprite frames on top of a pre-rendered
    rink background image.
    """
    frames_sorted = sorted(frames, key=lambda f: f["timeStamp"])

    # Optional smoothing: insert synthetic frames between real ones
    frames_sorted = interpolate_frames(frames_sorted, interp_extra_frames, puck_only=False)

    base_rink, tx, ty = draw_rink_base(
        rink_bg_path=rink_bg_path,
        target_width=target_width,
        home_abbr=home_abbr,
        away_abbr=away_abbr,
        season=season,
        logo_dir=logo_dir,
    )
    width, height = base_rink.size

    try:
        num_font_size = int(min(width, height) * 0.027)  # was ~0.025 → much bigger
        # Prefer SemiBold or Bold
        bold_font_path = FONT_DIR / "Inter-SemiBold.ttf"
        if bold_font_path.exists():
            logger.info("SemiBold font found for sweater numbers.")
            num_font = ImageFont.truetype(str(bold_font_path), size=num_font_size)
        else:
            num_font = ImageFont.truetype(str(INTER_REGULAR), size=num_font_size)
    except Exception:
        num_font = ImageFont.load_default()

    out_frames: List[Image.Image] = []
    puck_trail: List[Tuple[int, int]] = []

    goal_sweater = (goal_sweater or "").strip()
    is_goal_by_id = goal_player_id is not None
    is_goal_by_sweater = bool(goal_sweater)

    # Normalized home/away abbrevs for comparisons
    home_abbr_norm = (home_abbr or "").upper()
    away_abbr_norm = (away_abbr or "").upper()

    for frame in frames_sorted:
        img = base_rink.copy()
        draw = ImageDraw.Draw(img)

        puck_pos: Optional[Tuple[int, int]] = None

        for obj in frame.get("onIce", {}).values():
            x = tx(obj["x"])
            y = ty(obj["y"])

            if flip_vertical:
                y = height - y

            player_id = obj.get("playerId")
            team_abbrev = (obj.get("teamAbbrev") or "").upper()
            sweater = str(obj.get("sweaterNumber") or "").strip()

            if not player_id:
                # Puck
                puck_pos = (x, y)
                puck_trail.append(puck_pos)
                continue

            primary_color = TEAM_COLORS.get(team_abbrev, "#CC0000")

            # --- home vs away color scheme -----------------------------
            # HOME: filled with team color, white numbers
            # AWAY: white fill, team-color outline and numbers
            if team_abbrev == home_abbr_norm:
                fill_color = primary_color
                outline_color = primary_color
                text_color = "white"
            elif team_abbrev == away_abbr_norm:
                fill_color = "white"
                outline_color = primary_color
                text_color = primary_color
            else:
                # Fallback: away-style
                fill_color = "white"
                outline_color = primary_color
                text_color = primary_color
            # -----------------------------------------------------------

            base_r = max(10, int(min(width, height) * BASE_PLAYER_RADIUS_FACTOR * marker_scale))

            # Is this the goal scorer?
            is_goal_scorer = False
            if is_goal_by_id and player_id == goal_player_id:
                is_goal_scorer = True
            if is_goal_by_sweater and sweater == goal_sweater:
                is_goal_scorer = True

            if is_goal_scorer:
                # Double ring: outer halo + normal inner circle
                outer_r = int(base_r * 1.35)
                inner_r = base_r

                # outer halo: outline only
                draw.ellipse(
                    (x - outer_r, y - outer_r, x + outer_r, y + outer_r),
                    fill=None,  # <- key change
                    outline=outline_color,
                    width=4,
                )
                # inner circle: same as a normal marker
                draw.ellipse(
                    (x - inner_r, y - inner_r, x + inner_r, y + inner_r),
                    fill=fill_color,
                    outline=outline_color,
                    width=3,
                )
            else:
                # Normal single ring
                draw.ellipse(
                    (x - base_r, y - base_r, x + base_r, y + base_r),
                    fill=fill_color,
                    outline=outline_color,
                    width=3,
                )

            if sweater:
                draw.text((x, y), sweater, fill=text_color, anchor="mm", font=num_font)

        # Puck trail
        if len(puck_trail) > 1:
            segment = puck_trail[-trail_length:]
            draw.line(segment, width=int(4 * marker_scale), fill="black")

        if puck_pos is not None:
            pr = max(5, int(min(width, height) * BASE_PUCK_RADIUS_FACTOR * marker_scale))
            px, py = puck_pos
            draw.ellipse((px - pr, py - pr, px + pr, py + pr), fill="black")

        out_frames.append(img)

    if not out_frames:
        raise SystemExit("No frames rendered – sprites JSON may be empty?")

    # playback_speed: 1.0 = normal, <1 = slower, >1 = faster
    effective_fps = fps * playback_speed
    if effective_fps <= 0:
        effective_fps = 1.0

    duration_ms = int(1000 / effective_fps)

    logger.info(
        "Writing GIF to %s (%d frames @ %d fps, %d ms/frame)",
        output_path,
        len(out_frames),
        fps,
        duration_ms,
    )
    out_frames[0].save(
        output_path,
        save_all=True,
        append_images=out_frames[1:],
        duration=duration_ms,
        loop=0,
        optimize=True,
    )


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Render NHL EDGE sprites JSON into a GIF using a rink background image.")
    p.add_argument("--json", help="Path to local sprites JSON (evXXX.json).")
    p.add_argument("--season", help="Season ID, e.g., 20252026.")
    p.add_argument("--game", help="Game ID, e.g., 2025020268.")
    p.add_argument("--event", help="Event/goal id, e.g., 1077.")
    p.add_argument("-o", "--output", help="Output GIF path.")

    p.add_argument(
        "--rink-bg",
        required=True,
        help="Path to rink background PNG (e.g., rink_bg.png).",
    )

    p.add_argument("--home-abbr", help="Home team abbreviation (for logo + left-side label).")
    p.add_argument("--away-abbr", help="Away team abbreviation (for right-side label).")
    p.add_argument(
        "--logo-dir",
        help="Directory containing local team logos as PNG (e.g., CHI.png).",
    )

    p.add_argument(
        "--width",
        type=int,
        default=None,
        help=("Target GIF width in pixels (background is scaled; " "default = use original bg width)."),
    )
    p.add_argument(
        "--fps",
        type=int,
        default=12,
        help="Frames per second for GIF playback (lower = slower).",
    )
    p.add_argument(
        "--trail",
        type=int,
        default=30,
        help="Number of puck positions to keep in the trail.",
    )
    p.add_argument(
        "--flip-vertical",
        action="store_true",
        help="Flip coordinates vertically (mirror over horizontal center line).",
    )
    p.add_argument(
        "--marker-scale",
        type=float,
        default=1.0,
        help="Scale factor for player/puck marker sizes (1.0 = default).",
    )
    p.add_argument(
        "--goal-sweater",
        help="Sweater number of goal scorer (e.g., 86) for double-ring highlight.",
    )
    p.add_argument(
        "--goal-player-id",
        type=int,
        help="playerId of goal scorer for double-ring highlight.",
    )
    p.add_argument(
        "--playback-speed",
        type=float,
        default=1.0,
        help=("Playback speed multiplier: " "1.0 = normal, 0.5 = half-speed (slower), 2.0 = double-speed (faster)."),
    )
    p.add_argument(
        "--interp-extra-frames",
        type=int,
        default=0,
        help=("Number of interpolated frames to insert between each original " "pair (0 = off, 1–3 recommended)."),
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    frames = load_sprites_json(
        json_path=args.json,
        season=args.season,
        game_id=args.game,
        event_id=args.event,
    )

    if args.output:
        out_path = Path(args.output)
    else:
        if args.game and args.event:
            fname = f"goal_{args.game}_ev{args.event}.gif"
        else:
            base = Path(args.json or "goal").stem
            fname = f"{base}.gif"
        out_path = Path(fname)

    render_frames(
        frames=frames,
        output_path=out_path,
        rink_bg_path=args.rink_bg,
        target_width=args.width,
        trail_length=args.trail,
        fps=args.fps,
        playback_speed=args.playback_speed,
        interp_extra_frames=args.interp_extra_frames,
        flip_vertical=args.flip_vertical,
        home_abbr=args.home_abbr,
        away_abbr=args.away_abbr,
        season=args.season,
        logo_dir=args.logo_dir,
        marker_scale=args.marker_scale,
        goal_sweater=args.goal_sweater,
        goal_player_id=args.goal_player_id,
    )


if __name__ == "__main__":
    main()
