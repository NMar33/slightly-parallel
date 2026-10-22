"""Task ↔ chat: mentions derived from captured turns, and the task timeline."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    r = tmp_path / "data"
    (r / "projects" / "alpha").mkdir(parents=True)
    return r


@pytest.fixture()
def client(root: Path):
    app = create_app(data_root=root, watch=False)
    with TestClient(app) as c:
        yield c


def _chat(root: Path, agent: str, turns: list[tuple[str, str, str]]) -> None:
    d = root / "projects" / "alpha" / "chats" / agent
    d.mkdir(parents=True, exist_ok=True)
    body = f"# Chat log — {agent}\n\n---\n"
    for i, (at, user, reply) in enumerate(turns, start=1):
        body += f"\n## Turn {i} · {at}\n**User**: {user}\n**Agent**: {reply}\n"
    (d / "chat.md").write_text(body, encoding="utf-8")
    (d / "meta.json").write_text(json.dumps({"agent_id": agent}), encoding="utf-8")


def test_mentions_are_derived_from_turns(client: TestClient, root: Path) -> None:
    now = datetime.now()
    t0 = (now - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S")
    t1 = (now - timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%S")
    created = client.post("/api/tasks", json={
        "created_date": "2608-19", "created_time": "01:00", "project": "alpha",
        "agent_id": "operator", "title": "Wire it", "status": "todo",
    }).json()["metadata"]
    tid = created["id"]
    _chat(root, "cc-abc12345", [
        (t0, f"please do {tid} · Wire it\nContext here", "on it"),
        (t1, "status?", f"{tid} done, tests green"),
    ])
    client.app.state.store.rebuild()

    m = client.get(f"/api/tasks/{tid}/mentions").json()
    assert m["total"] == 2
    assert [x["role"] for x in m["mentions"]] == ["agent", "user"]  # newest first
    assert m["mentions"][1]["turn"] == 1 and m["mentions"][1]["session_id"].startswith("ses_")
    assert "Wire it" in m["mentions"][1]["excerpt"]

    summary = client.get("/api/tasks/mentions/summary?project=alpha").json()["mentions"]
    assert summary[tid]["n"] == 2 and summary[tid]["last_role"] == "agent"


def test_a_mention_carries_the_agent_behind_it(client: TestClient, root: Path) -> None:
    """The row names the agent and says how to pick the chat back up."""
    now = datetime.now()
    t0 = (now - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S")
    tid = client.post("/api/tasks", json={
        "created_date": "2609-18", "created_time": "01:00", "project": "alpha",
        "agent_id": "operator", "title": "Name me", "status": "todo",
    }).json()["metadata"]["id"]
    _chat(root, "cc-c0b0e20f", [(t0, f"take {tid} · Name me", "done")])
    (root / "projects" / "alpha" / "chats" / "cc-c0b0e20f" / "meta.json").write_text(
        json.dumps({
            "agent_id": "cc-c0b0e20f", "agent_name": "Calendar work",
            "tool": "claude-code", "cwd": "/w/app",
            "session_ref": "c0b0e20f-1111-2222-3333-444455556666",
        }), encoding="utf-8",
    )
    # A second agent captured before the hook recorded where it ran: named,
    # but with nothing to build a resume command from.
    _chat(root, "cc-0ld00000", [(t0, f"also {tid} · Name me", "ok")])
    client.app.state.store.rebuild()

    rows = client.get(f"/api/tasks/{tid}/mentions").json()["mentions"]
    named = next(r for r in rows if r["agent_id"] == "cc-c0b0e20f")["agent"]
    assert named["agent_name"] == "Calendar work"
    assert named["tool"] == "claude-code" and named["cwd"] == "/w/app"
    assert named["session_ref"] == "c0b0e20f-1111-2222-3333-444455556666"

    older = next(r for r in rows if r["agent_id"] == "cc-0ld00000")["agent"]
    assert older["agent_name"] == "cc-0ld00000"   # no rename: the id stands in
    assert older["tool"] == "" and older["session_ref"] == ""

    summary = client.get("/api/tasks/mentions/summary?project=alpha").json()["mentions"]
    assert summary[tid]["agent"]["agent_id"] == summary[tid]["last_agent"]


def test_timeline_merges_creation_events_and_mentions(client: TestClient, root: Path) -> None:
    now = datetime.now()
    tid = client.post("/api/tasks", json={
        "created_date": now.strftime("%y%m-%d"), "created_time": now.strftime("%H:%M"),
        "project": "alpha", "agent_id": "operator", "title": "Timeline me", "status": "todo",
    }).json()["metadata"]["id"]
    client.post(f"/api/tasks/{tid}/update", json={"status": "doing", "actor": "operator"})
    client.post(f"/api/tasks/{tid}/update", json={"priority": "high", "actor": "operator"})
    _chat(root, "cc-def67890", [
        (now.strftime("%Y-%m-%dT%H:%M:%S"), f"take {tid}", "ok"),
    ])
    client.app.state.store.rebuild()

    tl = client.get("/api/tasks/timeline?project=alpha&window=day&limit=10").json()
    assert [t["id"] for t in tl["tasks"]] == [tid]
    kinds = [e["kind"] for e in tl["tasks"][0]["events"]]
    assert kinds.count("created") == 1
    assert "status" in kinds and "edit" in kinds and "mention" in kinds
    status_ev = next(e for e in tl["tasks"][0]["events"] if e["kind"] == "status")
    assert (status_ev["from"], status_ev["to"]) == ("todo", "doing")
    # A mention on the timeline carries its agent, so the dot names it.
    mention_ev = next(e for e in tl["tasks"][0]["events"] if e["kind"] == "mention")
    assert mention_ev["agent"]["agent_id"] == "cc-def67890"

    # An old task with nothing in the window is left out; limit=0 means all.
    client.post("/api/tasks", json={
        "created_date": "2501-01", "created_time": "09:00", "project": "alpha",
        "agent_id": "operator", "title": "ancient", "status": "done",
    })
    client.app.state.store.rebuild()
    assert len(client.get("/api/tasks/timeline?project=alpha&window=week&limit=0").json()["tasks"]) == 1


def test_mentions_by_agent_carry_titles(client: TestClient, root: Path) -> None:
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    tid = client.post("/api/tasks", json={
        "created_date": "2608-19", "created_time": "01:00", "project": "alpha",
        "agent_id": "operator", "title": "Named task", "status": "todo",
    }).json()["metadata"]["id"]
    _chat(root, "cc-lane0001", [(now, f"go {tid}", f"{tid} shipped")])
    client.app.state.store.rebuild()
    by = client.get("/api/tasks/mentions/by-agent?project=alpha").json()["agents"]
    assert [m["role"] for m in by["cc-lane0001"]] == ["user", "agent"]
    assert by["cc-lane0001"][0]["title"] == "Named task"


def test_status_since_prefers_the_last_move(client: TestClient) -> None:
    tid = client.post("/api/tasks", json={
        "created_date": "2608-18", "created_time": "09:00", "project": "alpha",
        "agent_id": "operator", "title": "Ager", "status": "todo",
    }).json()["metadata"]["id"]
    fresh = client.post("/api/tasks", json={
        "created_date": "2608-20", "created_time": "01:00", "project": "alpha",
        "agent_id": "operator", "title": "Never moved", "status": "todo",
    }).json()["metadata"]["id"]
    client.post(f"/api/tasks/{tid}/update", json={"status": "doing", "actor": "operator"})
    since = client.get("/api/tasks/status-since?project=alpha").json()["since"]
    assert since[fresh] == "2026-08-20T01:00:00"      # creation fallback
    assert since[tid].startswith("20") and since[tid] > "2026-08-18T09:00:00"  # the move
