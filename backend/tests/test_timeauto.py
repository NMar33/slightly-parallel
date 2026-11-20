"""The smart timer: away pauses, auto spans that top a manual timer up,
time on a task, and each project's mode."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import idle, timeauto
from backend.server import create_app

# Now, not a fixed hour: a timer started through the API takes the real clock.
T0 = datetime.now().replace(microsecond=0).timestamp()


def test_sandbox_timer_does_not_read_the_host_idle_clock(monkeypatch):
    monkeypatch.setenv("SP_SANDBOX", "1")
    monkeypatch.setattr(idle, "_cache", (0.0, None, ""))
    monkeypatch.setattr(idle, "_read", lambda: (3600.0, "host"))
    assert idle.reading() == (None, "")
    monkeypatch.delenv("SP_SANDBOX")
    assert idle.reading() == (3600.0, "host")


def _when(stored: str) -> float:
    """A stored moment as Unix time; it carries its UTC offset (tk_3a363c87)."""
    got = datetime.fromisoformat(stored)
    assert got.tzinfo is not None, f"{stored} has no offset"
    return got.timestamp()


class Clock:
    """Time and idle, moved by the test."""

    def __init__(self) -> None:
        self.now = T0
        self.idle: float | None = 0.0

    def __call__(self) -> float:
        return self.now

    def reading(self):
        return self.idle, "test"


@pytest.fixture()
def env(tmp_path: Path):
    # T0 is now, per test: an entry started below takes the real clock, and
    # a slow runner can take minutes from collecting the module to running it.
    global T0
    T0 = datetime.now().replace(microsecond=0).timestamp() - 1   # a second before any entry starts
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    app = create_app(data_root=root, watch=False)
    clock = Clock()
    app.state.timer = timeauto.AutoTimer(app.state.store, read_idle=clock.reading, clock=clock)
    with TestClient(app) as c:
        yield c, app.state.timer, clock


def _entries(c) -> list[dict]:
    return c.get("/api/time-entries").json()["time_entries"]


def _row(c, entry: dict) -> dict:
    return c.get(f"/api/time-entries/{entry['id']}").json()["metadata"]


def _at(clock: Clock, sec: float, timer, idle: float | None = 0.0) -> None:
    clock.now = T0 + sec
    clock.idle = idle
    timer.tick()


def test_a_project_is_reminded_by_default_and_takes_the_mode_it_is_given(env) -> None:
    c, _, _ = env
    assert c.get("/api/time/auto").json()["default_mode"] == "remind"
    assert c.post("/api/time/auto/mode", json={"project": "alpha", "mode": "auto"}).json()["mode"] == "auto"
    assert c.get("/api/time/auto").json()["modes"] == {"alpha": "auto"}
    assert c.post("/api/time/auto/mode", json={"project": "alpha", "mode": "sometimes"}).status_code == 422


def test_working_on_an_auto_project_writes_its_own_entry_on_the_task(env) -> None:
    c, timer, clock = env
    c.post("/api/time/auto/mode", json={"project": "alpha", "mode": "auto"})
    timer.beat("alpha", "tk_one", "page")
    _at(clock, 0, timer)
    for s in range(20, 300, 20):          # five minutes of beats
        clock.now = T0 + s
        timer.beat("alpha", "tk_one", "page")
        _at(clock, s, timer)
    running = [e for e in _entries(c) if not e.get("ended_at")]
    assert len(running) == 1 and running[0]["source"] == "auto" and running[0]["share_pct"] == 100
    assert running[0]["task_id"] == "tk_one"

    # A 40-second glance elsewhere is inside the grace: the span goes on.
    _at(clock, 320, timer)
    timer.beat("alpha", "tk_one", "page")
    _at(clock, 330, timer)
    assert len([e for e in _entries(c) if not e.get("ended_at")]) == 1

    # Gone past the grace: the span ends where the last beat was.
    _at(clock, 500, timer)
    [done] = _entries(c)
    assert _when(done["ended_at"]) == T0 + 320 and done["duration_min"] == 5
    got = c.get("/api/time/summary", params={"task_id": "tk_one"}).json()
    assert got["total_min"] == 5


def test_auto_time_tops_a_manual_timer_up_to_full(env) -> None:
    c, timer, clock = env
    c.post("/api/time/auto/mode", json={"project": "alpha", "mode": "auto"})
    manual = c.post("/api/time/start", json={"project": "alpha", "share_pct": 10}).json()
    timer.beat("alpha", "", "terminal")
    _at(clock, 0, timer)
    auto = [e for e in _entries(c) if e.get("source") == "auto"]
    # 10 % by hand + 90 % while working = the whole of the time, no overlap.
    assert [e["share_pct"] for e in auto] == [90]
    # The auto row never blocks a timer of its own block.
    assert manual["share_pct"] == 10


def test_a_glance_is_not_work(env) -> None:
    c, timer, clock = env
    c.post("/api/time/auto/mode", json={"project": "alpha", "mode": "auto"})
    timer.beat("alpha", "", "page")
    _at(clock, 0, timer)
    _at(clock, 200, timer)   # one beat, then nothing: under a minute
    assert _entries(c) == []


def test_a_remind_project_counts_nothing_by_itself(env) -> None:
    c, timer, clock = env
    timer.beat("alpha", "tk_one", "page")
    _at(clock, 0, timer)
    _at(clock, 30, timer)
    assert _entries(c) == []


def test_away_pauses_back_to_the_last_input_and_counting_it_gives_it_back(env) -> None:
    c, timer, clock = env
    entry = c.post("/api/time/start", json={"project": "alpha"}).json()
    # Twelve minutes with no input anywhere: paused where the input stopped.
    _at(clock, 12 * 60, timer, idle=12 * 60 - 1)
    row = _row(c, entry)
    assert row["paused_at"]
    # Back 23 minutes after leaving: resumed by itself, the gap noticed.
    _at(clock, 24 * 60, timer, idle=5)
    notice = c.get("/api/time/auto").json()["away"]
    assert len(notice) == 1 and not notice[0]["long"] and 22 * 60 <= notice[0]["sec"] <= 24 * 60
    row = _row(c, entry)
    assert not row["paused_at"] and row["paused_total_sec"] > 0
    counted = c.post(f"/api/time/auto/away/{entry['id']}", json={"action": "count"}).json()
    assert counted["paused_total_sec"] < 60
    assert c.get("/api/time/auto").json()["away"] == []


def test_a_long_absence_stays_paused_and_asks(env) -> None:
    c, timer, clock = env
    entry = c.post("/api/time/start", json={"project": "alpha"}).json()
    _at(clock, 15 * 60, timer, idle=14 * 60)
    _at(clock, 5 * 3600, timer, idle=3)
    [notice] = c.get("/api/time/auto").json()["away"]
    assert notice["long"]
    assert _row(c, entry)["paused_at"]
    stopped = c.post(f"/api/time/auto/away/{entry['id']}", json={"action": "stop"}).json()
    assert stopped["ended_at"] and stopped["duration_min"] <= 2


def test_idle_that_cannot_be_read_never_pauses(env) -> None:
    c, timer, clock = env
    entry = c.post("/api/time/start", json={"project": "alpha"}).json()
    _at(clock, 3600, timer, idle=None)
    assert not _row(c, entry)["paused_at"]
    assert c.get("/api/time/auto").json()["idle_sec"] is None


def test_a_restart_closes_the_span_where_it_was_last_seen(env) -> None:
    c, timer, clock = env
    c.post("/api/time/auto/mode", json={"project": "alpha", "mode": "auto"})
    for s in range(0, 181, 20):
        clock.now = T0 + s
        timer.beat("alpha", "", "page")
        _at(clock, s, timer)
    fresh = timeauto.AutoTimer(timer.store, read_idle=clock.reading, clock=clock)
    fresh.recover()
    [row] = _entries(c)
    assert _when(row["ended_at"]) == T0 + 180 and row["duration_min"] == 3


# ------------------------------------------------------------------ the terminal window
#
# The terminal window (/term) sends the pages' beat with source "window"
# while it is in front on a tab of the project and there is input.


def _window(c, project: str, task_id: str = "") -> None:
    got = c.post("/api/time/auto/beat", json={"project": project, "task_id": task_id, "source": "window"})
    assert got.status_code == 200, got.text


def test_a_window_beat_starts_the_projects_span_and_more_beats_extend_it(env) -> None:
    c, timer, clock = env
    c.post("/api/time/auto/mode", json={"project": "alpha", "mode": "auto"})
    _window(c, "alpha", "tk_w")
    _at(clock, 0, timer)
    [span] = c.get("/api/time/auto").json()["working"]
    assert span["project"] == "alpha" and span["task_id"] == "tk_w"
    assert c.get("/api/time/auto").json()["signals"] == [{"project": "alpha", "source": "window", "task_id": "tk_w", "sec_ago": 0}]
    for s in range(20, 181, 20):
        clock.now = T0 + s
        _window(c, "alpha", "tk_w")
        _at(clock, s, timer)
    assert [s["entry_id"] for s in c.get("/api/time/auto").json()["working"]] == [span["entry_id"]]
    _at(clock, 400, timer)                    # no beat past the grace: it ends at the last one
    [done] = _entries(c)
    assert done["source"] == "auto" and done["duration_min"] == 3 and done["task_id"] == "tk_w"


def test_idle_stops_a_window_span_even_with_a_fresh_beat(env) -> None:
    c, timer, clock = env
    c.post("/api/time/auto/mode", json={"project": "alpha", "mode": "auto"})
    for s in range(0, 121, 20):
        clock.now = T0 + s
        _window(c, "alpha")
        _at(clock, s, timer)
    clock.now = T0 + 140
    _window(c, "alpha")
    _at(clock, 140, timer, idle=11 * 60)      # the computer says nobody is here
    assert c.get("/api/time/auto").json()["working"] == []
    [done] = _entries(c)
    assert done["ended_at"] and done["duration_min"] == 2


def test_switching_the_tab_to_another_project_moves_the_time_there(env) -> None:
    c, timer, clock = env
    for p in ("alpha", "beta"):
        c.post("/api/time/auto/mode", json={"project": p, "mode": "auto"})
    for s in range(0, 121, 20):
        clock.now = T0 + s
        _window(c, "alpha")
        _at(clock, s, timer)
    for s in range(140, 321, 20):             # the tab of beta in front from here
        clock.now = T0 + s
        _window(c, "beta")
        _at(clock, s, timer)
    working = c.get("/api/time/auto").json()["working"]
    assert [w["project"] for w in working] == ["beta"]
    alpha = [e for e in _entries(c) if e["project"] == "alpha"]
    assert len(alpha) == 1 and alpha[0]["ended_at"] and alpha[0]["duration_min"] == 2
    _at(clock, 500, timer)
    beta = [e for e in _entries(c) if e["project"] == "beta"]
    assert len(beta) == 1 and beta[0]["duration_min"] == 3


def test_a_beat_from_an_unknown_source_is_refused_and_counts_nothing(env) -> None:
    c, timer, clock = env
    c.post("/api/time/auto/mode", json={"project": "alpha", "mode": "auto"})
    got = c.post("/api/time/auto/beat", json={"project": "alpha", "source": "terminal"})
    assert got.status_code == 422
    _at(clock, 0, timer)
    assert c.get("/api/time/auto").json()["working"] == []
