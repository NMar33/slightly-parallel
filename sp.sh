#!/usr/bin/env bash
# sp.sh — the launcher on Linux and macOS: runs sp.py, which does
# the work on every system (Windows: sp.cmd). See sp.py for the
# commands: up [--dev] · down · restart · status · logs · terminal on|off · run
# · open · autostart on|off · shortcut [off].
cd "$(dirname "$0")" || exit 1
# The newest named interpreter first: on macOS plain python3 is often an
# old system one while a newer python3.1x sits beside it.
PY="$(command -v python3.14 || command -v python3.13 || command -v python3.12 || command -v python3.11 || command -v python3 || command -v python)" || { echo "[sp] ERROR: Python 3.11+ not found" >&2; exit 1; }
exec "$PY" sp.py "$@"
