#!/usr/bin/env python3
"""Rebuild benchmark — how long a view rebuild takes as a data root grows.

A rebuild happens whenever a watched file changes, so its cost is the thing
that decides whether the dashboard still feels live once you have real
history. Run it before and after touching anything in ``db.py``.

    cd backend && .venv/bin/python ../scripts/bench_rebuild.py
    cd backend && .venv/bin/python ../scripts/bench_rebuild.py --turns 50000

It reports three numbers, each the minimum of N runs after a warm-up:

    fixtures   the shipped demo data — the small case
    synthetic  a generated root, sized by --decisions/--goals/--chats/--turns
    query      one filtered lens query against the synthetic root

Writing this script is how the 20.4 s session-insert stall was found
(fixed in db.py by staging through DuckDB's CSV reader instead of
executemany). If a future change regresses that, this is where it shows.
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from backend.db import ViewStore  # noqa: E402


def timed(store: ViewStore, runs: int) -> float:
    store.rebuild()  # warm
    best = float("inf")
    for _ in range(runs):
        t0 = time.perf_counter()
        store.rebuild()
        best = min(best, (time.perf_counter() - t0) * 1000)
    return best


def write_csv(path: Path, header: list[str], rows) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def build_synthetic(root: Path, decisions: int, goals: int, chats: int, turns: int) -> None:
    (root / "projects").mkdir(parents=True, exist_ok=True)
    write_csv(
        root / "decisions.csv",
        ["id", "created_date", "created_time", "project", "agent_id",
         "decision_text", "rationale", "source", "related_goal_id", "tags", "md_ref"],
        ([f"dc_{i:08d}", "2608-10", "12:00", f"proj{i % 20}", f"agent-{i % 50}",
          f"Decision number {i}", "because reasons", "explicit", "", "", ""]
         for i in range(decisions)),
    )
    write_csv(
        root / "goals.csv",
        ["id", "created_date", "project", "agent_id", "goal_text", "parent_goal_id",
         "related", "time_est", "confidence_pct", "success_comment", "status",
         "children_n", "retro_outcome", "md_ref", "sprint_id"],
        ([f"g_{i:08d}", "2608-10", f"proj{i % 20}", f"agent-{i % 50}",
          f"Goal number {i}", "", "", "1d", "80", "", "active", "0", "unknown", "", ""]
         for i in range(goals)),
    )
    per_chat = max(1, turns // max(1, chats))
    for a in range(chats):
        d = root / "projects" / f"proj{a % 20}" / "chats" / f"cc-{a:04d}"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "chat.md", "w", encoding="utf-8") as fh:
            fh.write("# Chat log\n\n---\n")
            for t in range(per_chat):
                fh.write(
                    f"\n## Turn {t + 1} · 2026-08-1{t % 4}T"
                    f"{(t % 12) + 8:02d}:{(t * 7) % 60:02d}:00\n"
                    f"**User**: question {t}\n**Agent**: answer {t}\n"
                )
        (d / "meta.json").write_text(
            '{"agent_id": "cc-%04d", "project": "proj%d"}' % (a, a % 20),
            encoding="utf-8",
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--decisions", type=int, default=20000)
    ap.add_argument("--goals", type=int, default=20000)
    ap.add_argument("--chats", type=int, default=200)
    ap.add_argument("--turns", type=int, default=10000)
    ap.add_argument("--keep", action="store_true", help="don't delete the synthetic root")
    args = ap.parse_args()

    fixtures = REPO / "fixtures"
    store = ViewStore(fixtures)
    ms = timed(store, args.runs)
    sessions = store.query("SELECT COUNT(*) AS n FROM sessions")[0]["n"]
    print(f"fixtures   rebuild {ms:8.0f} ms   ({sessions} sessions)")

    tmp = Path(tempfile.mkdtemp(prefix="sp-bench-"))
    root = tmp / "data"
    try:
        build_synthetic(root, args.decisions, args.goals, args.chats, args.turns)
        store = ViewStore(root)
        ms = timed(store, args.runs)
        sessions = store.query("SELECT COUNT(*) AS n FROM sessions")[0]["n"]
        rows = args.decisions + args.goals
        print(f"synthetic  rebuild {ms:8.0f} ms   "
              f"({rows:,} CSV rows, {args.turns:,} turns -> {sessions:,} sessions)")

        best = float("inf")
        for _ in range(20):
            t0 = time.perf_counter()
            store.query(
                "SELECT * FROM decisions_mutual WHERE project = ? "
                "ORDER BY created_date DESC LIMIT 50", ("proj3",))
            best = min(best, (time.perf_counter() - t0) * 1000)
        print(f"query      filter  {best:8.1f} ms   "
              f"(over {args.decisions:,} decisions, no index)")
        if args.keep:
            print(f"\nsynthetic root kept at {root}")
    finally:
        if not args.keep:
            shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
