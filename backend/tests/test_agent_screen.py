import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_pty_close_escalates_without_a_blocking_wait(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import screen

    monkeypatch.setattr(screen, "WINDOWS", False)
    instance = screen.Screen.__new__(screen.Screen)
    instance.pid, instance.fd = 82, 12
    signals = []
    closed = []

    def waitpid(pid, flags):
        assert flags == 1
        return (pid, 0) if len(signals) == 2 else (0, 0)

    def killpg(pid, sig):
        if sig == 0:
            raise ProcessLookupError
        signals.append((pid, sig))

    ticks = iter([0, 30, 30])
    monkeypatch.setattr(screen, "os", SimpleNamespace(killpg=killpg, close=closed.append,
                                                     waitpid=waitpid, WNOHANG=1))
    monkeypatch.setattr(signal, "SIGKILL", 9, raising=False)
    monkeypatch.setattr(screen, "time", type("Clock", (), {"monotonic": staticmethod(lambda: next(ticks))}))

    instance.close()

    assert signals == [(82, signal.SIGTERM), (82, signal.SIGKILL)]
    assert closed == [12]


@pytest.mark.skipif(os.name == "nt", reason="Unix PTY process groups")
def test_pty_close_signals_the_real_child_group(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import screen

    child = """
import os, signal, time
from pathlib import Path
signal.signal(signal.SIGHUP, signal.SIG_IGN)
def done(*_):
    Path('stopped').touch()
    raise SystemExit(0)
signal.signal(signal.SIGTERM, done)
Path('child.pid').write_text(str(os.getpid()))
time.sleep(30)
"""
    leader = """
import signal, subprocess, sys
signal.signal(signal.SIGTERM, signal.SIG_IGN)
subprocess.run([sys.executable, '-c', sys.argv[1]], check=True)
"""
    monkeypatch.setattr(screen, "PTY_CLOSE_TIMEOUT_S", 0.5)
    instance = screen.Screen([sys.executable, "-c", leader, child], tmp_path, os.environ.copy())
    pid_file = tmp_path / "child.pid"
    try:
        deadline = time.monotonic() + 5
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert pid_file.is_file(), "the child did not start"
        instance.close()
        assert (tmp_path / "stopped").is_file(), "shutdown missed the subprocess"
    finally:
        if pid_file.is_file() and not (tmp_path / "stopped").exists():
            try:
                os.kill(int(pid_file.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
        if instance.fd is not None:
            try:
                os.close(instance.fd)
            except OSError:
                pass


@pytest.mark.parametrize("outcome", ["gentle", "child survived", "taskkill failed"])
def test_conpty_checks_the_whole_tree_after_gentle_shutdown(monkeypatch, outcome):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import psutil
    import screen

    requests = []
    closed = []
    killed = []
    waits = []
    child = SimpleNamespace(pid=83, kill=lambda: killed.append(83))
    leader = SimpleNamespace(pid=82, children=lambda *, recursive: [child], kill=lambda: killed.append(82))

    def wait(procs, *, timeout):
        assert timeout == screen.PTY_CLOSE_TIMEOUT_S
        waits.append([p.pid for p in procs])
        if outcome == "taskkill failed":
            return [], procs
        if outcome == "child survived" and len(waits) == 1:
            return [leader], [child]
        return procs, []

    def run(args, *, capture_output, timeout):
        assert capture_output and timeout == screen.PTY_CLOSE_TIMEOUT_S
        requests.append(args)
        if "/F" in args and outcome == "taskkill failed":
            raise subprocess.TimeoutExpired(args, timeout)
        return subprocess.CompletedProcess(args, int(outcome == "taskkill failed"))

    monkeypatch.setattr(screen, "WINDOWS", True)
    monkeypatch.setattr(psutil, "Process", lambda pid: leader)
    monkeypatch.setattr(psutil, "wait_procs", wait)
    monkeypatch.setattr(screen.subprocess, "run", run)
    instance = screen.Screen.__new__(screen.Screen)
    instance.proc = SimpleNamespace(pid=82, close=lambda *, force: closed.append(force))
    instance.close()

    assert waits[0] == [83, 82]
    assert requests[0] == ["taskkill", "/PID", "82", "/T"]
    if outcome == "gentle":
        assert len(requests) == 1 and len(waits) == 1 and killed == [] and closed == [False]
    elif outcome == "child survived":
        assert len(requests) == 1 and waits[1] == [83] and killed == [83] and closed == [False]
    else:
        assert requests[1] == ["taskkill", "/PID", "82", "/T", "/F"]
        assert killed == [83, 82] and closed == [True]


def test_trace_saves_the_complete_rendered_frame_after_terminal_redraw(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    from screen import Screen, TerminalTrace

    trace = tmp_path / "startup.log"
    terminal = Screen.__new__(Screen)
    terminal.trace = TerminalTrace(trace)
    terminal.trace.feed("Previous frame\x1b[2J\x1b[HSelect login method:\r\n"
                        "❯ Account\r\n  API key\r\n  Cloud provider\r\n  sk-ant-… testSecretSuffix5678")
    assert terminal.rendered.splitlines()[:3] == ["Select login method:", "❯ Account", "  API key"]

    terminal.save_frame("startup failed")

    saved = trace.read_text(encoding="utf-8")
    assert "  Cloud provider" in saved
    assert "Previous frame" not in saved
    assert "testSecretSuffix5678" not in saved


@pytest.mark.parametrize("display", ["full", "partial", "dots", "stars", "ellipsis"])
def test_trace_hides_the_known_key_at_every_wrap_column(monkeypatch, tmp_path, display):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    from screen import COLS, TerminalTrace

    tail = "Q7aZ8wR9sZ1xK2yD3fB4"
    key = "sk-ant-api03-fakeSecret" + tail
    forms = {"full": key, "partial": tail, "dots": "sk-ant-api03-..." + tail,
             "stars": "sk-ant-api03-*** " + tail, "ellipsis": "SK-ANT-… " + tail}
    monkeypatch.setenv("ANTHROPIC_API_KEY", key)
    for column in range(COLS):
        path = tmp_path / "trace.log"
        trace = TerminalTrace(path)
        trace.feed("X" * column + forms[display] + " is invalid; keep this text")
        trace.save("error")
        saved = path.read_text(encoding="utf-8")
        compact = "".join(saved.split())
        assert tail not in compact, (display, column)
        assert "isinvalid;keepthistext" in compact, (display, column)
        path.unlink()
@pytest.mark.parametrize("windows", [False, True])
def test_only_unix_pty_emulates_color_replies(monkeypatch, windows):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import screen

    monkeypatch.setattr(screen, "WINDOWS", windows)
    sent = []
    terminal = screen.Screen.__new__(screen.Screen)
    terminal._write = sent.append
    terminal._answer("\x1b]10;?\x07\x1b]11;?\x07")
    assert len(sent) == (0 if windows else 2)


@pytest.mark.parametrize("reply_to_kitty_query", [False, True], ids=["claude", "codex"])
def test_terminal_keeps_unwanted_kitty_reply_out_of_the_composer(monkeypatch, reply_to_kitty_query):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    from screen import Screen

    terminal = Screen.__new__(Screen)
    terminal.reply_to_kitty_query = reply_to_kitty_query
    sent = []
    terminal._write = sent.append
    terminal._answer("\x1b[c\x1b[?u")
    assert sent == (["\x1b[?1;2c", "\x1b[?0u"] if reply_to_kitty_query else ["\x1b[?1;2c"])


def test_application_cursor_mode_changes_arrow_encoding_even_across_reads(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import screen

    terminal = screen.Screen.__new__(screen.Screen)
    terminal.text = terminal.history = terminal._cursor_tail = ""
    terminal.application_cursor = False
    terminal.trace = None
    sent = []
    terminal._write = sent.append
    monkeypatch.setattr(screen.time, "sleep", lambda _: None)
    terminal._receive("\x1b[?")
    terminal._receive("1h")
    terminal.send(screen.DOWN)
    terminal._receive("\x1b[?1l")
    terminal.send(screen.DOWN)
    assert sent == ["\x1bOB", "\x1b[B"]


def test_wait_for_rendered_prompt_after_incremental_repaint(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import screen

    instance = screen.Screen.__new__(screen.Screen)
    instance.trace = screen.TerminalTrace(tmp_path / "terminal.log")
    instance.trace.feed("Say")
    instance.text = ""
    instance.read = lambda: instance.trace.feed("\x1b[1;4H hello")
    assert instance.wait_for("Say hello", 1)
