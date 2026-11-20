"""The terminal verification pilot's dispatch and result contracts."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
from threading import Event

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
    result = runner.run_step(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        tmp_path, tmp_path / "timeout.log", dict(os.environ), 0.1, Event(),
    )
    assert result == 124
