"""Links between tasks — blocks / relates / parent — as an edge ledger."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app


@pytest.fixture()
def client(tmp_path: Path):
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    (root / "projects" / "beta").mkdir(parents=True)
    app = create_app(data_root=root, watch=False)
    with TestClient(app) as c:
        yield c


def _task(client: TestClient, title: str, project: str = "alpha", t: str = "10:00") -> str:
    r = client.post("/api/tasks", json={
        "created_date": "2608-19", "created_time": t, "project": project,
        "agent_id": "operator", "title": title, "status": "todo",
    })
    assert r.status_code == 201
    return r.json()["metadata"]["id"]


def test_link_both_directions_resolved_and_idempotent(client: TestClient) -> None:
    a = _task(client, "A blocker")
    b = _task(client, "B blocked", t="10:01")
    r = client.post(f"/api/tasks/{a}/link", json={"to": b, "kind": "blocks", "actor": "operator"})
    assert r.status_code == 201 and r.json()["created"] is True
    again = client.post(f"/api/tasks/{a}/link", json={"to": b, "kind": "blocks"})
    assert again.json()["created"] is False

    fromb = client.get(f"/api/tasks/{b}/links").json()
    assert fromb["total"] == 1
    l = fromb["links"][0]
    assert (l["from"]["title"], l["to"]["title"], l["kind"]) == ("A blocker", "B blocked", "blocks")

    # Both task timelines got a link event.
    ev_a = client.get(f"/api/tasks/{a}/events").json()["events"]
    ev_b = client.get(f"/api/tasks/{b}/events").json()["events"]
    assert any(e["field"] == "link" and e["new_value"] == f"blocks → {b}" for e in ev_a)
    assert any(e["field"] == "link" and e["new_value"] == f"blocks ← {a}" for e in ev_b)


def test_relates_is_stored_once_and_unlink_works(client: TestClient) -> None:
    a = _task(client, "A")
    b = _task(client, "B", t="10:02")
    r1 = client.post(f"/api/tasks/{b}/link", json={"to": a, "kind": "relates"}).json()
    r2 = client.post(f"/api/tasks/{a}/link", json={"to": b, "kind": "relates"}).json()
    assert r2["created"] is False and r1["link"]["id"] == r2["link"]["id"]
    assert client.get("/api/tasks/links?project=alpha").json()["total"] == 1
    assert client.post(f"/api/tasks/links/{r1['link']['id']}/delete", json={}).json() == {"deleted": r1["link"]["id"]}
    assert client.get("/api/tasks/links?project=alpha").json()["total"] == 0
    assert client.post("/api/tasks/links/lk_nope/delete", json={}).status_code == 404


def test_link_validation_and_cross_project(client: TestClient) -> None:
    a = _task(client, "A")
    z = _task(client, "Z", project="beta")
    assert client.post(f"/api/tasks/{a}/link", json={"to": a, "kind": "blocks"}).status_code == 422
    assert client.post(f"/api/tasks/{a}/link", json={"to": z, "kind": "eats"}).status_code == 422
    assert client.post(f"/api/tasks/{a}/link", json={"to": "tk_missing", "kind": "blocks"}).status_code == 422
    assert client.post(f"/api/tasks/{a}/link", json={"to": z, "kind": "parent"}).status_code == 201
    # Visible from both projects' boards.
    assert client.get("/api/tasks/links?project=alpha").json()["total"] == 1
    assert client.get("/api/tasks/links?project=beta").json()["links"][0]["to"]["title"] == "Z"


def test_blocks_and_parent_never_loop_and_a_task_has_one_parent(client: TestClient) -> None:
    a = _task(client, "A")
    b = _task(client, "B", t="10:01")
    c = _task(client, "C", t="10:02")
    link = lambda x, y, k: client.post(f"/api/tasks/{x}/link", json={"to": y, "kind": k})
    assert link(a, b, "blocks").status_code == 201
    assert link(b, c, "blocks").status_code == 201
    r = link(c, a, "blocks")
    assert r.status_code == 422 and "loop" in r.json()["detail"]
    assert link(b, a, "blocks").status_code == 422
    # Parent: a tree — one parent each, no loops.
    assert link(a, b, "parent").status_code == 201
    r = link(c, b, "parent")
    assert r.status_code == 422 and "already a sub-task of A" in r.json()["detail"]
    assert link(b, c, "parent").status_code == 201
    assert link(c, a, "parent").status_code == 422
    # The same pair may still relate; nothing above was written twice.
    assert link(c, a, "relates").status_code == 201
    assert client.get("/api/tasks/links?project=alpha").json()["total"] == 5


def test_a_link_changes_kind_and_turns_around_under_the_same_rules(client: TestClient) -> None:
    a = _task(client, "A")
    b = _task(client, "B", t="10:01")
    c = _task(client, "C", t="10:02")
    lid = client.post(f"/api/tasks/{a}/link", json={"to": b, "kind": "blocks"}).json()["link"]["id"]
    r = client.post(f"/api/tasks/links/{lid}/update", json={"reverse": True}).json()
    assert r["changed"] and (r["link"]["from_id"], r["link"]["to_id"], r["link"]["kind"]) == (b, a, "blocks")
    lid = r["link"]["id"]
    r = client.post(f"/api/tasks/links/{lid}/update", json={"kind": "parent"}).json()
    assert r["link"]["kind"] == "parent" and r["link"]["from_id"] == b
    lid = r["link"]["id"]
    assert client.post(f"/api/tasks/links/{lid}/update", json={"kind": "parent"}).json()["changed"] is False
    # c blocks b; turning a b→a blocks the other way is fine, but b blocks c would loop.
    client.post(f"/api/tasks/{c}/link", json={"to": b, "kind": "blocks"})
    rel = client.post(f"/api/tasks/{b}/link", json={"to": c, "kind": "relates"}).json()["link"]["id"]
    assert client.post(f"/api/tasks/links/{rel}/update", json={"kind": "blocks"}).status_code == 422
    assert client.post("/api/tasks/links/lk_nope/update", json={"kind": "blocks"}).status_code == 404
    assert client.get("/api/tasks/links?project=alpha").json()["total"] == 3
