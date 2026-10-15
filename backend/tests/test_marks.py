"""Important marks: #important in a chat, the ★ by hand, and the ☆ that wins."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app
from backend.sessions import IMPORTANT_TAG_RE

AGENT = "alpha-lead-2609-01"


def _chat(root: Path, turns: list[str]) -> None:
    d = root / "projects" / "alpha" / "chats" / AGENT
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps({
        "agent_id": AGENT, "agent_name": "lead", "project": "alpha",
        "created_date": "2609-01", "last_active": "2026-09-01T10:30:00",
    }), encoding="utf-8")
    body = [f"# Chat log — {AGENT}\n"]
    for i, user in enumerate(turns, start=1):
        body.append(f"\n## Turn {i} · 2026-09-01T10:{i:02d}:00\n**User**: {user}\n**Agent**: ok\n")
    (d / "chat.md").write_text("".join(body), encoding="utf-8")


@pytest.fixture()
def env(tmp_path: Path):
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    with TestClient(create_app(data_root=root, watch=False)) as c:
        ids = []
        for i, title in enumerate(("First", "Second")):
            r = c.post("/api/tasks", json={
                "created_date": "2609-01", "created_time": f"09:0{i}", "project": "alpha",
                "agent_id": "operator", "title": title, "status": "todo",
            })
            ids.append(r.json()["metadata"]["id"])
        yield c, root, ids


def _marks(c: TestClient) -> set[tuple[str, str]]:
    return {(m["kind"], m["target"]) for m in c.get("/api/marks?project=alpha").json()["marks"]}


@pytest.mark.parametrize("text,kind", [
    ("this matters #important", None), ("#important-agent", "agent"),
    ("#IMPORTANT-task now", "task"), ("#important-message", "message"),
])
def test_the_tag(text, kind):
    m = IMPORTANT_TAG_RE.search(text)
    assert m is not None and ((m.group(1) or '').lower() or None) == kind


@pytest.mark.parametrize("text", ["#importantly", "##important", "#important-other", "x#important"])
def test_the_tag_does_not_fire(text):
    assert IMPORTANT_TAG_RE.search(text) is None


def test_important_marks_the_message_the_agent_and_the_named_task(env) -> None:
    c, root, (t1, t2) = env
    _chat(root, [f"look at {t1}", f"this one {t2} #important"])
    c.app.state.store.rebuild()
    assert _marks(c) == {("message", f"{AGENT}#2"), ("agent", AGENT), ("task", t2)}
    got = {m["kind"]: m for m in c.get("/api/marks?project=alpha").json()["marks"]}
    assert got["task"]["task"]["title"] == "Second" and got["message"]["excerpt"] == f"this one {t2}"


def test_important_task_without_a_name_takes_the_last_task_of_the_chat(env) -> None:
    c, root, (t1, t2) = env
    _chat(root, [f"start {t1}", f"then {t2}", "that one #important-task"])
    c.app.state.store.rebuild()
    assert _marks(c) == {("task", t2)}


def test_plain_important_marks_no_task_it_does_not_name(env) -> None:
    c, root, (t1, _t2) = env
    _chat(root, [f"start {t1}", "#important"])
    c.app.state.store.rebuild()
    assert ("task", t1) not in _marks(c)


def test_the_star_by_hand_and_the_unmark_that_sticks(env) -> None:
    c, root, (t1, _t2) = env
    _chat(root, ["#important-agent"])
    c.app.state.store.rebuild()
    assert _marks(c) == {("agent", AGENT)}
    assert c.post("/api/marks/unmark", json={"kind": "agent", "target": AGENT}).json()["removed"] == 1
    assert _marks(c) == set(), "the old tag is not adopted again"
    r = c.post("/api/marks", json={"kind": "agent", "target": "other", "project": "alpha"})
    assert r.status_code == 201
    again = c.post("/api/marks", json={"kind": "agent", "target": "other", "project": "alpha"})
    assert again.json()["mark"]["id"] == r.json()["mark"]["id"]
    assert _marks(c) == {("agent", "other")}


def test_a_task_star_is_the_boards_remember(env) -> None:
    c, root, (t1, t2) = env
    _chat(root, [f"this {t1} #important-task"])
    c.app.state.store.rebuild()
    assert _marks(c) == {("task", t1)}
    assert c.get(f"/api/tasks/{t1}").json()["metadata"]["remember"] == "yes"
    # The board's star by hand shows as a mark; the ☆ takes it off, for good.
    c.post(f"/api/tasks/{t2}/update", json={"remember": "yes", "actor": "operator"})
    assert _marks(c) == {("task", t1), ("task", t2)}
    c.post("/api/marks/unmark", json={"kind": "task", "target": t1})
    assert not c.get(f"/api/tasks/{t1}").json()["metadata"]["remember"]
    assert _marks(c) == {("task", t2)}
    assert c.post("/api/marks", json={"kind": "task", "target": "tk_gone"}).status_code == 404
    assert c.post("/api/marks", json={"kind": "task", "target": t1, "actor": "cc-x"}).status_code == 422
    # The chat's agent rides along as `chat_agent`; the operator is still the writer.
    assert c.post("/api/marks", json={"kind": "agent", "target": "cc-y", "chat_agent": "cc-y"}).status_code == 201
    assert c.post("/api/marks", json={"kind": "file", "target": "x"}).status_code == 422


def test_a_star_moves_the_chats_etag(env) -> None:
    c, root, _ = env
    _chat(root, ["hello"])
    c.app.state.store.rebuild()
    first = c.get("/api/sessions?project=alpha")
    etag = first.headers.get("etag")
    c.post("/api/marks", json={"kind": "message", "target": f"{AGENT}#1", "project": "alpha",
                               "agent_id": AGENT, "session_id": first.json()["sessions"][0]["id"], "turn": 1})
    again = c.get("/api/sessions?project=alpha", headers={"If-None-Match": etag})
    assert again.status_code == 200 and again.headers.get("etag") != etag


def test_the_pages_own_star_passes_the_agents_gate(tmp_path: Path, monkeypatch) -> None:
    """With the MCP gate on (as in the product), the page's star must get
    through: it names the chat's agent `chat_agent`, never `agent_id`."""
    from backend import server as _server
    monkeypatch.setattr(_server.AgentsViaMcp, "_enforced", lambda self: True)
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    with TestClient(create_app(data_root=root, watch=False)) as c:
        ok = c.post("/api/marks", json={"kind": "message", "target": f"{AGENT}#1", "project": "alpha",
                                        "chat_agent": AGENT, "turn": 1, "actor": "operator"})
        assert ok.status_code == 201, ok.text
        assert ok.json()["mark"]["agent_id"] == AGENT
        side = c.post("/api/marks", json={"kind": "agent", "target": "x", "agent_id": "cc-sneaky", "actor": "operator"})
        assert side.status_code == 422
