"""The log is small, sums itself up, and comes out as text an AI can read."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi.testclient import TestClient

from backend import logbook
from backend.server import create_app


def test_the_ring_keeps_only_the_last_lines():
    ring = logbook.RingHandler(size=5)
    lg = logging.getLogger("test.ring")
    lg.addHandler(ring)
    try:
        for i in range(9):
            lg.info("line %d", i)
    finally:
        lg.removeHandler(ring)
    assert [r["msg"] for r in ring.snapshot()] == [f"line {i}" for i in range(4, 9)]
    assert ring.tail(2) == ring.snapshot()[-2:]


def test_the_stats_sum_requests_by_path_shape_and_name_the_slow_ones():
    rows = [
        {"ts": 1.0, "level": "INFO", "logger": "s", "msg": "req", "method": "GET",
         "path": "/api/tasks/tk_1234abcd", "status": 200, "ms": 20},
        {"ts": 2.0, "level": "WARNING", "logger": "s", "msg": "req", "method": "GET",
         "path": "/api/tasks/tk_99aabbcc", "status": 200, "ms": 900, "why": "slow"},
        {"ts": 3.0, "level": "INFO", "logger": "s", "msg": "req", "method": "GET",
         "path": "/api/health", "status": 500, "ms": 1},
        {"ts": 4.0, "level": "INFO", "logger": "db", "msg": "views rebuilt: projects=1", "ms": 120},
        {"ts": 5.0, "level": "ERROR", "logger": "s", "msg": "request failed", "exc": "X: y"},
    ]
    s = logbook.stats(rows)
    assert s["requests"]["n"] == 3 and s["requests"]["slow_n"] == 1
    by = {p["path"]: p for p in s["requests"]["by_path"]}
    assert by["GET /api/tasks/{id}"]["n"] == 2 and by["GET /api/tasks/{id}"]["max_ms"] == 900
    assert by["GET /api/health"]["errors"] == 1
    assert s["rebuilds"] == {"n": 1, "p50_ms": 120, "max_ms": 120, "last_ms": 120}
    assert s["errors_n"] == 1 and s["warnings_n"] == 1
    assert s["requests"]["by_path"][0]["path"] == "GET /api/tasks/{id}", "the costliest first"


def test_the_health_page_reads_the_log_and_copies_it_as_text(tmp_path: Path):
    root = tmp_path / "data"
    root.mkdir()
    app = create_app(data_root=root, watch=False)
    with TestClient(app) as c:
        assert c.get("/api/health").status_code == 200
        d = c.get("/api/logs?limit=50").json()
        s = d["summary"]
        assert s["data_root"] == str(root)
        assert s["uptime_s"] >= 0 and "rebuilds" in s and "requests" in s
        assert any(r["msg"] == "req" and r["path"] == "/api/health" for r in d["records"])
        t = c.get("/api/logs/text?limit=50")
        assert t.status_code == 200 and t.headers["content-type"].startswith("text/plain")
        assert "# Slightly Parallel health" in t.text and "GET /api/health → 200" in t.text
        assert "## Log tail" in t.text


def test_a_slow_request_is_named_slow_in_the_log(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(logbook, "SLOW_REQUEST_MS", 0)
    root = tmp_path / "data"
    root.mkdir()
    app = create_app(data_root=root, watch=False)
    with TestClient(app) as c:
        c.get("/api/health")
        rows = [r for r in logbook.RING.snapshot() if r.get("path") == "/api/health"]
    assert rows and rows[-1]["level"] == "WARNING" and rows[-1]["why"] == "slow"
