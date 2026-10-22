"""Archive (reversible) and delete (to .trash) for tasks."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app


@pytest.fixture()
def client(tmp_path: Path):
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    app = create_app(data_root=root, watch=False)
    with TestClient(app) as c:
        yield c


def _task(client: TestClient, title: str, t: str = "10:00") -> str:
    r = client.post("/api/tasks", json={
        "created_date": "2608-19", "created_time": t, "project": "alpha",
        "agent_id": "operator", "title": title, "status": "todo", "description": "body",
    })
    assert r.status_code == 201
    return r.json()["metadata"]["id"]


def test_archive_and_restore_keep_everything(client: TestClient) -> None:
    a = _task(client, "Archive me")
    r = client.post(f"/api/tasks/{a}/archive", json={"actor": "operator"})
    assert r.status_code == 200 and r.json()["archived_at"]
    row = client.get("/api/tasks?project=alpha").json()["tasks"][0]
    assert row["archived_at"]
    ev = client.get(f"/api/tasks/{a}/events").json()["events"]
    assert any(e["field"] == "archived" and e["new_value"] == "yes" for e in ev)
    assert client.post(f"/api/tasks/{a}/restore", json={}).json()["archived_at"] == ""
    assert not client.get("/api/tasks?project=alpha").json()["tasks"][0]["archived_at"]
    assert client.post("/api/tasks/tk_nope/archive", json={}).status_code == 404


def test_delete_moves_the_task_and_its_satellites_to_trash(client: TestClient, tmp_path: Path) -> None:
    a = _task(client, "Doomed")
    b = _task(client, "Neighbour", t="10:01")
    client.post(f"/api/tasks/{a}/link", json={"to": b, "kind": "blocks"})
    n = client.post(f"/api/tasks/{a}/notes", json={"type": "release", "body": "shipped"}).json()["note"]
    d = client.post("/api/docs", json={"project": "alpha", "kind": "release", "title": "notes"}).json()["doc"]
    client.post(f"/api/docs/{d['id']}/items", json={"note_id": n["id"]})

    out = client.post(f"/api/tasks/{a}/delete").json()
    assert out["deleted"] == a and out["moved"]["task"] == 1 and out["moved"]["notes"] == 1 and out["moved"]["links"] == 1
    trash = Path(out["trash"])
    assert (trash / "tasks.csv").exists() and (trash / "task_notes.csv").exists() and (trash / "task_links.csv").exists()
    assert (trash / "task_details").exists()

    titles = [t["title"] for t in client.get("/api/tasks?project=alpha").json()["tasks"]]
    assert titles == ["Neighbour"]
    assert client.get(f"/api/tasks/{b}/links").json()["total"] == 0
    items = client.get(f"/api/docs/{d['id']}").json()["items"]
    assert not items[0]["note_id"] and "removed" in items[0]["text"]
    assert client.post(f"/api/tasks/{a}/delete").status_code == 404


def test_resurfacing_brings_tasks_back(client) -> None:
    """Bring it back: a due date returns the task to its target status,
    logged as actor `resurface`; a repeating task re-arms on done."""
    import datetime as dt
    from backend.routers import tasks_extra

    tid = client.post("/api/tasks", json={
        "created_date": "2608-20", "created_time": "10:00", "project": "alpha",
        "agent_id": "operator", "title": "monthly backup check", "status": "done",
        "resurface_on": (dt.date.today() - dt.timedelta(days=1)).isoformat(),
        "resurface_to": "review",
    }).json()["metadata"]["id"]
    moved = tasks_extra.resurface_sweep(client.app.state.store)
    assert moved == 1
    row = next(t for t in client.get("/api/tasks?project=alpha").json()["tasks"] if t["id"] == tid)
    assert row["status"] == "review" and not row["resurface_on"] and row["resurfaced_at"]
    ev = client.get(f"/api/tasks/{tid}/events").json()["events"]
    assert any(e["actor"] == "resurface" and e["field"] == "status" for e in ev)

    # Re-arm: done + every-days sets the next comeback automatically.
    client.post(f"/api/tasks/{tid}/update", json={"resurface_every_days": "30", "status": "done", "actor": "operator"})
    row = next(t for t in client.get("/api/tasks?project=alpha").json()["tasks"] if t["id"] == tid)
    assert row["resurface_on"] == (dt.date.today() + dt.timedelta(days=30)).isoformat()
    # Sweep again: nothing due — the future date stays armed.
    assert tasks_extra.resurface_sweep(client.app.state.store) == 0
