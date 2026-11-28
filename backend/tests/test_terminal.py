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
        termlib.tmux(root, "new-session", "-d", "-s", "mk-probe", "sleep 1; printf 'selected text\\n'; exec cat")
        for table in ("copy-mode", "copy-mode-vi"):
            keys = termlib.tmux(root, "list-keys", "-T", table).stdout
            assert "MouseDragEnd1Pane" not in keys
            assert "S-MouseDown1Pane" in keys
            assert all("copy-pipe" not in line for line in keys.splitlines()
                       if "DoubleClick1Pane" in line or "TripleClick1Pane" in line)
        assert not termlib.copy_selection(root, "probe")
        assert "selected text" in _wait_screen(root, "probe", "selected text")
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
@pytest.mark.parametrize("enable_raw", [True, False])
def test_first_socket_input_reaches_a_client_that_goes_raw_after_its_only_frame(env, monkeypatch, enable_raw) -> None:
    from backend.routers import terminal

    c, _, work = env
    _on(c)
    sid = c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha"}).json()["session"]["id"]
    armed = work / "enable-raw"
    received = work / "received-input"
    startup = """
import os
from pathlib import Path
import sys
import time
import tty

os.write(1, b'only frame before raw mode')
while not Path(sys.argv[1]).exists():
    time.sleep(0.01)
tty.setraw(0)
out = Path(sys.argv[2])
temp = out.with_suffix('.tmp')
temp.write_bytes(os.read(0, 4096))
temp.replace(out)
"""
    monkeypatch.setattr(termlib, "attach_argv", lambda *_: [sys.executable, "-c", startup, str(armed), str(received)])
    monkeypatch.setattr(terminal, "TMUX_INPUT_READY_TIMEOUT_S", 1)
    token = c.get("/api/terminal/state").json()["token"]
    with c.websocket_connect(f"/ws/terminal/{sid}?token={token}") as ws:
        assert ws.receive_bytes() == b"only frame before raw mode"
        ws.send_json({"type": "input", "data": "first input", "typed": True})
        if not enable_raw:
            assert ws.receive()["code"] == 4500
            assert not received.exists()
            return
        armed.touch()
        deadline = time.monotonic() + 2
        while not received.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert received.is_file(), "the first input was never written after the client's raw-mode transition"
        assert received.read_bytes() == b"first input"


def _set_range_test_prompt(root: Path, sid: str) -> None:
    # GitHub's macOS hostname once included A5. Keep that collision in both
    # fixtures so a prompt on its own cannot pass for the command's output.
    row = termlib.get(root, sid)
    assert row and termlib.type_into(root, row, "PS1='runner-A5$ '", enter=True)
    termlib.wait_for_prompt(root, sid)
    assert termlib.capture(root, sid)["text"].splitlines()[-1].strip() == "runner-A5$"


@pytest.mark.skipif(not TMUX, reason="tmux is not installed")
def test_a_wrapped_line_above_does_not_shift_the_lines_cut_out(env) -> None:
    """What the page copies goes by the screen's rows. A command wider than the
    pane takes two of them; on CI's macOS a long machine name in the prompt did
    this now and then, and only then did the test above fail."""
    c, root, _ = env
    _on(c)
    sid = c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha"}).json()["session"]["id"]
    termlib.wait_for_prompt(root, sid)
    _set_range_test_prompt(root, sid)
    tok = c.get("/api/terminal/state").json()["token"]
    with c.websocket_connect(f"/ws/terminal/{sid}?token={tok}") as ws:
        ws.send_text(json.dumps({"type": "input", "data": f"printf 'A%s\\n' 1 2 3 4 5 # {'x' * 240}\r"}))
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and "A5" not in termlib.capture(root, sid)["text"].splitlines():
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
    _set_range_test_prompt(root, sid)
    tok = c.get("/api/terminal/state").json()["token"]
    log = root / "pane-bytes.log"
    termlib.tmux(root, "pipe-pane", "-t", termlib.PREFIX + sid, f"cat >> {shlex.quote(str(log))}")
    # Typed over the socket, as the page types: the Enter stamps the history.
    with c.websocket_connect(f"/ws/terminal/{sid}?token={tok}") as ws:
        ws.send_text(json.dumps({"type": "input", "data": "printf 'A%s\\n' 1 2 3 4 5\r"}))
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and "A5" not in termlib.capture(root, sid)["text"].splitlines():
            time.sleep(0.1)
        inside = _pane_state(root, sid, log)
    screen = termlib.capture(root, sid)
    after = _pane_state(root, sid, log)
    assert screen["lines"] >= 5 and "A5" in screen["text"].splitlines(), f"INSIDE THE SOCKET\n{inside}\nAFTER IT\n{after}"

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
    from backend.app_settings import MAX_TERMINAL_SESSIONS
    from backend.routers.terminal import MAX_TERMINAL_VIEWS, _PTY_READS, _read_pty

    # Every plain terminal and every tmux view can hold a read at once.
    assert _PTY_READS._max_workers >= MAX_TERMINAL_SESSIONS + MAX_TERMINAL_VIEWS

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


def _screen(root: Path, sid: str, *, ansi: bool = False) -> str:
    flags = ("-p", "-e") if ansi else ("-p",)
    return termlib.tmux(root, "capture-pane", *flags, "-t", termlib.PREFIX + sid).stdout


def _wait_screen(root: Path, sid: str, text: str, timeout: float = 5.0, *, ansi: bool = False) -> str:
    end = time.time() + timeout
    while time.time() < end:
        got = _screen(root, sid, ansi=ansi)
        if text in got:
            return got
        time.sleep(0.1)
    return _screen(root, sid, ansi=ansi)


