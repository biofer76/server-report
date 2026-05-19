#!/bin/bash
# =============================================================================
# remove-cron.sh - Remove the server-report cron entry
#
# Usage:
#   bash scripts/remove-cron.sh
#   sudo bash scripts/remove-cron.sh   # required on most systems
#
# Removes any cron entry referencing server-report/main.py from the
# root crontab. Must be run as root.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON="$PROJECT_DIR/.venv/bin/python"
MAIN="$PROJECT_DIR/main.py"

if [ ! -f "$PYTHON" ]; then
    echo "[ERROR] Virtualenv not found at $PROJECT_DIR/.venv"
    echo "        Run: python3 -m venv $PROJECT_DIR/.venv && $PROJECT_DIR/.venv/bin/pip install -r $PROJECT_DIR/requirements.txt"
    exit 1
fi

if [ ! -f "$MAIN" ]; then
    echo "[ERROR] main.py not found at $MAIN"
    exit 1
fi

sudo "$PYTHON" "$MAIN" --remove-cron