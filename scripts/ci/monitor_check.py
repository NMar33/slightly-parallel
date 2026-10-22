#!/usr/bin/env python3
"""CI: the resource monitor, live, on the runner's own system.

The unit tests feed the monitor made-up readings; this asks the running
server (``sp.py up``) for what it measured on this machine — processor,
memory, disks, network, ping, its own memory and the heaviest processes —
and fails on a reading that is missing or not a number a machine can have.
Temperature and battery are printed, not required: Windows and most CI
machines have no sensor to read. Run from the repository folder, with the
server running.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

BASE = f"http://127.0.0.1:{os.environ.get('SP_PORT') or 8123}"


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def number(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v


def main() -> int:
    now: dict = {}
    procs: dict = {}
    # The first sample comes a few seconds after the start, the process scan
    # later (every 30 s by default), and the ping on its own clock.
    for _ in range(120):
        now = get("/api/monitor/now")
        procs = get("/api/monitor/processes?limit=5")
        s = now.get("sample") or {}
        if s and procs.get("processes") and "ping_ok" in s and s.get("net_rx") is not None:
            break
        time.sleep(1)
    s = now.get("sample") or {}
    host = now.get("host") or {}
    print(f"host: {host.get('os')} · {host.get('cpus')} cpus · {(host.get('memory') or 0) / 1e9:.1f} GB · Python {host.get('python')}")
    checks: list[tuple[str, bool, object]] = [
        ("the monitor runs", now.get("running") is True, now.get("running")),
        ("processor %", number(s.get("cpu")) and 0 <= s["cpu"] <= 100, s.get("cpu")),
        ("memory total", number(s.get("mem_total")) and s["mem_total"] > 0, s.get("mem_total")),
        ("memory %", number(s.get("mem_pct")) and 0 < s["mem_pct"] <= 100, s.get("mem_pct")),
        ("disks", bool(s.get("disks")) and all(number(d.get("total")) and d["total"] > 0 for d in s["disks"]),
         [d.get("mount") for d in s.get("disks") or []]),
        ("disk %", number(s.get("disk_pct")) and 0 < s["disk_pct"] <= 100, s.get("disk_pct")),
        ("disk read / write", number(s.get("disk_read")) and number(s.get("disk_write")), (s.get("disk_read"), s.get("disk_write"))),
        ("network in / out", number(s.get("net_rx")) and number(s.get("net_tx")), (s.get("net_rx"), s.get("net_tx"))),
        ("ping", s.get("ping_ok") is True and number(s.get("ping_ms")), (s.get("ping_host"), s.get("ping_ms"))),
        ("the server's own memory", number(s.get("self_rss")) and s["self_rss"] > 10e6, s.get("self_rss")),
        ("heaviest processes", bool(procs.get("processes")) and all(
            p.get("name") and number(p.get("rss")) for p in procs["processes"]),
         [(p.get("name"), round((p.get("rss") or 0) / 1e6)) for p in procs.get("processes") or []]),
    ]
    failed = [name for name, ok, _ in checks if not ok]
    for name, ok, value in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: {value}")
    for name in ("load1", "swap_total", "temp_c", "battery"):
        print(f"  info {name}: {s.get(name)}")
    if failed:
        sys.exit("the monitor did not read: " + ", ".join(failed))
    print("every reading is there", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