@needs_tmux
@pytest.mark.parametrize("apply_resize", [True, False])
def test_tmux_input_after_resize_waits_for_the_shells_actual_size(env, monkeypatch, apply_resize: bool) -> None:
    from threading import Event

    from backend.routers import terminal

    c, root, work = env
    _on(c)
    sid = _open(c)["id"]
    target = termlib.PREFIX + sid
    # Tmux may redraw at the outer size before resizing the shell's own tty.
    # Hold its inner width manually until the test releases it.
    window = termlib.tmux(root, "resize-window", "-t", target, "-x", "63", "-y", "33")
    assert window.returncode == 0, window.stderr
    size_file = work / "typed-size"
    pending = shlex.quote(str(size_file.with_suffix(".pending")))
    command = f"stty size > {pending} && mv {pending} {shlex.quote(str(size_file))}\r"
    delivered = Event()
    writes = []
    write = terminal.PtySession.write

    def observe_write(session, data):
        if session.session_id == sid and data == command.encode():
            writes.append(data)
            delivered.set()
        return write(session, data)

    monkeypatch.setattr(terminal.PtySession, "write", observe_write)
    token = c.get("/api/terminal/state").json()["token"]
    with c.websocket_connect(f"/ws/terminal/{sid}?token={token}&cols=63&rows=33") as ws:
        ws.receive_bytes()
        ws.send_json({"type": "resize", "cols": 128, "rows": 33})
        ws.send_json({"type": "input", "data": command, "typed": True})
        assert not delivered.wait(0.15), "input reached the shell before its tty was resized"
        if apply_resize:
            window = termlib.tmux(root, "resize-window", "-t", target, "-x", "128", "-y", "33")
            assert window.returncode == 0, window.stderr
        assert delivered.wait(2), "input was lost while waiting for the pane"
        deadline = time.monotonic() + 2
        while not size_file.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert size_file.read_text(encoding="utf-8").split() == ["33", "128" if apply_resize else "63"]
        assert writes == [command.encode()]


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


@pytest.mark.parametrize("change", ["owner", "saved_command", "link"])
def test_confirmed_agent_wake_defers_when_the_selected_terminal_changes(env, monkeypatch, change):
    client, root, work = env
    _on(client)
    owner = "cc-11223344"
    sid = "t1234abcd"
    termlib.put(root, {"id": sid, "cwd": str(work), "project": "alpha", "kind": "shell",
                       "backend": "plain", "asleep": True, "agent_id": owner,
                       "created": "2026-09-18T12:00:00", "wake": ""})
    links = {}
    monkeypatch.setattr(termlib, "agent_links", lambda *_args, **_kwargs: links)
    before = _row(client, sid)
    if change == "owner":
        termlib.put(root, {"id": sid, "agent_id": "cc-55667788"})
    elif change == "saved_command":
        termlib.put(root, {"id": sid, "wake": "echo changed"})
    else:
        links[sid] = {"agent_id": "cc-55667788"}

    resp = client.post(f"/api/terminal/sessions/{sid}/wake", json={
        "actor": "operator", "expected_agent": owner, "wake_revision": before["wake_revision"],
        "expected_cwd": before["wake_cwd"],
    })

    assert resp.status_code == 409, resp.text
    assert termlib.get(root, sid)["asleep"] is True


def test_confirmed_wake_stops_if_the_displayed_worktree_disappears(env):
    client, root, work = env
    _on(client)
    checkout = work / "checkout"
    checkout.mkdir()
    owner = "cc-11223344"
    sid = "t1234abcd"
    termlib.put(root, {"id": sid, "cwd": str(checkout.resolve()), "project": "alpha", "kind": "shell",
                       "backend": "plain", "asleep": True, "agent_id": owner, "wake": ""})
    selected = _row(client, sid)
    checkout.rmdir()

    resp = client.post(f"/api/terminal/sessions/{sid}/wake", json={
        "actor": "operator", "expected_agent": owner, "wake_revision": selected["wake_revision"],
        "expected_cwd": selected["wake_cwd"],
    })

    assert resp.status_code == 409, resp.text
    assert termlib.get(root, sid)["asleep"] is True


def test_resume_shows_the_fallback_folder_and_refuses_a_changed_destination(env, monkeypatch):
    from backend.db import ViewStore

    client, root, work = env
    _on(client)
    owner = "cc-11223344"
    monkeypatch.setattr(ViewStore, "agents", lambda _self: [
        {"agent_id": owner, "tool": "claude-code", "session_ref": "capture",
         "project": "alpha", "cwd": str(work / "gone-checkout")},
    ])
    monkeypatch.setattr(termlib, "resume_command", lambda _tool, _ref: "echo resumed-fixture")

    preview = client.get(f"/api/terminal/resume/{owner}")
    assert preview.status_code == 200, preview.text
    assert preview.json()["cwd"] == str(work.resolve())
    alternate = root / "alternate"
    alternate.mkdir()
    (root / "integrations.csv").write_text(f"project,path\nalpha,{alternate}\n", encoding="utf-8")

    resp = client.post("/api/terminal/sessions", json={
        "actor": "operator", "kind": "resume", "agent": owner,
        "expected_cwd": preview.json()["cwd"], "resume_revision": preview.json()["resume_revision"],
    })

    assert resp.status_code == 409, resp.text
    assert termlib.rows(root) == []

    updated = client.get(f"/api/terminal/resume/{owner}").json()
    assert updated["cwd"] == str(alternate.resolve())
    opened = client.post("/api/terminal/sessions", json={
        "actor": "operator", "kind": "resume", "agent": owner,
        "expected_cwd": updated["cwd"], "resume_revision": updated["resume_revision"],
    })
    assert opened.status_code == 201, opened.text
    assert opened.json()["session"]["cwd"] == updated["cwd"]


