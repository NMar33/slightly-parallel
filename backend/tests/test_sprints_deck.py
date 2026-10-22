"""The sprints deck answers, with a board that has an open backlog."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.server import create_app


def test_the_deck_reads_with_blocks_and_a_backlog(tmp_path: Path) -> None:
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    with TestClient(create_app(data_root=root, watch=False)) as c:
        assert c.post("/api/sprints", json={
            "created_date": "2609-24", "started_date": "2609-24", "name": "S1",
            "projects": "alpha", "status": "active", "agent_id": "operator", "project": "alpha",
        }).status_code == 201
        for i, status in enumerate(("todo", "doing", "done")):
            assert c.post("/api/tasks", json={
                "created_date": "2609-24", "created_time": f"10:0{i}", "project": "alpha",
                "agent_id": "operator", "title": f"t{i}", "status": status,
            }).status_code == 201
        r = c.get("/api/sprints/deck")
        assert r.status_code == 200, r.text
        d = r.json()
        # Two open tasks with no block wait in alpha's backlog; the done one does not.
        assert d["backlog"] == {"alpha": 2}, d.get("backlog")
