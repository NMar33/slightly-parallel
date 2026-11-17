"""The real ConPTY (pywinpty), on Windows only: a shell starts in a folder
with its environment, takes typed input, prints UTF-8, follows a resize,
and ends with everything it started — and the same through the routes.

These never ran on the machine they were written on (Linux): CI's
windows-latest is their first run (windows.yml, terminal.yml).
"""

from __future__ import annotations

import json
import os
import queue
import re
import threading
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name != "nt", reason="ConPTY is Windows only")

# The screen's own codes (colours, cursor moves, titles): out of the way of a search.
_CODES = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][0-9A-Za-z]|\x1b[=>78]")


class Reader:
    """A ConPty's output on a thread of its own, so a test can wait with a timeout."""

    def __init__(self, con):
        self.con = con
        self.q: queue.Queue[bytes] = queue.Queue()
        self.text = ""
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            chunk = self.con.read()
            self.q.put(chunk)
            if not chunk:
                return

    def until(self, want: str, timeout: float = 30.0) -> str:
        end = time.time() + timeout
        while time.time() < end:
            if want in _CODES.sub("", self.text):
                return self.text
            try:
                chunk = self.q.get(timeout=0.2)
            except queue.Empty:
                continue
            if not chunk:
                break
            self.text += chunk.decode("utf-8", "replace")
        return self.text

    def ended(self, timeout: float = 15.0) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            try:
                if not self.q.get(timeout=0.2):
                    return True
            except queue.Empty:
                pass
        return False


def _shell():
    from backend import termlib
    argv = termlib.windows_shell()
    return argv, termlib.family_of(argv[0])


def _echo(family: str, marker: str, expr: str) -> str:
    """A line that prints `marker` + the value of `expr`, written so the typed
    line itself never holds the result."""
    if family == "cmd":
        return f"set /a _x={expr} >nul & call echo {marker}%_x%"
    return f'echo "{marker}$({expr})"'


@pytest.fixture()
def con(tmp_path: Path):
    from backend import conpty
    argv, _ = _shell()
    # Wide: a long temp path printed on one row, not wrapped across two.
    c = conpty.ConPty(argv, str(tmp_path), 250, 30, {**os.environ, "SP_TERMINAL": "tq-win", "TERM": "xterm-256color"})
    yield c
    c.kill()
    c.release()


def test_pywinpty_is_installed_and_the_terminal_is_on() -> None:
    from backend import conpty
    from backend.routers import terminal
    assert conpty.available(), conpty.MISSING
    assert terminal.SUPPORTED


def test_a_shell_starts_in_its_folder_with_its_environment_and_takes_input(con, tmp_path: Path) -> None:
    _, family = _shell()
    out = Reader(con)
    var = "%SP_TERMINAL%" if family == "cmd" else "$env:SP_TERMINAL"
    con.write(f"echo env-{var}\r".encode())
    assert "env-tq-win" in _CODES.sub("", out.until("env-tq-win")), out.text[-2000:]
    # The folder's own name, printed by the shell (the typed line names no folder).
    here = "for %I in (.) do @echo where-%~nxI" if family == "cmd" else 'echo "where-$(Split-Path -Leaf $PWD)"'
    con.write(f"{here}\r".encode())
    assert f"where-{tmp_path.name}" in _CODES.sub("", out.until(f"where-{tmp_path.name}")), out.text[-2000:]
    con.write((_echo(family, "calc-", "6*7") + "\r").encode())
    assert "calc-42" in _CODES.sub("", out.until("calc-42")), out.text[-2000:]


def test_output_is_utf8(con) -> None:
    _, family = _shell()
    out = Reader(con)
    con.write("echo ünï-✓-ок\r".encode())
    # Echoed (typed) and printed: both are the same characters, in UTF-8.
    assert "ünï-✓-ок" in _CODES.sub("", out.until("✓-ок")), out.text[-2000:]


def test_a_resize_reaches_the_shell(con) -> None:
    _, family = _shell()
    if family == "cmd":
        pytest.skip("cmd prints no window size")  # pragma: no cover — the runner has PowerShell
    out = Reader(con)
    con.resize(120, 40)
    time.sleep(0.5)
    con.write(b'echo "sz-$([Console]::WindowWidth)x$([Console]::WindowHeight)"\r')
    assert "sz-120x40" in _CODES.sub("", out.until("sz-120x40")), out.text[-2000:]


def test_closing_ends_the_shell_and_everything_it_started(con) -> None:
    import psutil
    from backend import termlib
    out = Reader(con)
    # A child of the shell that would outlive it if only the shell were ended.
    con.write(b"ping -n 120 127.0.0.1\r")
    deadline = time.time() + 30
    while termlib.foreground_of_pid(con.pid).lower() != "ping" and time.time() < deadline:
        time.sleep(0.2)
    assert termlib.foreground_of_pid(con.pid).lower() == "ping"
    tree = [psutil.Process(con.pid), *psutil.Process(con.pid).children(recursive=True)]
    con.kill()
    gone, alive = psutil.wait_procs(tree, timeout=15)
    assert not alive, alive
    assert out.ended(), "a read was left blocked after the shell was killed"


def test_exit_is_seen_as_the_end(con) -> None:
    out = Reader(con)
    con.write(b"exit\r")
    assert out.ended(30), out.text[-2000:]
    deadline = time.time() + 10
    while con.alive() and time.time() < deadline:
        time.sleep(0.1)
    assert not con.alive()


def test_a_terminal_through_the_routes(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect
    from backend.server import create_app
    _, family = _shell()
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    work = tmp_path / "work"
    work.mkdir()
    (root / "integrations.csv").write_text(f"project,path\nalpha,{work}\n", encoding="utf-8")
    with TestClient(create_app(data_root=root, watch=False)) as c:
        assert c.post("/api/settings", json={"values": {"terminal.enabled": True}}).status_code == 200
        st = c.get("/api/terminal/state").json()
        assert st["supported"] and st["windows"] and not st["tmux"]
        tok = st["token"]
        sid = c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha"}).json()["session"]
        assert sid["backend"] == "plain"
        sid = sid["id"]
        seen = ""
        with c.websocket_connect(f"/ws/terminal/{sid}?token={tok}&cols=100&rows=30") as ws:
            ws.send_text(json.dumps({"type": "input", "data": _echo(family, "ws-", "6*7") + "\r"}))
            end = time.time() + 30
            while "ws-42" not in _CODES.sub("", seen) and time.time() < end:
                seen += ws.receive_bytes().decode("utf-8", "replace")
            assert "ws-42" in _CODES.sub("", seen), seen[-2000:]
            row = next(x for x in c.get("/api/terminal/sessions").json()["sessions"] if x["id"] == sid)
            assert row["state"] != "ended" and row["program"]
            assert c.post(f"/api/terminal/sessions/{sid}/sleep", json={}).json()["session"]["state"] == "asleep"
            with pytest.raises(WebSocketDisconnect) as e:
                while True:
                    ws.receive_bytes()
            assert e.value.code == 4000
        assert c.get("/api/terminal/restore").json()["needed"] == 0
        c.post(f"/api/terminal/sessions/{sid}/close", json={})
        assert c.get("/api/terminal/sessions").json()["sessions"] == []
