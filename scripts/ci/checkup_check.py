#!/usr/bin/env python3
"""CI: #sp's checks and the report, live, on the runner's own system.

``python scripts/ci/checkup_check.py up`` — with the server running
(``sp.py up``): the checks for a folder that is not connected say so, with
its recipe; what CI cannot prove (this chat, MCP) is unknown, never fine;
the checks of the machine and the server run; ``sp.py check`` prints them;
``sp.py report`` writes its file with every section and nothing from .env.

``python scripts/ci/checkup_check.py down`` — after ``sp.py down``:
``sp.py check`` fails and looks from outside (the supervisor, the data
folder, the disk). Run from the repository folder.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

BASE = f"http://127.0.0.1:{os.environ.get('SP_PORT') or 8123}"
SECTIONS = ("## Machine", "## Server now", "## Memory and machine, last 24 hours", "## Server log",
            "## Capture hook errors", "## Data", "## Tool transcripts", "## Settings",
            "## Supervisor output (last 60 lines)")
# A word that reaches the server's log in a query string: the report must cut it.
SENTINEL = "sp-ci-sentinel-7f3a91"


def sp(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "sp.py", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=180)


def up() -> list[str]:
    failed: list[str] = []

    def check(name: str, ok: bool, detail: object = "") -> None:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f": {detail}" if detail != "" else ""))
        if not ok:
            failed.append(name)

    folder = tempfile.mkdtemp(prefix="sp-checkup-")
    with urllib.request.urlopen(f"{BASE}/api/checkup?{urllib.parse.urlencode({'cwd': folder})}", timeout=60) as r:
        got = json.loads(r.read().decode("utf-8"))
    by = {f["id"]: f for f in got["findings"]}
    print("verdict:", got["verdict"])
    check("a folder not connected is a concern", by.get("folder", {}).get("reason") == "folder.not_integrated",
          by.get("folder", {}).get("title"))
    check("…with its recipe, saying who acts", "**Who:** operator" in by.get("folder", {}).get("recipe", ""))
    check("this chat is unknown, not fine", by.get("chat", {}).get("status") == "unknown", by.get("chat", {}).get("title"))
    check("MCP is unknown, not fine", by.get("mcp", {}).get("status") == "unknown", by.get("mcp", {}).get("title"))
    # Checked means a finding with its evidence: a runner short of disk or
    # memory may rightly answer note or concern.
    for fid in ("data", "disk", "memory", "errors"):
        f = by.get(fid, {})
        check(f"{fid} was checked", f.get("status") in ("ok", "note", "concern"),
              f"{f.get('status')} · {f.get('title')}")
    check("the verdict is not 'All fine'", not got["verdict"].startswith("All fine"), got["verdict"])

    out = sp("check")
    check("sp.py check prints the checks", "Data is readable and writable" in out.stdout, out.stdout[-300:])

    try:
        urllib.request.urlopen(f"{BASE}/api/search?q={SENTINEL}", timeout=60).read()
    except OSError:
        pass
    before = set(Path(".").glob("slightly-parallel-report-*.md"))
    out = sp("report")
    reports = sorted(set(Path(".").glob("slightly-parallel-report-*.md")) - before, key=lambda p: p.stat().st_mtime)
    text = reports[-1].read_text(encoding="utf-8") if reports else ""
    check("sp.py report wrote its file", bool(text), out.stdout[-200:])
    missing = [s for s in SECTIONS if s not in text]
    check("the report has every section", not missing, missing)
    check("the report is from the running server", "## The running server's summary" in text)
    check("a query string in the log is cut from the report", SENTINEL not in text)
    env = Path(".env")
    secrets = [ln.split("=", 1)[1].strip().strip('"') for ln in env.read_text(encoding="utf-8").splitlines()
               if "=" in ln and not ln.startswith("#") and any(w in ln.split("=", 1)[0].upper()
                                                               for w in ("TOKEN", "KEY", "SECRET", "PASSWORD"))] if env.is_file() else []
    check("no secret from .env in the report", not any(v and v in text for v in secrets))
    for p in reports:
        p.unlink()
    return failed


def down() -> list[str]:
    out = sp("check")
    print(out.stdout[-1500:])
    failed = []
    for name, ok in (("sp.py check fails with the server down", out.returncode != 0),
                     ("it says the server does not answer", "does not answer" in out.stdout),
                     ("it looks at the supervisor", "supervisor:" in out.stdout),
                     ("it looks at the data folder and the disk", "data folder:" in out.stdout and "disk:" in out.stdout)):
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
        if not ok:
            failed.append(name)
    return failed


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "up"
    bad = up() if mode == "up" else down()
    if bad:
        sys.exit("failed: " + ", ".join(bad))
    print("all checks passed")
