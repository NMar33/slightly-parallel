"""The terminal verification pilot's dispatch and result contracts."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import time
from threading import Event

import psutil
import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("terminal_verify", ROOT / "scripts" / "verify.py")
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def _waves():
    return tuple((name, ((name, [], ".", 1),)) for name in ("logic", "window", "rest"))


@pytest.mark.parametrize("jobs", [1, 2])
def test_first_failure_is_kept_and_independent_waves_still_run(jobs):
    calls = []
    finished = {}

    def run(step):
        assert not calls or finished["logic"] == 1
        calls.append(step[0])
        return int(step[0] == "logic")

    code = runner.run_waves(run, finished.__setitem__, _waves(), jobs, Event())
    assert code == 1
    assert calls[0] == "logic"
    assert sorted(calls[1:]) == ["rest", "window"]
    assert finished == {"logic": 1, "window": 0, "rest": 0}


def test_parallel_mode_overlaps_independent_waves():
    window_started = Event()
    rest_started = Event()

    def run(step):
        if step[0] == "window":
            window_started.set()
            assert rest_started.wait(5)
        elif step[0] == "rest":
            rest_started.set()
            assert window_started.wait(5)
        return 0

    assert runner.run_waves(run, lambda *_: None, _waves(), 2, Event()) == 0


def test_a_timed_out_subprocess_returns_a_failure(tmp_path):
    probe = (
        "import os, runpy, sys; from pathlib import Path; from threading import Event; "
        "run_step = runpy.run_path(sys.argv[1])['run_step']; "
        "raise SystemExit(run_step([sys.executable, '-c', 'import time; time.sleep(60)'], "
        "Path.cwd(), Path('timeout.log'), dict(os.environ), 0.1, Event()))"
    )
    result = subprocess.run([sys.executable, "-c", probe, str(ROOT / "scripts" / "verify.py")],
                            cwd=tmp_path, timeout=20, check=False)
    assert result.returncode == 124


def test_a_direct_command_waits_for_the_same_lock_and_returns_its_status(tmp_path):
    lock = tmp_path / "queue.lock"
    waiting = tmp_path / "waiting"
    ran = tmp_path / "ran"
    handoff = (
        "import runpy, sys; from pathlib import Path; "
        "main = runpy.run_path(sys.argv.pop(1))['main']; "
        "main.__globals__['LOCK'] = Path(sys.argv.pop(1)); "
        "Path(sys.argv.pop(1)).touch(); raise SystemExit(main())"
    )
    command = [
        sys.executable, "-c", handoff, str(ROOT / "scripts" / "verify.py"), str(lock), str(waiting),
        "queue", "--", sys.executable, "-c",
        "import sys; from pathlib import Path; Path(sys.argv[1]).touch(); sys.exit(7)", str(ran),
    ]
    queued = None
    try:
        with runner.machine_queue(lock):
            queued = subprocess.Popen(command)
            deadline = time.monotonic() + 10
            while not waiting.exists() and time.monotonic() < deadline and queued.poll() is None:
                time.sleep(0.01)
            assert waiting.exists()
            with pytest.raises(subprocess.TimeoutExpired):
                queued.wait(timeout=0.5)
            assert not ran.exists()
        assert queued.wait(timeout=10) == 7
        assert ran.is_file()
    finally:
        if queued is not None and queued.poll() is None:
            queued.kill()
            queued.wait(timeout=5)


def test_stopping_a_command_also_ends_a_child_that_ignores_term(tmp_path):
    marker = tmp_path / "descendant.pid"
    script = (
        "import os, signal, sys, time; from pathlib import Path; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(60)"
    )
    command = [sys.executable, "-c", (
        "import subprocess, sys, time; subprocess.Popen(sys.argv[1:]); time.sleep(60)"
    ), sys.executable, "-c", script, str(marker)]
    child = subprocess.Popen(command, start_new_session=not runner.WINDOWS,
                             creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if runner.WINDOWS else 0)
    descendant = None

    def running(process):
        try:
            return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:
            return False

    try:
        deadline = time.monotonic() + 10
        while (not marker.exists() or not marker.stat().st_size) and time.monotonic() < deadline:
            time.sleep(0.01)
        descendant = psutil.Process(int(marker.read_text()))
        runner.stop_process(child)
        deadline = time.monotonic() + 2
        while running(descendant) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not running(descendant)
    finally:
        if descendant is not None and running(descendant):
            descendant.kill()
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
