"""Terminals: off until switched on, the token only for Slightly Parallel's pages, tmux sessions that outlive a socket."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import termlib
from backend.server import create_app

TMUX = termlib.tmux_path() is not None

# A terminal is a Unix pty; on Windows the server says so (tested below) and
# nothing here can run.
pytestmark = pytest.mark.skipif(os.name == "nt", reason="the terminal needs macOS or Linux")


@pytest.fixture()
def env(tmp_path: Path, monkeypatch):
    # A plain shell with no rc files: the operator's own bashrc may run
    # anything (on this machine it asks for a sudo password), and a test
    # must not depend on it.
    monkeypatch.setenv("SHELL", "/bin/sh")
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    work = tmp_path / "work"
    work.mkdir()
    (root / "integrations.csv").write_text(f"project,path\nalpha,{work}\n", encoding="utf-8")
    with TestClient(create_app(data_root=root, watch=False)) as c:
        yield c, root, work
    if TMUX:
        termlib.tmux(root, "kill-server")


def _on(c) -> None:
    assert c.post("/api/settings", json={"values": {"terminal.enabled": True}}).status_code == 200


def test_off_until_switched_on(env) -> None:
    c, _, _ = env
    st = c.get("/api/terminal/state").json()
    assert st["enabled"] is False and st["token"] == ""
    assert c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha"}).status_code == 409
    _on(c)
    st = c.get("/api/terminal/state").json()
    assert st["enabled"] and len(st["token"]) > 20 and st["projects"]["alpha"]


def test_the_token_is_only_for_slightly_parallels_pages(env) -> None:
    c, _, _ = env
    _on(c)
    assert c.get("/api/terminal/state", headers={"Origin": "https://evil.example"}).status_code == 403
    assert c.get("/api/terminal/state", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert c.get("/api/terminal/state", headers={"Origin": "http://127.0.0.1:5173"}).status_code == 200


def test_a_bad_token_or_origin_is_refused_on_the_socket(env) -> None:
    c, _, _ = env
    _on(c)
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as e:
        with c.websocket_connect("/ws/terminal/t1?token=nope") as ws:
            ws.receive_bytes()
    assert e.value.code == 4401


def test_resume_needs_a_resumable_chat_and_start_a_task(env) -> None:
    c, _, _ = env
    _on(c)
    assert c.post("/api/terminal/sessions", json={"kind": "resume", "agent": "nobody"}).status_code == 404
    assert c.post("/api/terminal/sessions", json={"kind": "start", "task_id": "tk_nope"}).status_code == 404
    assert c.post("/api/terminal/sessions", json={"kind": "shell", "actor": "cc-x"}).status_code == 422
    # An agent named in agent_id is an agent too, whatever `actor` says.
    assert c.post("/api/terminal/sessions", json={"kind": "shell", "actor": "operator",
                                                  "agent_id": "cc-x1234567"}).status_code == 422
    assert c.post("/api/terminal/sessions", json={"kind": "nope"}).status_code == 422


def test_commands() -> None:
    assert termlib.resume_command("claude-code", "abc-1") == "claude -r abc-1"
    assert termlib.resume_command("codex", "abc; rm -rf /") == ""
    cmd = termlib.start_command("claude", {"id": "tk_1", "title": "It's \"quoted\"", "description": "line1\nline2"})
    assert cmd.startswith("claude $'") and "\\n" in cmd and "\n" not in cmd and "\\'" in cmd


def test_state_of() -> None:
    now = 1000.0
    assert termlib.state_of("bash", now, now, None, False) == "shell"
    assert termlib.state_of("claude", now - 1, now, None, False) == "working"
    assert termlib.state_of("claude", now - 30, now, None, False) == "waiting"
    assert termlib.state_of("npm", now - 30, now, None, False) == "running"
    link = {"last_active": "2026-09-27T10:00:00", "last_stop": "2026-09-27T10:01:00"}
    assert termlib.state_of("node", now - 3, now, link, False) == "waiting"
    assert termlib.state_of("", 0, now, None, True) == "ended"


@pytest.mark.skipif(not TMUX, reason="tmux is not installed")
def test_a_tmux_terminal_runs_a_command_and_outlives_its_socket(env) -> None:
    c, root, work = env
    _on(c)
    tok = c.get("/api/terminal/state").json()["token"]
    got = c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha", "command": "echo mk-$((6*7))", "label": "calc"})
    assert got.status_code == 201
    sid = got.json()["session"]["id"]
    # Resolved: on macOS a temp folder lives under /private/var.
    assert got.json()["session"]["cwd"] == str(work.resolve())
    deadline = time.time() + 5
    seen = b""
    with c.websocket_connect(f"/ws/terminal/{sid}?token={tok}&cols=80&rows=24") as ws:
        while b"mk-42" not in seen and time.time() < deadline:
            seen += ws.receive_bytes()
    assert b"mk-42" in seen
    # The socket is gone; the terminal is not.
    assert termlib.alive_tmux(root, sid)
    items = c.get("/api/terminal/sessions?project=alpha").json()["sessions"]
    assert [(x["id"], x["label"], x["state"]) for x in items] == [(sid, "calc", "shell")]
    c.post(f"/api/terminal/sessions/{sid}/rename", json={"label": "maths"})
    assert c.get("/api/terminal/sessions").json()["sessions"][0]["label"] == "maths"
    c.post(f"/api/terminal/sessions/{sid}/close", json={})
    assert not termlib.alive_tmux(root, sid) and c.get("/api/terminal/sessions").json()["sessions"] == []


def test_the_capture_hook_ties_an_agent_to_its_terminal(env) -> None:
    c, root, _ = env
    d = root / "projects" / "alpha" / "chats" / "cc-aaaa1111"
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"agent_id": "cc-aaaa1111", "project": "alpha", "terminal": "tq1",
                                             "last_active": "2026-09-27T10:00:00"}), encoding="utf-8")
    termlib._link_cache = (0.0, {})
    assert termlib.agent_links(root)["tq1"]["agent_id"] == "cc-aaaa1111"


def test_the_page_opens_a_resume_through_the_agents_gate(tmp_path: Path, monkeypatch) -> None:
    from backend import server as _server
    monkeypatch.setattr(_server.AgentsViaMcp, "_enforced", lambda self: True)
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    with TestClient(create_app(data_root=root, watch=False)) as c:
        _on(c)
        # Not refused as an agent: it reaches the router, which knows no such agent.
        r = c.post("/api/terminal/sessions", json={"kind": "resume", "agent": "cc-aaaa1111", "actor": "operator"})
        assert r.status_code == 404, r.text


def test_a_replay_carries_no_questions_for_the_new_screen() -> None:
    from backend.routers.terminal import _QUERIES
    raw = b"hello\x1b[c there\x1b[>0c\x1b[6n \x1b[1;31mred\x1b[0m"
    assert _QUERIES.sub(b"", raw) == b"hello there \x1b[1;31mred\x1b[0m"


def test_a_folder_cannot_walk_out_of_the_allowlist(env) -> None:
    _, root, work = env
    (work / "src").mkdir()
    assert termlib.resolve_cwd(root, "", str(work / "src")) == (work / "src").resolve()
    # `..` inside an allowed folder, and a symlink out of it, both end at the data root.
    assert termlib.resolve_cwd(root, "", str(work / ".." / ".." / "..")) == root
    (work / "out").symlink_to("/")
    assert termlib.resolve_cwd(root, "", str(work / "out")) == root


def test_a_ref_that_looks_like_an_option_is_not_resumed() -> None:
    assert termlib.resume_command("claude-code", "--dangerously-skip-permissions") == ""
    assert "\x1b" not in termlib.start_command("claude", {"id": "tk_1", "title": "a\x1b[2Jb", "description": "x\x15y"})


def test_a_closed_terminal_stays_closed(env) -> None:
    c, _, _ = env
    _on(c)
    tok = c.get("/api/terminal/state").json()["token"]
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as e:
        with c.websocket_connect(f"/ws/terminal/tgone123?token={tok}") as ws:
            ws.receive_bytes()
    assert e.value.code == 4000
    assert c.get("/api/terminal/sessions").json()["sessions"] == []


@pytest.mark.skipif(not TMUX, reason="tmux is not installed")
def test_typed_text_keeps_its_semicolons_and_dashes(env) -> None:
    c, root, _ = env
    _on(c)
    sid = c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha"}).json()["session"]["id"]
    termlib.wait_for_prompt(root, sid)
    # POSIX printf, so the test holds in any $SHELL; the leading - and the ; are the point.
    assert c.post(f"/api/terminal/sessions/{sid}/type", json={"text": "printf -- mk; printf ok;", "enter": True}).status_code == 200
    deadline = time.time() + 4
    while time.time() < deadline and "mkok" not in termlib.tmux(root, "capture-pane", "-p", "-t", termlib.PREFIX + sid).stdout:
        time.sleep(0.1)
    assert "mkok" in termlib.tmux(root, "capture-pane", "-p", "-t", termlib.PREFIX + sid).stdout
    c.post(f"/api/terminal/sessions/{sid}/close", json={})
    assert c.post(f"/api/terminal/sessions/{sid}/type", json={"text": "x"}).status_code == 404


@pytest.mark.skipif(not TMUX, reason="tmux is not installed")
def test_lines_are_cut_out_by_their_absolute_ids(env) -> None:
    c, root, _ = env
    _on(c)
    sid = c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha"}).json()["session"]["id"]
    termlib.wait_for_prompt(root, sid)
    tok = c.get("/api/terminal/state").json()["token"]
    # Typed over the socket, as the page types: the Enter stamps the history.
    with c.websocket_connect(f"/ws/terminal/{sid}?token={tok}") as ws:
        ws.send_text(json.dumps({"type": "input", "data": "printf 'A%s\\n' 1 2 3 4 5\r"}))
        deadline = time.time() + 5
        while time.time() < deadline and "A5" not in termlib.capture(root, sid)["text"]:
            time.sleep(0.1)
    screen = termlib.capture(root, sid)
    assert screen["lines"] >= 5 and "A5" in screen["text"]

    # The row that shows A2, anchored to an absolute id, survives arithmetic.
    pos = c.get(f"/api/terminal/sessions/{sid}/pos").json()
    rows = screen["text"].split("\n")
    idx = next(i for i, l in enumerate(rows) if l.strip() == "A2")
    a = pos["history"] - pos["scroll"] + idx
    got = c.post(f"/api/terminal/sessions/{sid}/capture", json={"mode": "range", "from": a, "to": a + 2}).json()
    assert got["text"].split("\n") == ["A2", "A3", "A4"] and got["truncated"] is False

    # "last": everything since that Enter — the output, not the command line.
    last = c.post(f"/api/terminal/sessions/{sid}/capture", json={"mode": "last"}).json()
    assert last["mode"] == "last"
    assert last["text"].split("\n")[0] == "A1" and "printf" not in last["text"]

    bad = c.post(f"/api/terminal/sessions/{sid}/capture", json={"mode": "range", "from": "x"})
    assert bad.status_code == 422
    c.post(f"/api/terminal/sessions/{sid}/close", json={})


@pytest.mark.skipif(not TMUX, reason="tmux is not installed")
def test_a_pane_keeps_the_history_it_was_born_with_and_comes_back_to_the_bottom(env) -> None:
    c, root, _ = env
    _on(c)
    c.post("/api/settings", json={"values": {"terminal.scrollback": "10000"}})
    assert c.get("/api/terminal/state").json()["scrollback"] == 10000
    sid = c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha"}).json()["session"]["id"]
    termlib.wait_for_prompt(root, sid)
    limit = termlib.tmux(root, "display-message", "-p", "-t", termlib.PREFIX + sid, "#{history_limit}").stdout.strip()
    assert limit == "10000"

    # Output enough to scroll, climb into it, and come back.
    termlib.type_into(root, termlib.get(root, sid), "seq 1 200", enter=True)
    time.sleep(0.6)
    termlib.tmux(root, "copy-mode", "-t", termlib.PREFIX + sid)
    termlib.tmux(root, "send-keys", "-X", "-t", termlib.PREFIX + sid, "-N", "30", "scroll-up")
    assert termlib.pane_pos(root, sid)["scroll"] > 0
    back = c.post(f"/api/terminal/sessions/{sid}/bottom", json={}).json()
    assert back["scroll"] == 0
    c.post(f"/api/terminal/sessions/{sid}/close", json={})


@pytest.mark.skipif(not TMUX, reason="tmux is not installed")
def test_a_printed_path_opens_in_the_editor_where_the_shell_stands(env, monkeypatch) -> None:
    c, root, work = env
    _on(c)
    (work / "sub").mkdir()
    (work / "sub" / "app.ts").write_text("x\n", encoding="utf-8")
    launched: list[list[str]] = []
    real_which = termlib.shutil.which
    # VS Code "installed", nothing else; tmux stays the real one.
    monkeypatch.setattr(termlib.shutil, "which", lambda name: "/usr/bin/code" if name == "code"
                        else (real_which(name) if name == "tmux" else None))
    monkeypatch.setattr(termlib, "_spawn", launched.append)
    assert c.get("/api/terminal/state").json()["editor"] == "vscode"

    sid = c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha"}).json()["session"]["id"]
    termlib.wait_for_prompt(root, sid)
    # The shell moves; a relative path it prints now means sub/…
    termlib.type_into(root, termlib.get(root, sid), "cd sub", enter=True)
    time.sleep(0.6)
    got = c.post(f"/api/terminal/sessions/{sid}/open", json={"path": "app.ts", "line": 42, "col": 3})
    assert got.status_code == 200, got.text
    assert launched == [["/usr/bin/code", "-g", f"{(work / 'sub' / 'app.ts').resolve()}:42:3"]]

    assert c.post(f"/api/terminal/sessions/{sid}/open", json={"path": "nope.ts"}).status_code == 404
    c.post("/api/settings", json={"values": {"terminal.editor": "off"}})
    assert c.get("/api/terminal/state").json()["editor"] == ""
    assert c.post(f"/api/terminal/sessions/{sid}/open", json={"path": "app.ts"}).status_code == 409
    c.post(f"/api/terminal/sessions/{sid}/close", json={})


def test_the_snapshot_says_the_terminal_is_on_when_the_setting_says_so(env) -> None:
    # The project's Terminals tab reads the snapshot: it must agree with /state.
    c, _, _ = env
    assert c.get("/api/snapshot").json()["capabilities"]["terminal_enabled"] is False
    _on(c)
    assert c.get("/api/terminal/state").json()["enabled"] is True
    assert c.get("/api/snapshot").json()["capabilities"]["terminal_enabled"] is True


def test_a_server_on_any_port_trusts_its_own_pages(monkeypatch) -> None:
    from backend.config import Settings
    monkeypatch.delenv("SP_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("SCAN_CORS_ORIGINS", raising=False)
    monkeypatch.setenv("SP_PORT", "8129")
    got = Settings.from_env().cors_origins
    assert "http://127.0.0.1:8129" in got and "http://127.0.0.1:5173" in got


def test_idle_terminals_do_not_take_the_threads_the_server_works_on() -> None:
    """Each pump waits in a blocking read for its terminal's life. In the
    default executor, about eight idle terminals left asyncio.to_thread no
    thread to run on."""
    import asyncio
    from backend.routers.terminal import _MAX_SESSIONS, _PTY_READS, _read_pty

    # Every plain terminal and every tmux view can hold a read at once.
    assert _PTY_READS._max_workers >= _MAX_SESSIONS * 5

    async def main() -> None:
        pipes = [os.pipe() for _ in range(40)]
        try:
            reads = [asyncio.ensure_future(_read_pty(r)) for r, _ in pipes]
            await asyncio.sleep(0.1)
            assert await asyncio.wait_for(asyncio.to_thread(lambda: 7), 3) == 7
            for _, w in pipes:
                os.write(w, b"x")
            assert await asyncio.wait_for(asyncio.gather(*reads), 3) == [b"x"] * 40
        finally:
            for r, w in pipes:
                os.close(r)
                os.close(w)

    asyncio.run(main())


def test_a_terminal_gets_its_environment_without_the_server_changing_its_own() -> None:
    from backend.routers.terminal import PtySession

    s = PtySession("tq-env", ["/bin/sh", "-c", "echo got-$SP_TERMINAL-$HOME"], "/", 80, 24,
                   {"SP_TERMINAL": "tq-env"})
    seen = b""
    deadline = time.time() + 5
    while b"got-" not in seen or not seen.endswith(b"\n") and time.time() < deadline:
        try:
            chunk = os.read(s.fd, 1024)
        except OSError:
            break
        if not chunk:
            break
        seen += chunk
    os.waitpid(s.pid, 0)
    os.close(s.fd)
    assert f"got-tq-env-{os.environ.get('HOME', '')}".encode() in seen
    assert os.environ.get("SP_TERMINAL") != "tq-env"


def test_the_foreground_program_is_named_without_proc(monkeypatch) -> None:
    """macOS has no /proc: the program comes from ps there."""
    from backend.routers.terminal import PtySession

    s = PtySession("tq-fg", ["sleep", "5"], "/", 80, 24, {})
    try:
        deadline = time.time() + 3
        while termlib.foreground_of_fd(s.fd) != "sleep" and time.time() < deadline:
            time.sleep(0.05)
        monkeypatch.setattr(termlib, "_PROC", "/nonexistent-proc")
        assert termlib.foreground_of_fd(s.fd) == "sleep"
    finally:
        os.kill(s.pid, 9)
        os.waitpid(s.pid, 0)
        os.close(s.fd)


@pytest.mark.skipif(not TMUX, reason="tmux is not installed")
def test_a_text_frame_that_is_json_but_no_message_is_typed_not_fatal(env) -> None:
    """"5", "null", "[]" parse as JSON and are no message: they ended the
    socket with an AttributeError. They are typed, as text that is no JSON is."""
    c, root, work = env
    _on(c)
    tok = c.get("/api/terminal/state").json()["token"]
    sid = c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha", "label": "t"}).json()["session"]["id"]
    deadline = time.time() + 5
    seen = b""
    with c.websocket_connect(f"/ws/terminal/{sid}?token={tok}&cols=80&rows=24") as ws:
        for frame in ("[]", "null"):
            ws.send_text(frame)
        ws.send_text(json.dumps({"type": "input", "data": "\x15echo mk-$((6*7))-alive\r"}))
        while b"mk-42-alive" not in seen and time.time() < deadline:
            seen += ws.receive_bytes()
    assert b"mk-42-alive" in seen
    c.post(f"/api/terminal/sessions/{sid}/close", json={})


def test_a_refused_token_is_told_after_the_handshake_so_the_page_reads_4401(env) -> None:
    """Closed before the handshake, a socket fails with HTTP 403 and a browser
    reports 1006: the page kept the old token after a restart and reconnected
    with it for good. Now the handshake completes, then 4401 says why; a
    token that is not ASCII is a refusal too, not an error."""
    c, _, _ = env
    _on(c)
    from starlette.websockets import WebSocketDisconnect
    for bad in ("nope", "токен", "x" * 5000):
        opened = False
        with pytest.raises(WebSocketDisconnect) as e:
            with c.websocket_connect(f"/ws/terminal/t1?token={bad}") as ws:
                opened = True
                ws.receive_bytes()
        assert opened and e.value.code == 4401, bad
    # Another site's page is still turned away at the handshake itself.
    opened = False
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect("/ws/terminal/t1?token=nope", headers={"Origin": "https://evil.example"}):
            opened = True
    assert not opened


def test_the_token_is_new_at_each_start_and_never_cached(tmp_path: Path, monkeypatch) -> None:
    from backend.routers import terminal
    monkeypatch.delenv("SP_TOKEN", raising=False)
    root = tmp_path / "data"
    (root / "projects").mkdir(parents=True)
    a, b = create_app(data_root=root, watch=False), create_app(data_root=root, watch=False)
    assert terminal.token_of(a) == terminal.token_of(a) != terminal.token_of(b)
    # SP_TOKEN no longer fixes it: a set one is ignored.
    monkeypatch.setenv("SP_TOKEN", "fixed-token-for-this-test")
    assert terminal.token_of(create_app(data_root=root, watch=False)) != "fixed-token-for-this-test"
    with TestClient(a) as c:
        _on(c)
        r = c.get("/api/terminal/state")
        assert r.headers["cache-control"] == "no-store" and r.json()["token"] == terminal.token_of(a)
