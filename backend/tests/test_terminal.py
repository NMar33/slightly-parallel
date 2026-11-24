"""Terminals: off until switched on, the token only for Slightly Parallel's pages, tmux sessions that outlive a socket."""

from __future__ import annotations

import json
import shlex
import os
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import termlib
from backend.server import create_app

TMUX = termlib.tmux_path() is not None

# The routes run on every system: a Unix pty on macOS and Linux, a ConPTY on
# Windows (tests/test_conpty.py runs the real one there; tests/test_terminal_
# windows.py the Windows path with a stand-in pywinpty, everywhere). A test
# that forks a Unix pty itself says so and skips on Windows.
unix_pty = pytest.mark.skipif(os.name == "nt", reason="a Unix pty (the Windows one: tests/test_conpty.py)")


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
    cmd = termlib.start_command("claude", {"id": "tk_1", "title": "It's \"quoted\"", "description": "line1\nline2"}, "bash")
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
    assert termlib.agent_links(root)["tq1"]["agent_id"] == "cc-aaaa1111"
    assert termlib.agent_links(root / "other") == {}


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
    try:
        (work / "out").symlink_to("/")
    except OSError:  # pragma: no cover — Windows without the right to make one
        pytest.skip("a symlink needs privileges on Windows")
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


def test_terminals_opened_in_the_same_second_keep_their_order(tmp_path: Path) -> None:
    # `created` orders the tabs. In whole seconds, two terminals opened in the
    # same second tied and their random ids decided which tab came first: the
    # window's "+" put the new shell first or second by chance.
    root = tmp_path / "data"
    root.mkdir()
    ids = []
    for _ in range(4):
        ids.append(termlib.open_session(root, {"terminal.keep": "plain"}, kind="shell", project="", cwd="")["id"])
        time.sleep(0.002)
    rows = [termlib.get(root, i) for i in ids]
    assert all(len(r["created"]) == 23 and r["created"][19] == "." for r in rows)
    assert [r["id"] for r in sorted(rows, key=lambda r: (r["created"], r["id"]))] == ids


@pytest.mark.skipif(not TMUX, reason="tmux is not installed")
def test_a_middle_click_is_not_a_second_paste_from_tmux(tmp_path: Path) -> None:
    # The page pastes on a middle click (the browser's selection); tmux's own
    # binding pasted its buffer as well, and a line just copied in the
    # terminal reached the shell twice. A mouse-reading program keeps the click.
    root = tmp_path / "data"
    root.mkdir()
    try:
        assert termlib.tmux(root, "new-session", "-d", "-s", "mk-probe", "sleep 30").returncode == 0
        keys = termlib.tmux(root, "list-keys", "-T", "root", "MouseDown2Pane").stdout
        assert "MouseDown2Pane" in keys
        assert "paste" not in keys
        assert "send -M" in keys or "send-keys -M" in keys
    finally:
        termlib.tmux(root, "kill-server")


