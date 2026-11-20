"""The tab's six dots (tk_d2e11125): each chat's rhythm in /api/terminal/tabs —
messages, commits, tasks closed and tokens in each of the last six clock hours."""

from __future__ import annotations

import csv
import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import gitwork, rhythm, termlib
from backend.server import create_app


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _iso(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%S")


def _git(repo: Path, *args: str, at: datetime | None = None) -> None:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    if at is not None:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = at.strftime("%Y-%m-%dT%H:%M:%S")
    subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=repo, env=env, check=True, capture_output=True)


def _commit(repo: Path, n: int, msg: str, at: datetime) -> None:
    _write(repo / f"f{n}.txt", str(n))
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", msg, at=at)


def test_periods_are_six_clock_hours() -> None:
    now = datetime(2026, 11, 18, 16, 42, 10)
    starts = rhythm.periods(now)
    assert [s.hour for s in starts] == [11, 12, 13, 14, 15, 16]
    assert rhythm.slot(starts, datetime(2026, 11, 18, 11, 0)) == 0
    assert rhythm.slot(starts, datetime(2026, 11, 18, 10, 59, 59)) is None
    assert rhythm.slot(starts, datetime(2026, 11, 18, 13, 59, 59)) == 2
    assert rhythm.slot(starts, now) == 5
    assert rhythm.slot(starts, datetime(2026, 11, 18, 17, 0)) is None
    # Across midnight the hours run on into the next day.
    assert [s.hour for s in rhythm.periods(datetime(2026, 11, 19, 2, 5))] == [21, 22, 23, 0, 1, 2]


@pytest.fixture()
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "data"
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    gitwork.forget()
    rhythm.forget()
    folder = root / "projects" / "alpha" / "chats" / "cc-one"
    _write(folder / "meta.json", json.dumps({
        "agent_id": "cc-one", "agent_name": "one", "project": "alpha", "created_date": "2611-18",
        "last_active": "2026-11-18T12:00:00", "message_count": 3, "tool": "claude-code",
        "cwd": str(repo), "session_ref": "ref-one", "terminal": "t1",
    }))
    _write(folder / "chat.md", "# Chat log — cc-one\n\n---\n")
    _write(termlib.registry_path(root), json.dumps({"sessions": [
        {"id": "t1", "kind": "shell", "label": "claude", "project": "alpha", "backend": "plain", "created": "2026-11-18T10:00:00"},
    ]}))
    app = create_app(data_root=root, watch=False)
    with TestClient(app) as c:
        yield c, root, repo, folder
    gitwork.forget()
    rhythm.forget()


def _periods(c: TestClient) -> list[dict]:
    r = c.get("/api/terminal/tabs")
    assert r.status_code == 200, r.text
    rh = r.json()["tabs"]["t1"]["chat"]["rhythm"]
    assert rh["period_min"] == 60 and len(rh["periods"]) == 6
    return rh["periods"]


