"""The Windows terminal, on every system: what can be checked without Windows.

- the pure parts: the shell a Windows terminal runs, quoting for PowerShell
  and cmd, the commands built for them, what degrades without tmux;
- the Windows pty path (routers/terminal.WinPtySession over conpty.ConPty)
  with a stand-in for pywinpty's ``PTY``: the same calls, an echo for a
  shell, a real process for its pid (so killing the tree is real too);
- the plain terminal (no tmux) end to end on this system's own pty: what a
  Windows terminal is, with sleep, wake and restore.

The real ConPTY runs in tests/test_conpty.py, on Windows only.
"""

from __future__ import annotations

import base64
import json
import os
import queue
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import psutil
import pytest
from fastapi.testclient import TestClient

from backend import conpty, termlib
from backend.routers import terminal
from backend.server import create_app

# ---------------------------------------------------------------------------
# The shell, and the family its commands are written for
# ---------------------------------------------------------------------------


def _which(*present: str):
    table = {"pwsh": r"C:\Program Files\PowerShell\7\pwsh.exe",
             "powershell": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
             "cmd": r"C:\Windows\system32\cmd.exe"}
    return lambda name: table[name] if name in present else None


def test_a_windows_terminal_runs_powershell_7_then_windows_powershell_then_cmd() -> None:
    argv = termlib.windows_shell(_which("pwsh", "powershell", "cmd"), env={})
    assert argv[0].endswith("pwsh.exe") and argv[1:4] == ["-NoLogo", "-NoExit", "-EncodedCommand"]
    # UTF-8 both ways, said in a string the command line cannot take apart.
    said = base64.b64decode(argv[4]).decode("utf-16-le")
    assert "[Console]::OutputEncoding" in said and "UTF8Encoding" in said and "$OutputEncoding" in said
    assert termlib.windows_shell(_which("powershell"), env={})[0].endswith("powershell.exe")
    assert termlib.windows_shell(_which(), env={"ComSpec": r"C:\Windows\system32\cmd.exe"}) == \
        [r"C:\Windows\system32\cmd.exe", "/K", "chcp 65001>nul"]
    assert termlib.windows_shell(_which(), env={})[0] == "cmd.exe"


def test_a_shell_is_known_by_its_program_name() -> None:
    fam = termlib.family_of
    assert fam(r"C:\Program Files\PowerShell\7\pwsh.exe") == "powershell"
    assert fam(r"C:\Windows\System32\WindowsPowerShell\v1.0\PowerShell.EXE") == "powershell"
    assert fam(r"C:\Windows\system32\cmd.exe") == "cmd"
    assert fam("/usr/bin/pwsh") == "powershell"
    assert fam("/bin/bash") == fam("/usr/bin/fish") == fam("") == "bash"


def test_on_windows_the_commands_are_built_for_the_terminals_shell(monkeypatch) -> None:
    monkeypatch.setattr(termlib, "WINDOWS", True)
    monkeypatch.setattr(termlib, "windows_shell", lambda *a, **k: [r"C:\pwsh\pwsh.exe", "-NoLogo"])
    assert termlib.plain_shell()[0] == r"C:\pwsh\pwsh.exe" and termlib.command_family() == "powershell"
    assert termlib.start_command("claude", {"id": "tk_1", "title": "x"}).startswith("claude 'Work on")
    monkeypatch.setattr(termlib, "windows_shell", lambda *a, **k: ["cmd.exe", "/K", "chcp 65001>nul"])
    assert termlib.command_family() == "cmd"
    assert termlib.start_command("codex", {"id": "tk_1", "title": "x"}).startswith('codex "Work on')
    # Typed as built: there is no bash on Windows to hand it to.
    assert termlib.typed_form("claude 'a b'", r"C:\pwsh\pwsh.exe") == "claude 'a b'"
    monkeypatch.setattr(termlib, "WINDOWS", False)
    # On macOS and Linux nothing changed: bash quoting, and other shells hand it to bash.
    assert termlib.command_family() == "bash"
    assert termlib.typed_form("claude $'x'", "/usr/bin/pwsh").startswith("bash -lc 'eval")


