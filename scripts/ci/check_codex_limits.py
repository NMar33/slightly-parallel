#!/usr/bin/env python3
"""One read of the plan limits from the real Codex program, for CI.

The tests of backend/codexlimits.py talk to a stand-in. This talks to Codex
itself on each system: does it start (codex.cmd on Windows), does it answer
the protocol, does everything it started end. It spends no tokens.

CI logs in with an API key, which has no plan limits as far as is known, so
a sentence from Codex in place of percentages passes. What fails: no answer,
no app-server, an answer that cannot be read, a process left behind. The
percentages themselves need a login through ChatGPT: docs/release-testing.md.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

import psutil  # noqa: E402

from backend import codexlimits  # noqa: E402

#: Causes that say this program could not talk to Codex.
BROKEN = ("no answer in", "codex has no app-server", "codex could not start", "codex is not on this machine",
          "unreadable answer")


def codex_processes() -> dict[int, str]:
    """The running processes of Codex, with their command lines."""
    out: dict[int, str] = {}
    for p in psutil.process_iter(["pid", "cmdline"]):
        line = " ".join(p.info["cmdline"] or [])
        if "codex" in line.lower() and "app-server" in line and p.info["pid"] != os.getpid():
            out[p.info["pid"]] = line[:160]
    return out


def main() -> int:
    found = codexlimits.detect()
    print(f"codex: {found['exe'] or 'not found'}  home: {found['home']}")
    before = codex_processes()
    got = codexlimits.read()
    if got["ok"]:
        line = got["limits_line"]
        print(f"limits: plan {line.get('plan', '')}, 5-hour {line.get('five_hour')}, weekly {line.get('seven_day')}")
        print(f"account usage: {'read' if got.get('usage') else 'not read'}")
    else:
        print(f"no limits, Codex says: {got['cause']}")
    time.sleep(3)
    left = {k: v for k, v in codex_processes().items() if k not in before}
    failed = False
    if not got["ok"] and got["cause"].startswith(BROKEN):
        print(f"FAILED: could not talk to Codex: {got['cause']}")
        failed = True
    if left:
        print(f"FAILED: left running: {left}")
        failed = True
    print("failed" if failed else "ok")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
