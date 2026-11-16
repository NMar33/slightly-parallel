#!/usr/bin/env python3
"""macOS: a server started at login finds Codex in /opt/homebrew/bin.

A login item or a service starts with a short PATH (``/usr/bin:/bin``), so
``shutil.which("codex")`` finds nothing there and codexlimits.find_codex
looks in the usual install folders. CI runs this with ``env -i`` and that
PATH, after linking a stand-in ``codex`` (the tests' app-server stand-in)
into /opt/homebrew/bin when no codex is there. It checks the program is
found there, answers the limits read, and leaves no process behind; then it
removes the link it made.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

import psutil  # noqa: E402

from backend import codexlimits  # noqa: E402
from tests.test_codexlimits import fake_codex  # noqa: E402

BREW = Path("/opt/homebrew/bin")


def main() -> int:
    print(f"PATH={os.environ.get('PATH', '')}")
    if not BREW.is_dir():
        print(f"FAILED: {BREW} is not on this machine")
        return 1
    target = BREW / "codex"
    made = False
    with tempfile.TemporaryDirectory() as tmp:
        if not target.exists():
            target.symlink_to(fake_codex(Path(tmp)))
            made = True
        try:
            found = codexlimits.find_codex()
            print(f"found: {found or 'nothing'}")
            if Path(found or "/nonexistent") != target:
                print(f"FAILED: expected {target}")
                return 1
            got = codexlimits.read(timeout=15, exe=found)
            print(f"read: {'ok, 5-hour ' + str(got['limits_line'].get('five_hour')) if got['ok'] else got['cause']}")
            if made and not got["ok"]:
                print("FAILED: the stand-in did not answer")
                return 1
            time.sleep(2)
            left = [p.pid for p in psutil.process_iter(["cmdline"])
                    if "fake_codex.py" in " ".join(p.info["cmdline"] or [])]
            if left:
                print(f"FAILED: left running: {left}")
                return 1
        finally:
            if made:
                target.unlink()
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
