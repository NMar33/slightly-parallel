"""Derived sessions (time axis from turn logs) + generic lifecycle updates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app
from backend.sessions import group_sessions, parse_turns

# The snapshot's hours cover the last 30 days, so the turns are stamped from
# today: a session of two turns ten minutes apart, then a third turn after
# a gap. Hard-coded August dates made this test fail from mid-September on.
from datetime import datetime, timedelta

_T0 = (datetime.now() - timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
_STAMP = lambda minutes: (_T0 + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S")

CHAT = f"""# Chat log — agent-x-2608-14
*Started {_STAMP(0)}.*

---

## Turn 1 · {_STAMP(0)}
**User**: Kick off the migration
**Agent**: Plan the schema change

## Turn 2 · {_STAMP(10)}
**User**: Looks good
**Agent**: Apply and run the tests

## Turn 3 · {_STAMP(240)}
**User**: New topic after lunch
**Agent**: Start the frontend work
"""


@pytest.fixture()
def data_root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    agent_dir = root / "projects" / "alpha" / "chats" / "agent-x-2608-14"
    agent_dir.mkdir(parents=True)
    (agent_dir / "chat.md").write_text(CHAT, encoding="utf-8")
    (agent_dir / "meta.json").write_text(
        json.dumps(
            {
                "agent_id": "agent-x-2608-14",
                "agent_name": "agent-x",
                "project": "alpha",
                "message_count": 3,
                "l1_headline": "",
            }
        ),
        encoding="utf-8",
    )
    (root / "goals.csv").write_text(
        "id,created_date,project,agent_id,goal_text,parent_goal_id,related,"
        "time_est,confidence_pct,success_comment,status,children_n,"
        "retro_outcome,md_ref,sprint_id\n"
        "g_x,2608-14,alpha,agent-x-2608-14,Ship it,,,,80,,active,0,unknown,,\n",
        encoding="utf-8",
    )
    (root / "sprints.csv").write_text(
        "id,created_date,started_date,ended_date,name,theme,projects,"
        "time_budget_h,status,confidence_pct,goals_declared_n,"
        "goals_shipped_n,md_ref\n"
        "sp_x,2608-14,2608-14,,Sprint X,Focus,alpha,10,active,80,1,0,\n",
        encoding="utf-8",
    )
    return root


def test_turn_parsing_and_gap_grouping() -> None:
    turns = parse_turns_from_text()
    assert [t.number for t in turns] == [1, 2, 3]
    sessions = group_sessions("alpha", "agent-x", turns, 30, total_lines=20)
    # 9:00+9:10 in one block; 13:00 (230-min gap) starts a new one.
    assert len(sessions) == 2
    assert sessions[0].turns_n == 2
    assert sessions[0].duration_min == 10
    assert sessions[1].turns_n == 1
    assert sessions[1].duration_min == 1  # single turn floors at 1


def parse_turns_from_text():
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as fh:
        fh.write(CHAT)
        path = Path(fh.name)
    try:
        return parse_turns(path)
    finally:
        path.unlink()


def test_sessions_api_and_snapshot_hours(data_root: Path) -> None:
    app = create_app(data_root=data_root, watch=False)
    with TestClient(app) as client:
        body = client.get("/api/sessions").json()
        assert body["total"] == 2
        newest = body["sessions"][0]
        assert newest["turns_n"] == 1

        detail = client.get(
            f"/api/sessions/{body['sessions'][1]['id']}"
        ).json()
        assert detail["metadata"]["turns_n"] == 2
        assert len(detail["l3"]) == 2
        assert "Turn 1" in detail["l4"]
        assert "Turn 3" not in detail["l4"]

        # Snapshot time math now comes from derived sessions (11 real min).
        snap = client.get("/api/snapshot").json()
        assert snap["projects"][0]["est_hours_30d"] == round(11 / 60.0, 1)
        assert any(
            r["activity_type"] == "session" for r in snap["recent_activity"]
        )


def test_goal_lifecycle_update(data_root: Path) -> None:
    app = create_app(data_root=data_root, watch=False)
    with TestClient(app) as client:
        r = client.post(
            "/api/goals/g_x/update",
            json={"status": "done", "retro_outcome": "hit",
                  "goal_text": "IGNORED — not mutable"},
        )
        assert r.status_code == 200
        meta = r.json()["metadata"]
        assert meta["status"] == "done"
        assert meta["retro_outcome"] == "hit"
        assert meta["goal_text"] == "Ship it"  # immutable field untouched


def test_sprint_end_update(data_root: Path) -> None:
    app = create_app(data_root=data_root, watch=False)
    with TestClient(app) as client:
        r = client.post(
            "/api/sprints/sp_x/update",
            json={"status": "ended", "ended_date": "2608-15",
                  "goals_shipped_n": 1, "l2": "Retro: shipped the goal."},
        )
        assert r.status_code == 200
        meta = r.json()["metadata"]
        assert meta["status"] == "ended"
        assert meta["ended_date"] == "2608-15"
        assert meta["goals_shipped_n"] == 1
        assert r.json()["l2"].startswith("Retro:")


def test_update_unknown_id_404(data_root: Path) -> None:
    app = create_app(data_root=data_root, watch=False)
    with TestClient(app) as client:
        assert (
            client.post("/api/goals/g_nope/update", json={"status": "done"})
            .status_code
            == 404
        )


def test_append_only_entities_have_no_update_route(data_root: Path) -> None:
    app = create_app(data_root=data_root, watch=False)
    with TestClient(app) as client:
        # scans/standups/decisions are append-only records by design.
        # (404 without a frontend build; 405 when the GET-only SPA fallback
        # route matches the path.)
        assert (
            client.post("/api/standups/st_x/update", json={"l1": "x"})
            .status_code
            in (404, 405)
        )


def test_list_with_l2_attaches_summaries(data_root: Path) -> None:
    """?with_l2=1 inlines each row's summary — one request instead of N."""
    app = create_app(data_root=data_root, watch=False)
    with TestClient(app) as client:
        created = client.post(
            "/api/tasks",
            json={
                "created_date": "2608-14", "created_time": "10:00",
                "project": "alpha", "agent_id": "operator",
                "title": "Wire the exporter", "status": "todo",
                "description": "Needs the CSV writer done first.",
            },
        )
        assert created.status_code == 201

        plain = client.get("/api/tasks?project=alpha").json()["tasks"]
        assert "description" not in plain[0]

        withl2 = client.get("/api/tasks?project=alpha&with_l2=1").json()["tasks"]
        assert withl2[0]["description"] == "Needs the CSV writer done first."