# ---------------------------------------------------------------------------
# Quoting for PowerShell and cmd
# ---------------------------------------------------------------------------


def test_a_powershell_argument_expands_nothing_and_stays_one_argument() -> None:
    q = termlib.ps_quote
    assert q("It's") == "'It''s'"
    # PowerShell reads the curly single quotes as quotes too: doubled as well.
    assert q("it\u2019s") == "'it\u2019\u2019s'"
    # Nothing in single quotes is expanded: $, backtick, $( ) stay text.
    assert q("$env:SECRET `n $(calc)") == "'$env:SECRET `n $(calc)'"
    # A line break would end the line typed: a space. A " is a ' (a .cmd splits at it).
    assert q('a\nb\r\nc\td "e"') == "'a b c d ''e'''"
    # cmd (under an npm .cmd) expands %NAME% even inside quotes: full-width.
    assert q("50% of %PATH%") == "'50\uff05 of \uff05PATH\uff05'"
    # Keys a terminal would act on are dropped; a trailing \\ would escape the closing quote.
    assert q("a\x1b[2Jb\x03c\\\\") == "'a[2Jbc'"
    # A path keeps its characters.
    assert q(r"C:\Users\o'neil\50%", literal=True) == r"'C:\Users\o''neil\50%'"


def test_a_cmd_argument_has_nothing_left_that_acts_inside_quotes() -> None:
    q = termlib.cmd_quote
    got = q('a & b | c > d ^ e "f" %PATH% !x!')
    assert got == "\"a & b | c > d ^ e 'f' \uff05PATH\uff05 !x!\""
    assert got.count('"') == 2
    assert q('C:\\work\\my "dir"', literal=True) == '"C:\\work\\my dir"'


def test_a_task_started_on_windows_carries_its_text_safely() -> None:
    task = {"id": "tk_1", "title": "It's \"quoted\" & 100%", "description": "line1\nline2 `whoami` $(calc)"}
    ps = termlib.start_command("claude", task, "powershell")
    assert ps == ("claude 'Work on the Slightly Parallel task tk_1 \u00b7 It''s ''quoted'' & 100\uff05.  "
                  "line1 line2 `whoami` $(calc)'")
    assert termlib.start_command("opencode", task, "powershell").startswith("opencode --prompt 'Work")
    cmd = termlib.start_command("claude", task, "cmd")
    assert cmd.startswith('claude "Work on') and cmd.count('"') == 2 and "%" not in cmd
    # Long text is cut where cmd's line limit still holds it.
    long = termlib.start_command("claude", {"id": "tk_2", "title": "t", "description": "x" * 5000}, "cmd")
    assert len(long) < 8191


def test_a_fork_on_windows_changes_folder_the_way_its_shell_does() -> None:
    ps = termlib.fork_command("claude-code", "abc-1", r"C:\work\o'neil", "go on", "powershell")
    assert ps == r"Set-Location -LiteralPath 'C:\work\o''neil'; if ($?) { claude -r abc-1 --fork-session 'go on' }"
    cmd = termlib.fork_command("codex", "abc-1", r"C:\work", "go on", "cmd")
    assert cmd == 'cd /d "C:\\work" && codex fork abc-1 "go on"'
    assert len(termlib.fork_command("claude-code", "abc-1", r"C:\w", "y" * 200_000, "powershell")) < 8191
    # bash: as before.
    assert termlib.fork_command("claude-code", "abc-1", "/w", "go", "bash") == "cd /w && claude -r abc-1 --fork-session $'go'"


# ---------------------------------------------------------------------------
# What degrades without tmux
# ---------------------------------------------------------------------------


