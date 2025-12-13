#!/usr/bin/env python
"""
Standalone dashboard HTTP server for HockeyGameBot.

- Serves dashboard.html and status-*.json from the repo root.
- Exposes /api/bots which returns a list of currently "active" bots
  based on any status-<slug>.json files in the working directory.
"""

import argparse
import glob
import http.server
import json
import logging
import os
import socketserver
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger("hgb.dashboard")


def discover_bots() -> List[Dict[str, Any]]:
    """
    Discover bots by enumerating status-*.json files in the current directory.

    Returns:
        List of dicts: {slug, status_file, label}
    """
    bots: List[Dict[str, Any]] = []

    for path in glob.glob("status_*.json"):
        # status-njd.json -> njd
        slug = path[len("status_") : -len(".json")]
        label = slug.updas()
        status_file = path

        # Try to read nicer label info from the JSON (home/away teams, etc.)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            game = data.get("game", {}) or {}
            home = game.get("home_team") or ""
            away = game.get("away_team") or ""

            if home and away:
                label = f"{slug.upper()} — {away} @ {home}"
            elif home or away:
                label = f"{slug.upper()} — {home or away}"
        except Exception:
            # Fallback is fine
            pass

        bots.append(
            {
                "slug": slug,
                "status_file": status_file,
                "label": label,
            }
        )

    # Sort by slug for stable ordering
    bots.sort(key=lambda b: b["slug"])
    return bots


class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler that serves static files + /api/bots."""

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        # Silence per-request logging; we log at server level instead.
        logger.debug("HTTP: " + format, *args)

    def do_GET(self) -> None:
        if self.path.startswith("/api/bots"):
            self._handle_bots_api()
            return

        # Default: serve static files (dashboard.html, status-*.json, etc.)
        return super().do_GET()

    def _handle_bots_api(self) -> None:
        try:
            bots = discover_bots()
            payload = json.dumps(bots).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Error handling /api/bots: %s", exc)
            msg = json.dumps({"error": "internal server error"}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)


def main() -> None:
    parser = argparse.ArgumentParser(description="Standalone dashboard HTTP server.")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
    )

    # Serve from repo root (where dashboard.html + status-*.json live)
    base_dir = Path(__file__).resolve().parent
    os.chdir(base_dir)

    with socketserver.TCPServer((args.host, args.port), DashboardHandler) as httpd:
        logger.info("Dashboard server listening on http://%s:%d/dashboard.html", args.host, args.port)
        logger.info("Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("Shutting down dashboard server...")


if __name__ == "__main__":
    main()
