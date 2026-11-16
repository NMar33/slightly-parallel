"""Do the parts add up to the whole, on a real data folder? (docs/testing.md case 4)

    backend/.venv/bin/python scripts/check_consistency.py <data folder>

Read-only: the folder is copied to a temporary one first and the server runs
on the copy (a GET may write a cache file: test_every_get_answers.py lists
four), so the folder given is never written. Each check prints its numbers;
the exit code is the number of checks that failed.

- Usage: each range's totals equal the sum of its chats, and the sum of its
  tools (every chat counted: the page shows the top 40).
- The split of the limit's use: its parts add up to its total.
- The board: the API's tasks of each project, by status, are the rows of
  tasks.csv for that project.

CI runs it on the demo data (tests/test_consistency.py); run it by hand on
the operator's folder after a change to usage or the board.
"""

from __future__ import annotations

import csv
import os
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "backend"))
for _k, _v in (("SP_SANDBOX", "1"), ("SP_LOG_FILE", "0"), ("SP_EXAMPLE", "0"), ("SP_FSYNC", "0")):
    os.environ.setdefault(_k, _v)

SUMMED = ("new", "output", "cache", "cache_write", "rebuilt", "new_output", "turns")
TOLERANCE = 0.002   # the split's percentages are rounded


def _copy(src: Path) -> Path:
    dst = Path(tempfile.mkdtemp(prefix="sp-consistency-")) / "data"
    # Reading only; sockets, locks and the server's own log stay behind.
    shutil.copytree(src, dst, symlinks=True, ignore=shutil.ignore_patterns("*.lock", "*.sock", "logs"))
    return dst


def check(src: Path, out=print) -> list[str]:
    from fastapi.testclient import TestClient

    from backend import usagelib
    from backend.server import create_app, operator_cookie

    usagelib.TOP_CHATS = 10 ** 6
    root = _copy(src)
    failed: list[str] = []

    def fail(msg: str) -> None:
        failed.append(msg)
        out(f"FAIL {msg}")

    try:
        app = create_app(data_root=root, watch=False, run_monitor=False)
        with TestClient(app, base_url="http://127.0.0.1:8123") as c:
            name, value = operator_cookie(app)
            c.cookies.set(name, value)
            for rng in ("today", "7d", "30d"):
                got = c.get(f"/api/usage?range={rng}").json()
                totals, chats, tools = got["totals"], got["chats"], got["by_tool"]
                if got.get("chats_total", len(chats)) != len(chats):
                    fail(f"usage {rng}: {len(chats)} chats listed of {got['chats_total']}")
                for k in SUMMED:
                    whole = totals.get(k) or 0
                    by_chat = sum(ch.get(k) or 0 for ch in chats)
                    by_tool = sum(t.get(k) or 0 for t in tools)
                    if whole != by_chat or whole != by_tool:
                        fail(f"usage {rng} {k}: total {whole}, chats {by_chat}, tools {by_tool}")
                mix = (got.get("analysis") or {}).get("mix") or {}
                parts = sum(p.get("pct") or 0 for p in mix.get("parts") or [])
                if abs(parts - (mix.get("total_pct") or 0)) > TOLERANCE * max(1.0, abs(parts)):
                    fail(f"usage {rng} split: parts {parts:.4f} against a total of {mix.get('total_pct')}")
                out(f"ok   usage {rng}: {len(chats)} chats, new_output {totals.get('new_output')}, "
                    f"split {parts:.4f}/{mix.get('total_pct')}")
            rows: list[dict] = []
            if (root / "tasks.csv").exists():
                with open(root / "tasks.csv", encoding="utf-8", newline="") as fh:
                    rows = list(csv.DictReader(fh))
            for project in sorted({r.get("project") or "" for r in rows} - {""}):
                want = Counter(r.get("status") or "" for r in rows
                               if r.get("project") == project)
                api = c.get(f"/api/tasks?project={project}").json().get("tasks") or []
                home = Counter(t.get("status") or "" for t in api if t.get("project") == project)
                if home != want:
                    fail(f"board {project}: API {dict(home)} against tasks.csv {dict(want)}")
            out(f"ok   board: {len(rows)} rows in tasks.csv")
    finally:
        shutil.rmtree(root.parent, ignore_errors=True)
    return failed


if __name__ == "__main__":
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_dir():
        print(__doc__)
        sys.exit(2)
    sys.exit(len(check(Path(sys.argv[1]).resolve())))