def test_windows_never_uses_tmux_even_with_one_on_the_path(monkeypatch) -> None:
    monkeypatch.setattr(termlib.shutil, "which", lambda name: "/usr/bin/tmux" if name == "tmux" else None)
    monkeypatch.setattr(termlib, "WINDOWS", True)
    assert termlib.tmux_path() is None
    assert termlib.uses_tmux({"terminal.keep": "tmux"}) is False
    assert termlib.tmux_server_pid(Path(".")) == "" and termlib.tmux_panes(Path(".")) == {}
    assert termlib.tmux_version() == ""
    # Restore offers no plain terminal: nothing tells how it ended.
    assert termlib.lost([{"id": "a", "state": "ended", "backend": "plain", "server": "1"}], "") == []


def test_the_program_in_a_plain_windows_terminal_comes_from_its_process_tree() -> None:
    """No foreground process group on Windows: the newest process at the
    bottom of the shell's tree. Run here on real processes (psutil)."""
    code = ("import subprocess, sys, time; "
            "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); time.sleep(30)")
    shell = subprocess.Popen([sys.executable, "-c", code])
    try:
        deadline = time.time() + 10
        while not psutil.Process(shell.pid).children() and time.time() < deadline:
            time.sleep(0.05)
        child = psutil.Process(shell.pid).children()[0]
        want = os.path.basename(child.name())
        want = want[:-4] if want.lower().endswith(".exe") else want
        assert termlib.foreground_of_pid(shell.pid) == want
        conpty.kill_tree(shell.pid)
        shell.wait(timeout=10)
        # The grandchild too (killed, not yet gone the moment after: waited for).
        _, alive = psutil.wait_procs([child], timeout=10)
        assert not alive or alive[0].status() == psutil.STATUS_ZOMBIE
    finally:
        if shell.poll() is None:
            shell.kill()
            shell.wait()
    assert termlib.foreground_of_pid(shell.pid) == ""


def test_the_environment_block_is_what_windows_takes() -> None:
    block = conpty.env_block({"b": "2", "A": "1", "SP_TERMINAL": "t1", "=C:": "x", "BAD": "a\0b"})
    assert block == "A=1\0b=2\0SP_TERMINAL=t1\0"


def test_sizes_stay_inside_sixteen_bits() -> None:
    assert terminal._size(99999, -3) == (1000, 1)
    assert terminal._size(120, 40) == (120, 40)


def test_a_woken_plain_terminal_types_what_it_wakes_with() -> None:
    assert terminal._pending({"command": "echo once"}) == "echo once"
    assert terminal._pending({"command": "echo once", "woken_at": "x", "wake": ""}) == ""
    assert terminal._pending({"command": "claude 'task'", "woken_at": "x", "wake": "claude -r abc"}) == "claude -r abc"


# ---------------------------------------------------------------------------
# The Windows pty path, with a stand-in for pywinpty
# ---------------------------------------------------------------------------


class FakeError(Exception):
    pass


class FakePTY:
    """pywinpty's PTY as conpty.py uses it: a real process for the pid (a
    sleeping Python), an echo for the shell's output, "exit" ends it."""

    made: list["FakePTY"] = []

    def __init__(self, cols: int, rows: int, backend: int | None = None):
        self.size = (cols, rows)
        self.backend = backend
        self.out: queue.Queue[str] = queue.Queue()
        self.cancelled = False
        self.written: list[str] = []
        FakePTY.made.append(self)

    def spawn(self, appname, cmdline=None, cwd=None, env=None):
        self.appname, self.cmdline, self.cwd, self.env = appname, cmdline, cwd, env
        self.proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.out.put("PS C:\\> ")
        return True

    @property
    def pid(self):
        return self.proc.pid

    def read(self, blocking=False):
        while True:
            try:
                return self.out.get(timeout=0.02)
            except queue.Empty:
                pass
            if self.cancelled:
                self.cancelled = False
                raise FakeError("The I/O operation has been aborted")
            if self.proc.poll() is not None:
                raise FakeError("Standard out reached EOF")

    def write(self, text):
        self.written.append(text)
        self.out.put(text)
        if "exit\r" in text:
            self.proc.kill()
            self.proc.wait()
        return len(text)

    def set_size(self, cols, rows):
        self.size = (cols, rows)
        self.out.put(f"[size {cols}x{rows}]")

    def isalive(self):
        return self.proc.poll() is None

    def cancel_io(self):
        self.cancelled = True
        return True


