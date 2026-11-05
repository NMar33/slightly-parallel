"""Codex's plan limits read through codex app-server (codexlimits.py)."""

from __future__ import annotations

import json
import os
import stat
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend import app_settings, codexlimits, hookshared, usagelib

LIMITS_RESULT: dict[str, Any] = {
    "ordinaryUsageAllowed": True,
    "rateLimits": {"limitId": "codex", "primary": {"usedPercent": 1, "windowDurationMins": 300, "resetsAt": 1793813098},
                   "secondary": {"usedPercent": 0, "windowDurationMins": 10080, "resetsAt": 1794399898},
                   "planType": "plus", "rateLimitReachedType": None},
    "rateLimitsByLimitId": {"codex": {"limitId": "codex",
                                      "primary": {"usedPercent": 37, "windowDurationMins": 300, "resetsAt": 1793813098},
                                      "secondary": {"usedPercent": 12, "windowDurationMins": 10080, "resetsAt": 1794399898},
                                      "planType": "plus"}},
    "accountId": "f01e811e-5bb8-43a8-b34d-04c284101f1f",
}
USAGE_RESULT: dict[str, Any] = {
    "summary": {"lifetimeTokens": 232245512, "peakDailyTokens": 33340739},
    "dailyUsageBuckets": [{"startDate": "2026-09-21", "tokens": 324645}, {"startDate": "2026-09-22", "tokens": None}],
    "threadUsage": None,
}

FAKE = r'''
import json, sys, time
sys.stderr.write("warning: Codex's Linux sandbox uses bubblewrap\n"); sys.stderr.flush()
mode = %(mode)r
limits = json.loads(%(limits)r)
usage = json.loads(%(usage)r)
if mode == "old":
    sys.exit(2)
if mode == "tree":
    import subprocess
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    open(%(pidfile)r, "w").write(str(child.pid))
    time.sleep(60)
for raw in sys.stdin:
    msg = json.loads(raw)
    if "id" not in msg:
        continue
    i, m = msg["id"], msg["method"]
    if mode == "silent":
        time.sleep(30)
    if m == "initialize":
        print(json.dumps({"id": i, "result": {"userAgent": "fake/0.163.0", "codexHome": "/x"}}))
        print(json.dumps({"method": "account/updated", "params": {"authMode": "chatgpt"}}))
    elif m == "account/read":
        if msg.get("params") != {"refreshToken": False}:
            print(json.dumps({"id": i, "error": {"code": -32600, "message": "Invalid request: missing field `params`"}}))
        elif mode == "out":
            print(json.dumps({"id": i, "result": {"account": None, "requiresOpenaiAuth": True}}))
        else:
            print(json.dumps({"id": i, "result": {"account": {"type": "chatgpt", "planType": "plus"}}}))
    elif m == "account/rateLimits/read":
        if mode == "neterr":
            print(json.dumps({"id": i, "error": {"code": -32000, "message": "failed to fetch usage: dns error for me@example.com"}}))
        else:
            print(json.dumps({"id": i, "result": limits}))
    elif m == "account/usage/read":
        print(json.dumps({"id": i, "result": usage}))
    sys.stdout.flush()
'''


