"""A break the operator takes (timebreak.py, POST /api/time/auto/break):
the smart timer's spans close and stay closed, manual timers pause, and
«Готово» resumes only what the break paused (tk_810245f2, tk_caf2b06a)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import timeauto
from backend.server import create_app

T0 = datetime.now().replace(microsecond=0).timestamp()


class Clock:
    def __init__(self) -> None:
        self.now = T0
        self.idle: float | None = 0.0

    def __call__(self) -> float:
        return self.now

    def reading(self):
        return self.idle, "test"


@pytest.fixture()
def env(tmp_path: Path):
    global T0
    T0 = datetime.now().replace(microsecond=0).timestamp() - 1
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    (root / "projects" / "beta").mkdir(parents=True)
    app = create_app(data_root=root, watch=False)
    clock = Clock()
    clock.now = T0
    app.state.timer = timeauto.AutoTimer(app.state.store, read_idle=clock.reading, clock=clock)
    with TestClient(app) as c:
        yield c, app.state.timer, clock, root


def _entries(c) -> list[dict]:
    return c.get("/api/time-entries").json()["time_entries"]


def _row(c, entry_id: str) -> dict:
    return c.get(f"/api/time-entries/{entry_id}").json()["metadata"]


def _work(c, timer, clock, project: str, start: int, end: int) -> None:
    """Beats every 20 s from `start` to `end` seconds, with a tick after each."""
    for s in range(start, end + 1, 20):
        clock.now = T0 + s
        timer.beat(project, "", "window")
        timer.tick()


def _open_auto(c) -> list[dict]:
    return [e for e in _entries(c) if e.get("source") == "auto" and not e.get("ended_at")]


def test_a_break_closes_the_auto_span_and_beats_open_none_until_done(env) -> None:
    c, timer, clock, _ = env
    c.post("/api/time/auto/mode", json={"project": "alpha", "mode": "auto"})
    _work(c, timer, clock, "alpha", 0, 300)
    [span] = _open_auto(c)

    got = c.post("/api/time/auto/break", json={"on": True, "note": ""}).json()
    assert got["on"] is True and got["closed"] == [span["id"]]
    assert _open_auto(c) == []
    assert _row(c, span["id"])["ended_at"]

    # Typing in the window during the break counts nothing.
    _work(c, timer, clock, "alpha", 320, 600)
    assert _open_auto(c) == []
    assert c.get("/api/time/auto").json()["working"] == []

    done = c.post("/api/time/auto/break", json={"on": False, "note": "чай"}).json()
    assert done["on"] is False and done["ended"]["note"] == "чай"
    assert done["ended"]["sec"] == 300
    # The next beat opens a span again.
    _work(c, timer, clock, "alpha", 620, 700)
    assert len(_open_auto(c)) == 1


def test_a_break_pauses_running_manual_timers_and_resumes_only_those(env) -> None:
    c, timer, clock, _ = env
    a = c.post("/api/time/start", json={"project": "alpha"}).json()
    b = c.post("/api/time/start", json={"project": "beta"}).json()
    held = c.post("/api/time/start", json={"project": "beta", "sprint_id": "sp_x"}).json()
    c.post(f"/api/time/{held['id']}/pause")          # paused by hand before the break
    before_held = _row(c, held["id"])["paused_at"]

    clock.now = T0 + 60
    got = c.post("/api/time/auto/break", json={"on": True}).json()
    assert sorted(got["paused"]) == sorted([a["id"], b["id"]])
    assert _row(c, a["id"])["paused_at"] and _row(c, b["id"])["paused_at"]

    # beta is resumed by hand during the break: the break leaves it alone after.
    c.post(f"/api/time/{b['id']}/resume")

    clock.now = T0 + 60 + 600
    done = c.post("/api/time/auto/break", json={"on": False}).json()
    assert done["ended"]["resumed"] == [a["id"]]
    ra = _row(c, a["id"])
    assert not ra["paused_at"] and int(ra["paused_total_sec"]) >= 600
    # The timer paused by hand stays paused, untouched.
    assert _row(c, held["id"])["paused_at"] == before_held


def test_a_break_for_one_project_holds_only_that_project(env) -> None:
    c, timer, clock, _ = env
    for p in ("alpha", "beta"):
        c.post("/api/time/auto/mode", json={"project": p, "mode": "auto"})
    _work(c, timer, clock, "alpha", 0, 100)
    _work(c, timer, clock, "beta", 0, 100)
    c.post("/api/time/auto/break", json={"on": True, "project": "alpha"})
    _work(c, timer, clock, "alpha", 120, 200)
    _work(c, timer, clock, "beta", 120, 200)
    assert [e["project"] for e in _open_auto(c)] == ["beta"]


def test_twice_is_once_and_ending_without_a_break_changes_nothing(env) -> None:
    c, timer, clock, root = env
    assert c.post("/api/time/auto/break", json={"on": False}).json() == {"on": False, "today": []}
    assert not (root / "timer" / "break.json").exists()
    first = c.post("/api/time/auto/break", json={"on": True}).json()
    clock.now = T0 + 30
    again = c.post("/api/time/auto/break", json={"on": True, "note": "x"}).json()
    assert again["since"] == first["since"] and again["note"] == ""
    assert c.get("/api/time/auto/break").json()["sec"] == 30


def test_a_break_survives_a_restart_of_the_timer(env) -> None:
    c, timer, clock, _ = env
    c.post("/api/time/auto/mode", json={"project": "alpha", "mode": "auto"})
    c.post("/api/time/auto/break", json={"on": True})
    fresh = timeauto.AutoTimer(timer.store, read_idle=clock.reading, clock=clock)
    from backend import timebreak
    assert timebreak.held(fresh, "alpha")
    fresh.beat("alpha", "", "window")
    fresh.tick()
    assert fresh.spans == {}


def test_today_lists_the_breaks_with_their_notes(env) -> None:
    c, timer, clock, root = env
    c.post("/api/time/auto/break", json={"on": True})
    clock.now = T0 + 900
    c.post("/api/time/auto/break", json={"on": False, "note": "прогулка"})
    got = c.get("/api/time/auto/break").json()
    assert got["on"] is False
    assert [(b["sec"], b["note"]) for b in got["today"]] == [(900, "прогулка")]
    kept = json.loads((root / "timer" / "break.json").read_text(encoding="utf-8"))
    assert kept["on"] is None and len(kept["log"]) == 1


@pytest.mark.parametrize("body", [{}, {"on": "yes"}, {"on": 1}, {"on": True, "note": ["x"]}, {"on": True, "project": ["alpha"]}])
def test_a_wrong_body_is_refused_and_writes_nothing(env, body) -> None:
    c, _, _, root = env
    assert c.post("/api/time/auto/break", json=body).status_code == 422
    assert not (root / "timer" / "break.json").exists()
    assert c.get("/api/time/auto/break").json()["on"] is False
