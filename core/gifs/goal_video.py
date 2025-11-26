# core/gifs/goal_video.py
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional, Sequence, Union

logger = logging.getLogger(__name__)

PathLike = Union[str, Path]


def gif_to_mp4(
    gif_path: PathLike,
    output_path: Optional[PathLike] = None,
    *,
    crf: int = 23,
    preset: str = "medium",
    extra_ffmpeg_args: Optional[Sequence[str]] = None,
) -> Path:
    """Convert an animated GIF (e.g. EDGE goal GIF) to an MP4 file.

    Intended as a *drop-in* helper for the existing GIF pipeline:

        1. Render the normal high-quality GIF via edge_renderer.render_frames().
        2. Call gif_to_mp4(...) on the resulting GIF path.
        3. Use the returned MP4 path for platforms that prefer / require video
           (Threads, Bluesky), while still using the GIF for others (X, Telegram).

    Implementation
    --------------
    - Uses the system `ffmpeg` binary via subprocess (no new Python deps).
    - Re-encodes GIF frames to H.264:
        * pixel format: yuv420p (widely supported)
        * filter: scale=trunc(iw/2)*2:trunc(ih/2)*2 to ensure even dimensions
        * -movflags +faststart for better streamable playback
    - `crf` controls quality (lower = higher quality / larger file).
      Typical range: 18–28; default 23 is a good starting point.
    - `preset` trades encoding speed for compression efficiency:
      ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow

    Requirements
    ------------
    - ffmpeg must be installed and available on PATH.
    - gif_path must point to an animated GIF (single-frame is supported but
      not very interesting for this bot).

    Returns:
        Path to the generated MP4 file.

    Raises:
        FileNotFoundError: if gif_path does not exist.
        RuntimeError: if ffmpeg exits with a non-zero code.
    """
    gif_path = Path(gif_path)

    if not gif_path.exists():
        raise FileNotFoundError(gif_path)

    if output_path is None:
        output_path = gif_path.with_suffix(".mp4")

    output_path = Path(output_path)

    # Base ffmpeg invocation.
    # NOTE: we deliberately do not set -r (fps) here; ffmpeg will respect
    # the timing information embedded in the GIF.
    cmd: list[str] = [
        "ffmpeg",
        "-y",  # overwrite existing output
        "-i",
        str(gif_path),
        "-movflags",
        "+faststart",
        "-pix_fmt",
        "yuv420p",
        "-vf",
        "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        str(crf),
        str(output_path),
    ]

    if extra_ffmpeg_args:
        # Insert any caller-provided flags *before* the output path.
        out = cmd.pop()
        cmd.extend(extra_ffmpeg_args)
        cmd.append(out)

    logger.info("Converting GIF to MP4 via ffmpeg: %s -> %s", gif_path, output_path)
    logger.debug("ffmpeg command: %s", " ".join(cmd))

    try:
        proc = subprocess.run(
            cmd,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg not found on PATH; cannot encode video") from exc

    if proc.returncode != 0:
        logger.error(
            "ffmpeg exited with code %s when converting %s -> %s",
            proc.returncode,
            gif_path,
            output_path,
        )
        logger.debug("ffmpeg output:\n%s", proc.stdout.decode("utf-8", errors="ignore"))
        raise RuntimeError(f"ffmpeg failed with exit code {proc.returncode}")

    logger.debug("ffmpeg output:\n%s", proc.stdout.decode("utf-8", errors="ignore"))
    logger.info(
        "GIF to MP4 complete: %s (%.2f MB) -> %s (%.2f MB)",
        gif_path,
        gif_path.stat().st_size / (1024 * 1024),
        output_path,
        output_path.stat().st_size / (1024 * 1024),
    )
    return output_path


def ensure_goal_video(
    gif_path: PathLike,
    *,
    force_reencode: bool = False,
    crf: int = 23,
    preset: str = "medium",
) -> Path:
    """Ensure we have an MP4 video corresponding to a goal GIF.

    Typical usage from goal event logic or a test harness:

        gif_path = render_goal_gif(...)
        mp4_path = ensure_goal_video(gif_path)

    Behavior:
    - If `<gif_path>.mp4` already exists and `force_reencode=False`, it is
      returned without doing any work.
    - Otherwise gif_to_mp4(...) is called to (re)generate the MP4.
    """
    gif_path = Path(gif_path)
    mp4_path = gif_path.with_suffix(".mp4")

    if mp4_path.exists() and not force_reencode:
        logger.info("Reusing existing MP4 for GIF: %s", mp4_path)
        return mp4_path

    return gif_to_mp4(gif_path, mp4_path, crf=crf, preset=preset)


if __name__ == "__main__":
    # Tiny CLI shim so you can experiment locally, e.g.:
    #   python -m core.gifs.goal_video /path/to/goal_123.gif
    import argparse

    parser = argparse.ArgumentParser(description="Convert EDGE GIF to MP4.")
    parser.add_argument("gif", help="Path to the input GIF")
    parser.add_argument(
        "--crf",
        type=int,
        default=23,
        help="H.264 CRF quality (lower = better; default: 23)",
    )
    parser.add_argument(
        "--preset",
        type=str,
        default="medium",
        help="ffmpeg preset (e.g. veryfast, fast, medium, slow)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-encode even if an existing MP4 is present.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    gif = Path(args.gif)
    mp4 = ensure_goal_video(gif, force_reencode=args.force, crf=args.crf, preset=args.preset)
    print(mp4)