def test_rhythm_counts_each_hour(world, monkeypatch: pytest.MonkeyPatch) -> None:
    c, root, repo, folder = world
    # A task of the chat, closed now: its close is stamped by the real clock, so the test's
    # moment follows it (the six hours end in the hour of the close).
    r = c.post("/api/tasks", json={"created_date": "2611-18", "created_time": "10:00", "project": "alpha",
                                   "agent_id": "operator", "title": "A", "status": "doing"})
    tid = r.json()["metadata"]["id"]
    other = c.post("/api/tasks", json={"created_date": "2611-18", "created_time": "10:00", "project": "alpha",
                                       "agent_id": "operator", "title": "B", "status": "doing"}).json()["metadata"]["id"]
    # The chat names task A in a turn (task B is another chat's); written before the closes, which refresh the views.
    _write(folder / "chat.md", f"# Chat log — cc-one\n*Started 2026-11-18T09:00:00. Verbatim captured turns.*\n\n---\n\n"
                               f"## Turn 1 · 2026-11-18T09:00:00\n**User**: do {tid}\n**Agent**: on it\n")
    assert c.post(f"/api/tasks/{tid}/update", json={"status": "done"}).status_code == 200
    assert c.post(f"/api/tasks/{other}/update", json={"status": "done"}).status_code == 200
    with open(root / "task_events.csv", encoding="utf-8") as fh:
        closed = max(row["timestamp"] for row in csv.DictReader(fh) if row["task_id"] == tid)
    now = datetime.fromisoformat(closed) + timedelta(seconds=1)
    monkeypatch.setenv("SP_NOW", _iso(now))
    starts = rhythm.periods(now)
    h = lambda i, m=5: starts[i] + timedelta(minutes=m)  # noqa: E731

    # Messages: turn 1 asked and answered in hour 0; turn 2 asked in hour 2, answered in hour 3;
    # a second stamp of turn 2 (a helper's report) is not a message; turn 3 timed only by work.jsonl.
    _write(folder / "turns.jsonl", "\n".join(json.dumps(x) for x in [
        {"turn": 1, "start": _iso(h(0)), "end": _iso(h(0, 20)), "source": "hook"},
        {"turn": 2, "start": _iso(h(2, 50)), "end": _iso(h(3, 2)), "source": "hook"},
        {"turn": 2, "start": _iso(h(2, 50)), "end": _iso(h(3, 9)), "source": "hook"},
        {"turn": 0, "start": _iso(starts[0] - timedelta(hours=2)), "end": _iso(starts[0] - timedelta(hours=1)), "source": "hook"},
    ]) + "\n")
    # Commits: mine by Agent:, mine by Task:, another agent's naming my task, an unrelated one.
    _commit(repo, 1, "mine\n\nAgent: cc-one", h(1))
    _commit(repo, 2, f"for the task\n\nTask: {tid}", h(4))
    _commit(repo, 3, f"theirs\n\nTask: {tid}\nAgent: cc-two", h(4, 10))
    _commit(repo, 4, "unrelated", h(4, 20))
    # A turn timed only by the git stamp, which lists the unrelated commit as this chat's.
    sha4 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
    _write(folder / "work.jsonl", json.dumps({"turn": 3, "at": _iso(h(5, 0)), "head": sha4, "commits": [sha4]}) + "\n")
    # Tokens: new + output of the main agent, on the turn's last message; a helper's are not the chat's.
    _write(folder / "usage.jsonl", "\n".join(json.dumps(x) for x in [
        {"turn": 1, "at": _iso(h(0, 19)), "id": "m1", "tool": "claude-code", "model": "claude-opus-4-1", "new": 1000, "output": 200, "cache": 50000},
        {"turn": 2, "at": _iso(h(3, 1)), "id": "m2", "tool": "claude-code", "model": "claude-opus-4-1", "new": 3000, "output": 500},
        {"turn": 2, "at": _iso(h(3, 2)), "id": "m3", "tool": "claude-code", "model": "claude-opus-4-1", "new": 9000, "output": 9000, "helper": "a1"},
    ]) + "\n")

    p = _periods(c)
    assert [x["start"] for x in p] == [_iso(s) for s in starts]
    assert p[5]["end"] == _iso(starts[5] + timedelta(hours=1))
    assert [x["msgs"] for x in p] == [2, 0, 1, 1, 0, 1]
    assert [x["commits"] for x in p] == [0, 1, 0, 0, 2, 0]
    assert [x["tasks"] for x in p] == [0, 0, 0, 0, 0, 1]
    assert [x["tokens"] for x in p] == [1200, 0, 0, 3500, 0, 0]

    # More work in the current hour is seen at the next read.
    with open(folder / "turns.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"turn": 4, "start": _iso(h(5, 0)), "end": _iso(h(5, 0)), "source": "hook"}) + "\n")
    assert _periods(c)[5]["msgs"] == 3


def test_a_quiet_chat_has_six_empty_hours(world) -> None:
    c, *_ = world
    p = _periods(c)
    assert all((x["msgs"], x["commits"], x["tasks"], x["tokens"]) == (0, 0, 0, 0) for x in p)


def test_the_read_writes_nothing(world) -> None:
    c, root, *_ = world
    before = {p: p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()}
    _periods(c)
    after = {p: p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()}
    assert before == after
