"""The test run starts from a clean environment (conftest.py).

A shell in Slightly Parallel's own terminal exports SP_ENABLE_TERMINAL and
SP_TERMINAL; an agent's shell exports its session. Before conftest cleared
them, four terminal tests failed for every agent working in that terminal
and passed on CI. These tests run a pytest with such a shell's variables and
see the same four pass.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from tests.conftest import LEAKED_NAMES, TEST_KNOBS, leaked

BACKEND = Path(__file__).resolve().parents[1]

#: What conftest itself sets for the run (SP_EXAMPLES by an autouse
#: fixture, per test); nothing else of the leaked kind.
SET_BY_CONFTEST = {"SP_SANDBOX", "SP_DATA_ROOT", "SP_LOG_FILE", "SP_FSYNC", "SP_EXAMPLE",
                   "SP_EXAMPLES"}

#: The tests that failed in Slightly Parallel's terminal (18 Nov 2026).
WERE_FAILING = [
    "tests/test_terminal.py::test_off_until_switched_on",
    "tests/test_terminal.py::test_the_snapshot_says_the_terminal_is_on_when_the_setting_says_so",
    "tests/test_terminal.py::test_the_new_writes_are_off_with_the_terminal",
    "tests/test_settings.py::test_snapshot_capabilities_and_no_daily_activity",
]

#: A developer's shell inside Slightly Parallel's terminal, run by an agent.
LEAKY_SHELL = {
    "SP_ENABLE_TERMINAL": "1",
    "SP_TERMINAL": "t00000000",
    "SP_PORT": "9",
    "SP_ALLOW_LAN": "1",
    "SP_EXAMPLES": "1",
    "SP_SMART_TIMER": "1",
    "SP_API": "http://127.0.0.1:9",
    "SP_TOKEN": "a-leaked-token",
    "SCAN_DATA_ROOT": "/nonexistent/operator-data",
    "DATA_ROOT": "/nonexistent/operator-data",
    "PORT": "9",
    "HOST": "0.0.0.0",
    "CLAUDECODE": "1",
    "CLAUDE_CODE_SESSION_ID": "00000000-0000-0000-0000-000000000000",
    "CLAUDE_PID": "1",
    "CODEX_THREAD_ID": "leaked-thread",
    "TMUX": "/tmp/tmux-0/default,1,0",
    "TMUX_PANE": "%0",
}


def test_this_run_sees_none_of_the_shells_variables() -> None:
    left = {n for n in os.environ if leaked(n)} - SET_BY_CONFTEST
    assert left == set()
    assert os.environ["SP_SANDBOX"] == "1"


def test_the_suites_own_knobs_are_kept() -> None:
    assert all(not leaked(n) for n in TEST_KNOBS)
    assert leaked("SP_ENABLE_TERMINAL") and leaked("SP_SOMETHING_NEW")
    assert leaked("CLAUDE_CODE_SESSION_ID") and "SCAN_DATA_ROOT" in LEAKED_NAMES


def test_the_terminal_tests_pass_under_a_leaky_shell() -> None:
    env = {**os.environ, **LEAKY_SHELL}
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-o", "addopts=",
         "-q", *WERE_FAILING],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=300,
    )
    assert run.returncode == 0, run.stdout[-3000:] + run.stderr[-2000:]
    assert f"{len(WERE_FAILING)} passed" in run.stdout