FAKE = SimpleNamespace(PTY=FakePTY, WinptyError=FakeError, Backend=SimpleNamespace(ConPTY=0, WinPTY=1))


def _drain(con: conpty.ConPty, want: str, timeout: float = 5.0) -> str:
    seen = ""
    end = time.time() + timeout
    while want not in seen and time.time() < end:
        seen += con.read().decode()
    return seen


def test_a_conpty_reads_writes_resizes_and_ends_with_its_whole_tree() -> None:
    con = conpty.ConPty(["C:\\pwsh.exe", "-NoLogo", "-EncodedCommand", "a b"], "C:\\work", 80, 24,
                        {"SP_TERMINAL": "t1"}, module=FAKE)
    fake = FakePTY.made[-1]
    try:
        assert fake.backend == 0 and fake.appname == "C:\\pwsh.exe"
        assert fake.cmdline == '-NoLogo -EncodedCommand "a b"' and fake.cwd == "C:\\work"
        assert fake.env == "SP_TERMINAL=t1\0"
        assert "PS C:\\>" in _drain(con, "PS C:\\>")
        con.write("echo ünï ✓\r".encode())
        assert "echo ünï ✓" in _drain(con, "✓")
        con.resize(120, 40)
        assert "[size 120x40]" in _drain(con, "[size")
        assert con.alive() and con.foreground()
        con.kill()
        fake.proc.wait(timeout=10)
        assert con.read() == b"" and not con.alive()
    finally:
        if fake.proc.poll() is None:
            fake.proc.kill()
            fake.proc.wait()
    con.release()
    assert con.read() == b""


def test_a_conpty_whose_shell_exits_reads_to_the_end() -> None:
    con = conpty.ConPty(["cmd.exe"], "", 80, 24, {}, module=FAKE)
    fake = FakePTY.made[-1]
    assert fake.cmdline is None and fake.cwd is None
    con.write(b"exit\r")
    seen = b""
    while True:
        chunk = con.read()
        if not chunk:
            break
        seen += chunk
    assert b"exit" in seen and not con.alive()


def test_a_read_error_while_the_shell_lives_is_retried(monkeypatch) -> None:
    con = conpty.ConPty(["cmd.exe"], "", 80, 24, {}, module=FAKE)
    fake = FakePTY.made[-1]
    try:
        fake.cancelled = True          # one aborted read, the shell still alive
        con.write(b"after\r")
        assert "after" in _drain(con, "after")
    finally:
        con.kill()
        fake.proc.wait(timeout=10)


def test_without_conpty_the_older_backend_is_taken() -> None:
    class NoConPTY(FakePTY):
        def __init__(self, cols, rows, backend=None):
            if backend == 0:
                raise FakeError("ConPTY is not available")
            super().__init__(cols, rows, backend)
    con = conpty.ConPty(["cmd.exe"], "", 80, 24, {}, module=SimpleNamespace(PTY=NoConPTY, WinptyError=FakeError,
                                                                             Backend=FAKE.Backend))
    assert FakePTY.made[-1].backend is None
    con.kill()
    FakePTY.made[-1].proc.wait(timeout=10)


