"""Global kanban: multi-project task membership and saved boards."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app


@pytest.fixture()
def client(tmp_path: Path):
    root = tmp_path / "data"
    for code in ("alpha", "beta"):
        (root / "projects" / code).mkdir(parents=True)
    app = create_app(data_root=root, watch=False)
    with TestClient(app) as c:
        yield c


def _task(client: TestClient, **over) -> dict:
    body = {
        "created_date": "2608-19", "created_time": "10:00", "project": "alpha",
        "agent_id": "operator", "title": "shared thing", "status": "todo",
    }
    body.update(over)
    r = client.post("/api/tasks", json=body)
    assert r.status_code == 201, r.text
    return r.json()["metadata"]


def test_membership_defaults_to_home_and_home_is_never_lost(client: TestClient) -> None:
    solo = _task(client)
    assert solo["projects"] == "alpha"
    both = _task(client, created_time="10:01", projects=["beta", "alpha", "beta"])
    assert both["projects"] == "alpha,beta"

    # Shrinking membership keeps the home project.
    r = client.post(f"/api/tasks/{both['id']}/update", json={"projects": "beta", "actor": "operator"})
    assert r.status_code == 200
    rows = {t["id"]: t for t in client.get("/api/tasks?project=alpha").json()["tasks"]}
    assert rows[both["id"]]["projects"] == "alpha,beta"


def test_project_board_shows_home_and_member_tasks(client: TestClient) -> None:
    _task(client, title="alpha only")
    shared = _task(client, created_time="10:02", title="alpha+beta", projects="beta")
    _task(client, created_time="10:03", title="beta only", project="beta")

    alpha = {t["title"] for t in client.get("/api/tasks?project=alpha").json()["tasks"]}
    beta = {t["title"] for t in client.get("/api/tasks?project=beta").json()["tasks"]}
    assert alpha == {"alpha only", "alpha+beta"}
    assert beta == {"beta only", "alpha+beta"}
    # One row, one status: moving it in beta moves it in alpha.
    client.post(f"/api/tasks/{shared['id']}/update", json={"status": "doing", "actor": "operator"})
    assert next(t for t in client.get("/api/tasks?project=alpha").json()["tasks"] if t["id"] == shared["id"])["status"] == "doing"


def test_boards_combined_and_standalone(client: TestClient) -> None:
    assert client.get("/api/boards").json()["boards"] == []
    combined = client.post("/api/boards", json={"name": "Everything", "projects": ["alpha", "beta"]})
    assert combined.status_code == 201
    b = combined.json()
    assert b["projects"] == ["alpha", "beta"] and b["standalone"] is False

    solo = client.post("/api/boards", json={"name": "Side Quests!"}).json()
    assert solo["standalone"] is True and solo["projects"] == ["side-quests"]

    # Idempotent create; rename; delete leaves tasks alone.
    again = client.post("/api/boards", json={"name": "Everything", "projects": ["alpha", "beta"]}).json()
    assert again["id"] == b["id"]
    assert client.post(f"/api/boards/{b['id']}/update", json={"name": "All"}).json()["name"] == "All"
    assert client.post(f"/api/boards/{solo['id']}/update", json={"projects": ["alpha"]}).json()["projects"] == ["side-quests"]
    _task(client, project="side-quests", title="on the side")
    assert client.post(f"/api/boards/{solo['id']}/delete").json() == {"deleted": solo["id"]}
    assert len(client.get("/api/boards").json()["boards"]) == 1
    assert client.get("/api/tasks?project=side-quests").json()["total"] == 1
    assert client.post("/api/boards/bd_missing/delete").status_code == 404
    assert client.post("/api/boards", json={"name": "   "}).status_code == 422


def test_two_tasks_in_the_same_minute_both_survive(client: TestClient) -> None:
    """The reported bug: rapid task entry — same minute, same board, same
    actor — must create two tasks, not fold the second into the first."""
    base = {
        "created_date": "2608-20", "created_time": "01:32", "project": "alpha",
        "agent_id": "operator", "status": "todo",
    }
    a = client.post("/api/tasks", json={**base, "title": "Wi-Fi info"})
    b = client.post("/api/tasks", json={**base, "title": "Communication map"})
    assert a.status_code == 201 and b.status_code == 201
    assert a.json()["metadata"]["id"] != b.json()["metadata"]["id"]
    titles = {t["title"] for t in client.get("/api/tasks?project=alpha").json()["tasks"]}
    assert titles == {"Wi-Fi info", "Communication map"}
    # Idempotency still holds for a genuine double-post.
    again = client.post("/api/tasks", json={**base, "title": "Wi-Fi info"})
    assert again.json()["metadata"]["id"] == a.json()["metadata"]["id"]
    # And their detail docs never share a path (the md_ref carries the id).
    assert a.json()["metadata"]["md_ref"] != b.json()["metadata"]["md_ref"]


def test_a_stack_promotes_its_next_member(client) -> None:
    """A stack is an ordered queue in one column: when the head leaves, the
    next member is stamped as the new head — whatever moved it."""
    def mk(title: str, pos: str, stack: str) -> str:
        return client.post("/api/tasks", json={
            "created_date": "2608-23", "created_time": "10:00", "project": "alpha",
            "agent_id": "operator", "title": title, "status": "todo",
            "position": pos, "stack_id": stack,
        }).json()["metadata"]["id"]
    head = mk("step one", "1", "st_demo")
    second = mk("step two", "2", "st_demo")
    third = mk("step three", "3", "st_demo")

    rows = {t["id"]: t for t in client.get("/api/tasks?project=alpha").json()["tasks"]}
    assert not rows[second]["stack_head_at"], "nobody is promoted while the head is in place"

    client.post(f"/api/tasks/{head}/update", json={"status": "doing", "actor": "operator"})
    rows = {t["id"]: t for t in client.get("/api/tasks?project=alpha").json()["tasks"]}
    assert rows[second]["stack_head_at"], "the next member takes the head's place"
    assert not rows[third]["stack_head_at"], "only the next one, not the whole tail"
    ev = client.get(f"/api/tasks/{second}/events").json()["events"]
    assert any(e["actor"] == "stack" and e["field"] == "stack_head_at" for e in ev)
