"""The capture hook never harms the session it observes: how it finds its
parents without /proc, and where its failure notices go."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from backend import hookshared

_HOOK = Path(__file__).resolve().parents[2] / "scripts" / "hooks" / "claude-code-capture.py"


def test_ancestors_without_proc_call_ps_once_and_walk_in_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    if os.name == "nt":
        pytest.skip("Windows reads the process table from the kernel, not from ps")
    calls: list[list[str]] = []
    me = os.getpid()
    table = f"  1     0\n {me}  500\n  500   400\n  400   300\n  300     1\n  999   500\n"

    def fake_run(argv, **_kw):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout=table, stderr="")

    real_isdir = os.path.isdir
    monkeypatch.setattr(os.path, "isdir", lambda p: False if str(p).startswith("/proc") else real_isdir(p))
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert hookshared.ancestors() == [500, 400, 300]
    assert calls == [["ps", "-A", "-o", "pid=,ppid="]]


def test_ancestors_without_ps_are_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    if os.name == "nt":
        pytest.skip("Windows reads the process table from the kernel, not from ps")

    def no_ps(*_a, **_kw):
        raise FileNotFoundError("ps")

    real_isdir = os.path.isdir
    monkeypatch.setattr(os.path, "isdir", lambda p: False if str(p).startswith("/proc") else real_isdir(p))
    monkeypatch.setattr(subprocess, "run", no_ps)
    assert hookshared.ancestors() == []


@pytest.mark.skipif(not os.path.isdir("/proc/self"), reason="Linux /proc")
def test_ancestors_on_linux_read_proc_and_run_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_run(*_a, **_kw):
        raise AssertionError("ps must not run where /proc exists")

    monkeypatch.setattr(subprocess, "run", no_run)
    got = hookshared.ancestors()
    assert got and got[0] == os.getppid()


def _fire(event: dict, data_root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_HOOK), "--project", "alpha", "--data-root", str(data_root)],
        input=json.dumps(event), capture_output=True, text=True, timeout=60,
    )


def test_a_failure_on_stop_is_written_to_stderr(tmp_path: Path) -> None:
    """Claude Code shows a Stop hook's stderr, not its stdout."""
    gone = tmp_path / "no-such-root"
    got = _fire({"hook_event_name": "Stop", "session_id": "s1"}, gone)
    assert got.returncode == 0
    assert got.stdout == "" and "capture failed" in got.stderr


def test_a_failure_on_a_prompt_stays_on_stdout(tmp_path: Path) -> None:
    """On UserPromptSubmit stdout reaches the agent's context."""
    gone = tmp_path / "no-such-root"
    got = _fire({"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "hi"}, gone)
    assert got.returncode == 0
    assert "capture failed" in got.stdout and got.stderr == ""


def test_an_exception_on_stop_is_written_to_stderr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    spec = importlib.util.spec_from_file_location("sp_cc_safety", _HOOK)
    cc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cc)

    class Boom:
        def __init__(self, *_a, **_kw):
            raise RuntimeError("disk gone")

    monkeypatch.setattr(cc, "TurnCapture", Boom)
    monkeypatch.setattr(cc, "record_failure", lambda *a, **k: None)
    monkeypatch.setattr(sys, "argv", ["hook", "--project", "alpha", "--data-root", str(tmp_path)])
    import io
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"hook_event_name": "Stop", "session_id": "s1"})))
    assert cc.main() == 0
    out = capsys.readouterr()
    assert out.out == "" and "disk gone" in out.err
