#!/usr/bin/env bash
# macOS / Linux wrapper: activate the venv and run the scout.
# Logging is handled by the app itself (state/scout.log, rotated).
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

if [ ! -x ".venv/bin/python" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: .venv is missing." >&2
    echo "  Set it up first:  python3 setup.py" >&2
    exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
exec python run.py