def test_without_pywinpty_the_terminal_says_what_to_install(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(conpty, "load", lambda: None)
    with pytest.raises(RuntimeError, match="pywinpty"):
        conpty.ConPty(["cmd.exe"], "", 80, 24, {})
    root = tmp_path / "data"
    (root / "projects").mkdir(parents=True)
    monkeypatch.setattr(terminal, "SUPPORTED", False)
    monkeypatch.setattr(terminal, "UNSUPPORTED", conpty.MISSING)
    with TestClient(create_app(data_root=root, watch=False)) as c:
        assert c.post("/api/settings", json={"values": {"terminal.enabled": True}}).status_code == 200
        assert c.get("/api/terminal/state").json()["supported"] is False
        r = c.post("/api/terminal/sessions", json={"kind": "shell"})
        assert r.status_code == 501 and "pip install pywinpty" in r.json()["detail"]
        from starlette.websockets import WebSocketDisconnect
        with pytest.raises(WebSocketDisconnect) as e:
            with c.websocket_connect("/ws/terminal/t1?token=x") as ws:
                ws.receive_bytes()
        assert e.value.code == 4403 and e.value.reason == terminal.UNSUPPORTED_WS


# ---------------------------------------------------------------------------
# The routes on the Windows path (stand-in pywinpty), and plain on this system
# ---------------------------------------------------------------------------


@pytest.fixture()
def plain(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SHELL", "/bin/sh")
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    work = tmp_path / "work"
    work.mkdir()
    (root / "integrations.csv").write_text(f"project,path\nalpha,{work}\n", encoding="utf-8")
    with TestClient(create_app(data_root=root, watch=False)) as c:
        assert c.post("/api/settings", json={"values": {"terminal.enabled": True, "terminal.keep": "plain"}}).status_code == 200
        yield c, root, work


def _until(ws, want: bytes, timeout: float = 8.0) -> bytes:
    seen = b""
    end = time.time() + timeout
    while want not in seen and time.time() < end:
        seen += ws.receive_bytes()
    return seen


def _row(c, sid: str) -> dict:
    return next(x for x in c.get("/api/terminal/sessions").json()["sessions"] if x["id"] == sid)


def test_the_windows_path_through_the_routes(plain, monkeypatch) -> None:
    """Open, type, resize, sleep, wake (typing the wake command), close — the
    router's Windows session over a stand-in pywinpty, with termlib on Windows."""
    c, root, work = plain
    monkeypatch.setattr(termlib, "WINDOWS", True)
    monkeypatch.setattr(termlib, "windows_shell", lambda *a, **k: [r"C:\pwsh\pwsh.exe", "-NoLogo"])
    monkeypatch.setattr(terminal, "open_pty", lambda sid, argv, cwd, cols, rows, env:
                        terminal.WinPtySession(sid, argv, cwd, cols, rows, env, module=FAKE))
    tok = c.get("/api/terminal/state").json()["token"]
    assert c.get("/api/terminal/state").json()["windows"] is True
    s = c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha", "role": "server",
                                              "command": "npm run dev", "label": "web"}).json()["session"]
    assert s["backend"] == "plain"
    # The pty is made when the terminal opens, before any view: listed live.
    fake = FakePTY.made[-1]
    assert fake.appname == r"C:\pwsh\pwsh.exe" and fake.cwd == str(work.resolve())
    assert _row(c, s["id"])["state"] != "ended"
    with c.websocket_connect(f"/ws/terminal/{s['id']}?token={tok}&cols=90&rows=30") as ws:
        # The first view gets what the shell printed before it came, at its size.
        assert b"PS C:" in _until(ws, b"PS C:")
        assert FakePTY.made[-1] is fake and fake.size == (90, 30)
        assert f"SP_TERMINAL={s['id']}\0" in fake.env and "TERM=xterm-256color\0" in fake.env
        # Its command, typed once, as built: no bash wrapping on Windows.
        assert b"npm run dev\r" in _until(ws, b"npm run dev\r")
        ws.send_text(json.dumps({"type": "resize", "cols": 99999, "rows": 0}))
        assert b"[size 1000x1]" in _until(ws, b"[size")
        ws.send_text(json.dumps({"type": "input", "data": "echo \u2713\r"}))
        assert "echo \u2713".encode() in _until(ws, "\u2713".encode())
        assert c.post(f"/api/terminal/sessions/{s['id']}/type", json={"text": "typed", "enter": True}).status_code == 200
        assert b"typed\r" in _until(ws, b"typed\r")
        row = _row(c, s["id"])
        assert row["state"] in ("working", "running", "shell") and row["program"]
        # No server-side history for a plain terminal: the page keeps it.
        assert c.post(f"/api/terminal/sessions/{s['id']}/capture", json={}).status_code == 409
        assert c.get(f"/api/terminal/sessions/{s['id']}/pos").status_code == 409
        got = c.post(f"/api/terminal/sessions/{s['id']}/sleep", json={}).json()["session"]
        assert got["state"] == "asleep" and got["wake"] == "npm run dev"
        # The shell and its tree are gone.
        fake.proc.wait(timeout=10)
    assert c.get("/api/terminal/restore").json()["needed"] == 0
    woke = c.post(f"/api/terminal/sessions/{s['id']}/wake", json={}).json()["session"]
    # Its shell is back at once, not when a view comes (before: `ended` until then).
    assert woke["state"] not in ("ended", "asleep") and not woke["asleep"]
    second = FakePTY.made[-1]
    assert second is not fake
    with c.websocket_connect(f"/ws/terminal/{s['id']}?token={tok}") as ws:
        assert b"PS C:" in _until(ws, b"PS C:")
        assert b"npm run dev\r" in _until(ws, b"npm run dev\r")
        ws.send_text(json.dumps({"type": "input", "data": "exit\r"}))
        from starlette.websockets import WebSocketDisconnect
        with pytest.raises(WebSocketDisconnect) as e:
            while True:
                ws.receive_bytes()
        assert e.value.code == 4000
    assert second.proc.poll() is not None
    c.post(f"/api/terminal/sessions/{s['id']}/close", json={})
    assert c.get("/api/terminal/sessions").json()["sessions"] == []