@pytest.mark.skipif(not TMUX, reason="tmux is not installed")
def test_tmux_mouse_bindings_select_without_copying(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    try:
        termlib.tmux(root, "new-session", "-d", "-s", "mk-probe", "printf 'selected text\\n'; sleep 30")
        for table in ("copy-mode", "copy-mode-vi"):
            keys = termlib.tmux(root, "list-keys", "-T", table).stdout
            assert "MouseDragEnd1Pane" not in keys
            assert "S-MouseDown1Pane" in keys
            assert all("copy-pipe" not in line for line in keys.splitlines()
                       if "DoubleClick1Pane" in line or "TripleClick1Pane" in line)
        assert not termlib.copy_selection(root, "probe")
        termlib.tmux(root, "copy-mode", "-t", "mk-probe")
        for key in ("history-top", "start-of-line", "begin-selection", "end-of-line"):
            termlib.tmux(root, "send-keys", "-X", "-t", "mk-probe", key)
        assert termlib.pane_pos(root, "probe")["selecting"]
        assert termlib.copy_selection(root, "probe").strip() == "selected text"
        assert termlib.tmux(root, "show-buffer").stdout.strip() == "selected text"
        assert not termlib.copy_selection(root, "probe")
    finally:
        termlib.tmux(root, "kill-server")


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


def _pane_state(root: Path, sid: str, log: Path) -> str:
    """What a failure on a machine we can only reach through CI has to say:
    the shell's pid (a new one: the shell was replaced), the size, the history
    (grown: tmux moved the text), the cursor, all the text, the shell's bytes."""
    target = termlib.PREFIX + sid
    fmt = "pid=#{pane_pid} h=#{window_height} w=#{window_width} hist=#{history_size} cy=#{cursor_y} tmux=#{version}"
    state = termlib.tmux(root, "list-panes", "-t", target, "-F", fmt).stdout.strip()
    text = termlib.tmux(root, "capture-pane", "-p", "-S", "-", "-t", target).stdout
    raw = log.read_bytes() if log.exists() else b""
    return f"{state}\ntext: {text!r}\nbytes: {raw!r}"


@pytest.mark.skipif(not TMUX, reason="tmux is not installed")
@pytest.mark.parametrize("early_query", [False, True])
def test_first_socket_input_survives_tmux_initializing_its_tty(env, monkeypatch, early_query) -> None:
    c, root, _ = env
    _on(c)
    sid = c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha"}).json()["session"]["id"]
    termlib.wait_for_prompt(root, sid)
    argv = termlib.attach_argv(root, sid)
    # Model a slow tmux client that flushes the tty before drawing. If input
    # arrives early, select wakes immediately and the flush discards it.
    query = "os.write(1, b'\\x1b[6n'); " if early_query else ""
    startup = (
        "import os, select, sys, termios; "
        "mode = termios.tcgetattr(0); mode[3] |= termios.ICANON; termios.tcsetattr(0, termios.TCSANOW, mode); "
        f"{query}"
        "select.select([0], [], [], 1); "
        "termios.tcflush(0, termios.TCIFLUSH); "
        "os.execvp(sys.argv[1], sys.argv[1:])"
    )
    monkeypatch.setattr(termlib, "attach_argv", lambda *_: [sys.executable, "-c", startup, *argv])
    token = c.get("/api/terminal/state").json()["token"]
    with c.websocket_connect(f"/ws/terminal/{sid}?token={token}") as ws:
        # Split the marker so its full form only appears in command output.
        ws.send_text(json.dumps({"type": "input", "data": "printf '%s%s\\n' sp-early- input\r"}))
        screen = _wait_screen(root, sid, "sp-early-input")
        assert "sp-early-input" in screen, screen


@pytest.mark.skipif(not TMUX, reason="tmux is not installed")
def test_a_wrapped_line_above_does_not_shift_the_lines_cut_out(env) -> None:
    """What the page copies goes by the screen's rows. A command wider than the
    pane takes two of them; on CI's macOS a long machine name in the prompt did
    this now and then, and only then did the test above fail."""
    c, root, _ = env
    _on(c)
    sid = c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha"}).json()["session"]["id"]
    termlib.wait_for_prompt(root, sid)
    tok = c.get("/api/terminal/state").json()["token"]
    with c.websocket_connect(f"/ws/terminal/{sid}?token={tok}") as ws:
        ws.send_text(json.dumps({"type": "input", "data": f"printf 'A%s\\n' 1 2 3 4 5 # {'x' * 240}\r"}))
        deadline = time.time() + 5
        while time.time() < deadline and "A5" not in termlib.capture(root, sid)["text"]:
            time.sleep(0.1)
    target = termlib.PREFIX + sid
    rows = termlib.tmux(root, "capture-pane", "-p", "-t", target).stdout.split("\n")
    joined = termlib.capture(root, sid)["text"].split("\n")
    # When it fails, say what the pane held (CI's macOS, 2026-11-10: no row was "A2").
    assert any(l.strip() == "A2" for l in rows), f"the pane:\n{chr(10).join(rows)}\njoined:\n{chr(10).join(joined)}"
    row = next(i for i, l in enumerate(rows) if l.strip() == "A2")
    assert row > next(i for i, l in enumerate(joined) if l.strip() == "A2")      # it does take more rows
    pos = c.get(f"/api/terminal/sessions/{sid}/pos").json()
    a = pos["history"] - pos["scroll"] + row
    got = c.post(f"/api/terminal/sessions/{sid}/capture", json={"mode": "range", "from": a, "to": a + 2}).json()
    assert got["text"].split("\n") == ["A2", "A3", "A4"]
    c.post(f"/api/terminal/sessions/{sid}/close", json={})


@pytest.mark.skipif(not TMUX, reason="tmux is not installed")
def test_lines_are_cut_out_by_their_absolute_ids(env) -> None:
    c, root, _ = env
    _on(c)
    sid = c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha"}).json()["session"]["id"]
    termlib.wait_for_prompt(root, sid)
    tok = c.get("/api/terminal/state").json()["token"]
    log = root / "pane-bytes.log"
    termlib.tmux(root, "pipe-pane", "-t", termlib.PREFIX + sid, f"cat >> {shlex.quote(str(log))}")
    # Typed over the socket, as the page types: the Enter stamps the history.
    with c.websocket_connect(f"/ws/terminal/{sid}?token={tok}") as ws:
        ws.send_text(json.dumps({"type": "input", "data": "printf 'A%s\\n' 1 2 3 4 5\r"}))
        deadline = time.time() + 5
        while time.time() < deadline and "A5" not in termlib.capture(root, sid)["text"]:
            time.sleep(0.1)
        inside = _pane_state(root, sid, log)
    screen = termlib.capture(root, sid)
    after = _pane_state(root, sid, log)
    assert screen["lines"] >= 5 and "A5" in screen["text"], f"INSIDE THE SOCKET\n{inside}\nAFTER IT\n{after}"

    # The row that shows A2, anchored to an absolute id, survives arithmetic.
    pos = c.get(f"/api/terminal/sessions/{sid}/pos").json()
    # Counted on the screen's own rows, as the page counts them: the screen's
    # text joins a wrapped line, so its lines can sit a row above the screen's.
    rows = termlib.tmux(root, "capture-pane", "-p", "-t", termlib.PREFIX + sid).stdout.split("\n")
    idx = next(i for i, l in enumerate(rows) if l.strip() == "A2")
    a = pos["history"] - pos["scroll"] + idx
    got = c.post(f"/api/terminal/sessions/{sid}/capture", json={"mode": "range", "from": a, "to": a + 2}).json()
    assert got["text"].split("\n") == ["A2", "A3", "A4"] and got["truncated"] is False, (
        f"INSIDE THE SOCKET\n{inside}\nAFTER IT\n{after}\nNOW\n{_pane_state(root, sid, log)}\npos {pos} a {a} idx {idx}")

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
    screen = _wait_screen(root, sid, "\n200\n")
    assert "\n200\n" in screen, screen
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


@unix_pty
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


@unix_pty
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


# ---------------------------------------------------------------------------
# Roles, sleep and wake, restore after a restart, groups, typing
# ---------------------------------------------------------------------------

needs_tmux = pytest.mark.skipif(not TMUX, reason="tmux is not installed")


def _open(c, **body) -> dict:
    r = c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha", **body})
    assert r.status_code == 201, r.text
    return r.json()["session"]


def _row(c, sid: str) -> dict:
    return next(x for x in c.get("/api/terminal/sessions").json()["sessions"] if x["id"] == sid)


def _screen(root: Path, sid: str) -> str:
    return termlib.tmux(root, "capture-pane", "-p", "-t", termlib.PREFIX + sid).stdout


def _wait_screen(root: Path, sid: str, text: str, timeout: float = 5.0) -> str:
    end = time.time() + timeout
    while time.time() < end:
        got = _screen(root, sid)
        if text in got:
            return got
        time.sleep(0.1)
    return _screen(root, sid)


@needs_tmux
def test_a_terminal_has_a_role(env) -> None:
    c, _, _ = env
    _on(c)
    shell = _open(c)
    server = _open(c, role="server", command="echo serving", label="web")
    rows = {x["id"]: x for x in c.get("/api/terminal/sessions").json()["sessions"]}
    assert rows[shell["id"]]["role"] == "shell" and rows[server["id"]]["role"] == "server"


@needs_tmux
def test_a_server_sleeps_and_wakes_running_its_command_again(env) -> None:
    c, root, _ = env
    _on(c)
    s = _open(c, role="server", command="echo up-$((6*7))", label="web")
    assert "up-42" in _wait_screen(root, s["id"], "up-42")
    got = c.post(f"/api/terminal/sessions/{s['id']}/sleep", json={}).json()["session"]
    assert got["state"] == "asleep" and got["wake"] == "echo up-$((6*7))"
    assert not termlib.alive_tmux(root, s["id"])
    from starlette.websockets import WebSocketDisconnect
    tok = c.get("/api/terminal/state").json()["token"]
    with pytest.raises(WebSocketDisconnect) as refused:
        with c.websocket_connect(f"/ws/terminal/{s['id']}?token={tok}") as ws:
            ws.receive_bytes()
    assert refused.value.code == 4000 and refused.value.reason == "asleep"
    assert not termlib.alive_tmux(root, s["id"])
    assert _row(c, s["id"])["command"] == s["command"]
    assert _row(c, s["id"])["created"] == s["created"]
    listed = c.get("/api/terminal/sessions").json()
    assert listed["counts"]["asleep"] == 1 and listed["counts"]["ended"] == 0
    # Asleep is not lost: Restore does not offer it.
    assert c.get("/api/terminal/restore").json()["needed"] == 0
    woke = c.post(f"/api/terminal/sessions/{s['id']}/wake", json={}).json()["session"]
    assert woke["id"] == s["id"] and woke["state"] != "asleep" and woke["label"] == "web" and woke["role"] == "server"
    assert "up-42" in _wait_screen(root, s["id"], "up-42")
    # Waking one that is awake changes nothing.
    assert c.post(f"/api/terminal/sessions/{s['id']}/wake", json={}).json()["session"]["state"] != "asleep"
    termlib.tmux(root, "kill-session", "-t", termlib.PREFIX + s["id"])
    bare = c.post(f"/api/terminal/sessions/{s['id']}/wake", json={"shell": True}).json()["session"]
    assert bare["id"] == s["id"] and bare["command"] == s["command"] and bare["wake"] == ""
    assert "up-42" not in _screen(root, s["id"])


@needs_tmux
def test_a_plain_shell_wakes_empty(env) -> None:
    c, root, _ = env
    _on(c)
    s = _open(c, command="echo once-$((2*3))")
    assert "once-6" in _wait_screen(root, s["id"], "once-6")
    assert c.post(f"/api/terminal/sessions/{s['id']}/sleep", json={}).json()["session"]["wake"] == ""
    c.post(f"/api/terminal/sessions/{s['id']}/wake", json={})
    time.sleep(0.6)
    assert "once-6" not in _screen(root, s["id"])
    # The command it was opened with is still on its row.
    assert _row(c, s["id"])["command"] == "echo once-$((2*3))"


def test_what_a_terminal_runs_when_it_comes_back() -> None:
    wc = termlib.wake_command
    assert wc({"kind": "resume", "command": "claude -r abc"}) == "claude -r abc"
    # A terminal that started an agent on a task: the agent's session, never a second start.
    assert wc({"kind": "start", "command": "claude 'do the task'"}, "claude -r xyz") == "claude -r xyz"
    assert wc({"kind": "start", "command": "claude 'do the task'"}) == ""
    assert wc({"kind": "shell", "role": "server", "command": "npm run dev"}) == "npm run dev"
    assert wc({"kind": "shell", "command": "ls"}) == ""


@needs_tmux
def test_after_a_restart_restore_brings_back_what_was_not_asleep(env, monkeypatch) -> None:
    c, root, _ = env
    _on(c)
    web = _open(c, role="server", command="echo back-$((5*5))", label="web")
    sh = _open(c, label="scratch")
    from backend.db import ViewStore
    monkeypatch.setattr(termlib, "agent_links", lambda _root: {sh["id"]: {"agent_id": "cc-aaaa1111"}})
    monkeypatch.setattr(ViewStore, "agents", lambda _self: [
        {"agent_id": "cc-aaaa1111", "tool": "claude-code", "session_ref": "captured"},
    ])
    monkeypatch.setattr(termlib, "resume_command", lambda tool, ref:
                        "echo linked-$((2*3))" if (tool, ref) == ("claude-code", "captured") else "")
    napping = _open(c, role="server", command="echo nap", label="docs")
    c.post(f"/api/terminal/sessions/{napping['id']}/sleep", json={})
    assert c.get("/api/terminal/restore").json()["needed"] == 0
    # The computer restarts: the tmux server and every session in it are gone.
    termlib.tmux(root, "kill-server")
    time.sleep(0.3)
    from starlette.websockets import WebSocketDisconnect
    tok = c.get("/api/terminal/state").json()["token"]
    with pytest.raises(WebSocketDisconnect) as refused:
        with c.websocket_connect(f"/ws/terminal/{web['id']}?token={tok}") as ws:
            ws.receive_bytes()
    assert refused.value.code == 4000
    assert _row(c, web["id"])["created"] == web["created"]
    assert _row(c, web["id"])["command"] == web["command"]
    state = c.get("/api/terminal/restore").json()
    assert {x["id"] for x in state["sessions"]} == {web["id"], sh["id"]}
    assert next(x for x in state["sessions"] if x["id"] == web["id"])["wake"] == "echo back-$((5*5))"
    done = c.post("/api/terminal/restore", json={}).json()
    assert done["restored"] == 2 and all(r["ok"] for r in done["results"])
    assert "back-25" in _wait_screen(root, web["id"], "back-25")
    assert "linked-6" in _wait_screen(root, sh["id"], "linked-6")
    assert _row(c, napping["id"])["state"] == "asleep"
    assert c.get("/api/terminal/restore").json()["needed"] == 0


@needs_tmux
def test_a_shell_left_with_exit_is_not_offered_back(env) -> None:
    c, root, _ = env
    _on(c)
    keep = _open(c, label="keep")
    gone = _open(c, label="gone")
    termlib.tmux(root, "kill-session", "-t", termlib.PREFIX + gone["id"])
    assert _row(c, gone["id"])["state"] == "ended"
    assert termlib.alive_tmux(root, keep["id"])
    assert c.get("/api/terminal/restore").json()["needed"] == 0


@needs_tmux
def test_restore_takes_only_the_named_ones(env) -> None:
    c, root, _ = env
    _on(c)
    a, b = _open(c, label="a"), _open(c, label="b")
    termlib.tmux(root, "kill-server")
    time.sleep(0.3)
    done = c.post("/api/terminal/restore", json={"ids": [a["id"]]}).json()
    assert [r["id"] for r in done["results"]] == [a["id"]]
    assert _row(c, b["id"])["state"] == "ended"


@needs_tmux
def test_groups_hold_terminals_of_any_project(env) -> None:
    c, _, _ = env
    _on(c)
    assert c.get("/api/terminal/groups").json() == {"groups": []}
    g = c.post("/api/terminal/groups", json={"name": "Release week", "color": 3}).json()["group"]
    assert g["name"] == "Release week" and g["color"] == 3 and g["id"]
    s = _open(c)
    moved = c.post(f"/api/terminal/sessions/{s['id']}/group", json={"group": g["id"]}).json()["session"]
    assert moved["group"] == g["id"] and moved["project"] == "alpha"
    born = _open(c, group=g["id"])
    assert _row(c, born["id"])["group"] == g["id"]
    assert c.post(f"/api/terminal/sessions/{s['id']}/group", json={"group": "nope"}).status_code == 422
    assert c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha", "group": "nope"}).status_code == 422
    g2 = c.post(f"/api/terminal/groups/{g['id']}", json={"name": "Launch", "color": 5}).json()["group"]
    assert g2["name"] == "Launch" and g2["color"] == 5
    assert c.post(f"/api/terminal/groups/{g['id']}", json={"color": 9}).status_code == 422
    assert c.post("/api/terminal/groups", json={"name": " "}).status_code == 422
    assert c.post("/api/terminal/groups/nope", json={"name": "x"}).status_code == 404
    # Removing a group returns its terminals to their projects.
    assert c.post(f"/api/terminal/groups/{g['id']}/remove", json={}).json() == {"removed": g["id"]}
    assert _row(c, s["id"])["group"] == "" and _row(c, born["id"])["group"] == ""
    assert c.get("/api/terminal/groups").json() == {"groups": []}
    assert c.post(f"/api/terminal/groups/{g['id']}/remove", json={}).status_code == 404


def test_tab_groups_keep_their_project_on_create_move_and_rename(env) -> None:
    c, *_ = env
    _on(c)
    g = c.post("/api/terminal/groups", json={"name": "Release", "project": "alpha"}).json()["group"]
    gid = g["id"]
    assert g["project"] == "alpha"
    assigned = _open(c, project="alpha", group=gid)
    other = _open(c, project="")
    assert c.post("/api/terminal/sessions", json={"kind": "shell", "project": "", "group": gid}).status_code == 422
    assert c.post(f"/api/terminal/sessions/{other['id']}/group", json={"group": gid}).status_code == 422
    assert not _row(c, other["id"]).get("group")
    rename = c.post(f"/api/terminal/groups/{gid}", json={"name": "Launch", "project": ""}).json()["group"]
    assert rename["project"] == "alpha" and rename["name"] == "Launch"
    assert c.get("/api/terminal/groups").json()["groups"] == [rename]
    assert c.post(f"/api/terminal/groups/{gid}/remove", json={}).is_success
    assert _row(c, assigned["id"])["group"] == ""


def test_tab_group_batch_assignments_validate_every_tab_before_moving(env) -> None:
    c, root, _ = env
    _on(c)
    a, b = _open(c)["id"], _open(c)["id"]
    other = _open(c, project="")["id"]
    create = "/api/terminal/groups"
    move = f"{create}/move"
    invalid = {"project": "alpha", "tabs": [a, other]}
    assert c.post(create, json={"name": "Mixed", **invalid}).status_code == 422
    assert c.get(create).json()["groups"] == []
    assert not (termlib.registry_path(root).parent / termlib.GROUPS).exists()
    assert not _row(c, a).get("group")
    group = c.post(create, json={"name": "Pair", "project": "alpha", "tabs": [a, b]}).json()["group"]["id"]
    assert _row(c, a)["group"] == _row(c, b)["group"] == group
    assert c.post(move, json={"group": "", **invalid}).status_code == 422
    assert c.post(move, json={"group": "", "project": "alpha", "tabs": [a, "missing"]}).status_code == 422
    assert _row(c, a)["group"] == _row(c, b)["group"] == group
    assert c.post(move, json={"group": "", "project": "alpha", "tabs": [a, b]}).is_success
    assert _row(c, a)["group"] == _row(c, b)["group"] == ""


def test_codex_uses_its_own_app_server_if_the_cli_supports_it(env, monkeypatch) -> None:
    from subprocess import CompletedProcess

    c, *_ = env
    _on(c)
    monkeypatch.setattr(termlib.shutil, "which", lambda exe: "/test/codex" if exe == "codex" else None)
    with monkeypatch.context() as m:
        m.setattr(termlib.subprocess, "run", lambda args, **kw: CompletedProcess(args, 0, "      --no-daemon\n", ""))
        assert termlib.codex_in_terminal() == "codex --no-daemon"
        assert termlib.resume_command("codex", "session1") == "codex --no-daemon resume session1"

    monkeypatch.setattr(termlib, "uses_tmux", lambda settings: False)
    assert _open(c, command="codex")["command"] == "codex --no-daemon"
    with monkeypatch.context() as m:
        m.setattr(termlib.subprocess, "run", lambda args, **kw: CompletedProcess(args, 0, "codex help\n", ""))
        termlib._codex_has_no_daemon.cache_clear()
        assert termlib.codex_in_terminal() == "codex"
    termlib._codex_has_no_daemon.cache_clear()


@needs_tmux
def test_typing_is_counted_never_kept(env) -> None:
    c, root, _ = env
    _on(c)
    s = _open(c)
    assert c.post("/api/terminal/typing", json={"sid": s["id"], "keys": 12}).json() == {"noted": True}
    assert c.post("/api/terminal/typing", json={"sid": s["id"], "keys": 0}).json() == {"noted": False}
    assert c.post("/api/terminal/typing", json={"sid": "nope", "keys": 5}).json() == {"noted": False}
    assert c.post("/api/terminal/typing", json={"sid": s["id"], "keys": "abc"}).json() == {"noted": False}
    day = c.get("/api/terminal/typing").json()
    assert day["minutes"] == {"alpha": 1} and day["total"] == 1
    lines = (root / "terminal" / "typing.csv").read_text().splitlines()
    assert lines[0] == "at,terminal,project,agent_id,keys" and lines[1].endswith(f",{s['id']},alpha,,12")
    assert c.get("/api/terminal/typing?day=2020-01-01").json()["total"] == 0


def test_an_agent_cannot_sleep_wake_restore_or_group(env) -> None:
    c, _, _ = env
    _on(c)
    who = {"agent_id": "cc-1"}
    for path in ("/api/terminal/sessions/x/sleep", "/api/terminal/sessions/x/wake", "/api/terminal/restore",
                 "/api/terminal/groups", "/api/terminal/groups/x", "/api/terminal/groups/x/remove",
                 "/api/terminal/sessions/x/group", "/api/terminal/typing"):
        assert c.post(path, json=who).status_code in (403, 422), path


def test_the_new_writes_are_off_with_the_terminal(env) -> None:
    c, _, _ = env
    for path in ("/api/terminal/sessions/x/sleep", "/api/terminal/sessions/x/wake", "/api/terminal/restore",
                 "/api/terminal/groups", "/api/terminal/typing"):
        assert c.post(path, json={}).status_code == 409, path


def test_a_terminal_from_before_the_server_was_recorded_is_not_offered_back() -> None:
    old = {"id": "a", "state": "ended", "backend": "tmux"}
    new = {"id": "b", "state": "ended", "backend": "tmux", "server": "100"}
    assert termlib.lost([old, new], "") == [new]
    assert termlib.lost([old, new], "200") == [new]
    assert termlib.lost([old, new], "100") == []


@needs_tmux
def test_a_terminal_opens_while_the_last_one_closes(tmp_path: Path, monkeypatch) -> None:
    # tmux's server quits when its last session ends; a new-session that
    # reaches it in that moment came back "server exited unexpectedly" (exit
    # 1) and the page said "the terminal could not open". The bench saw it 4
    # times in one run. Here the close and the open race 60 times.
    import subprocess
    monkeypatch.setenv("SHELL", "/bin/sh")
    root = tmp_path / "data"
    root.mkdir()
    settings = {"terminal.keep": "tmux"}
    failed: list[str] = []
    try:
        for i in range(60):
            first = termlib.open_session(root, settings, kind="shell", project="", cwd="")
            closing = subprocess.Popen(termlib.tmux_argv(root, "kill-session", "-t", termlib.PREFIX + first["id"]),
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.001 * (i % 10))
            try:
                second = termlib.open_session(root, settings, kind="shell", project="", cwd="")
            except subprocess.CalledProcessError as exc:
                failed.append(exc.stderr.strip())
                second = None
            closing.wait()
            if second:
                termlib.tmux(root, "kill-session", "-t", termlib.PREFIX + second["id"])
    finally:
        termlib.tmux(root, "kill-server")
    assert failed == []


def test_only_a_server_going_away_is_tried_again(tmp_path: Path, monkeypatch) -> None:
    import subprocess
    calls: list[tuple[str, ...]] = []
    answers: list[tuple[int, str]] = []

    def fake(_root, *args, check=False):
        calls.append(args)
        code, err = answers.pop(0)
        return subprocess.CompletedProcess(["tmux", *args], code, "", err)

    monkeypatch.setattr(termlib, "tmux", fake)
    monkeypatch.setattr(termlib.time, "sleep", lambda _s: None)
    answers[:] = [(1, "server exited unexpectedly\n"), (1, "lost server\n"), (0, "")]
    assert termlib.tmux_starting(tmp_path, "new-session", "-d").returncode == 0
    assert len(calls) == 3
    calls.clear()
    answers[:] = [(1, "duplicate session: mk-a\n"), (0, "")]
    with pytest.raises(subprocess.CalledProcessError):
        termlib.tmux_starting(tmp_path, "new-session", "-d")
    assert len(calls) == 1
    calls.clear()
    answers[:] = [(1, "server exited unexpectedly\n")] * 4
    with pytest.raises(subprocess.CalledProcessError):
        termlib.tmux_starting(tmp_path, "new-session", "-d")
    assert len(calls) == 4


# ------------------------------------------------- a tmux that does not answer

@pytest.fixture()
def hanging_tmux(tmp_path: Path, monkeypatch):
    """A `tmux` on the PATH that never answers — a server busy dying (CI on
    macOS: list-panes timed out while the e2e killed tmux, and the list
    answered 500). `exec` so the timeout's kill reaches the sleeper itself
    and no grandchild holds the pipes open."""
    if os.name == "nt":
        pytest.skip("no tmux on Windows")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "tmux"
    fake.write_text("#!/bin/sh\nexec sleep 30\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("SHELL", "/bin/sh")
    monkeypatch.setattr(termlib, "READ_TIMEOUT", 0.3)
    monkeypatch.setattr(termlib, "WRITE_TIMEOUT", 0.3)
    assert termlib.tmux_path() == str(fake)
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    with TestClient(create_app(data_root=root, watch=False)) as c:
        _on(c)
        for sid in ("hang1", "hang2"):
            termlib.put(root, {"id": sid, "kind": "shell", "label": sid, "project": "alpha", "cwd": str(tmp_path),
                               "command": "", "created": f"2026-11-17T09:40:0{sid[-1]}", "backend": "tmux",
                               "server": "4242", "asleep": False})
        yield c, root


def test_a_hanging_tmux_still_lists_the_terminals(hanging_tmux) -> None:
    c, _ = hanging_tmux
    t0 = time.time()
    got = c.get("/api/terminal/sessions")
    assert got.status_code == 200
    body = got.json()
    assert [s["id"] for s in body["sessions"]] == ["hang1", "hang2"]
    assert {s["state"] for s in body["sessions"]} == {"ended"}
    assert body["counts"]["ended"] == 2
    # The restore offer works from the same answer: tmux's server is not the one recorded.
    offer = c.get("/api/terminal/restore")
    assert offer.status_code == 200 and offer.json()["needed"] == 2
    assert c.get("/api/terminal/state").status_code == 200
    assert time.time() - t0 < 10  # each read waits READ_TIMEOUT, not tmux's 30 s


def test_a_hanging_tmux_reads_a_pane_as_empty(hanging_tmux) -> None:
    c, _ = hanging_tmux
    pos = c.get("/api/terminal/sessions/hang1/pos")
    assert pos.status_code == 200 and pos.json() == {
        "history": 0, "scroll": 0, "rows": 0, "cursor": 0, "cols": 0,
        "alt": False, "mouse": False, "in_mode": False, "selecting": False,
    }
    cap = c.post("/api/terminal/sessions/hang1/capture", json={"mode": "screen"})
    assert cap.status_code == 200 and cap.json()["text"] == ""


def test_a_hanging_tmux_fails_a_write_with_a_message(hanging_tmux) -> None:
    c, root = hanging_tmux
    typed = c.post("/api/terminal/sessions/hang1/type", json={"text": "ls", "enter": True})
    assert typed.status_code == 503 and "tmux did not answer" in typed.json()["detail"]
    closed = c.post("/api/terminal/sessions/hang1/close", json={})
    assert closed.status_code == 503 and "was not closed" in closed.json()["detail"]
    assert termlib.get(root, "hang1") is not None  # not forgotten while its session may live
    bottom = c.post("/api/terminal/sessions/hang1/bottom")
    assert bottom.status_code == 503
    opened = c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha"})
    assert opened.status_code == 500 and "tmux did not answer" in opened.json()["detail"]


def test_a_tmux_timeout_never_leaves_tmux_read(tmp_path: Path, monkeypatch) -> None:
    import subprocess

    def timing_out(argv, **kw):
        raise subprocess.TimeoutExpired(argv, kw.get("timeout"))

    monkeypatch.setattr(termlib.shutil, "which", lambda name: "/usr/bin/tmux" if name == "tmux" else None)
    monkeypatch.setattr(termlib, "WINDOWS", False)
    monkeypatch.setattr(termlib.subprocess, "run", timing_out)
    (tmp_path / "terminal").mkdir()
    assert termlib.tmux_panes(tmp_path) == {}
    assert termlib.alive_tmux(tmp_path, "x") is False
    assert termlib.tmux_server_pid(tmp_path) == ""
    assert termlib.tmux_version() == ""
    assert termlib.pane_pos(tmp_path, "x")["history"] == 0
    with pytest.raises(termlib.TmuxError):
        termlib.tmux(tmp_path, "kill-session", "-t", "x")


@pytest.mark.skipif(not TMUX, reason="tmux is not installed")
def test_the_reader_gets_the_pane_rows_with_colours_and_the_wheel_knows_what_the_pane_shows(env) -> None:
    """The page's smooth reader (Screen.tsx, reader.ts): mode history gives the
    last rows of the history and the screen, one row per line, colours kept,
    with the anchor (history) and what the pane shows (alt, mouse, in_mode)."""
    c, root, _ = env
    _on(c)
    sid = c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha"}).json()["session"]["id"]
    termlib.wait_for_prompt(root, sid)
    termlib.type_into(root, termlib.get(root, sid), "i=1; while [ $i -le 120 ]; do printf '\\033[31mR%03d\\033[0m\\n' $i; i=$((i+1)); done", enter=True)
    deadline = time.time() + 5
    while time.time() < deadline and "R120" not in termlib.capture(root, sid)["text"]:
        time.sleep(0.1)
    pos = c.get(f"/api/terminal/sessions/{sid}/pos").json()
    assert pos["alt"] is False and pos["mouse"] is False and pos["in_mode"] is False and pos["cols"] > 0, pos

    got = c.post(f"/api/terminal/sessions/{sid}/capture", json={"mode": "history", "rows": 50}).json()
    rows = got["text"].split("\n")
    assert got["mode"] == "history" and got["above"] == 50 and got["complete"] is False
    # 50 rows of history, then the screen: the reader's last rows are the live screen.
    assert len(rows) == 50 + got["rows"], (len(rows), got["rows"])
    assert any("\x1b[31m" in r and "R1" in r for r in rows), "the colours are kept"
    # Row i of the answer is absolute line history - above + i: the same as a range capture of it.
    i = next(k for k, r in enumerate(rows) if "R100" in r)
    a = got["history"] - got["above"] + i
    assert c.post(f"/api/terminal/sessions/{sid}/capture", json={"mode": "range", "from": a, "to": a}).json()["text"] == "R100"

    everything = c.post(f"/api/terminal/sessions/{sid}/capture", json={"mode": "history", "rows": 10**9}).json()
    assert everything["complete"] is True and everything["above"] == everything["history"]
    assert c.post(f"/api/terminal/sessions/{sid}/capture", json={"mode": "history", "rows": "x"}).status_code == 422

    # A full-screen program: the wheel goes to it, not to a reader.
    termlib.type_into(root, termlib.get(root, sid), "printf '\\033[?1049h'; sleep 30", enter=True)
    deadline = time.time() + 5
    while time.time() < deadline and not c.get(f"/api/terminal/sessions/{sid}/pos").json()["alt"]:
        time.sleep(0.1)
    assert c.get(f"/api/terminal/sessions/{sid}/pos").json()["alt"] is True
    c.post(f"/api/terminal/sessions/{sid}/close", json={})


@pytest.mark.skipif(not TMUX, reason="tmux is not installed")
def test_the_wheel_over_a_full_screen_program_without_the_mouse_sends_arrow_keys(env) -> None:
    """tmux's default enters copy mode there, which has no history on the
    alternate screen: less, man and vim without the mouse did not move at all."""
    c, root, _ = env
    _on(c)
    sid = c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha"}).json()["session"]["id"]
    termlib.wait_for_prompt(root, sid)
    keys = termlib.tmux(root, "list-keys", "-T", "root").stdout
    up = next(l for l in keys.splitlines() if " WheelUpPane " in l)
    down = next(l for l in keys.splitlines() if " WheelDownPane " in l)
    assert "alternate_on" in up and "send-keys -t = Up" in up and "copy-mode -e" in up and "send-keys -M" in up
    assert "alternate_on" in down and "send-keys -t = Down" in down
    c.post(f"/api/terminal/sessions/{sid}/close", json={})


# ------------------------------------------------- typing, not xterm's replies
# A click in a tmux terminal (tmux runs with the mouse on) made xterm send
# mouse reports through the socket, and attaching made it answer tmux's
# questions; the server took each for typing and beat the timer, so the
# window's own beat (source "window") was overwritten by "terminal" at once
# (desktop/e2e/timer.spec.ts, 2026-11-18). What xterm sent then:
SEEN_ON_A_CLICK = ["\x1b[?1;2c", "\x1b[>0;276;0c", "\x1b]10;rgb:e6e6/e8e8/ebeb\x1b\\",
                   "\x1b]11;rgb:0e0e/1010/1313\x1b\\", "\x1b[I", "\x1b[O", "\x1b[<0;65;17M", "\x1b[<0;65;17m"]


@pytest.mark.parametrize("data", SEEN_ON_A_CLICK + [
    "\x1b[12;40R", "\x1b[?12;40;1R", "\x1b[0n", "\x1b[?2004;2$y", "\x1b[8;34;128t", "\x1b[?0u",
    "\x1bP1$r0m\x1b\\", "\x1b]4;1;rgb:ffff/0000/0000\x07", "\x1b[64;10;5M", "\x1b[M !!",
    "\x1b[<0;1;1M\x1b[<0;1;1m\x1b[<64;3;3M",
])
def test_reports_and_replies_are_not_typing(data: str) -> None:
    assert termlib.is_terminal_reply(data)
    assert termlib.is_terminal_reply(data.encode())


@pytest.mark.parametrize("data", ["a", "ls\r", "\r", "\x7f", "\x03", "\x1b", "\x1b[A", "\x1bOP", "\x1b[15~",
                                  "\x1b[200~pasted\x1b[201~", "привет", "\x1b[Ix", "x\x1b[<0;1;1M", ""])
def test_keys_and_pastes_are_typing(data: str) -> None:
    assert not termlib.is_terminal_reply(data)


def test_only_keys_and_pastes_on_the_socket_beat_the_timer(env, monkeypatch) -> None:
    """Marked by the page (`typed`) or, unmarked, read by the bytes: a report
    or a reply never beats; a key or a paste does, once each."""
    from backend import timeauto
    from backend.routers import terminal

    c, root, _ = env
    _on(c)
    beats: list[tuple[str, str]] = []
    monkeypatch.setattr(timeauto.of(c.app), "beat", lambda project, task_id="", source="page": beats.append((project, source)))
    monkeypatch.setattr(terminal.PtySession, "write", lambda self, data: None)   # nothing reaches a shell
    sid = c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha"}).json()["session"]["id"]
    tok = c.get("/api/terminal/state").json()["token"]

    def wait(n: int) -> None:
        deadline = time.time() + 5
        while len(beats) < n and time.time() < deadline:
            time.sleep(0.02)
        assert len(beats) == n, beats

    with c.websocket_connect(f"/ws/terminal/{sid}?token={tok}") as ws:
        for data in SEEN_ON_A_CLICK:
            ws.send_text(json.dumps({"type": "input", "data": data}))               # unmarked: the bytes say
            ws.send_text(json.dumps({"type": "input", "data": data, "typed": False}))
            ws.send_text(data)                                                    # a raw text frame
            ws.send_bytes(data.encode())                                          # a binary frame
        # The page's word wins: a "reply" that came from a key (Ctrl+F3) is typing,
        # and a key the page says is not typing (its own wheel report) is not.
        ws.send_text(json.dumps({"type": "input", "data": "x", "typed": False}))
        ws.send_text(json.dumps({"type": "input", "data": "\x1b[1;5R", "typed": True}))
        wait(1)
        ws.send_text(json.dumps({"type": "input", "data": "ls\r", "typed": True}))
        wait(2)
        ws.send_text(json.dumps({"type": "input", "data": "\x1b[200~a paste\x1b[201~"}))
        wait(3)
        ws.send_bytes(b"q")
        wait(4)
        ws.send_text("y")
        wait(5)
    assert beats == [("alpha", "terminal")] * 5
    c.post(f"/api/terminal/sessions/{sid}/close", json={})


# ---------------------------------------------------------------------------
# The terminal's colours, told to programs before any page is attached
# ---------------------------------------------------------------------------

# What Codex does at its start (tk_11bd239e): the device attributes, then the
# text and ground colours (OSC 10/11), answers read raw within a moment. It
# draws its input box in a shade of the ground; told nothing, no box. The
# script prints the answers it got as plain text.
ASK_GROUND = r"""
import os, select, sys, termios, time, tty
fd = os.open('/dev/tty', os.O_RDWR)
old = termios.tcgetattr(fd)
tty.setraw(fd)
os.write(fd, b'\x1b[c\x1b]10;?\x1b\\\x1b]11;?\x1b\\')
got, end = b'', time.time() + 1.0
while time.time() < end:
    r, _, _ = select.select([fd], [], [], 0.05)
    if r:
        got += os.read(fd, 1000)
termios.tcsetattr(fd, termios.TCSADRAIN, old)
import re
told = dict(re.findall(rb'\x1b\](1[01]);(rgb:[0-9a-f/]+)', got))
print('told-' + sys.argv[1], 'text=' + told.get(b'10', b'none').decode(), 'ground=' + told.get(b'11', b'none').decode())
"""


def test_scheme_colours_are_known_for_every_scheme_the_server_accepts() -> None:
    from backend import app_settings
    spec = next(s for s in app_settings.SPECS if s.key == "terminal.scheme")
    assert sorted(termlib.SCHEME_COLOURS) == sorted(spec.options)
    assert termlib.window_style({"terminal.scheme": "sp-paper"}) == "fg=#1F2522,bg=#F6F5F1"
    # No scheme, or one the server no longer knows: the terminal's own colours.
    assert termlib.window_style({}) == termlib.window_style({"terminal.scheme": "gone"}) == "fg=#E6E8EB,bg=#0E1013"


@needs_tmux
def test_a_program_started_before_any_page_attaches_is_told_the_schemes_colours(env) -> None:
    c, root, work = env
    _on(c)
    (work / "ask.py").write_text(ASK_GROUND, encoding="utf-8")
    import sys
    ask = f"{shlex.quote(sys.executable)} ask.py"
    # No socket is ever opened: tmux has no client to ask, as when an agent's
    # terminal opens and its command starts before the window attaches.
    s = _open(c, command=f"{ask} first", label="agent")
    got = _wait_screen(root, s["id"], "told-first")
    assert "told-first text=rgb:e6e6/e8e8/ebeb ground=rgb:0e0e/1010/1313" in got, got
    # A new scheme reaches the terminal already open: a program started now hears it.
    assert c.post("/api/settings", json={"values": {"terminal.scheme": "sp-paper"}}).status_code == 200
    termlib.type_into(root, _row(c, s["id"]) | {"backend": "tmux"}, f"{ask} again", enter=True)
    got = _wait_screen(root, s["id"], "told-again")
    assert "told-again text=rgb:1f1f/2525/2222 ground=rgb:f6f6/f5f5/f1f1" in got, got
    # And a terminal opened after the change is born with it.
    t = _open(c, command=f"{ask} new", label="next")
    assert "told-new text=rgb:1f1f/2525/2222 ground=rgb:f6f6/f5f5/f1f1" in _wait_screen(root, t["id"], "told-new")


def test_a_new_scheme_with_no_tmux_running_changes_nothing(env) -> None:
    c, root, _ = env
    # No terminal was opened: no tmux server, and none is started for this.
    assert c.post("/api/settings", json={"values": {"terminal.scheme": "nord"}}).status_code == 200
    if TMUX:
        assert termlib.tmux(root, "list-sessions").returncode != 0
