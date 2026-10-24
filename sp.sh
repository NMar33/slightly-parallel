#!/usr/bin/env bash
# sp.sh — the launcher on Linux and macOS: runs sp.py, which does
# the work on every system (Windows: sp.cmd). See sp.py for the
# commands: up [--dev] · down · restart · status · logs · terminal on|off · run
# · open · autostart on|off · shortcut [off].
cd "$(dirname "$0")" || exit 1
# The newest named interpreter first: on macOS plain python3 is often an
# old system one while a newer python3.1x sits beside it.
# Each candidate is run, not only found: a pyenv shim is on PATH for every
# version pyenv knows, and prints "command not found" for one not installed.
for name in python3.14 python3.13 python3.12 python3.11 python3 python; do
  PY="$(command -v "$name")" || continue
  "$PY" -c "import sys; sys.exit(sys.version_info < (3, 11))" >/dev/null 2>&1 && exec "$PY" sp.py "$@"
done
echo "[sp] ERROR: Python 3.11+ not found — Ubuntu/Debian: sudo apt install python3.12 python3.12-venv · macOS: brew install python@3.12 · or https://www.python.org/downloads/" >&2
exit 1
