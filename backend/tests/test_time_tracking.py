"""Manual time tracking — the clock, pause accounting, and attribution."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.routers import time_tracking as tt
from backend.server import create_app


@pytest.fixture()
def client(tmp_path: Path):
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    app = create_app(data_root=root, watch=False)
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Pure elapsed-time arithmetic (no HTTP) — the part most easily got wrong
# ---------------------------------------------------------------------------


def _row(**over) -> dict:
    base = {
        "started_at": "2026-08-16T10:00:00",
        "ended_at": "",
        "paused_at": "",
        "paused_total_sec": 0,
        "duration_min": 0,
        "share_pct": 100,
    }
    base.update(over)
    return base


NOW = datetime(2026, 8, 16, 11, 0, 0)  # one hour after the start above


def test_running_elapsed_is_wall_time() -> None:
    assert tt.elapsed_seconds(_row(), NOW) == 3600


def test_paused_time_is_excluded() -> None:
    # 15 minutes were banked as paused earlier in the hour.
    assert tt.elapsed_seconds(_row(paused_total_sec=900), NOW) == 2700


def test_clock_freezes_while_paused() -> None:
    # Paused at 10:30 and never resumed — elapsed stays 30 min no matter how
    # much later "now" is.
    row = _row(paused_at="2026-08-16T10:30:00")
    assert tt.elapsed_seconds(row, NOW) == 1800
    assert tt.elapsed_seconds(row, NOW + timedelta(hours=5)) == 1800


def test_finished_entry_ignores_now() -> None:
    row = _row(ended_at="2026-08-16T10:20:00")
    assert tt.elapsed_seconds(row, NOW + timedelta(days=2)) == 1200


def test_attribution_applies_the_share() -> None:
    d = tt.decorate(_row(share_pct=50), NOW)
    assert d["elapsed_sec"] == 3600
    assert d["attributed_sec"] == 1800  # half of you on this project
    assert d["status"] == "running"


def test_runaway_flag_after_eight_hours() -> None:
    late = datetime(2026, 8, 16, 19, 30, 0)
    assert tt.decorate(_row(), NOW)["runaway"] is False
    assert tt.decorate(_row(), late)["runaway"] is True


# ---------------------------------------------------------------------------
# The endpoints
# ---------------------------------------------------------------------------


def test_start_pause_resume_stop_roundtrip(client: TestClient) -> None:
    started = client.post(
        "/api/time/start",
        json={"project": "alpha", "note": "wiring the tracker", "share_pct": 60},
    )
    assert started.status_code == 201
    entry = started.json()
    assert entry["status"] == "running"
    assert entry["share_pct"] == 60
    eid = entry["id"]

    paused = client.post(f"/api/time/{eid}/pause").json()
    assert paused["status"] == "paused"
    # Pausing twice is a no-op, not an error.
    assert client.post(f"/api/time/{eid}/pause").json()["status"] == "paused"

    resumed = client.post(f"/api/time/{eid}/resume").json()
    assert resumed["status"] == "running"
    assert resumed["paused_total_sec"] >= 0

    stopped = client.post(f"/api/time/{eid}/stop", json={"note": "done"}).json()
    assert stopped["status"] == "done"
    assert stopped["note"] == "done"
    assert stopped["ended_at"]

    # A stopped entry cannot be paused, resumed, or stopped again.
    assert client.post(f"/api/time/{eid}/pause").status_code == 409
    assert client.post(f"/api/time/{eid}/resume").status_code == 409
    assert client.post(f"/api/time/{eid}/stop").status_code == 409


def test_one_running_timer_per_block(client: TestClient) -> None:
    first = client.post("/api/time/start", json={"project": "alpha"})
    assert first.status_code == 201
    # The same block (here: no sprint) cannot be punched twice…
    clash = client.post("/api/time/start", json={"project": "alpha"})
    assert clash.status_code == 409
    # …but another block of the same project runs in parallel — that's the
    # whole point of share_pct — and so does another project.
    assert client.post("/api/time/start", json={"project": "alpha", "sprint_id": "sp_x"}).status_code == 201
    assert client.post("/api/time/start", json={"project": "alpha", "sprint_id": "sp_x"}).status_code == 409
    assert client.post("/api/time/start", json={"project": "beta"}).status_code == 201


def test_running_endpoint_lists_open_timers_only(client: TestClient) -> None:
    a = client.post("/api/time/start", json={"project": "alpha"}).json()
    client.post("/api/time/start", json={"project": "beta"})
    assert client.get("/api/time/running").json()["total"] == 2

    client.post(f"/api/time/{a['id']}/stop")
    running = client.get("/api/time/running").json()
    assert running["total"] == 1
    assert running["running"][0]["project"] == "beta"


def test_summary_counts_attributed_minutes(client: TestClient) -> None:
    e = client.post(
        "/api/time/start",
        json={"project": "alpha", "goal_id": "g_1", "share_pct": 50},
    ).json()
    client.post(f"/api/time/{e['id']}/stop")

    # Hand-written entry for time worked away from the timer.
    client.post(
        "/api/time-entries",
        json={
            "created_date": "2608-16", "created_time": "09:00",
            "project": "alpha", "agent_id": "operator",
            "started_at": "2026-08-16T09:00:00",
            "ended_at": "2026-08-16T11:00:00",
            "duration_min": 120, "share_pct": 50, "goal_id": "g_1",
            "note": "pairing offline",
        },
    )
    summary = client.get("/api/time/summary?project=alpha").json()
    # 120 minutes at 50% = 60 attributed to the goal (the timer entry
    # rounds to zero seconds in a test this fast).
    assert summary["per_goal_min"]["g_1"] == 60
    assert summary["total_min"] == 60


def test_manual_edit_through_the_generic_update(client: TestClient) -> None:
    e = client.post("/api/time/start", json={"project": "alpha"}).json()
    client.post(f"/api/time/{e['id']}/stop")
    fixed = client.post(
        f"/api/time-entries/{e['id']}/update",
        json={"duration_min": 45, "note": "forgot to stop — trimmed"},
    )
    assert fixed.status_code == 200
    assert fixed.json()["metadata"]["duration_min"] == 45


def test_start_validates_input(client: TestClient) -> None:
    assert client.post("/api/time/start", json={}).status_code == 422
    assert client.post(
        "/api/time/start", json={"project": "alpha", "share_pct": 250}
    ).status_code == 422
    assert client.post("/api/time/nope/pause").status_code == 404


def test_delete_removes_the_row(client: TestClient) -> None:
    e = client.post("/api/time/start", json={"project": "alpha"}).json()
    client.post(f"/api/time/{e['id']}/stop")
    assert client.get("/api/time-entries?project=alpha").json()["total"] == 1

    assert client.post(f"/api/time/{e['id']}/delete").status_code == 200
    assert client.get("/api/time-entries?project=alpha").json()["total"] == 0
    # Deleting twice is a clear 404, not a silent success.
    assert client.post(f"/api/time/{e['id']}/delete").status_code == 404
