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


def test_conpty_can_fall_back_after_gentle_and_forced_tree_shutdown(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import screen

    requests = []
    closed = []

    def run(args, *, capture_output, timeout):
        assert capture_output and timeout == screen.PTY_CLOSE_TIMEOUT_S
        requests.append(args)
        if "/F" in args:
            raise subprocess.TimeoutExpired(args, timeout)
        return subprocess.CompletedProcess(args, 1)

    monkeypatch.setattr(screen, "WINDOWS", True)
    monkeypatch.setattr(screen.subprocess, "run", run)
    instance = screen.Screen.__new__(screen.Screen)
    instance.proc = SimpleNamespace(pid=82, close=lambda *, force: closed.append(force))
    instance.close()

    assert requests == [["taskkill", "/PID", "82", "/T"], ["taskkill", "/PID", "82", "/T", "/F"]]
    assert closed == [True]


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
