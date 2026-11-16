#!/usr/bin/env bash
# run.sh — Slightly Parallel in the foreground: `./run.sh` (dev: backend + Vite hot
# reload) or `./run.sh --prod` (built UI served from the backend port).
# Same as `./sp.sh run [--prod]`; the work is in sp.py.
cd "$(dirname "$0")" || exit 1
# As sp.sh: the newest Python the backend's packages are built for first.
PY="$(command -v python3.14 || command -v python3.13 || command -v python3.12 || command -v python3.11 || command -v python3 || command -v python)" || { echo "[run] ERROR: Python 3.11+ not found — Ubuntu/Debian: sudo apt install python3.12 python3.12-venv · macOS: brew install python@3.12 · or https://www.python.org/downloads/" >&2; exit 1; }
exec "$PY" sp.py run "$@"
