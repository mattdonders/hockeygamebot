#!/usr/bin/env bash
# SAMPLE thin PROD wrapper for HockeyGameBot.
# Copy this file to scripts/hgb-prod.sh and edit REPO / VENV_NAME / VENV_PATH as needed.

set -euo pipefail

# --- EDIT THESE FOR YOUR ENVIRONMENT ---
REPO="/path/to/your/hockeygamebot-prod"
VENV_NAME="hockeygamebot"
VENV_PATH="$HOME/.virtualenvs/$VENV_NAME"
# ---------------------------------------

cd "$REPO"

# 1) Sync repo hard to origin/main
git fetch --prune origin
git checkout main
git branch --set-upstream-to=origin/main main >/dev/null 2>&1 || true
git reset --hard origin/main
git submodule update --init --recursive

# 2) Activate virtualenv
if [ -d "$VENV_PATH" ]; then
  # shellcheck source=/dev/null
  source "$VENV_PATH/bin/activate"
else
  echo "[HGB] ❌ Missing venv at $VENV_PATH."
  echo "[HGB] Create it with something like: mkvirtualenv $VENV_NAME"
  exit 1
fi

# 3) Hand off to Python orchestrator
exec python -m orchestrator
