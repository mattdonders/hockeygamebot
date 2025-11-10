#!/usr/bin/env bash
# Template launcher for PROD. Copy to your prod machine as scripts/hgb-prod.sh
# and customize the paths below. Keep this file tracked in Git as a reference.
set -euo pipefail

# --- EDIT THESE ON PROD AFTER COPYING ---
REPO="/Users/YOURUSER/Development/python/hockeygamebot-prod"
VENV_NAME="hockeygamebot"
VENV_PATH="$HOME/.virtualenvs/$VENV_NAME"
LAUNCH_LOG="$REPO/hgb-launch.out"
# ---------------------------------------

cd "$REPO"

# 1) Sync repo hard to origin/main
git fetch --prune origin
git checkout main
git branch --set-upstream-to=origin/main main >/dev/null 2>&1 || true
git reset --hard origin/main
git submodule update --init --recursive
COMMIT="$(git rev-parse --short HEAD)"

# 2) Activate venvwrapper environment
if [ -d "$VENV_PATH" ]; then
  # shellcheck source=/dev/null
  source "$VENV_PATH/bin/activate"
else
  echo "[HGB] ❌ Missing venv at $VENV_PATH. Create with: mkvirtualenv $VENV_NAME"
  exit 1
fi

# 3) Keep deps fresh (safe to run repeatedly)
# python -m pip install --upgrade pip >/dev/null
# pip install -r requirements.txt >/dev/null

# 4) Stop any previous bot instance
pkill -f "python -m hockeygamebot" || true
sleep 1

# 5) Version banner (wrapper log)
{
  echo "################################################################################"
  echo "# HockeyGameBot PROD Launch"
  echo "# Timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
  echo "# Commit: $COMMIT"
  echo "# Host: $(hostname)"
  echo "################################################################################"
  echo ""
} >> "$LAUNCH_LOG"

# 6) Start bot in background; app logs go to its own files
HOCKEYBOT_MODE=prod nohup python -m hockeygamebot \
  >> /dev/null 2>> "$LAUNCH_LOG" < /dev/null &

echo "[HGB] Started commit $COMMIT | PID: $! | Wrapper log: $LAUNCH_LOG"