def fake_codex(tmp_path: Path, mode: str = "ok", limits: dict[str, Any] | None = None) -> str:
    """A ``codex`` on disk that speaks the app-server protocol; its path."""
    script = tmp_path / "fake_codex.py"
    script.write_text(FAKE % {"mode": mode, "limits": json.dumps(limits or LIMITS_RESULT), "usage": json.dumps(USAGE_RESULT),
                              "pidfile": str(tmp_path / "child.pid")})
    if os.name == "nt":
        exe = tmp_path / "codex.cmd"
        exe.write_text(f'@"{sys.executable}" -I "{script}" %*\r\n')
        return str(exe)
    exe = tmp_path / "codex"
    exe.write_text(f"#!/bin/sh\nexec '{sys.executable}' -I '{script}' \"$@\"\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return str(exe)


def test_the_limits_line_takes_the_codex_bucket_by_window_length() -> None:
    line = codexlimits.limits_line(LIMITS_RESULT, "2026-11-05T01:00:00")
    assert line is not None
    assert line["tool"] == "codex" and line["source"] == "app-server" and line["plan"] == "plus"
    assert line["five_hour"]["used"] == 37.0 and line["five_hour"]["span_s"] == 300 * 60
    assert line["seven_day"]["used"] == 12.0 and line["seven_day"]["span_s"] == 10080 * 60
    assert line["five_hour"]["resets_at"] == hookshared.epoch_local(1793813098)
    assert line["account_id"] == "f01e811e-5bb8-43a8-b34d-04c284101f1f"
    assert line["model"] == "" and line["session"] == "" and len(line["account"]) == 12


def test_a_window_of_another_length_is_not_written_as_a_known_one() -> None:
    odd = {"rateLimits": {"primary": {"usedPercent": 5, "windowDurationMins": 60, "resetsAt": 1793813098},
                          "secondary": {"usedPercent": 9, "windowDurationMins": 10080, "resetsAt": 1794399898}}}
    line = codexlimits.limits_line(odd, "2026-11-05T01:00:00")
    assert line is not None and "five_hour" not in line and line["seven_day"]["used"] == 9.0
    only_odd = {"rateLimits": {"primary": {"usedPercent": 5, "windowDurationMins": 60, "resetsAt": 1}}}
    assert codexlimits.limits_line(only_odd, "2026-11-05T01:00:00") is None


def test_read_speaks_to_a_codex_on_disk(tmp_path: Path) -> None:
    got = codexlimits.read(timeout=10, exe=fake_codex(tmp_path), at="2026-11-05T01:00:00")
    assert got["ok"], got
    assert got["limits_line"]["five_hour"]["used"] == 37.0
    assert got["account_id"].startswith("f01e811e")
    assert got["usage"]["days"] == [{"date": "2026-09-21", "tokens": 324645}, {"date": "2026-09-22", "tokens": None}]
    assert got["usage"]["summary"]["lifetimeTokens"] == 232245512


def test_read_names_its_causes(tmp_path: Path) -> None:
    assert codexlimits.read(exe="")["cause"] == "codex is not on this machine"
    (tmp_path / "old").mkdir()
    assert codexlimits.read(timeout=10, exe=fake_codex(tmp_path / "old", mode="old"))["cause"] == "codex has no app-server (older version)"
    (tmp_path / "out").mkdir()
    assert codexlimits.read(timeout=10, exe=fake_codex(tmp_path / "out", mode="out"))["cause"] == "not signed in"
    (tmp_path / "neterr").mkdir()
    assert codexlimits.read(timeout=10, exe=fake_codex(tmp_path / "neterr", mode="neterr"))["cause"] == "failed to fetch usage: dns error for <address>"
    (tmp_path / "silent").mkdir()
    t0 = time.monotonic()
    assert codexlimits.read(timeout=1.5, exe=fake_codex(tmp_path / "silent", mode="silent"))["cause"] == "no answer in 1 s"
    assert time.monotonic() - t0 < 10   # the process was killed, not waited for


def test_a_read_that_times_out_ends_what_the_wrapper_started(tmp_path: Path) -> None:
    psutil = pytest.importorskip("psutil")
    # Long enough for the stand-in to start its child with the whole suite running.
    assert codexlimits.read(timeout=8, exe=fake_codex(tmp_path, mode="tree"))["cause"] == "no answer in 8 s"
    child = int((tmp_path / "child.pid").read_text())
    for _ in range(50):
        if not psutil.pid_exists(child) or psutil.Process(child).status() == psutil.STATUS_ZOMBIE:
            return
        time.sleep(0.1)
    raise AssertionError("the program the wrapper started is still running")


def test_codex_is_found_outside_the_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.setattr(codexlimits.Path, "home", lambda: tmp_path)
    assert codexlimits.find_codex() == ""
    for version in ("v9.1.0", "v24.15.0"):
        folder = tmp_path / ".nvm" / "versions" / "node" / version / "bin"
        folder.mkdir(parents=True)
        fake_codex(folder)
    if os.name != "nt":
        assert "v24.15.0" in codexlimits.find_codex()


def _values(**over: Any) -> dict[str, Any]:
    return {**app_settings.defaults(), **over}


def test_poll_writes_the_reading_the_account_file_and_the_state(tmp_path: Path) -> None:
    now = datetime(2026, 11, 5, 1, 0, 0).timestamp()
    exe = fake_codex(tmp_path)
    st = codexlimits.poll(tmp_path, _values(), now=now, reader=lambda: codexlimits.read(exe=exe, at="2026-11-05T01:00:00"))
    assert st["written"] and st["failures"] == 0 and st["cause"] == ""
    assert st["last_success"] == "2026-11-05T01:00:00" and st["next_attempt"] == "2026-11-05T07:00:00"
    rows, _bad = usagelib.limit_history(tmp_path)
    assert rows["codex"][-1]["source"] == "app-server" and rows["codex"][-1]["five_hour"]["used"] == 37.0
    account = json.loads((tmp_path / ".usage" / "codex-account.json").read_text())
    assert account["days"][0] == {"date": "2026-09-21", "tokens": 324645}
    state = codexlimits.state(tmp_path, _values())
    assert state["last_success"] == "2026-11-05T01:00:00" and state["every_hours"] == 6 and state["enabled"]
    # Fresh: not due before the next attempt; due after it.
    assert not codexlimits.due(tmp_path, _values(), now=now + 3600) or not codexlimits.detect()["found"]
    assert codexlimits.due(tmp_path, _values(), now=now + 7 * 3600) == codexlimits.detect()["found"]


def test_a_failing_poll_backs_off_and_keeps_its_cause(tmp_path: Path) -> None:
    now = datetime(2026, 11, 5, 1, 0, 0).timestamp()
    bad = lambda: {"ok": False, "cause": "not signed in"}  # noqa: E731
    st = codexlimits.poll(tmp_path, _values(), now=now, reader=bad)
    assert st["failures"] == 1 and st["cause"] == "not signed in" and st["next_attempt"] == "2026-11-05T01:15:00"
    st = codexlimits.poll(tmp_path, _values(), now=now + 900, reader=bad)
    assert st["failures"] == 2 and st["next_attempt"] == "2026-11-05T02:15:00"
    st = codexlimits.poll(tmp_path, _values(), now=now + 4500, reader=bad)
    assert st["failures"] == 3 and st["next_attempt"] == "2026-11-05T08:15:00"
    # The backoff never passes the setting's interval.
    st = codexlimits.poll(tmp_path, _values(**{"usage.codex_poll_hours": 1}), now=now + 4500, reader=bad)
    assert st["next_attempt"] == "2026-11-05T03:15:00"
    assert not (tmp_path / ".usage" / "limits.jsonl").exists()
    assert codexlimits.state(tmp_path, _values())["cause"] == "not signed in"


def test_another_cause_starts_the_backoff_over(tmp_path: Path) -> None:
    now = datetime(2026, 11, 5, 9, 0, 0).timestamp()
    codexlimits.poll(tmp_path, _values(), now=now, reader=lambda: {"ok": False, "cause": "not signed in"})
    st = codexlimits.poll(tmp_path, _values(), now=now + 60, reader=lambda: {"ok": False, "cause": "dns error"})
    assert st["failures"] == 1 and st["next_attempt"] == "2026-11-05T09:16:00"


def test_the_poller_waits_for_the_network_after_the_machine_slept(tmp_path: Path) -> None:
    p = codexlimits.Poller(tmp_path)
    assert p._settled(1000.0)                     # the first look
    assert p._settled(1060.0)                     # a minute later
    assert not p._settled(30000.0)                # the clock jumped: it slept
    assert not p._settled(30060.0)
    assert p._settled(30000.0 + codexlimits.SETTLE_S)


def test_the_poll_is_off_by_the_setting(tmp_path: Path) -> None:
    assert not codexlimits.due(tmp_path, _values(**{"usage.codex_poll": False}))


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    from backend.server import create_app
    root = tmp_path / "root"
    root.mkdir()
    (root / "projects").mkdir()
    app = create_app(root, watch=False)
    return TestClient(app)


def test_the_limits_answer_carries_the_poll_state(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(codexlimits, "find_codex", lambda: "/usr/bin/codex")
    got = client.get("/api/usage/limits").json()
    assert got["codex_poll"]["found"] and got["codex_poll"]["every_hours"] == 6 and got["codex_poll"]["cause"] == ""


def test_refresh_is_the_operators_and_keeps_a_fresh_reading(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(codexlimits, "find_codex", lambda: "")
    assert client.post("/api/usage/limits/refresh", json={}).json() == {"refreshed": False, "why": "absent"}
    monkeypatch.setattr(codexlimits, "find_codex", lambda: "/usr/bin/codex")
    r = client.post("/api/usage/limits/refresh", json={"agent_id": "codex-abc"})
    assert r.status_code == 422 and "operator" in r.json()["detail"]
    root = Path(client.app.state.settings.data_root)
    (root / ".usage").mkdir(exist_ok=True)
    at = datetime.now().replace(microsecond=0).isoformat()
    (root / ".usage" / "limits.jsonl").write_text(json.dumps(
        {"at": at, "tool": "codex", "account": "aaaaaaaaaaaa", "model": "", "session": "",
         "five_hour": {"used": 3.0, "resets_at": at}, "source": "app-server"}) + "\n")
    assert client.post("/api/usage/limits/refresh", json={}).json() == {"refreshed": False, "why": "fresh"}
    ran: list[Any] = []
    monkeypatch.setattr(codexlimits, "refresh_wanted", lambda _root, now=None: True)
    monkeypatch.setattr(codexlimits, "poll", lambda root, *a, **k: ran.append(root))
    assert client.post("/api/usage/limits/refresh", json={}).json() == {"refreshed": True}
    for _ in range(50):
        if ran:
            break
        time.sleep(0.02)
    assert ran == [root]


def test_the_poller_thread_starts_and_stops(tmp_path: Path) -> None:
    p = codexlimits.Poller(tmp_path)
    p.start()
    p.stop(wait=2)
    assert p._thread is not None and not p._thread.is_alive()


def test_limits_append_keeps_the_series_with_rollout_lines(tmp_path: Path) -> None:
    """An app-server reading and a rollout reading of the same CODEX_HOME are one series."""
    from backend import hookshared
    rollout = hookshared.limits_line_codex({"primary": {"used_percent": 20, "window_minutes": 300, "resets_at": 1793813098}},
                                           "2026-11-05T00:50:00")
    hookshared.limits_append(tmp_path, rollout, now=datetime(2026, 11, 5, 0, 50).timestamp())
    line = codexlimits.limits_line(LIMITS_RESULT, "2026-11-05T01:00:00")
    assert line is not None and line["account"] == rollout["account"]
    assert hookshared.limits_append(tmp_path, line, now=datetime(2026, 11, 5, 1, 0).timestamp())
    got = usagelib.limits(tmp_path, datetime(2026, 11, 5, 1, 1))["codex"]
    assert got["accounts_n"] == 1 and got["source"] == "app-server" and got["five_hour"]["used"] == 37.0


def test_no_tmp_files_left(tmp_path: Path) -> None:
    codexlimits.poll(tmp_path, _values(), now=time.time(), reader=lambda: {"ok": False, "cause": "x"})
    assert not [p for p in (tmp_path / ".usage").iterdir() if p.suffix == ".tmp"]
