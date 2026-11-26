"""The capture hook and the membership ledger (tk_d1d25a4d step 3, note
nt_258a7ed7 §5 and §6).

One stat of the ledgers per turn against ``membership_seen``; the fold only
on a task command or a change, the stat taken after that read; a missing
ledger is normal; an unreadable one is one failure line and home only; the
operator summary on the turn after a change; «tk_… → project · lane» on the
turn after a task was made; a task made outside the home says so in its
history.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import memberships, mcp
from backend import membership_fold as mf
from backend.server import create_app

pytestmark = pytest.mark.strict_membership

A = "cc-hook0001"
_HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"


def _load():
    spec = importlib.util.spec_from_file_location("sp_capture_mhook", _HOOKS / "capture.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sp_capture_mhook"] = mod
    spec.loader.exec_module(mod)
    return mod


capture = _load()


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    r = tmp_path / "data"
    for code in ("alpha", "beta"):
        (r / "projects" / code).mkdir(parents=True)
    return r


def _cap(root: Path):
    cap = capture.TurnCapture(root, "alpha", A)
    cap.open_turn("hello")              # the chat exists; its first look at the ledgers
    cap.complete_turn("hi")
    return cap


def _turn(cap, text: str) -> str:
    out = capture.format_signals(cap.open_turn(text))
    cap.complete_turn("ok")
    return out


def _failures(root: Path) -> list[str]:
    f = root / ".capture" / "errors.jsonl"
    return [line for line in f.read_text(encoding="utf-8").splitlines()
            if "membership" in line] if f.exists() else []


class _Count:
    def __init__(self, fn):
        self.fn, self.n = fn, 0

    def __call__(self, *a, **k):
        self.n += 1
        return self.fn(*a, **k)


def test_a_missing_ledger_writes_no_failure_line(root: Path) -> None:
    cap = _cap(root)
    out = _turn(cap, "#task check the login")
    assert "→ alpha (" in out
    assert _failures(root) == []


def test_an_unchanged_ledger_costs_one_stat_and_no_fold(root: Path, monkeypatch) -> None:
    cap = _cap(root)
    stats, folds = _Count(capture.ledger_stats), _Count(capture.fold_agent)
    monkeypatch.setattr(capture, "ledger_stats", stats)
    monkeypatch.setattr(capture, "fold_agent", folds)
    _turn(cap, "just talk")
    assert (stats.n, folds.n) == (1, 0)


def test_a_task_command_costs_one_fold(root: Path, monkeypatch) -> None:
    cap = _cap(root)
    folds = _Count(capture.fold_agent)
    monkeypatch.setattr(capture, "fold_agent", folds)
    _turn(cap, "#now {ui} fix it and #task later")
    assert folds.n == 1


def test_the_summary_shows_on_the_turn_after_a_change(root: Path) -> None:
    cap = _cap(root)
    assert "projects changed" not in _turn(cap, "talk")
    memberships.write(root, A, "join", "beta")
    out = _turn(cap, "go on")
    assert "[slightly-parallel] this chat's projects changed —" in out
    assert f"agent {A}\nhome: alpha · member of: alpha, beta · runs from folder: alpha\ntask level: 2" in out
    assert "projects changed" not in _turn(cap, "and on")      # once


def test_a_join_landing_after_the_read_is_told_next_turn(root: Path, monkeypatch) -> None:
    # The critic of 54c217ee: with the stat taken after the read, a join
    # landing between them was saved as seen and never told. The stat is
    # taken before the read, so the next turn sees the change and tells it.
    cap = _cap(root)
    real = capture.fold_agent

    def join_after_reading(*a, **k):
        got = real(*a, **k)
        memberships.write(root, A, "join", "beta")      # lands after the read, before the turn ends
        return got

    monkeypatch.setattr(capture, "fold_agent", join_after_reading)
    _turn(cap, "#task first")
    monkeypatch.setattr(capture, "fold_agent", real)
    out = _turn(cap, "next")
    assert "[slightly-parallel] this chat's projects changed —" in out
    assert "member of: alpha, beta" in out


def test_the_first_ledger_is_a_change(root: Path) -> None:
    # No ledger yet is seen as «none»; the first join makes one and is told.
    cap = _cap(root)
    memberships.write(root, A, "join", "beta")
    assert "projects changed" in _turn(cap, "go on")


def test_an_unreadable_ledger_falls_back_with_one_failure_line(root: Path) -> None:
    cap = _cap(root)
    (root / mf.LEDGER).mkdir()                 # there, and not a file anyone can read
    out = _turn(cap, "#task {beta} check it")
    assert "is not a member of beta" in out    # home only
    assert len(_failures(root)) == 1


def test_the_next_turn_says_where_the_tasks_went(root: Path) -> None:
    cap = _cap(root)
    _turn(cap, "work")
    with open(root / "tasks.csv", "w", encoding="utf-8") as fh:
        fh.write("id,project,agent_id,title,status,lane,assignee\n"
                 f"tk_made0001,beta,{A},made,agent,docs,docs\n"
                 "tk_other001,beta,cc-other,theirs,agent,,\n")
    out = _turn(cap, "next")
    assert "[slightly-parallel] where the tasks of your last turn went: tk_made0001 → beta · lane docs." in out
    assert "tk_other001" not in out
    assert "where the tasks" not in _turn(cap, "and next")     # once


def test_a_task_made_outside_the_home_says_so_in_its_history(data_root: Path) -> None:
    from tests.conftest import make_chat
    make_chat(data_root, "ALPHA", A, [("2026-11-20T10:00:00", "start", "ok")])
    with TestClient(create_app(data_root=data_root, watch=False)) as c:
        assert c.post(f"/api/agents/{A}/membership", json={"op": "join", "project": "BETA"}).status_code == 200
        ids = []
        for project in ("ALPHA", "BETA"):
            r = c.post("/api/tasks", json={"agent_id": A, "project": project, "created_date": "2611-20",
                                           "created_time": "10:06", "title": f"made in {project}", "tags": "ag_bug"},
                       headers={mcp.VIA_HEADER: mcp.VIA_VALUE})
            assert r.status_code == 201, r.text
            ids.append(r.json()["metadata"]["id"])
        rows = c.app.state.store.query(
            "SELECT task_id, field, new_value FROM task_events_mutual WHERE field = 'created_in'")
        assert [(r["task_id"], r["new_value"]) for r in rows] == [(ids[1], "BETA (home ALPHA)")]


def test_a_resumed_chat_reads_the_same_origins_as_the_server(root: Path) -> None:
    # The critic of c1: the hook folded with its own folder only.
    cap = _cap(root)
    second = root / "projects" / "beta" / "chats" / A
    second.mkdir(parents=True)
    (second / "meta.json").write_text(json.dumps({"agent_id": A, "project": "beta"}), encoding="utf-8")
    members, home, _aliases, _codes = capture.agent_projects(root, "alpha", A)
    assert members == ["alpha", "beta"] and home == "alpha"
    assert "→ beta (" in _turn(cap, "#task {beta} check it")