def test_a_shell_that_does_not_start_closes_the_socket_with_why(plain, monkeypatch) -> None:
    c, root, _ = plain

    def fail(*_a, **_k):
        raise OSError("no such shell")
    monkeypatch.setattr(terminal, "open_pty", fail)
    tok = c.get("/api/terminal/state").json()["token"]
    # Opening: a 500 that says why, and no terminal left behind.
    r = c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha"})
    assert r.status_code == 500 and "no such shell" in r.json()["detail"]
    assert c.get("/api/terminal/sessions").json()["sessions"] == []
    # A terminal whose shell is gone (the server restarted), opened in a view:
    # the socket closes with why.
    sid = termlib.open_session(root, {"terminal.keep": "plain"}, kind="shell", project="alpha", cwd="")["id"]
    assert _row(c, sid)["state"] == "ended"
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as e:
        with c.websocket_connect(f"/ws/terminal/{sid}?token={tok}") as ws:
            ws.receive_bytes()
    assert e.value.code == 4500 and "no such shell" in e.value.reason


@pytest.mark.skipif(os.name == "nt", reason="a Unix pty (the Windows one: tests/test_conpty.py)")
def test_a_plain_terminal_sleeps_and_wakes_running_its_command_again(plain) -> None:
    """What every Windows terminal is, on this system's own pty: a server
    sleeps, and wakes typing its command again (before, a woken plain
    terminal kept `typed` from its first life and came back empty)."""
    c, _, _ = plain
    tok = c.get("/api/terminal/state").json()["token"]
    s = c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha", "role": "server",
                                              "command": "echo up-$((6*7))", "label": "web"}).json()["session"]
    assert s["backend"] == "plain"
    with c.websocket_connect(f"/ws/terminal/{s['id']}?token={tok}") as ws:
        assert b"up-42" in _until(ws, b"up-42")
        assert c.post(f"/api/terminal/sessions/{s['id']}/sleep", json={}).json()["session"]["state"] == "asleep"
    assert c.get("/api/terminal/restore").json()["needed"] == 0
    c.post(f"/api/terminal/sessions/{s['id']}/wake", json={})
    with c.websocket_connect(f"/ws/terminal/{s['id']}?token={tok}") as ws:
        assert b"up-42" in _until(ws, b"up-42")
    # A plain shell wakes empty: its one-off command is not typed again.
    sh = c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha",
                                               "command": "echo once-$((2*3))"}).json()["session"]
    with c.websocket_connect(f"/ws/terminal/{sh['id']}?token={tok}") as ws:
        assert b"once-6" in _until(ws, b"once-6")
    c.post(f"/api/terminal/sessions/{sh['id']}/sleep", json={})
    c.post(f"/api/terminal/sessions/{sh['id']}/wake", json={})
    with c.websocket_connect(f"/ws/terminal/{sh['id']}?token={tok}") as ws:
        ws.send_text(json.dumps({"type": "input", "data": "echo mark-$((3+4))\r"}))
        seen = _until(ws, b"mark-7")
        assert b"mark-7" in seen and b"once-6" not in seen
    for sid in (s["id"], sh["id"]):
        c.post(f"/api/terminal/sessions/{sid}/close", json={})


