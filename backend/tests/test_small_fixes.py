"""Small defects from the 2026-10 review, one test each."""

from __future__ import annotations

import http.server
import threading
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from backend.db import ViewStore


def test_a_swap_that_fails_part_way_keeps_every_old_table(data_root: Path) -> None:
    store = ViewStore(data_root)
    names = [n for n, sig in store._sigs.items() if sig is not None]
    assert len(names) > 2
    real = store._con

    class Flaky:
        alters = 0

        def execute(self, sql, *args):
            if sql.startswith("ALTER TABLE"):
                Flaky.alters += 1
                if Flaky.alters == 2:
                    raise duckdb.IOException("the disk went away")
            return real.execute(sql, *args)

        def __getattr__(self, name):
            return getattr(real, name)

    store._sigs.clear()  # every table is built again
    store._con = Flaky()  # type: ignore[assignment]
    store.rebuild()
    store._con = real
    for name in names:
        store.query(f"SELECT count(*) AS n FROM {name}")  # none dropped and left missing


def test_a_query_that_fails_is_not_read_as_no_marks(data_root: Path, monkeypatch) -> None:
    from backend import produced
    store = ViewStore(data_root)

    def broken(sql, params=()):
        raise duckdb.BinderException("Referenced column \"kind\" not found")
    monkeypatch.setattr(store, "query", broken)
    with pytest.raises(duckdb.BinderException):
        produced.marks(store)
    with pytest.raises(duckdb.BinderException):
        produced.task_mentions(store)


def test_the_mcp_client_does_not_go_through_a_proxy(monkeypatch) -> None:
    from backend.mcp import Api

    class Answer(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Answer)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        for name in ("HTTP_PROXY", "http_proxy"):
            monkeypatch.setenv(name, "http://127.0.0.1:9")
        monkeypatch.delenv("NO_PROXY", raising=False)
        monkeypatch.delenv("no_proxy", raising=False)
        assert Api(f"http://127.0.0.1:{server.server_port}").get("/api/health") == {"ok": True}
    finally:
        server.shutdown()


def test_a_turn_number_that_is_not_a_number_is_a_422(client: TestClient) -> None:
    r = client.post("/api/tasks", json={
        "created_date": "2608-29", "created_time": "10:00", "project": "alpha",
        "agent_id": "operator", "title": "Turn number", "status": "todo", "description": "first"})
    tid = r.json()["metadata"]["id"]
    for n in ([1], {"a": 1}, "two"):
        r = client.post(f"/api/tasks/{tid}/update", json={"turn": {"n": n, "text": "x"}, "actor": "operator"})
        assert r.status_code == 422, r.text
