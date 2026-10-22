"""Regression tests: malformed or legacy-encoded CSVs must never break the app.

Older Slightly Parallel versions wrote ``task_events.csv`` through ``csv.writer``
without ``newline=""``, producing ``\r\n`` row terminators; newer appends use
``\n``. DuckDB's dialect sniffer hard-fails on the mixed file, which used to
crash ``rebuild()`` — and with it every request that triggered one.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.db import ViewStore
from backend.server import create_app


@pytest.fixture()
def mixed_endings_root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    (root / "tasks.csv").write_text(
        "id,created_date,created_time,project,agent_id,title,status,priority,"
        "assignee,due_date,lane,tags,position,md_ref\n"
        "tk_x1,2608-10,09:00,alpha,agent-a,Fix the flaky test,todo,med,,,"
        ",,0,\n",
        encoding="utf-8",
    )
    # Legacy \r\n rows followed by a modern \n row — the sniffer-killer.
    (root / "task_events.csv").write_bytes(
        b"event_id,task_id,timestamp,actor,field,old_value,new_value\r\n"
        b"ev_old1,tk_x1,2026-08-11T10:00:00,operator,status,todo,doing\r\n"
        b"ev_new1,tk_x1,2026-08-12T09:00:00,operator,status,doing,todo\n"
    )
    return root


def test_rebuild_survives_mixed_line_endings(mixed_endings_root: Path) -> None:
    store = ViewStore(data_root=mixed_endings_root)
    rows = store.query("SELECT * FROM task_events_mutual ORDER BY timestamp")
    # Both the legacy and the modern row parse.
    assert [r["event_id"] for r in rows] == ["ev_old1", "ev_new1"]


def test_task_update_succeeds_with_legacy_events_file(
    mixed_endings_root: Path,
) -> None:
    app = create_app(data_root=mixed_endings_root, watch=False)
    with TestClient(app) as client:
        r = client.post(
            "/api/tasks/tk_x1/update", json={"status": "doing", "actor": "operator"}
        )
        assert r.status_code == 200
        assert r.json()["task"]["status"] == "doing"

        events = client.get("/api/tasks/tk_x1/events")
        assert events.status_code == 200
        fields = [e["field"] for e in events.json()["events"]]
        assert "status" in fields


def test_rebuild_survives_binary_garbage_events_file(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    (root / "task_events.csv").write_bytes(b"\x00\xff\x00\xff not a csv at all")
    # Must not raise; the view degrades to empty.
    store = ViewStore(data_root=root)
    rows = store.query("SELECT * FROM task_events_mutual")
    assert rows == []


def test_append_upgrades_an_older_header(tmp_path: Path) -> None:
    """A CSV written before a column was added must not misalign new rows."""
    from backend.csvio import append_row, read_rows

    p = tmp_path / "t.csv"
    p.write_text("id,title\nA,first\n", encoding="utf-8")
    append_row(p, ("id", "title", "extra"), {"id": "B", "title": "second", "extra": "x"})
    rows = read_rows(p)
    assert p.read_text(encoding="utf-8").splitlines()[0] == "id,title,extra"
    assert rows[0] == {"id": "A", "title": "first", "extra": ""}
    assert rows[1] == {"id": "B", "title": "second", "extra": "x"}
