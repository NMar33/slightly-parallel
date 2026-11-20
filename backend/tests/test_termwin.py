"""The terminal window's tab strip reads (routers/termwin.py, tk_a9306fb1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import termlib
from backend.routers import termwin
from backend.server import create_app

CHAT = """# Chat log — cc-one
*Started 2026-08-20T09:00:00. Verbatim captured turns.*

---

## Turn 1 · 2026-08-20T09:00:00
**User**: please do tk_aaaa1111 first
**Agent**: on it

## Turn 2 · 2026-08-20T09:20:00
**User**: and then tk_bbbb2222
**Agent**: tk_aaaa1111 is done, starting tk_bbbb2222
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _agent(root: Path, aid: str, chat: str = "", **meta: object) -> None:
    folder = root / "projects" / "alpha" / "chats" / aid
    _write(folder / "meta.json", json.dumps({
        "agent_id": aid, "agent_name": aid, "project": "alpha",
        "created_date": "2608-20", "last_active": "2026-08-21T12:00:00",
        "message_count": 3, "tool": "claude-code", "cwd": "/work/alpha",
        "session_ref": f"ref-{aid}", **meta,
    }))
    _write(folder / "chat.md", chat or f"# Chat log — {aid}\n\n---\n")


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture()
def client(root: Path):
    _agent(root, "cc-one", chat=CHAT, agent_name="hbr-2611-18", terminal="t1")
    _agent(root, "cc-two", parent_agent_id="cc-one")
    _agent(root, "cc-help", parent_agent_id="cc-one", helper=True)
    _agent(root, "cx-old", tool="codex", agent_name="cx-old", chat_title="Old codex chat", last_active="2026-08-22T08:00:00")
    _agent(root, "oc-x", tool="opencode")
    _agent(root, "cc-noref", session_ref="")
    # Two terminals: t1 holds cc-one (the hook's link), t2 is a plain shell.
    _write(termlib.registry_path(root), json.dumps({"sessions": [
        {"id": "t1", "kind": "shell", "label": "claude", "project": "alpha", "backend": "plain", "created": "2026-08-21T10:00:00"},
        {"id": "t2", "kind": "shell", "label": "alpha", "project": "alpha", "backend": "plain", "created": "2026-08-21T10:01:00"},
    ]}))
    app = create_app(data_root=root, watch=False)
    with TestClient(app) as c:
        yield c


def _task(client: TestClient, title: str, status: str) -> str:
    r = client.post("/api/tasks", json={
        "created_date": "2608-19", "created_time": "10:00", "project": "alpha",
        "agent_id": "operator", "title": title, "status": status,
    })
    assert r.status_code == 201
    return r.json()["metadata"]["id"]


def test_tabs_carry_the_chat_facts(client: TestClient, root: Path) -> None:
    a = _task(client, "A", "done")
    b = _task(client, "B", "doing")
    (root / "projects" / "alpha" / "chats" / "cc-one" / "chat.md").write_text(
        CHAT.replace("tk_aaaa1111", a).replace("tk_bbbb2222", b), encoding="utf-8")
    # A branch link from cc-one to cx-old, and cc-two started from it: two branches; the helper does not count.
    assert client.post("/api/agents/links", json={"from": "cc-one", "to": "cx-old", "kind": "branch"}).status_code == 201
    # Claude Code's status line for cc-one's session: 72% of a 200k window.
    _write(root / ".usage" / "sessions" / "claude-code-ref-cc-one.json",
           json.dumps({"at": "2026-08-21T12:00:00", "context": {"used_pct": 72, "size": 200000}}))

    r = client.get("/api/terminal/tabs")
    assert r.status_code == 200, r.text
    tabs = r.json()["tabs"]
    assert set(tabs) == {"t1", "t2"}
    one = tabs["t1"]
    assert one["agent_id"] == "cc-one" and one["title"] == ""
    chat = one["chat"]
    assert chat["name"] == "hbr-2611-18" and chat["tool"] == "claude-code"
    assert (chat["tasks_done"], chat["tasks_all"]) == (1, 2)
    assert chat["branches"] == 2
    assert (chat["ctx_pct"], chat["ctx_size"]) == (72.0, 200000)
    # A shell with no chat behind it.
    assert tabs["t2"] == {"title": "", "agent_id": "", "chat": None}


def test_context_unknown_without_a_status_line(client: TestClient) -> None:
    r = client.get("/api/terminal/tabs")
    chat = r.json()["tabs"]["t1"]["chat"]
    assert chat["ctx_pct"] is None and chat["ctx_size"] is None
    assert (chat["tasks_done"], chat["tasks_all"]) == (0, 0)


def test_pane_titles_skip_the_computer_name(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import socket
    import subprocess
    host = socket.gethostname()
    out = f"mk-t1\thbr-2611-18\nmk-t2\t{host}\nmk-t3\t\nother\tnot ours\n"
    monkeypatch.setattr(termlib, "tmux_path", lambda: "/usr/bin/tmux")
    monkeypatch.setattr(termlib, "tmux_read", lambda *a, **k: subprocess.CompletedProcess(list(a), 0, out, ""))
    assert termwin.pane_titles(tmp_path) == {"t1": "hbr-2611-18"}


def test_resumable_leaves_out_held_helpers_and_unresumable(client: TestClient) -> None:
    r = client.get("/api/terminal/resumable", params={"project": "alpha"})
    assert r.status_code == 200, r.text
    ids = [c["agent_id"] for c in r.json()["chats"]]
    # cc-one is held by t1; cc-help is a helper; cc-noref has no session.
    assert "cc-one" not in ids and "cc-help" not in ids and "cc-noref" not in ids
    assert ids[0] == "cx-old"  # the newest first
    assert {"cc-two", "oc-x"} <= set(ids)
    first = r.json()["chats"][0]
    assert first["name"] == "Old codex chat" and first["tool"] == "codex"


def test_branch_command(client: TestClient) -> None:
    r = client.get("/api/terminal/branch/cc-one")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["command"] == "cd /work/alpha && claude -r ref-cc-one --fork-session"
    assert d["project"] == "alpha" and d["name"] == "hbr-2611-18"
    assert client.get("/api/terminal/branch/cx-old").json()["command"] == (
        f"cd /work/alpha && {termlib.codex_in_terminal()} fork ref-cx-old")
    assert client.get("/api/terminal/branch/oc-x").status_code == 422
    assert client.get("/api/terminal/branch/cc-noref").status_code == 422
    assert client.get("/api/terminal/branch/nobody").status_code == 404


def test_branch_command_quotes_and_refuses_odd_refs() -> None:
    assert termwin.branch_command("claude-code", "r1", "/a b", family="bash") == "cd '/a b' && claude -r r1 --fork-session"
    assert termwin.branch_command("claude-code", "r1; rm", "/a", family="bash") == ""
    assert termwin.branch_command("codex", "r1", "", family="bash") == f"{termlib.codex_in_terminal()} fork r1"


def test_agents_installed(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.routers import setup
    monkeypatch.setattr(setup, "tools_installed", lambda: {"claude": True, "codex": False, "opencode": True, "cursor": True})
    assert client.get("/api/terminal/agents").json() == {"agents": {"claude": True, "codex": False, "opencode": True}}


def test_foreign_origin_is_refused(client: TestClient) -> None:
    r = client.get("/api/terminal/tabs", headers={"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
