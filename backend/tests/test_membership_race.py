"""A leave racing a write (tk_d1d25a4d step 3, note nt_258a7ed7 §8; the
coordinator's decision of 26 Nov: the window is accepted).

The rule pinned: a write whose membership check starts after the ``leave``
row is in the ledger is refused. A write checked while the agent was still
a member counts, even when it lands after the leave.

Two processes, 50 runs. A subprocess appends ``leave BETA`` with
memberships.write and prints the moment the append returned. This process
writes decisions to BETA in a loop as the agent, and the moment each
membership check began is taken inside the check itself: memberships.may_write
is wrapped to note ``time.perf_counter_ns()`` on entry. That counter is one
clock for the whole machine and fine-grained everywhere (CLOCK_MONOTONIC on
Linux, mach_absolute_time on macOS, QueryPerformanceCounter on Windows), so
the two processes' moments compare. ``time.monotonic_ns()`` is not: on
Windows it ticks every 15.6 ms, and CI found a check and the leave's end on
the same tick. A timestamp taken before the
request would only bound the check from below and could hide a late check.
Every write that succeeded must have begun its check before the leave's
append returned; every write checked after it must be refused.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import mcp, memberships
from backend.server import create_app
from tests.conftest import make_chat

pytestmark = pytest.mark.strict_membership

A = "cc-race0001"
VIA = {mcp.VIA_HEADER: mcp.VIA_VALUE}
RUNS = 50
#: How far ahead the leaver starts, so this process is already writing.
LEAD_S = 0.3
#: How long the loop writes in one run at most.
RUN_S = 4.0

_LEAVER = r"""
import sys, time
sys.path.insert(0, sys.argv[1])
from backend import memberships
root, agent, start = sys.argv[2:5]
while time.time() < float(start):
    pass
memberships.write(root, agent, "leave", "BETA")
print(time.perf_counter_ns())
"""


@pytest.fixture()
def world(data_root: Path, monkeypatch):
    make_chat(data_root, "ALPHA", A, [("2026-11-20T10:00:00", "start", "ok")])
    checks: list[int] = []
    real = memberships.may_write

    def noted(store, agent, project):
        if project == "BETA":
            checks.append(time.perf_counter_ns())
        return real(store, agent, project)

    monkeypatch.setattr(memberships, "may_write", noted)
    with TestClient(create_app(data_root=data_root, watch=False)) as c:
        yield c, data_root, checks


def test_a_write_checked_after_the_leave_is_refused(world) -> None:
    c, root, checks = world
    backend_dir = str(Path(__file__).resolve().parents[1])
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    seen = {"before": 0, "after": 0, "landed_after": 0}
    for run in range(RUNS):
        memberships.write(root, A, "join", "BETA")
        start = time.time() + LEAD_S
        leaver = subprocess.Popen([sys.executable, "-c", _LEAVER, backend_dir, str(root), A, str(start)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        writes: list[tuple[int, int, int]] = []       # (check began, status, answered)
        refused_since = 0
        end = time.time() + RUN_S
        n = 0
        while time.time() < end and refused_since < 3:
            n += 1
            checks.clear()
            r = c.post("/api/decisions", json={
                "agent_id": A, "project": "BETA", "created_date": "2611-26", "created_time": "10:00",
                "decision": f"race {run} write {n}", "why": "x"}, headers=VIA)
            assert checks, "the gate did not check the membership"
            writes.append((checks[0], r.status_code, time.perf_counter_ns()))
            refused_since = refused_since + 1 if r.status_code == 403 else 0
        out, err = leaver.communicate(timeout=60)
        assert leaver.returncode == 0, err
        left_at = int(out.strip())
        for began, status, answered in writes:
            if status == 201:
                assert began < left_at, (run, began, left_at)
                seen["before"] += 1
                seen["landed_after"] += answered > left_at
            else:
                assert status == 403, status
                seen["after"] += 1
        # Every write whose check began after the leave's append returned was refused.
        assert all(s == 403 for b, s, _a in writes if b > left_at), run
        assert any(s == 403 for _b, s, _a in writes), f"run {run}: the leave never showed"
    print("leave racing a write, 50 runs:", seen)
