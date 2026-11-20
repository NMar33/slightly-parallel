"""Two Codex chats under one app-server daemon each write and read as
themselves (tk_49aa81aa).

Codex 0.170 runs every chat's hooks and MCP servers inside one shared
daemon. The processes above the hook and the MCP server are the daemon's,
the same for every Codex chat, so /api/whoami's process match gave each MCP
call the newest Codex chat: messages arrived "from" the wrong chat and
``messages {}`` read another chat's inbox. Each tools/call names its thread
in ``_meta`` (recorded from a real 0.170 call, ids anonymised): that thread
is the caller. A call that names none is refused, never guessed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend import mcp, msgledger
from backend import server as _server
from backend.server import create_app

HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"
BACKEND = Path(__file__).resolve().parents[1]

THREAD_A = "01a1f331-a115-7b43-92cf-5a99aaaa0001"
THREAD_B = "01a1f383-22b6-7902-886c-4e73bbbb0002"
CODEX_A = "codex-aaaa0001"
CODEX_B = "codex-bbbb0002"
CLAUDE = "cc-cccc0003"
SENDER = "cc-dddd0004"


def _meta(thread: str) -> dict[str, Any]:
    """A tools/call's _meta as Codex 0.170 sends it (recorded, anonymised)."""
    return {
        "callId": "exec-00000000-0000-0000-0000-000000000000",
        "x-codex-turn-metadata": {
            "session_id": thread, "thread_id": thread, "reasoning_effort": "low",
            "turn_id": "01a1f3dc-c30c-7813-af2e-686ab08f2267", "model": "gpt-x",
            "thread_source": "user", "turn_trigger": "exec", "sandbox": "seccomp",
            "sandbox_mode": "read-only", "workspaces": {"/work": {"has_changes": False}},
            "turn_started_at_unix_ms": 1795092693776, "codex_version": "0.170.0"},
        "threadId": thread, "sessionId": thread, "windowId": f"{thread}:0",
        "itemId": "ctc_0", "progressToken": 1,
    }


# The shared daemon: one process runs the hook of each Codex chat (each
# writes its breadcrumb with the processes above it), then starts an MCP
# server, which prints the processes above it — the same daemon for both.
DAEMON = r'''
import subprocess, sys
root, cwd, hooks, backend = sys.argv[1:5]
for thread in sys.argv[5:]:
    hook = (
        "import sys, importlib.util; sys.path.insert(0, %r); "
        "s = importlib.util.spec_from_file_location('h', %r); m = importlib.util.module_from_spec(s); "
        "s.loader.exec_module(m); m.write_breadcrumb(%r, 'alpha', %r, %r, tool='codex')"
    ) % (hooks, hooks + "/claude-code-capture.py", root, thread, cwd)
    subprocess.run([sys.executable, "-c", hook], check=True, cwd=cwd)
mcp = "import sys; sys.path.insert(0, %r); from backend.hookshared import ancestors; print(','.join(map(str, ancestors())))" % backend
print(subprocess.run([sys.executable, "-c", mcp], check=True, cwd=cwd, capture_output=True, text=True).stdout.strip())
'''

# A Claude Code chat: its own tool process runs its hook and its MCP server.
TOOL = DAEMON.replace("tool='codex'", "tool='claude-code'")


def _run(script: str, tmp: Path, root: Path, cwd: Path, *sessions: str) -> str:
    path = tmp / ("daemon.py" if script is DAEMON else "tool.py")
    path.write_text(script, encoding="utf-8")
    out = subprocess.run([sys.executable, str(path), str(root), str(cwd), str(HOOKS), str(BACKEND), *sessions],
                         check=True, capture_output=True, text=True, timeout=60)
    return out.stdout.strip().splitlines()[-1]


def _chat(root: Path, agent: str, tool: str, session_ref: str = "") -> None:
    d = root / "projects" / "alpha" / "chats" / agent
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps({
        "agent_id": agent, "project": "alpha", "tool": tool, "session_ref": session_ref,
        "last_active": "2026-11-19T10:00:00"}), encoding="utf-8")


class _Api(mcp.Api):
    def __init__(self, c: TestClient) -> None:
        super().__init__("http://testserver")
        self.c = c

    def _call(self, method: str, path: str, body: dict | None = None) -> Any:
        r = self.c.request(method, path, json=body, headers={mcp.VIA_HEADER: mcp.VIA_VALUE})
        if r.status_code >= 400:
            raise mcp.ApiError(f"{r.status_code}: {r.json().get('detail', '')}")
        return r.json()


@pytest.fixture()
def world(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(_server.AgentsViaMcp, "_enforced", lambda self: True)
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    work = tmp_path / "repo"
    work.mkdir()
    _chat(root, CODEX_A, "codex", THREAD_A)
    _chat(root, CODEX_B, "codex", THREAD_B)
    _chat(root, CLAUDE, "claude-code", "cccc0003-0000-0000-0000-000000000000")
    _chat(root, SENDER, "claude-code", "dddd0004-0000-0000-0000-000000000000")
    daemon = _run(DAEMON, tmp_path, root, work, THREAD_A, THREAD_B)
    claude = _run(TOOL, tmp_path, root, work, "cccc0003-0000-0000-0000-000000000000")
    with TestClient(create_app(data_root=root, watch=False, run_monitor=False)) as c:
        yield c, root, work, daemon, claude


def _server_for(c: TestClient, work: Path, client: str) -> mcp.Translator:
    tr = mcp.Translator(_Api(c), cwd=str(work))
    mcp.handle(tr, {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "clientInfo": {"name": client, "title": "x", "version": "0.170.0"}}})
    return tr


