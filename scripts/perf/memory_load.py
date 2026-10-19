#!/usr/bin/env python3
"""Memory and latency of the server under a browser's load.

Starts the server on a spare port over a copy of a data root (the copy is
deleted after; the source is only read), sends every GET route the API lists,
12 at a time, for a number of rounds, and prints the server's memory after
each round and the latency of the requests. Environment variables after the
data root go to the server, so two settings can be compared:

    python3 scripts/perf/memory_load.py ~/sp-data
    python3 scripts/perf/memory_load.py ~/sp-data MALLOC_ARENA_MAX=2

docs/performance.md keeps what was measured with it and what came of it.
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORT = 8131
ROUNDS = 6
PARALLEL = 12
SKIP = ("terminal", "download", "export")
COPY_SKIP = shutil.ignore_patterns("tour_shots", "monitor", "*.lock")


def rss_mb(pid: int) -> int:
    with open(f"/proc/{pid}/statm") as fh:
        return int(fh.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") // 1_000_000


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    source = Path(sys.argv[1]).expanduser()
    extra = dict(a.split("=", 1) for a in sys.argv[2:])
    work = Path(tempfile.mkdtemp(prefix="sp-perf-"))
    data = work / "data"
    shutil.copytree(source, data, ignore=COPY_SKIP)
    python = ROOT / "backend" / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
    env = {**os.environ, "SP_DATA_ROOT": str(data), "SP_PORT": str(PORT), "SP_SANDBOX": "1", "SP_EXAMPLES": "0", **extra}
    base = f"http://127.0.0.1:{PORT}"
    proc = subprocess.Popen([str(python), "-m", "uvicorn", "backend.server:app", "--host", "127.0.0.1", "--port", str(PORT)],
                            cwd=ROOT / "backend", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            try:
                urllib.request.urlopen(base + "/api/health", timeout=2)
                break
            except OSError:
                time.sleep(0.5)
        paths = [p for p, ops in json.load(urllib.request.urlopen(base + "/openapi.json"))["paths"].items()
                 if "get" in ops and "{" not in p and not any(s in p for s in SKIP)]
        times: list[float] = []

        def hit(path: str) -> None:
            t = time.perf_counter()
            try:
                urllib.request.urlopen(f"{base}{path}?project=merkhet", timeout=120).read()
            except OSError:
                pass
            times.append(time.perf_counter() - t)

        print(f"{' '.join(sys.argv[2:]) or 'default'} · {len(paths)} routes × {ROUNDS} rounds, {PARALLEL} at a time")
        print(f"  started: {rss_mb(proc.pid)} MB")
        with cf.ThreadPoolExecutor(PARALLEL) as pool:
            for n in range(1, ROUNDS + 1):
                list(pool.map(hit, paths))
                print(f"  round {n}: {rss_mb(proc.pid)} MB, {len(os.listdir(f'/proc/{proc.pid}/task'))} threads")
        times.sort()
        print(f"  latency: median {statistics.median(times) * 1000:.0f} ms, "
              f"p95 {times[int(len(times) * 0.95)] * 1000:.0f} ms")
    finally:
        proc.terminate()
        proc.wait(timeout=30)
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