@pytest.mark.skipif(os.name == "nt", reason="a Unix pty (the Windows one: tests/test_conpty.py)")
def test_a_plain_terminal_runs_from_the_moment_it_opens_with_no_view(plain) -> None:
    """Every terminal on Windows. Opened through the API (as the window's
    suite does, as Start on a task does), a plain terminal's shell starts at
    once and runs its command with nobody looking: before, it listed as
    `ended` until a view attached, and the window showed its "ended" card
    instead of the screen. Woken, the same."""
    c, _, work = plain
    tok = c.get("/api/terminal/state").json()["token"]
    s = c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha", "role": "server",
                                              "command": "echo ran-$((6*7)) > ran.txt", "label": "web"}).json()["session"]
    assert s["backend"] == "plain"
    assert _row(c, s["id"])["state"] != "ended"
    end = time.time() + 8
    while not (work / "ran.txt").exists() and time.time() < end:
        time.sleep(0.1)
    assert (work / "ran.txt").read_text().strip() == "ran-42"
    assert _row(c, s["id"])["typed"] is True
    # The first view gets what was printed before it came, and the shell is the same one.
    with c.websocket_connect(f"/ws/terminal/{s['id']}?token={tok}") as ws:
        assert b"ran-$((6*7))" in _until(ws, b"ran-$((6*7))")
        ws.send_text(json.dumps({"type": "input", "data": "echo seen-$((3+4))\r"}))
        assert b"seen-7" in _until(ws, b"seen-7")
    # Asleep, then woken with no view: the server's command runs again at once.
    (work / "ran.txt").unlink()
    assert c.post(f"/api/terminal/sessions/{s['id']}/sleep", json={}).json()["session"]["state"] == "asleep"
    woke = c.post(f"/api/terminal/sessions/{s['id']}/wake", json={}).json()["session"]
    assert woke["state"] not in ("ended", "asleep")
    end = time.time() + 8
    while not (work / "ran.txt").exists() and time.time() < end:
        time.sleep(0.1)
    assert (work / "ran.txt").read_text().strip() == "ran-42"
    # A shell opened by the API with no command is a prompt, not `ended`.
    sh = c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha"}).json()["session"]
    # Until the forked child has exec'd the shell, its foreground is still
    # this test's python ("working"): a moment, never `ended`.
    end = time.time() + 5
    while _row(c, sh["id"])["state"] != "shell" and time.time() < end:
        assert _row(c, sh["id"])["state"] != "ended"
        time.sleep(0.05)
    assert _row(c, sh["id"])["state"] == "shell"
    for sid in (s["id"], sh["id"]):
        c.post(f"/api/terminal/sessions/{sid}/close", json={})
    assert c.get("/api/terminal/sessions").json()["sessions"] == []


# ---------------------------------------------------------------------------
# Closing: the console host goes too, and nothing waits on its close
# ---------------------------------------------------------------------------


