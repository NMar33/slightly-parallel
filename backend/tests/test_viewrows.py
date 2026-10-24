"""The store readers pages and libraries share (viewrows.py, date_utils.iso_moment),
and the routers still reach them through routers/deps as before."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from backend import viewrows
from backend.date_utils import iso_moment
from backend.db import ViewStore
from backend.routers import deps


def test_the_routers_names_are_the_same_functions() -> None:
    for name in ("agents_by_id", "attach_agent", "rows_or_empty", "AGENT_ORIGIN_FIELDS"):
        assert getattr(deps, name) is getattr(viewrows, name)
    assert deps.iso_moment is iso_moment


def test_iso_moment() -> None:
    assert iso_moment("2608-19", "02:47") == "2026-08-19T02:47:00"
    assert iso_moment("2608-19", "") == "2026-08-19T00:00:00"
    assert iso_moment("2026-08-19", "02:47") == ""


def test_a_missing_view_is_an_empty_ledger_and_the_agent_rides_along(tmp_path: Path) -> None:
    (tmp_path / "projects" / "alpha").mkdir(parents=True)
    store = ViewStore(tmp_path)
    store.rebuild()
    assert viewrows.rows_or_empty(store, "SELECT * FROM no_such_view") == []
    with pytest.raises(duckdb.Error):
        viewrows.rows_or_empty(store, "SELECT * FROM")            # a real error stays one
    rows = [{"agent_id": "cc-gone"}]
    viewrows.attach_agent(store, rows)
    assert rows == [{"agent_id": "cc-gone", "agent": None}]


def test_a_value_outside_the_vocabulary_is_refused_in_words(tmp_path: Path) -> None:
    """vocab.check_enum_fields: 422 and the allowed list, on create and update."""
    from fastapi.testclient import TestClient

    from backend.server import create_app
    (tmp_path / "projects" / "alpha").mkdir(parents=True)
    with TestClient(create_app(data_root=tmp_path, watch=False)) as c:
        body = {"created_date": "2610-24", "created_time": "10:00", "project": "alpha",
                "agent_id": "operator", "title": "x", "status": "bogus"}
        r = c.post("/api/tasks", json=body)
        assert r.status_code == 422 and r.json()["detail"].startswith("task.status bogus is not a known value — use one of: ")
        tid = c.post("/api/tasks", json={**body, "status": "todo"}).json()["metadata"]["id"]
        r = c.post(f"/api/tasks/{tid}/update", json={"status": "nope", "actor": "operator"})
        assert r.status_code == 422 and "task.status nope is not a known value" in r.json()["detail"]
