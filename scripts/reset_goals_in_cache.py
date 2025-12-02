#!/usr/bin/env python3
"""
reset_goals_in_cache.py

Removes all goal_snapshots and their sortOrders from a Game Cache JSON.

Usage:
    python reset_goals_in_cache.py /path/to/cache.json
"""

import json
import sys
from datetime import datetime
from pathlib import Path


def reset_goal_events(cache_path: Path):
    if not cache_path.exists():
        print(f"❌ File not found: {cache_path}")
        return

    print(f"🔍 Loading cache: {cache_path}")

    with open(cache_path, "r") as f:
        data = json.load(f)

    snapshots = data.get("goal_snapshots", {})
    processed = data.get("processed_sort_orders", [])

    if not snapshots:
        print("ℹ️  No goal_snapshots found. Nothing to remove.")
        return

    goal_event_ids = list(snapshots.keys())
    sort_orders_to_remove = []

    print(f"🏒 Found {len(goal_event_ids)} goal snapshot(s).")

    # Collect sortOrders linked to these goal events
    for event_id in goal_event_ids:
        snap = snapshots.get(event_id, {})
        so = snap.get("sortOrder")
        if so is not None:
            sort_orders_to_remove.append(so)

    print(f"📝 Sort orders to remove: {sort_orders_to_remove}")

    # --- REMOVE GOALS ---
    for event_id in goal_event_ids:
        snapshots.pop(event_id, None)

    # --- REMOVE processed_sort_orders entries ---
    new_processed = [so for so in processed if so not in sort_orders_to_remove]

    data["goal_snapshots"] = snapshots
    data["processed_sort_orders"] = new_processed

    # --- Backup original file ---
    backup = cache_path.with_suffix(f".backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
    cache_path.rename(backup)
    print(f"📦 Backup created: {backup}")

    # --- Write cleaned file ---
    with open(cache_path, "w") as f:
        json.dump(data, f, indent=2)

    print("✅ Goal snapshots removed.")
    print("✅ Relevant sortOrders removed from processed_sort_orders.")
    print(f"💾 Updated cache saved to: {cache_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python reset_goals_in_cache.py /path/to/cache.json")
        sys.exit(1)

    reset_goal_events(Path(sys.argv[1]))