class HostPTY(FakePTY):
    """A pseudo console with its console host: a process of this test
    started --headless (OpenConsole's role), and a drop that waits — as
    ClosePseudoConsole does — until that host has ended (at most 20 s).
    Not kept in FakePTY.made: only the ConPty holds it, so it is dropped
    where the product drops it. Its processes are in ``made_procs``."""

    dropped: list[int] = []
    made_procs: list[tuple[subprocess.Popen, subprocess.Popen]] = []

    def __init__(self, cols, rows, backend=None):
        super().__init__(cols, rows, backend)
        FakePTY.made.remove(self)
        self.host = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", "--headless"])

    def spawn(self, *a, **k):
        ok = super().spawn(*a, **k)
        HostPTY.made_procs.append((self.proc, self.host))
        return ok

    def __del__(self):
        end = time.time() + 20
        while self.host.poll() is None and time.time() < end:
            time.sleep(0.02)
        HostPTY.dropped.append(self.host.pid)


HOSTED = SimpleNamespace(PTY=HostPTY, WinptyError=FakeError, Backend=FAKE.Backend)


@pytest.fixture()
def python_is_a_host(monkeypatch):
    name = os.path.basename(psutil.Process().name()).lower()
    monkeypatch.setattr(conpty, "HOST_NAMES", {name[:-4] if name.endswith(".exe") else name})


def test_closing_a_conpty_ends_its_console_host(python_is_a_host) -> None:
    con = conpty.ConPty(["cmd.exe"], "", 80, 24, {}, module=HOSTED)
    proc, host = HostPTY.made_procs[-1]
    assert con.host_pid == host.pid
    con.kill()
    host.wait(timeout=10)
    proc.wait(timeout=10)
    assert con.read() == b""
    t0 = time.time()
    con.release()
    assert time.time() - t0 < 0.5


def test_a_close_that_waits_holds_only_its_own_thread(python_is_a_host) -> None:
    con = conpty.ConPty(["cmd.exe"], "", 80, 24, {}, module=HOSTED)
    proc, host = HostPTY.made_procs[-1]
    t0 = time.time()
    con.release()          # the host still runs: the drop waits, the caller does not
    assert time.time() - t0 < 0.5
    assert host.pid not in HostPTY.dropped
    host.kill()
    end = time.time() + 10
    while host.pid not in HostPTY.dropped and time.time() < end:
        time.sleep(0.05)
    assert host.pid in HostPTY.dropped
    proc.kill()
    proc.wait()


def test_closing_twenty_windows_terminals_never_stalls_the_server(plain, monkeypatch, python_is_a_host) -> None:
    """The Windows bench closed 20 terminals and the server answered nothing
    for an hour: a pseudo console's close waited for its host on the event loop."""
    c, _, _ = plain
    monkeypatch.setattr(termlib, "WINDOWS", True)
    monkeypatch.setattr(termlib, "windows_shell", lambda *a, **k: [r"C:\pwsh\pwsh.exe", "-NoLogo"])
    monkeypatch.setattr(terminal, "open_pty", lambda sid, argv, cwd, cols, rows, env:
                        terminal.WinPtySession(sid, argv, cwd, cols, rows, env, module=HOSTED))
    HostPTY.made_procs.clear()
    ids = [c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha"}).json()["session"]["id"]
           for _ in range(20)]
    procs = list(HostPTY.made_procs)
    assert len(procs) == 20
    try:
        t0 = time.time()
        for sid in ids:
            assert c.post(f"/api/terminal/sessions/{sid}/close", json={}).status_code == 200
            assert c.get("/api/terminal/sessions").status_code == 200
        assert time.time() - t0 < 15
        for proc, host in procs:
            host.wait(timeout=10)
            proc.wait(timeout=10)
        assert c.get("/api/terminal/sessions").json()["sessions"] == []
    finally:
        for proc, host in procs:
            for p in (proc, host):
                if p.poll() is None:
                    p.kill()
                    p.wait()