def _call(tr: mcp.Translator, name: str, args: dict, thread: str | None) -> tuple[bool, Any]:
    params: dict[str, Any] = {"name": name, "arguments": args}
    if thread:
        params["_meta"] = _meta(thread)
    got = mcp.handle(tr, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params})
    assert got is not None
    text = got["result"]["content"][0]["text"]
    return got["result"]["isError"], (text if got["result"]["isError"] else json.loads(text))


def test_the_shared_daemon_names_no_codex_chat_by_its_processes(world) -> None:
    c, _root, work, daemon, _claude = world
    # Both Codex chats share the daemon with this MCP server: neither is it.
    r = c.get("/api/whoami", params={"cwd": str(work), "pids": daemon})
    assert r.status_code == 409 and "cannot tell which Codex chat" in r.json()["detail"], r.text
    # The thread names the chat.
    for thread, want in ((THREAD_A, CODEX_A), (THREAD_B, CODEX_B)):
        got = c.get("/api/whoami", params={"cwd": str(work), "pids": daemon, "thread": thread}).json()
        assert (got["agent_id"], got["identity_source"]) == (want, "thread"), got
    # A thread no captured chat has is refused, not guessed.
    r = c.get("/api/whoami", params={"cwd": str(work), "thread": "01a1f3dc-0000-0000-0000-00000000ffff"})
    assert r.status_code == 404 and "cannot tell which Codex chat" in r.json()["detail"]


def test_each_codex_chat_writes_and_reads_as_itself(world, monkeypatch) -> None:
    c, root, work, daemon, _claude = world
    # The MCP server runs under the daemon: its processes are the daemon's.
    monkeypatch.setattr(mcp, "ancestors", lambda: [int(p) for p in daemon.split(",")])
    tr = _server_for(c, work, "codex-mcp-client")
    err, sent_a = _call(tr, "message", {"to": SENDER, "text": "from a"}, THREAD_A)
    assert not err and sent_a["message"]["from_agent"] == CODEX_A, sent_a
    err, sent_b = _call(tr, "message", {"to": SENDER, "text": "from b"}, THREAD_B)
    assert not err and sent_b["message"]["from_agent"] == CODEX_B, sent_b
    # A message to each: each inbox is read by its own chat only.
    for to, text in ((CODEX_A, "for a"), (CODEX_B, "for b")):
        r = c.post("/api/messages", json={"to": to, "text": text, "agent_id": SENDER},
                   headers={mcp.VIA_HEADER: mcp.VIA_VALUE})
        assert r.status_code == 201, r.text
    err, inbox_b = _call(tr, "messages", {}, THREAD_B)
    assert not err and [m["text"] for m in inbox_b["unread"]] == ["for b"], inbox_b
    err, inbox_a = _call(tr, "messages", {}, THREAD_A)
    assert not err and [m["text"] for m in inbox_a["unread"]] == ["for a"], inbox_a
    # No thread in the call: refused, nothing written or read.
    before = len(msgledger.read_rows(root))
    err, text = _call(tr, "message", {"to": SENDER, "text": "who am i"}, None)
    assert err and text == mcp.CODEX_UNKNOWN
    err, text = _call(tr, "messages", {}, None)
    assert err and text == mcp.CODEX_UNKNOWN
    assert len(msgledger.read_rows(root)) == before
    # The thread of one call does not carry over to the next request.
    _call(tr, "messages", {}, THREAD_A)
    assert tr.thread == THREAD_A
    mcp.handle(tr, {"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}})
    assert tr.thread == ""


def test_a_claude_code_chat_is_still_found_by_its_own_process(world, monkeypatch) -> None:
    c, _root, work, _daemon, claude = world
    monkeypatch.setattr(mcp, "ancestors", lambda: [int(p) for p in claude.split(",")])
    tr = _server_for(c, work, "claude-code")
    err, sent = _call(tr, "message", {"to": SENDER, "text": "from claude"}, None)
    assert not err and sent["message"]["from_agent"] == CLAUDE, sent
    got = c.get("/api/whoami", params={"cwd": str(work), "pids": claude}).json()
    assert (got["agent_id"], got["identity_source"]) == (CLAUDE, "process"), got


def test_the_thread_is_read_from_any_of_the_three_places_codex_puts_it() -> None:
    assert mcp.codex_thread({"_meta": _meta(THREAD_A)}) == THREAD_A
    assert mcp.codex_thread({"_meta": {"x-codex-turn-metadata": {"thread_id": THREAD_B}}}) == THREAD_B
    assert mcp.codex_thread({"_meta": {"sessionId": THREAD_A}}) == THREAD_A
    for params in ({}, {"_meta": "x"}, {"_meta": {"threadId": "../../etc"}}, {"_meta": {"threadId": 5}}):
        assert mcp.codex_thread(params) == ""
