"""The usage audit's checks by hand (docs/audit/rounds/2611-10.md), as far as
a CI runner can do them. Every test here runs on Linux, macOS and Windows in
CI's backend job; what differs by system is said where it does.

- The Usage page with Codex installed: the page asks for Codex's limits, a
  stand-in ``codex`` (``codex.cmd`` on Windows, as npm installs it) answers,
  and no process of it and no temp file is left.
- ``units.json`` written while another handle holds it open.
- ``#usage-warnings-off`` through the Claude Code hook script, and the facts
  log's lines: tests/test_usage_warnings.py (the hook runs as a process there,
  so CI's Windows job runs them on Windows).
- A poll after the machine slept, and the switch to winter time: a moved
  clock (``SP_NOW``) and ``TZ=America/New_York``.
- macOS: Codex at ``/opt/homebrew/bin`` with a short PATH:
  scripts/ci/codex_path_check.py, a step of the backend job on macOS.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path

import psutil
import pytest
from fastapi.testclient import TestClient

from backend import codexlimits, usagewarn

from .test_codexlimits import _values, fake_codex

MODEL = "claude-opus-5-5"


def _left(marker: str) -> list[str]:
    """Processes whose command line names ``marker``."""
    out = []
    for p in psutil.process_iter(["pid", "cmdline"]):
        try:
            line = " ".join(p.info["cmdline"] or [])
        except (psutil.Error, TypeError):
            continue
        if marker in line and p.info["pid"] != os.getpid():
            out.append(f"{p.info['pid']}: {line[:120]}")
    return out


def _stray(folder: Path) -> list[str]:
    """Temp files a write left: ``.units.json.*``, ``*.tmp``."""
    return sorted(p.name for p in folder.rglob("*") if p.name.endswith(".tmp") or p.name.startswith(".units.json."))


def test_the_usage_page_reads_codex_and_leaves_no_process_and_no_temp_file(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    exe = fake_codex(tmp_path)
    monkeypatch.setattr(codexlimits, "find_codex", lambda: exe)
    root = Path(client.app.state.store.data_root)  # type: ignore[attr-defined]
    assert client.get("/api/usage?project=all&range=7d").status_code == 200
    assert client.post("/api/usage/limits/refresh", json={}).json() == {"refreshed": True}
    deadline = time.monotonic() + 30
    state: dict = {}
    while time.monotonic() < deadline:
        state = client.get("/api/usage/limits").json()["codex_poll"]
        if state["last_success"]:
            break
        time.sleep(0.2)
    assert state["last_success"] and state["cause"] == "", state
    assert client.get("/api/usage/limits").json()["limits"]["codex"]["five_hour"]["used"] == 37.0
    script = str(tmp_path / "fake_codex.py")
    for _ in range(30):
        if not _left(script):
            break
        time.sleep(0.1)
    assert _left(script) == []
    assert _stray(root / ".usage") == []


def test_a_codex_that_starts_a_child_and_never_answers_leaves_nothing(tmp_path: Path) -> None:
    exe = fake_codex(tmp_path, mode="tree")
    got = codexlimits.read(timeout=5, exe=exe)
    assert got["cause"] == "no answer in 5 s"
    child = int((tmp_path / "child.pid").read_text())
    for _ in range(50):
        if not psutil.pid_exists(child) or psutil.Process(child).status() == psutil.STATUS_ZOMBIE:
            break
        time.sleep(0.1)
    assert not psutil.pid_exists(child) or psutil.Process(child).status() == psutil.STATUS_ZOMBIE
    assert _left(str(tmp_path / "fake_codex.py")) == []


def _units(rate: float) -> dict:
    return {"models": [{"model": MODEL, "pct_per_usd": rate}], "fallback": 1.0, "days": 30}


def test_units_are_written_while_another_handle_reads_them(tmp_path: Path) -> None:
    """A reader that lets go within a second (Windows refuses the swap while
    a handle is open; the write waits for it)."""
    assert usagewarn.write_units(tmp_path, _units(1.5))
    path = usagewarn.units_path(tmp_path)
    fh = open(path, encoding="utf-8")
    threading.Timer(0.3, fh.close).start()
    assert usagewarn.write_units(tmp_path, _units(2.5))
    assert usagewarn.read_units(tmp_path) == {"models": {MODEL: 2.5}, "fallback": 1.0}
    assert _stray(tmp_path / ".usage") == []


def test_units_held_open_throughout_keep_the_old_file_and_no_temp(tmp_path: Path) -> None:
    """On Windows the swap is refused while the reader holds the file: the
    write answers False, the old file stays whole, the temp file is deleted.
    Elsewhere the swap goes through."""
    assert usagewarn.write_units(tmp_path, _units(1.5))
    with open(usagewarn.units_path(tmp_path), encoding="utf-8") as held:
        wrote = usagewarn.write_units(tmp_path, _units(2.5))
        held.read()
    assert wrote is (os.name != "nt")
    want = 2.5 if wrote else 1.5
    assert usagewarn.read_units(tmp_path) == {"models": {MODEL: want}, "fallback": 1.0}
    assert _stray(tmp_path / ".usage") == []


# -- the clock --------------------------------------------------------------------


def _ok_reader(**_kw):
    return {"ok": True, "limits_line": {"at": "2026-11-01T00:45:00", "tool": "codex", "account": "a",
                                        "five_hour": {"used": 1.0, "resets_at": "2026-11-01T05:00:00"}},
            "account_id": "", "usage": None}


def test_a_poll_after_the_machine_slept_waits_for_the_network_then_runs(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "bin").mkdir()
    exe = fake_codex(tmp_path / "bin")
    monkeypatch.setattr(codexlimits, "find_codex", lambda: exe)
    p = codexlimits.Poller(tmp_path / "data")
    monkeypatch.setenv("SP_NOW", "2026-11-05T09:00:00")
    assert p.tick()                                         # the first wake: none yet, it polls
    assert codexlimits._read_state(tmp_path / "data")["next_attempt"] == "2026-11-05T15:00:00"
    monkeypatch.setenv("SP_NOW", "2026-11-05T09:01:00")
    assert not p.tick()                                     # a minute later: not due
    # The lid closed at 09:01 and opened at 17:30: the poll is overdue, the network is not up yet.
    monkeypatch.setenv("SP_NOW", "2026-11-05T17:30:00")
    assert not p.tick()
    monkeypatch.setenv("SP_NOW", "2026-11-05T17:31:00")
    assert not p.tick()                                     # still settling (two minutes)
    monkeypatch.setenv("SP_NOW", "2026-11-05T17:32:30")
    assert p.tick()
    st = codexlimits._read_state(tmp_path / "data")
    assert st["last_success"] == "2026-11-05T17:32:30" and st["next_attempt"] == "2026-11-05T23:32:30"


@pytest.fixture()
def new_york(monkeypatch: pytest.MonkeyPatch):
    if not hasattr(time, "tzset"):
        pytest.skip("Windows: a process cannot set its own time zone (no time.tzset)")
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def test_the_switch_to_winter_time_keeps_the_next_attempt(new_york, tmp_path: Path,
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    """2026-11-01: at 02:00 EDT the clocks go back to 01:00 EST, so 01:00 to
    02:00 happens twice. A failure at 01:50 EDT waits 15 minutes: 01:05 EST,
    which reads as an hour earlier in local time."""
    monkeypatch.setattr(codexlimits, "detect", lambda: {"found": True})
    first = datetime.fromisoformat("2026-11-01T01:50:00-04:00").timestamp()
    st = codexlimits.poll(tmp_path, _values(), now=first, reader=lambda: {"ok": False, "cause": "dns error"})
    assert st["next_attempt"] == "2026-11-01T01:05:00" and st["next_epoch"] == first + 900
    assert not codexlimits.due(tmp_path, _values(), now=first + 60)           # 01:51 EDT: not yet
    assert not codexlimits.due(tmp_path, _values(), now=first + 840)          # 01:04 EST
    assert codexlimits.due(tmp_path, _values(), now=first + 900)              # 01:05 EST
    # A success at 00:45 EDT with a 1-hour interval: next at 01:45 EDT, due at 01:15 EST (an hour later).
    early = datetime.fromisoformat("2026-11-01T00:45:00-04:00").timestamp()
    st = codexlimits.poll(tmp_path, _values(**{"usage.codex_poll_hours": 1}), now=early, reader=_ok_reader)
    assert st["next_attempt"] == "2026-11-01T01:45:00"
    assert not codexlimits.due(tmp_path, _values(), now=early + 3000)
    assert codexlimits.due(tmp_path, _values(), now=early + 3600 + 1800)
    # A state written before next_epoch: the local time, read as its first moment.
    path = tmp_path / ".usage" / codexlimits.POLL_FILE
    old = json.loads(path.read_text(encoding="utf-8"))
    old.pop("next_epoch")
    path.write_text(json.dumps(old), encoding="utf-8")
    assert not codexlimits.due(tmp_path, _values(), now=early + 3000)
    assert codexlimits.due(tmp_path, _values(), now=early + 3600)
