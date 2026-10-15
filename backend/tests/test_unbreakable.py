"""The unbreakable contract: no file and no row takes down boot, a page,
or navigation — and whatever does degrade says so.

Born from a real incident: one decision row missing its headline killed the
project page with a 500, and the audit that followed proved one corrupted
CSV stopped the server booting at all. Every test here pins one of those
failure classes shut.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app

AGGREGATES = [
    "/api/snapshot", "/api/project/alpha", "/api/search?q=goal",
    "/api/timeline", "/api/scans", "/api/goals",
    "/api/decisions",
]


def _fresh(tmp_path: Path) -> tuple[Path, TestClient]:
    root = tmp_path / "root"
    (root / "projects" / "alpha").mkdir(parents=True)
    app = create_app(data_root=root, watch=False)
    return root, TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Boot: corruption degrades, never kills
# ---------------------------------------------------------------------------


def test_server_boots_with_a_binary_corrupted_csv(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "projects" / "alpha").mkdir(parents=True)
    (root / "goals.csv").write_bytes(b"\x00\xff\xfegarbage header\ng_1,x\n")
    (root / "tasks.csv").write_text(
        "id,created_date,created_time,project,agent_id,title,status,md_ref\n"
        "tk_1,2608-27,10:00,alpha,a1,Fine task,todo,\n", encoding="utf-8",
    )
    app = create_app(data_root=root, watch=False)
    client = TestClient(app, raise_server_exceptions=False)
    # The healthy table still serves; the broken one reads as empty.
    assert client.get("/api/tasks?project=alpha").json()["total"] == 1
    assert client.get("/api/goals").json()["total"] == 0
    # And the degradation is announced, not hidden.
    health = client.get("/api/health").json()
    assert health["degraded"] is True
    assert any("goals.csv" in e["file"] for e in health["load_errors"])


def test_rebuild_survives_corruption_arriving_at_runtime(tmp_path: Path) -> None:
    root, client = _fresh(tmp_path)
    client.post("/api/tasks", json={
        "created_date": "2608-27", "created_time": "10:00", "project": "alpha",
        "agent_id": "operator", "title": "before the damage",
    })
    (root / "goals.csv").write_bytes(b"\xff\xfe broken")
    client.app.state.store.rebuild()
    # Writes still work (they call rebuild), reads still work.
    r = client.post("/api/tasks", json={
        "created_date": "2608-27", "created_time": "10:01", "project": "alpha",
        "agent_id": "operator", "title": "after the damage",
    })
    assert r.status_code == 201
    assert client.get("/api/tasks?project=alpha").json()["total"] == 2


# ---------------------------------------------------------------------------
# Readers: one malformed row never takes an aggregate down
# ---------------------------------------------------------------------------


def test_blank_goal_text_in_user_overlay_kills_nothing(tmp_path: Path) -> None:
    """The disaster scenario: a user's own project goals.csv with one
    headless row used to 500 the Overview, the sidebar's data source and
    search all at once."""
    root, client = _fresh(tmp_path)
    (root / "projects" / "alpha" / "goals.csv").write_text(
        "id,goal_text,parent_goal_id,related,time_est,confidence_pct,"
        "success_comment,created_date,agent_id,status,retro_date,retro_notes\n"
        "g_ok,Real goal,,,,80,,2608-01,a1,in_progress,,\n"
        "g_blank,,,,,,,2608-02,a1,open,,\n", encoding="utf-8",
    )
    client.app.state.store.rebuild()
    for url in AGGREGATES:
        assert client.get(url).status_code == 200, url
    # The readable row is served alongside the headless one — nothing 500s.
    goals = client.get("/api/goals?project=alpha").json()["goals"]
    assert "g_ok" in [g["id"] for g in goals]


def test_headless_mutual_decision_kills_nothing(tmp_path: Path) -> None:
    root, client = _fresh(tmp_path)
    (root / "decisions.csv").write_text(
        "id,created_date,created_time,project,agent_id,decision_text,rationale,"
        "source,related_goal_id,files_affected_n,alternatives_n,md_ref\n"
        "dc_bad,2608-27,10:00,alpha,a1,,why,,,,,\n", encoding="utf-8",
    )
    client.app.state.store.rebuild()
    for url in AGGREGATES:
        assert client.get(url).status_code == 200, url


def test_scan_row_without_id_kills_nothing(tmp_path: Path) -> None:
    root, client = _fresh(tmp_path)
    (root / "scans.csv").write_text(
        "id,created_date,created_time,project,agent_id,l1,files_n,lines_add,"
        "lines_del,decisions_n,scope,md_ref\n"
        ",2608-27,10:00,alpha,a1,headline,0,0,0,0,,\n", encoding="utf-8",
    )
    client.app.state.store.rebuild()
    assert client.get("/api/scans").status_code == 200


# ---------------------------------------------------------------------------
# Failures explain themselves
# ---------------------------------------------------------------------------


def test_unhandled_errors_return_a_traceable_id(tmp_path: Path) -> None:
    root, client = _fresh(tmp_path)

    def _boom() -> list:
        raise RuntimeError("deliberate")

    # Break a real dependency the timeline endpoint uses — the handler must
    # turn the resulting crash into a traceable JSON error.
    client.app.state.store.agents = _boom  # type: ignore[method-assign]
    r = client.get("/api/timeline")
    assert r.status_code == 500
    body = r.json()
    assert body["error_id"]
    assert body["error_id"] in body["detail"]


# ---------------------------------------------------------------------------
# Honest writes: vocabulary typos are refused, not swallowed
# ---------------------------------------------------------------------------


def _make_sprint(client: TestClient) -> str:
    r = client.post("/api/sprints", json={
        "created_date": "2608-27", "project": "alpha", "agent_id": "operator",
        "name": "Block", "projects": "alpha", "status": "active",
        "started_date": "2608-27",
    })
    assert r.status_code in (200, 201)
    return r.json()["metadata"]["id"]


def test_sprint_status_typo_is_refused_with_the_vocabulary(tmp_path: Path) -> None:
    root, client = _fresh(tmp_path)
    sid = _make_sprint(client)
    r = client.post(f"/api/sprints/{sid}/update", json={"status": "actve"})
    assert r.status_code == 422
    assert "active" in r.json()["detail"] and "ended" in r.json()["detail"]
    # The legitimate value still lands.
    assert client.post(f"/api/sprints/{sid}/update", json={"status": "ended"}).status_code == 200


def test_task_status_typo_is_refused_on_create_and_update(tmp_path: Path) -> None:
    root, client = _fresh(tmp_path)
    bad = client.post("/api/tasks", json={
        "created_date": "2608-27", "created_time": "10:00", "project": "alpha",
        "agent_id": "operator", "title": "t", "status": "doig",
    })
    assert bad.status_code == 422
    ok = client.post("/api/tasks", json={
        "created_date": "2608-27", "created_time": "10:00", "project": "alpha",
        "agent_id": "operator", "title": "t", "status": "doing",
    })
    tid = ok.json()["metadata"]["id"]
    assert client.post(f"/api/tasks/{tid}/update", json={"status": "don"}).status_code == 422
    assert client.post(f"/api/tasks/{tid}/update", json={"status": "done"}).status_code == 200


def test_doc_item_position_garbage_is_422_not_500(tmp_path: Path) -> None:
    root, client = _fresh(tmp_path)
    did = client.post("/api/docs", json={
        "project": "alpha", "title": "D", "kind": "article",
    }).json()["doc"]["id"]
    r = client.post(f"/api/docs/{did}/items", json={"text": "block", "position": "first"})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# The doctor sees what the gates and readers see
# ---------------------------------------------------------------------------


def test_doctor_reports_clean_on_a_healthy_root(tmp_path: Path) -> None:
    root, client = _fresh(tmp_path)
    client.post("/api/tasks", json={
        "created_date": "2608-27", "created_time": "10:00", "project": "alpha",
        "agent_id": "operator", "title": "healthy",
    })
    report = client.get("/api/doctor").json()
    assert report["ok"] is True
    assert report["checked"]["files"] >= 1


def test_doctor_names_every_class_of_damage(tmp_path: Path) -> None:
    root, client = _fresh(tmp_path)
    # duplicate id + headless decision + dangling md_ref + unknown status
    (root / "decisions.csv").write_text(
        "id,created_date,created_time,project,agent_id,decision_text,rationale,"
        "source,related_goal_id,files_affected_n,alternatives_n,md_ref\n"
        "dc_1,2608-27,10:00,alpha,a1,,why,,,,,gone/away.md\n"
        "dc_1,2608-27,10:00,alpha,a1,Second copy,,,,,,\n", encoding="utf-8",
    )
    (root / "sprints.csv").write_text(
        "id,created_date,started_date,ended_date,name,theme,projects,"
        "time_budget_h,bet_days,status,confidence_pct,goals_declared_n,"
        "goals_shipped_n,md_ref\n"
        "sp_1,2608-27,2608-27,,Block,,alpha,,7,actve,,,,\n", encoding="utf-8",
    )
    client.app.state.store.rebuild()
    report = client.get("/api/doctor").json()
    assert report["ok"] is False
    kinds = {i["kind"] for i in report["issues"]}
    assert "duplicate-id" in kinds
    assert "unreadable-row" in kinds
    assert "md-ref-missing" in kinds
    assert "unknown-value" in kinds
    # And the aggregates still serve while all of that is true.
    for url in AGGREGATES:
        assert client.get(url).status_code == 200, url


# ---------------------------------------------------------------------------
# P2: what a reader requires, a contract-shaped create guarantees
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("lens,url,payload", [
    ("decision", "/api/decisions", {"l1": "decided the thing", "l2": "why"}),
    ("goal", "/api/goals", {"l1": "ship the thing", "l2": "done when shipped"}),
    ("activity", "/api/activity", {"summary": "worked", "duration_min": 30}),
])
def test_contract_create_satisfies_the_read_model(
    tmp_path: Path, lens: str, url: str, payload: dict
) -> None:
    from backend.routers.lenses import READ_MODELS

    root, client = _fresh(tmp_path)
    body = {"created_date": "2608-27", "created_time": "09:00",
            "project": "alpha", "agent_id": "op", **payload}
    made = client.post(url, json=body)
    assert made.status_code in (200, 201), made.text
    row = made.json()["metadata"]
    model = READ_MODELS[lens]
    required = {
        name for name, f in model.model_fields.items() if f.is_required()
    }
    missing = [f for f in required if not str(row.get(f) or "").strip()]
    assert not missing, f"{lens}: create left required {missing} empty"