def test_task_impact_and_effort_round_trip(data_root: Path) -> None:
    """Impact × effort are stored on create, mutable on update, and logged."""
    app = create_app(data_root=data_root, watch=False)
    with TestClient(app) as client:
        created = client.post(
            "/api/tasks",
            json={
                "created_date": "2608-19", "created_time": "10:00",
                "project": "alpha", "agent_id": "operator",
                "title": "Quick win", "status": "todo",
                "priority": "med", "impact": "high", "effort": "S",
            },
        )
        assert created.status_code == 201
        tid = created.json()["metadata"]["id"]
        row = client.get("/api/tasks?project=alpha").json()["tasks"][0]
        assert (row["impact"], row["effort"]) == ("high", "S")

        upd = client.post(f"/api/tasks/{tid}/update", json={"effort": "L", "actor": "operator"})
        assert upd.status_code == 200
        row = client.get("/api/tasks?project=alpha").json()["tasks"][0]
        assert (row["impact"], row["effort"]) == ("high", "L")
        events = client.get(f"/api/tasks/{tid}/events").json()
        assert any(e.get("field") == "effort" for e in events.get("events", events if isinstance(events, list) else []))


def test_a_chat_says_everything_it_made_and_what_marked_it(client: TestClient) -> None:
    """`produced` listed eight kinds of the fourteen an agent can write, so a
    chat that posted a standup, a skill or an artifact showed
    nothing. `marks` is the other direction: the saved prompt a chat was sent
    from, and the messages kept out of it."""
    from backend import produced

    labels = {label for _, label in produced.VIEWS}
    assert {"standups", "skills", "artifacts", "scans", "decisions"} <= labels

    rows = client.get("/api/sessions?limit=200").json()["sessions"]
    assert rows and all("produced" in r and "marks" in r for r in rows)

    store = client.app.state.store
    assert produced.marks(store) is produced.marks(store)      # read once per version