def test_confirmed_wake_binds_a_recorded_alias_to_its_resolved_folder(env):
    client, root, work = env
    _on(client)
    alias = root / "checkout"
    try:
        alias.symlink_to(work, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            raise
        pytest.skip("a symlink needs privileges on Windows")
    owner = "cc-11223344"
    sid = "t1234abcd"
    termlib.put(root, {"id": sid, "cwd": str(alias), "project": "alpha", "kind": "shell",
                       "backend": "plain", "asleep": True, "agent_id": owner, "wake": ""})

    selected = _row(client, sid)
    assert selected.get("wake_cwd") == str(work.resolve())
    body = {"actor": "operator", "expected_agent": owner, "wake_revision": selected["wake_revision"],
            "expected_cwd": selected["wake_cwd"]}
    other = work / "other"
    other.mkdir()
    alias.unlink()
    alias.symlink_to(other, target_is_directory=True)

    response = client.post(f"/api/terminal/sessions/{sid}/wake", json=body)
    assert response.status_code == 409, response.text
    assert termlib.get(root, sid)["asleep"] is True

    alias.unlink()
    alias.symlink_to(work, target_is_directory=True)
    response = client.post(f"/api/terminal/sessions/{sid}/wake", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["session"]["cwd"] == str(work.resolve())


@unix_pty
@pytest.mark.parametrize("keep", ["plain", pytest.param("tmux", marks=needs_tmux)])
def test_confirmed_resume_runs_in_the_shown_folder_after_a_profile_changes_cwd(env, monkeypatch, keep):
    from backend.db import ViewStore

    client, root, work = env
    _on(client)
    assert client.post("/api/settings", json={"values": {"terminal.keep": keep}}).status_code == 200
    checkout = work / "the chat's worktree"
    checkout.mkdir()
    profile_folder = root / "profile-default"
    profile_folder.mkdir()
    profile = root / "shell-profile"
    profile.write_text(f"cd -- {shlex.quote(str(profile_folder))}\n", encoding="utf-8")
    shell = root / "bash"
    shell.write_text(
        f"#!/bin/sh\nexec /bin/bash --noprofile --rcfile {shlex.quote(str(profile))} -i\n",
        encoding="utf-8",
    )
    shell.chmod(0o755)
    monkeypatch.setenv("SHELL", str(shell))
    owner = "cc-11223344"
    output = root / "resume-directory"
    monkeypatch.setattr(ViewStore, "agents", lambda _self: [
        {"agent_id": owner, "tool": "claude-code", "session_ref": "capture",
         "project": "alpha", "cwd": str(checkout)},
    ])
    monkeypatch.setattr(termlib, "resume_command", lambda _tool, _ref: f"pwd -P > {shlex.quote(str(output))}")
    preview = client.get(f"/api/terminal/resume/{owner}").json()
    assert preview["cwd"] == str(checkout.resolve())

    response = client.post("/api/terminal/sessions", json={
        "actor": "operator", "kind": "resume", "agent": owner, "expected_cwd": preview["cwd"],
        "resume_revision": preview["resume_revision"],
    })

    assert response.status_code == 201, response.text
    end = time.monotonic() + 8
    while time.monotonic() < end and (not output.exists() or output.stat().st_size == 0):
        time.sleep(0.05)
    assert output.read_text(encoding="utf-8").strip() == str(checkout.resolve())


def test_simultaneous_resume_confirmations_reuse_one_terminal(env, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, Lock

    from backend.db import ViewStore

    client, root, work = env
    _on(client)
    assert client.post("/api/settings", json={"values": {"terminal.keep": "plain"}}).status_code == 200
    owner = "cc-11223344"
    monkeypatch.setattr(ViewStore, "agents", lambda _self: [
        {"agent_id": owner, "tool": "claude-code", "session_ref": "capture",
         "project": "alpha", "cwd": str(work)},
    ])
    monkeypatch.setattr(termlib, "resume_command", lambda _tool, _ref: "echo resumed-fixture")
    preview = client.get(f"/api/terminal/resume/{owner}").json()
    body = {"actor": "operator", "kind": "resume", "agent": owner, "expected_cwd": preview["cwd"],
            "resume_revision": preview["resume_revision"]}
    first_entered, second_entered, release_first = Event(), Event(), Event()
    counter_lock = Lock()
    opens = 0
    open_session = termlib.open_session

    def pause_first(*args, **kwargs):
        nonlocal opens
        with counter_lock:
            opens += 1
            first = opens == 1
        if first:
            first_entered.set()
            assert release_first.wait(10)
        else:
            second_entered.set()
        return open_session(*args, **kwargs)

    monkeypatch.setattr(termlib, "open_session", pause_first)

    def approve():
        return client.post("/api/terminal/sessions", json=body)

    with ThreadPoolExecutor(max_workers=2) as threads:
        first = threads.submit(approve)
        try:
            assert first_entered.wait(10)
            second = threads.submit(approve)
            second_entered.wait(2)
        finally:
            release_first.set()
        responses = [first.result(timeout=15), second.result(timeout=15)]

    assert opens == 1
    assert all(resp.status_code == 201 for resp in responses)
    results = [resp.json() for resp in responses]
    assert results[0]["session"]["id"] == results[1]["session"]["id"]
    assert sorted(r["existing"] for r in results) == [False, True]
    assert len(termlib.rows(root)) == 1


@unix_pty
def test_confirmed_command_aborts_if_a_component_is_replaced_after_confirmation(tmp_path):
    import subprocess

    parent = tmp_path / "chosen-parent"
    checkout = parent / "the chat's worktree"
    checkout.mkdir(parents=True)
    alternative = tmp_path / "alternate-parent"
    (alternative / checkout.name).mkdir(parents=True)
    marker = tmp_path / "launched"
    approved = str(checkout.resolve())
    command = termlib.launch_in_cwd(f"printf ran > {shlex.quote(str(marker))}", approved, "bash")

    parent.rename(tmp_path / "previous-parent")
    parent.symlink_to(alternative, target_is_directory=True)
    outcome = subprocess.run(["/bin/bash", "-c", command], cwd=tmp_path,
                             capture_output=True, timeout=5, check=False)

    assert outcome.returncode != 0 and not marker.exists()


@pytest.mark.skipif(not TMUX, reason="tmux is not installed")
def test_terminal_diagnostic_is_operator_only_and_changes_only_its_own_file(env) -> None:
    c, root, work = env
    _on(c)
    tok = c.get("/api/terminal/state").json()["token"]
    got = c.post("/api/terminal/sessions", json={
        "kind": "shell", "project": "alpha", "command": "printf '\\033[31mdiagnostic-marker\\033[0m\\n'; read -r diagnostic_hold",
    })
    assert got.status_code == 201
    sid = got.json()["session"]["id"]
    route = f"/api/terminal/sessions/{sid}/diagnostics"
    browser = {
        "capturedAt": "2026-11-28T00:00:00.000Z",
        "xterm": {"live": {"rows": 24, "cols": 80, "viewportY": 0, "rowsByIndex": []}, "reader": None},
        "dom": {"live": ["diagnostic-marker"], "reader": None},
        "scrollLayer": {"live": {"pos": 0, "target": 0, "max": 0, "rowH": 19}, "reader": None},
    }
    target = termlib.PREFIX + sid

    def files(folder: Path) -> dict:
        return {p.relative_to(folder): p.read_bytes() for p in folder.rglob("*") if p.is_file()}

    with c.websocket_connect(f"/ws/terminal/{sid}?token={tok}&cols=80&rows=24") as ws:
        ws.receive_bytes()
        coloured = "\x1b[31mdiagnostic-marker"
        tmux_before = _wait_screen(root, sid, coloured, ansi=True)
        assert coloured in tmux_before
        before = files(root)
        before_work = files(work)
        pane_before = termlib.pane_pos(root, sid)
        other = TestClient(c.app)
        try:
            other.cookies.clear()
            refused = other.post(route, json=browser)
        finally:
            other.close()
        assert refused.status_code == 403
        assert files(root) == before

        response = c.post(route, json={**browser, "path": str(work / "outside.json")})
        assert response.status_code == 201, response.text
        assert response.json()["owner_only"] is (os.name != "nt")
        path = Path(response.json()["path"])
        assert path.parent == root.resolve() / "diagnostics" and sid in path.name
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["terminal"] == sid and saved["browser"] == browser
        assert saved["server"]["pane"]["flags"]["alternate_on"] is False
        assert "mouse_any_flag" in saved["server"]["pane"]["flags"]
        assert saved["server"]["panePty"] == {"rows": 24, "cols": 80}
        assert any(client["pty"] == {"rows": 24, "cols": 80} for client in saved["server"]["tmuxClients"])
        assert saved["server"]["tmuxCapture"] == tmux_before
        assert termlib.pane_pos(root, sid) == pane_before
        assert termlib.tmux_read(root, "capture-pane", "-p", "-e", "-t", target).stdout == tmux_before
        assert files(root) == {**before, path.relative_to(root.resolve()): path.read_bytes()}
        assert files(work) == before_work


@pytest.mark.skipif(os.name == "nt", reason="a symlink needs privileges on Windows")
def test_terminal_diagnostic_rejects_a_diagnostics_folder_outside_the_data_root(env) -> None:
    c, root, work = env
    _on(c)
    got = c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha"})
    assert got.status_code == 201
    sid = got.json()["session"]["id"]
    (root / "diagnostics").symlink_to(work, target_is_directory=True)
    response = c.post(f"/api/terminal/sessions/{sid}/diagnostics", json={
        "capturedAt": "2026-11-28T00:00:00.000Z", "xterm": {}, "dom": {}, "scrollLayer": {},
    })
    assert response.status_code == 409
    assert list(work.iterdir()) == []


@pytest.mark.skipif(os.open not in os.supports_dir_fd, reason="requires POSIX directory descriptors")
def test_terminal_diagnostics_refuse_a_folder_changed_during_capture(tmp_path, monkeypatch) -> None:
    from fastapi import HTTPException

    from backend import terminal_diagnostics

    root = tmp_path / "data"
    folder = root / "diagnostics"
    previous = root / "previous-diagnostics"
    other = tmp_path / "other"
    folder.mkdir(parents=True)
    other.mkdir()

    def changed_directory(*_args):
        folder.rename(previous)
        folder.symlink_to(other, target_is_directory=True)
        return {}

    monkeypatch.setattr(terminal_diagnostics, "_tmux_snapshot", changed_directory)
    with pytest.raises(HTTPException) as error:
        terminal_diagnostics.save(root, "te2e", "tmux", {}, None)
    assert error.value.status_code == 409
    assert list(other.iterdir()) == list(previous.iterdir()) == []


def test_terminal_limit_reports_live_sessions_and_can_be_raised(env, monkeypatch) -> None:
    import subprocess

    from backend.routers import terminal

    c, _root, _work = env
    monkeypatch.setattr(terminal, "SUPPORTED", True)
    _on(c)
    assert c.get("/api/terminal/state").json().get("max_sessions") == 36
    for invalid in (-1, 257, 2.5, "2", True):
        refused = c.post("/api/settings", json={"values": {"terminal.max_sessions": invalid}})
        assert refused.status_code == 422
        assert "terminal.max_sessions" in refused.json()["detail"]
    assert c.post("/api/settings", json={"values": {"terminal.max_sessions": 2}}).status_code == 200
    live = [
        {"id": "recent", "state": "working", "project": "alpha", "agent_id": "cc-recent",
         "label": "Recent", "backend": "tmux", "created": "2026-11-26T12:00:00", "last_output": 200.0},
        {"id": "idle", "state": "shell", "project": "alpha",
         "label": "Idle", "created": "2026-11-25T12:00:00", "last_output": 100.0},
        {"id": "asleep", "state": "asleep", "last_output": 0.0},
    ]
    opened = []
    monkeypatch.setattr(termlib, "listing", lambda *_: live)
    monkeypatch.setattr(termlib, "tmux_read", lambda *_: subprocess.CompletedProcess(
        [], 0, stdout=f"{termlib.PREFIX}recent\t1\t150\n", stderr=""))

    def open_session(*_args, **kwargs):
        opened.append(kwargs)
        return {"id": "new", "backend": "tmux"}

    monkeypatch.setattr(termlib, "open_session", open_session)
    req = {"kind": "shell", "project": "alpha"}
    refused = c.post("/api/terminal/sessions", json=req)
    assert refused.status_code == 429
    body = refused.json()
    assert isinstance(body["detail"], str)
    assert (body["count"], body["limit"]) == (2, 2)
    assert [row["id"] for row in body["sessions"]] == ["idle", "recent"]
    recent = body["sessions"][1]
    assert recent["agent_id"] == "cc-recent"
    assert recent["created"] == "2026-11-26T12:00:00"
    assert recent["last_activity"] == 200.0
    assert recent["running"] is True
    assert recent["attached"] is True
    assert not opened
    assert c.post("/api/settings", json={"values": {"terminal.max_sessions": 3}}).status_code == 200
    assert c.post("/api/terminal/sessions", json=req).status_code == 201
    assert len(opened) == 1
    assert c.post("/api/settings", json={"values": {"terminal.max_sessions": 0}}).status_code == 200
    assert c.get("/api/terminal/state").json()["max_sessions"] == 0
    assert c.post("/api/terminal/sessions", json=req).status_code == 201
    assert len(opened) == 2


@pytest.mark.parametrize(("state", "attached"), [("working", False), ("shell", True)])
def test_closing_from_the_terminal_limit_requires_confirmation(env, monkeypatch, state, attached) -> None:
    import subprocess

    c, _root, _work = env
    monkeypatch.setattr(termlib, "listing", lambda *_: [
        {"id": "sid", "state": state, "backend": "tmux"},
    ])
    monkeypatch.setattr(termlib, "tmux_read", lambda *_: subprocess.CompletedProcess(
        [], 0, stdout=f"{termlib.PREFIX}sid\t{int(attached)}\t100\n", stderr=""))
    closed = []
    monkeypatch.setattr(termlib, "close", lambda _root, sid: closed.append(sid))
    path = "/api/terminal/sessions/sid/close"
    assert c.post(path, json={"from_limit": True}).status_code == 409
    assert closed == []
    assert c.post(path, json={"from_limit": True, "confirmed": True}).status_code == 200
    assert closed == ["sid"]


@pytest.mark.parametrize("host_readable", [True, False])
def test_terminal_limit_memory_counts_live_process_trees_without_writing(env, monkeypatch, host_readable) -> None:
    from types import SimpleNamespace

    import psutil

    c, root, _work = env
    now = time.time()
    termlib.put(root, {"id": "claude", "label": "Review", "project": "alpha",
                       "backend": "tmux", "kind": "start", "agent_id": "cc-aaaa1111",
                       "last_opened": now - 20})
    termlib.put(root, {"id": "shell", "label": "Shell", "project": "alpha",
                       "backend": "tmux", "kind": "shell"})
    termlib.put(root, {"id": "sleep", "backend": "tmux", "asleep": True})
    monkeypatch.setattr(termlib, "tmux_panes", lambda _root: {
        "claude": {"pid": "11", "fg": "claude", "activity": now - 1, "dead": False},
        "shell": {"pid": "21", "fg": "sh", "activity": now - 1200, "dead": False},
    })
    monkeypatch.setattr(termlib, "agent_links", lambda _root: {})
    class Process:
        def __init__(self, pid):
            self.pid = pid

        def memory_info(self):
            return SimpleNamespace(rss={11: 120, 12: 80, 21: 5}[self.pid])

    snapshots = []

    def parent_snapshot():
        snapshots.append(True)
        return {11: 1, 12: 11, 21: 1}

    def host_memory():
        if not host_readable:
            raise OSError("host memory unavailable")
        return SimpleNamespace(total=1000, available=500)

    monkeypatch.setattr(psutil, "Process", Process)
    monkeypatch.setattr(psutil, "_ppid_map", parent_snapshot, raising=False)
    monkeypatch.setattr(psutil, "virtual_memory", host_memory)
    registry = termlib.registry_path(root)
    before = registry.read_bytes(), registry.stat().st_mtime_ns
    response = c.get("/api/terminal/limit")
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["count"], data["limit"]) == (2, 36)
    assert snapshots == [True]
    assert data["memory"]["total"] == (1000 if host_readable else None)
    assert data["memory"]["available"] == (500 if host_readable else None)
    assert data["memory"]["used"] == 205
    assert data["memory"]["kinds"]["claude"] == {"count": 1, "bytes": 200, "measured": 1}
    assert data["memory"]["kinds"]["shell"] == {"count": 1, "bytes": 5, "measured": 1}
    sessions = {row["id"]: row for row in data["sessions"]}
    assert sessions["claude"]["last_opened"] == now - 20
    assert sessions["claude"]["recent_output"] is True
    assert sessions["shell"]["recent_output"] is False
    assert (registry.read_bytes(), registry.stat().st_mtime_ns) == before


def test_terminal_limit_excerpts_are_read_only(env, monkeypatch) -> None:
    from tests.conftest import make_chat

    c, root, _work = env
    agent = "cc-aaaa1111"
    make_chat(root, "alpha", agent, [
        (f"2026-11-20T10:0{i}:00", f"User prompt {i}", f"Agent output {i}") for i in range(1, 9)
    ])
    c.app.state.store.rebuild()
    termlib.put(root, {"id": "chat", "backend": "tmux", "project": "alpha",
                       "kind": "resume", "agent_id": agent})
    termlib.put(root, {"id": "shell", "backend": "tmux", "project": "alpha", "kind": "shell"})
    monkeypatch.setattr(termlib, "agent_links", lambda _root: {})
    monkeypatch.setattr(termlib, "pane_pos", lambda *_: {"history": 50, "cursor": 22})
    monkeypatch.setattr(termlib, "capture", lambda _root, sid, a, b: {
        "text": "\n".join(f"Line {i}" for i in range(a, b + 1)),
    })

    def tree():
        return {p.relative_to(root): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in root.rglob("*") if p.is_file()}

    before = tree()
    chat = c.get("/api/terminal/sessions/chat/excerpts")
    shell = c.get("/api/terminal/sessions/shell/excerpts")
    assert chat.status_code == shell.status_code == 200
    assert [item["text"] for item in chat.json()["first"]] == [f"User prompt {i}" for i in range(1, 4)]
    assert [item["text"] for item in chat.json()["last"]] == [f"User prompt {i}" for i in range(6, 9)]
    assert [item["text"] for item in shell.json()["first"]] == ["Line 0", "Line 1", "Line 2"]
    assert [item["text"] for item in shell.json()["last"]] == ["Line 70", "Line 71", "Line 72"]
    assert tree() == before


@pytest.mark.parametrize("path", ["/api/terminal/limit", "/api/terminal/sessions/private/excerpts"])
def test_terminal_recovery_reads_require_the_operator_cookie(env, path) -> None:
    c, root, _work = env
    termlib.put(root, {"id": "private", "label": "Private terminal", "backend": "plain"})
    allowed = c.get(path)
    assert allowed.status_code == 200
    assert allowed.headers["cache-control"] == "no-store"

    c.cookies.clear()
    refused = c.get(path)
    assert refused.status_code in (401, 403)
    assert "Private terminal" not in refused.text


@pytest.mark.parametrize("path", ["/api/terminal/limit", "/api/terminal/sessions/idle/excerpts"])
def test_terminal_recovery_reads_leave_due_tasks_untouched(env, monkeypatch, path) -> None:
    from backend import csvio, tasklib
    from backend.entities import ENTITIES

    c, root, _work = env
    termlib.put(root, {"id": "idle", "backend": "plain"})
    tasks = root / "tasks.csv"
    csvio.append_row(tasks, ENTITIES["task"].columns, {
        "id": "tk_scheduled", "project": "alpha", "title": "Scheduled",
        "status": "done", "resurface_on": "2000-01-01", "resurface_to": "todo",
    })
    before = tasks.read_bytes(), tasks.stat().st_mtime_ns
    monkeypatch.setattr(tasklib, "_last_sweep", 0.0)

    reply = c.get(path)
    assert reply.status_code == 200
    assert (tasks.read_bytes(), tasks.stat().st_mtime_ns) == before


def test_terminal_recovery_activity_counts_indexed_turns(env, monkeypatch) -> None:
    from datetime import datetime, timedelta

    from tests.conftest import make_chat

    c, root, _work = env
    agent = "cc-aaaa1111"
    recent = datetime.now().replace(second=0, microsecond=0) - timedelta(hours=1)
    old = recent - timedelta(days=8)
    make_chat(root, "alpha", agent, [
        (old.isoformat(), "An older prompt", "Older answer"),
        (recent.isoformat(), "A current prompt", "Current answer"),
    ])
    c.app.state.store.rebuild()
    termlib.put(root, {"id": "chat", "project": "alpha", "agent_id": agent,
                       "backend": "tmux", "kind": "resume"})
    monkeypatch.setattr(termlib, "agent_links", lambda _root: {})
    monkeypatch.setattr(termlib, "tmux_panes", lambda _root: {
        "chat": {"fg": "claude", "activity": recent.timestamp() - 60, "dead": False},
    })

    reply = c.get("/api/terminal/limit")
    assert reply.status_code == 200, reply.text
    (session,) = reply.json()["sessions"]
    assert 1 <= session["activity"] < 2
    assert session["last_activity"] == recent.timestamp()


@pytest.mark.parametrize("observation", ["tmux_timeout", "missing_pane", "attachment_timeout"])
def test_limit_close_requires_confirmation_when_tmux_state_is_unknown(env, monkeypatch, observation) -> None:
    from subprocess import CompletedProcess

    c, root, _work = env
    sid = "protected"
    termlib.put(root, {"id": sid, "backend": "tmux"})
    panes = {} if observation != "attachment_timeout" else {
        sid: {"fg": "sh", "activity": 0, "dead": False},
    }
    monkeypatch.setattr(termlib, "tmux_panes", lambda _root: panes)
    lookup = (CompletedProcess([], 0, stdout=f"{termlib.PREFIX}{sid}\t0\t0\n", stderr="")
              if observation == "missing_pane" else CompletedProcess([], 1, stdout="", stderr="tmux timed out"))
    monkeypatch.setattr(termlib, "tmux_read", lambda *_: lookup)
    closed = []
    monkeypatch.setattr(termlib, "close", lambda _root, name: closed.append(name))

    path = f"/api/terminal/sessions/{sid}/close"
    assert c.post(path, json={"from_limit": True}).status_code == 409
    assert not closed
    assert c.post(path, json={"from_limit": True, "confirmed": True}).status_code == 200
    assert closed == [sid]


@unix_pty
@pytest.mark.parametrize("observation", ["foreground", "registry"])
def test_limit_close_preserves_a_quiet_pty_when_observation_fails(env, monkeypatch, observation) -> None:
    from backend.routers import terminal

    c, root, _work = env
    _on(c)
    monkeypatch.setattr(termlib, "uses_tmux", lambda _settings: False)
    open_pty = terminal.open_pty
    held = {}

    def quiet_pty(sid, _argv, cwd, cols, rows, child_env):
        session = open_pty(sid, [sys.executable, "-c", "import time; time.sleep(30)"], cwd, cols, rows, child_env)
        session.last_output = 0
        held[sid] = session
        return session

    monkeypatch.setattr(terminal, "open_pty", quiet_pty)
    opened = c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha"})
    assert opened.status_code == 201, opened.text
    sid = opened.json()["session"]["id"]
    session = held[sid]
    assert session.alive() and not session.subscribers

    with monkeypatch.context() as failed:
        if observation == "foreground":
            failed.setattr(termlib, "foreground_of_fd", lambda _fd: "")
            (candidate,) = c.get("/api/terminal/limit").json()["sessions"]
            assert candidate["foreground_known"] is False
        else:
            read_json = termlib.safe_read_json

            def unreadable(path, **kwargs):
                if path == termlib.registry_path(root):
                    raise PermissionError("terminal registry unreadable")
                return read_json(path, **kwargs)

            failed.setattr(termlib, "safe_read_json", unreadable)
            # A missing handle alone cannot rule out an off-process tmux session.
            unknown = c.post("/api/terminal/sessions/unknown/close", json={"from_limit": True})
            assert unknown.status_code == 409, unknown.text

        path = f"/api/terminal/sessions/{sid}/close"
        reply = c.post(path, json={"from_limit": True})
        assert reply.status_code == 409, reply.text
        assert not session.closed and session.alive()

    assert termlib.get(root, sid) is not None
    assert c.post(path, json={"from_limit": True, "confirmed": True}).status_code == 200
    assert session.closed


@unix_pty
def test_limit_close_sees_a_plain_view_attaching_before_replay(env, monkeypatch) -> None:
    import threading

    from backend.routers import terminal

    c, root, work = env
    _on(c)
    sid = "attaching"
    termlib.put(root, {"id": sid, "backend": "plain", "cwd": str(work)})
    monkeypatch.setattr(termlib, "listing", lambda *_: [
        {"id": sid, "backend": "plain", "state": "shell", "last_output": 0},
    ])
    attached = threading.Event()
    proceed = threading.Event()
    run_in_threadpool = terminal.run_in_threadpool

    async def pause_before_replay(function, *args, **kwargs):
        result = await run_in_threadpool(function, *args, **kwargs)
        if function.__name__ == "_attach":
            attached.set()
            await run_in_threadpool(proceed.wait, 15)
        return result

    monkeypatch.setattr(terminal, "run_in_threadpool", pause_before_replay)
    token = c.get("/api/terminal/state").json()["token"]
    with c.websocket_connect(f"/ws/terminal/{sid}?token={token}"):
        try:
            assert attached.wait(10)
            refused = c.post(f"/api/terminal/sessions/{sid}/close", json={"from_limit": True})
            assert refused.status_code == 409, refused.text
            assert termlib.get(root, sid)
        finally:
            proceed.set()


def _resume_and_limit_close(root: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from backend.db import ViewStore
    from backend.server import operator_cookie

    os.environ["SHELL"] = "/bin/sh"
    work = root / "projects" / "alpha"
    work.mkdir(parents=True)
    owner = "cc-11223344"
    app = create_app(data_root=root, watch=False)
    with pytest.MonkeyPatch.context() as patch, TestClient(app, base_url="http://127.0.0.1:8123") as client:
        client.cookies.set(*operator_cookie(app))
        patch.setattr(ViewStore, "agents", lambda _self: [
            {"agent_id": owner, "tool": "claude-code", "session_ref": "capture",
             "project": "alpha", "cwd": str(work)},
        ])
        patch.setattr(termlib, "resume_command", lambda _tool, _ref: "echo resumed-fixture")
        _on(client)
        configured = client.post("/api/settings", json={"values": {
            "terminal.keep": "plain", "terminal.max_sessions": 2,
        }})
        assert configured.status_code == 200, configured.text
        previous = _open(client, agent=owner, role="chat")
        preview = client.get(f"/api/terminal/resume/{owner}").json()
        start = Barrier(2)

        def resume():
            start.wait(timeout=10)
            return client.post("/api/terminal/sessions", json={
                "kind": "resume", "actor": "operator", "agent": owner,
                "expected_cwd": preview["cwd"], "resume_revision": preview["resume_revision"],
            })

        def panel_close():
            start.wait(timeout=10)
            return client.post(f"/api/terminal/sessions/{previous['id']}/close", json={
                "actor": "operator", "from_limit": True, "confirmed": True,
            })

        with ThreadPoolExecutor(max_workers=2) as threads:
            resuming = threads.submit(resume)
            closing = threads.submit(panel_close)
            opened = resuming.result(timeout=10)
            closed = closing.result(timeout=10)
        assert opened.status_code == 201, opened.text
        assert closed.status_code == 200, closed.text
        current = opened.json()["session"]
        assert current["id"] != previous["id"] and current["agent_id"] == owner
        assert [row["id"] for row in termlib.rows(root)] == [current["id"]]


def test_resume_and_limit_panel_close_finish_without_deadlocking(tmp_path):
    import subprocess

    # A deadlock in server threads must not stall pytest's TestClient teardown.
    fixture = ("import runpy, sys; from pathlib import Path; "
               "runpy.run_path(sys.argv[1])['_resume_and_limit_close'](Path(sys.argv[2]))")
    result = subprocess.run(
        [sys.executable, "-c", fixture, str(Path(__file__).resolve()), str(tmp_path / "data")],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=35, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("point", ["preflight", "launch"])
def test_confirmed_windows_paths_compare_canonical_spelling_exactly(tmp_path, monkeypatch, point):
    import pathlib

    class WindowsFolder(pathlib.PureWindowsPath):
        def resolve(self, *, strict=False):
            return self

        def is_dir(self):
            return True

    approved = r"C:\projects\Agent"
    changed = r"C:\projects\agent"
    assert WindowsFolder(approved) == WindowsFolder(changed)

    if point == "preflight":
        monkeypatch.setattr(termlib, "Path", WindowsFolder)
        monkeypatch.setattr(termlib, "resolve_cwd", lambda *_args: WindowsFolder(changed))
        monkeypatch.setattr(termlib, "uses_tmux", lambda _settings: False)
        monkeypatch.setattr(termlib, "put", lambda _root, row: row)
        with pytest.raises(termlib.CwdChangedError):
            termlib.open_session(tmp_path, {}, kind="resume", project="alpha", cwd=changed, expected_cwd=approved)
    else:
        with monkeypatch.context() as isolated:
            isolated.setenv(termlib.CONFIRMED_CWD_ENV, approved)
            isolated.setattr(sys, "argv", ["-c", changed])
            isolated.setattr(pathlib, "Path", WindowsFolder)
            with pytest.raises(SystemExit) as result:
                exec(termlib.WINDOWS_CWD_CHECK, {})
        assert result.value.code == 1


@needs_tmux
def test_confirmed_empty_shell_preserves_its_login_profile(env, monkeypatch):
    _client, root, work = env
    alternate = root / "elsewhere"
    alternate.mkdir()
    moved = root / "profile-moved"
    profile = root / "shell-profile"
    profile.write_text(
        f"cd {shlex.quote(str(alternate))}\n"
        f"touch {shlex.quote(str(moved))}\n"
        "PS1='$ '\n", encoding="utf-8",
    )
    shell = root / "bash"
    shell.write_text(f"#!/bin/sh\nexec /bin/bash --noprofile --rcfile {shlex.quote(str(profile))} -i\n",
                     encoding="utf-8")
    shell.chmod(0o755)
    monkeypatch.setenv("SHELL", str(shell))

    def no_paste(*_args, **_kwargs):
        pytest.fail("an empty shell must leave terminal input to its profile")

    monkeypatch.setattr(termlib, "type_into", no_paste)
    approved = str(work.resolve())
    session = termlib.open_session(root, {"terminal.keep": "tmux"}, kind="shell", project="alpha",
                                   cwd=approved, expected_cwd=approved)
    deadline = time.monotonic() + 5
    while not moved.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert moved.exists()
    assert termlib.alive_tmux(root, session["id"])
    assert termlib.pane_dir(root, session) == alternate.resolve()


@unix_pty
@pytest.mark.parametrize("suffix", ["\n", "\x7f"])
def test_terminal_confirmation_refuses_a_folder_with_an_ambiguous_name(env, monkeypatch, suffix):
    from backend.db import ViewStore

    client, root, work = env
    _on(client)
    unsafe = work / f"checkout{suffix}"
    unsafe.mkdir()
    owner = "cc-11223344"
    monkeypatch.setattr(ViewStore, "agents", lambda _self: [
        {"agent_id": owner, "tool": "claude-code", "session_ref": "capture",
         "project": "alpha", "cwd": str(unsafe)},
    ])
    response = client.get(f"/api/terminal/resume/{owner}")
    assert response.status_code == 422, response.text
    assert "control character or line break" in response.json()["detail"]

    sid = "t1234abcd"
    termlib.put(root, {"id": sid, "cwd": str(unsafe), "project": "alpha", "kind": "shell",
                       "backend": "plain", "asleep": True, "agent_id": owner, "wake": ""})
    selected = _row(client, sid)
    assert selected["wake_cwd_has_controls"] is True and "wake_cwd" not in selected
    refused = client.post(f"/api/terminal/sessions/{sid}/wake", json={
        "actor": "operator", "expected_agent": owner, "wake_revision": selected["wake_revision"],
        "expected_cwd": str(unsafe.resolve()),
    })
    assert refused.status_code == 422, refused.text
    assert termlib.get(root, sid)["asleep"] is True


@needs_tmux
@unix_pty
def test_confirmed_tmux_agent_wrapper_ignores_bash_env_and_env(env, monkeypatch):
    _client, root, work = env
    elsewhere = root / "elsewhere"
    elsewhere.mkdir()
    startup = root / "bash-startup"
    sourced = root / "startup-source"
    launched = root / "launch-directory"
    startup.write_text(
        f"cd {shlex.quote(str(elsewhere))}\nprintf sourced > {shlex.quote(str(sourced))}\n",
        encoding="utf-8",
    )
    # The outer interactive shell has no startup files. Naming the shim
    # sh still exercises the child-Bash adapter used for POSIX shells.
    shell = root / "sh"
    shell.write_text("#!/bin/sh\nexec /bin/bash --norc --noprofile -i\n", encoding="utf-8")
    shell.chmod(0o755)
    monkeypatch.setenv("SHELL", str(shell))
    monkeypatch.setenv("BASH_ENV", str(startup))
    monkeypatch.setenv("ENV", str(startup))
    approved = str(work.resolve())
    command = f"pwd -P > {shlex.quote(str(launched))}"
    termlib.open_session(root, {"terminal.keep": "tmux"}, kind="resume", project="alpha",
                         cwd=approved, command=command, expected_cwd=approved)
    deadline = time.monotonic() + 5
    while not launched.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert launched.read_text(encoding="utf-8").strip() == approved
    assert not sourced.exists()
