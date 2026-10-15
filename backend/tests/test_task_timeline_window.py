"""The task timeline's window: day / week / month, and all — since the first event."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.server import create_app


def test_all_opens_at_the_first_event_and_keeps_old_tasks(tmp_path: Path) -> None:
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    with TestClient(create_app(data_root=root, watch=False)) as c:
        for day, title in (("2601-05", "old"), ("2609-24", "new")):
            assert c.post("/api/tasks", json={
                "created_date": day, "created_time": "10:00", "project": "alpha",
                "agent_id": "operator", "title": title, "status": "todo",
            }).status_code == 201
        week = c.get("/api/tasks/timeline?project=alpha&window=month&limit=0").json()
        every = c.get("/api/tasks/timeline?project=alpha&window=all&limit=0").json()
    assert "old" not in {t["title"] for t in week["tasks"]}
    assert {t["title"] for t in every["tasks"]} == {"old", "new"}
    assert every["window"] == "all" and every["since"] == "2026-01-05T10:00:00"
