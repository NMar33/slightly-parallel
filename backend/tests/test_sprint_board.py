"""Sprints as blocks of work: the board strip with derived numbers."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    r = tmp_path / "data"
    (r / "projects" / "alpha").mkdir(parents=True)
    return r


@pytest.fixture()
def client(root: Path):
    app = create_app(data_root=root, watch=False)
    with TestClient(app) as c:
        yield c


def _sprint(client: TestClient, name: str, bet: int = 7, budget: float = 20) -> str:
    today = time.strftime("%y%m-%d")
    r = client.post("/api/sprints", json={
        "created_date": today, "started_date": today, "name": name,
        "projects": "alpha", "status": "active", "bet_days": bet,
        "time_budget_h": budget, "agent_id": "operator",
    })
    assert r.status_code == 201, r.text
    return r.json()["metadata"]["id"]


def _task(client: TestClient, title: str, sprint_id: str = "", status: str = "todo", t: str = "10:00") -> str:
    r = client.post("/api/tasks", json={
        "created_date": "2608-20", "created_time": t, "project": "alpha",
        "agent_id": "operator", "title": title, "status": status, "sprint_id": sprint_id,
    })
    return r.json()["metadata"]["id"]


def test_board_derives_everything(client: TestClient, root: Path) -> None:
    sid = _sprint(client, "Authorization", bet=7, budget=20)
    _task(client, "login", sid, status="done")
    _task(client, "tokens", sid, status="doing", t="10:01")
    tid = _task(client, "logout", sid, status="todo", t="10:02")
    _task(client, "unrelated", t="10:03")

    # Human hours: a finished timer entry on the sprint at 50% share.
    client.post("/api/time-entries", json={
        "created_date": "2608-20", "created_time": "11:00", "project": "alpha",
        "agent_id": "operator", "duration_min": 120, "share_pct": 50,
        "sprint_id": sid, "note": "auth work",
    })
    # Agent hours: a captured session that mentioned a sprint task.
    d = root / "projects" / "alpha" / "chats" / "cc-agent001"
    d.mkdir(parents=True)
    # Anchored to midday, not "30 minutes ago": a chat that straddles
    # midnight is split into two sessions by date, and the 20-minute
    # session this asserts on collapsed to 2 whenever the suite ran just
    # after 00:00.
    t0 = datetime.now().replace(hour=11, minute=30, second=0, microsecond=0)
    body = f"# Chat log — cc-agent001\n\n---\n\n## Turn 1 · {t0.strftime('%Y-%m-%dT%H:%M:%S')}\n**User**: do {tid}\n**Agent**: on it\n\n## Turn 2 · {(t0 + timedelta(minutes=20)).strftime('%Y-%m-%dT%H:%M:%S')}\n**User**: status?\n**Agent**: {tid} done\n"
    (d / "chat.md").write_text(body, encoding="utf-8")
    (d / "meta.json").write_text(json.dumps({"agent_id": "cc-agent001"}), encoding="utf-8")
    client.app.state.store.rebuild()

    b = client.get("/api/sprints/board?project=alpha").json()
    assert b["no_sprint"] == 1
    sp = b["sprints"][0]
    assert (sp["name"], sp["tasks_total"], sp["tasks_done"]) == ("Authorization", 3, 1)
    assert sp["days_left"] == 7          # started today, 7-day bet
    assert sp["human_min"] == 60         # 120 min × 50%
    assert sp["agent_min"] == 20         # the session's duration
    assert float(sp["budget_h"]) == 20.0

    # Ending it removes it from the strip.
    client.post(f"/api/sprints/{sid}/update", json={"status": "ended", "ended_date": time.strftime("%y%m-%d"), "l2": "retro: shipped 1/3"})
    assert client.get("/api/sprints/board?project=alpha").json()["sprints"] == []


def test_delete_moves_the_sprint_to_trash_and_frees_its_tasks(client: TestClient) -> None:
    sid = _sprint(client, "Mistake")
    tid = _task(client, "captive", sid)
    out = client.post(f"/api/sprints/{sid}/delete").json()
    assert out["deleted"] == sid and out["tasks_freed"] == 1
    assert Path(out["trash"], "sprints.csv").exists()
    assert client.get("/api/sprints/board?project=alpha").json()["sprints"] == []
    row = next(t for t in client.get("/api/tasks?project=alpha").json()["tasks"] if t["id"] == tid)
    assert not row["sprint_id"]
    ev = client.get(f"/api/tasks/{tid}/events").json()["events"]
    assert any(e["field"] == "sprint_id" and not e["new_value"] for e in ev)
    assert client.post(f"/api/sprints/{sid}/delete").status_code == 404


def test_series_reconstructs_scope_done_and_clocks(client: TestClient) -> None:
    """The per-day series: scope from join events (creation counts), done
    from status events, human minutes × share bucketed by day."""
    import time as _time
    today = _time.strftime("%y%m-%d")
    sid = client.post("/api/sprints", json={
        "created_date": today, "started_date": today, "name": "Series", "projects": "alpha",
        "status": "active", "bet_days": 7, "agent_id": "operator",
    }).json()["metadata"]["id"]
    # One task created straight into the sprint, one joining via update.
    a = client.post("/api/tasks", json={
        "created_date": today, "created_time": "09:00", "project": "alpha",
        "agent_id": "operator", "title": "born aboard", "status": "todo", "sprint_id": sid,
    }).json()["metadata"]["id"]
    b = client.post("/api/tasks", json={
        "created_date": today, "created_time": "09:01", "project": "alpha",
        "agent_id": "operator", "title": "joins later", "status": "todo",
    }).json()["metadata"]["id"]
    client.post(f"/api/tasks/{b}/update", json={"sprint_id": sid, "actor": "operator"})
    client.post(f"/api/tasks/{a}/update", json={"status": "done", "actor": "operator"})
    client.post("/api/time-entries", json={
        "created_date": today, "created_time": "10:00", "project": "alpha",
        "agent_id": "operator", "duration_min": 90, "share_pct": 50, "sprint_id": sid,
        "started_at": f"20{today[:2]}-{today[2:4]}-{today[5:7]}T10:00:00", "note": "work",
    })
    s = client.get(f"/api/sprints/{sid}/series").json()
    assert len(s["days"]) == 1
    d = s["days"][0]
    assert d["scope"] == 2 and d["done"] == 1
    assert d["human_min"] == 45          # 90 × 50%
    assert d["events"] >= 2              # the join + the done


def test_timeline_and_dossier(client: TestClient) -> None:
    import time as _time
    today = _time.strftime("%y%m-%d")
    sid = client.post("/api/sprints", json={
        "created_date": today, "started_date": today, "name": "Dossier", "projects": "alpha",
        "status": "active", "bet_days": 5, "time_budget_h": 4, "agent_id": "operator",
        "l2": "the bet", "l3": ["goal one"],
    }).json()["metadata"]["id"]
    tid = _task(client, "in the window", sid)
    client.post(f"/api/tasks/{tid}/update", json={"status": "done", "actor": "operator"})

    tl = client.get("/api/sprints/timeline?project=alpha").json()["sprints"]
    row = next(r for r in tl if r["id"] == sid)
    assert row["tasks"][0]["done"] is not None and row["bet_days"] == 5

    d = client.get(f"/api/sprints/{sid}/dossier").json()
    assert d["sprint"]["ran_days"] == 0 and d["sprint"]["over_days"] == 0
    assert len(d["tasks"]) == 1 and d["events_n"] >= 1
    assert d["git"] == {"available": False}          # no registered repo
    assert d["l3"] == ["goal one"]
    assert client.get("/api/sprints/sp_missing/dossier").status_code == 404
