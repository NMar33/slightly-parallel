"""Mutual goals endpoint tests — index, tree filters, detail, POST.

Seeds a self-contained ``{data_root}/goals.csv`` +
``{data_root}/goal_details/*.md`` layout (the goal entity in
backend/entities.py; the product no longer writes goals, but the
routes still serve an old root's), then hits the endpoints:

    GET  /api/goals               (filters: project, agent_id, status,
                                   from_date, to_date, parent_goal_id,
                                   root_only)
    GET  /api/goals/{id}          (rich MD + children list)
    POST /api/goals               (append + parent's children_n recomputed)
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app


GOAL_COLUMNS = [
    "id", "created_date", "project", "agent_id",
    "goal_text", "parent_goal_id", "related", "time_est",
    "confidence_pct", "success_comment", "status",
    "children_n", "retro_outcome", "md_ref",
]


# Seven rows across three projects (alpha, beta, quizforge). ``quizforge``
# carries cyrillic through goal_text и success_comment для the round-trip
# test. Trees:
#   g_root_a (alpha) → g_child_a1, g_child_a2
#   g_root_b (beta)  → g_child_b1
#   g_root_m (quizforge) — leaf, cyrillic
GOALS_ROWS = [
    ("g_root_a1", "2608-01", "alpha-labs", "agent-genesis-2608-01",
     "Ship v1 API with OpenAPI docs", "", "", "3 days",
     80, "swagger generation needs work", "done",
     2, "hit", "goal_details/260801__alpha-labs__root_a1.md"),
    ("g_child_a1", "2608-02", "alpha-labs", "agent-genesis-2608-01",
     "Auth flow with OAuth2 + refresh tokens", "g_root_a1", "", "2 days",
     75, "refresh token rotation tricky", "done",
     0, "hit", "goal_details/260802__alpha-labs__child_a1.md"),
    ("g_child_a2", "2608-03", "alpha-labs", "agent-genesis-2608-01",
     "Rate limiting middleware", "g_root_a1", "", "1 day",
     90, "", "done",
     0, "hit", "goal_details/260803__alpha-labs__child_a2.md"),
    ("g_root_b1", "2608-02", "beta-corp", "agent-explorer-2608-03",
     "Migrate legacy MySQL to Postgres", "", "", "7 days",
     65, "long-running queries risky", "active",
     1, "pending", "goal_details/260802__beta-corp__root_b1.md"),
    ("g_child_b1", "2608-04", "beta-corp", "agent-explorer-2608-03",
     "Zero-downtime cutover", "g_root_b1", "", "2 days",
     55, "requires read replica", "active",
     0, "pending", "goal_details/260804__beta-corp__child_b1.md"),
    ("g_root_b2", "2608-03", "beta-corp", "agent-explorer-2608-03",
     "Analytics event pipeline (Kafka)", "", "", "10 days",
     70, "", "blocked",
     0, "pending", "goal_details/260803__beta-corp__root_b2.md"),
    # Cyrillic anchor row.
    ("g_root_m", "2608-05", "quizforge", "qf-content-sub",
     "рекогниция контента для 5 класса", "", "", "4 days",
     60, "проверка round-trip", "active",
     0, "pending", "goal_details/260805__quizforge__root_m.md"),
]


def _write_seed(root: Path) -> None:
    """Materialise a data_root mirroring what migrate_goals.py emits."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "goal_details").mkdir(exist_ok=True)

    # Empty project folders so ViewStore.projects populates for cross-check.
    projects_root = root / "projects"
    projects_root.mkdir(exist_ok=True)
    for code in {row[2] for row in GOALS_ROWS}:
        (projects_root / code).mkdir(exist_ok=True)

    # Mutual CSV
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    w.writerow(GOAL_COLUMNS)
    for r in GOALS_ROWS:
        w.writerow(r)
    (root / "goals.csv").write_text(buf.getvalue(), encoding="utf-8")

    # MD details. Row with quizforge code carries cyrillic all the way through.
    for row in GOALS_ROWS:
        gid = row[0]
        md_ref = row[13]
        md_path = root / md_ref
        cyr = row[2] == "quizforge"
        l2 = (
            "Матолимп pipeline — контент для средней школы, стабильно."
            if cyr else f"Rationale detail for {gid}."
        )
        l3_a = "- child-a · Ship green · 85%" if not cyr \
            else "- child-cyr · Продолжай спокойно · 90%"
        l3_b = "- child-b · No blockers · 75%" if not cyr \
            else "- child-cyr-2 · Второй подцель · 70%"
        l4 = (
            "- **actual_result**: Ничего не сломалось\n"
            "- **diff_from_pred**: соответствует прогнозу\n"
            "- **what_worked**: понятная спецификация"
            if cyr else
            "- **actual_result**: shipped as planned\n"
            "- **diff_from_pred**: on-target"
        )
        md = (
            "---\n"
            f"id: {gid}\n"
            "---\n\n"
            "## L2 — Rationale + plan\n\n"
            f"{l2}\n\n"
            "## L3 — Subtasks / child goals\n\n"
            f"{l3_a}\n"
            f"{l3_b}\n\n"
            "## L4 — Retrospective (if done)\n\n"
            f"{l4}\n"
        )
        md_path.write_text(md, encoding="utf-8")


@pytest.fixture()
def goals_data_root(tmp_path: Path) -> Path:
    root = tmp_path / "00-agents"
    _write_seed(root)
    return root


@pytest.fixture()
def goals_client(goals_data_root: Path) -> TestClient:
    app = create_app(data_root=goals_data_root, watch=False)
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# GET /api/goals — index + filters
# ---------------------------------------------------------------------------


def test_goals_list_all(goals_client: TestClient) -> None:
    r = goals_client.get("/api/goals")
    assert r.status_code == 200
    assert "ETag" in r.headers
    body = r.json()
    assert body["total"] == 7
    assert len(body["goals"]) == 7
    # Ordered newest first by date
    dates = [g["created_date"] for g in body["goals"]]
    assert dates == sorted(dates, reverse=True)
    # Mutual columns survived
    top = body["goals"][0]
    assert isinstance(top["children_n"], int)
    assert top["md_ref"].startswith("goal_details/")


def test_goals_list_project_filter(goals_client: TestClient) -> None:
    r = goals_client.get("/api/goals?project=alpha-labs")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert {g["project"] for g in body["goals"]} == {"alpha-labs"}


def test_goals_list_agent_filter(goals_client: TestClient) -> None:
    r = goals_client.get("/api/goals?agent_id=qf-content-sub")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["goals"][0]["project"] == "quizforge"


def test_goals_list_status_filter(goals_client: TestClient) -> None:
    r = goals_client.get("/api/goals?status=done")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert all(g["status"] == "done" for g in body["goals"])


def test_goals_list_date_range(goals_client: TestClient) -> None:
    r = goals_client.get("/api/goals?from_date=2608-02&to_date=2608-03")
    assert r.status_code == 200
    body = r.json()
    for g in body["goals"]:
        assert "2608-02" <= g["created_date"] <= "2608-03"
    assert body["total"] == 4


def test_goals_list_parent_id_returns_children_only(
    goals_client: TestClient,
) -> None:
    r = goals_client.get("/api/goals?parent_goal_id=g_root_a1")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert {g["id"] for g in body["goals"]} == {"g_child_a1", "g_child_a2"}
    assert all(g["parent_goal_id"] == "g_root_a1" for g in body["goals"])


def test_goals_list_root_only_excludes_children(
    goals_client: TestClient,
) -> None:
    r = goals_client.get("/api/goals?root_only=true")
    assert r.status_code == 200
    body = r.json()
    # g_root_a1, g_root_b1, g_root_b2, g_root_m — four roots
    assert body["total"] == 4
    for g in body["goals"]:
        assert g["parent_goal_id"] is None


def test_goals_list_etag_304(goals_client: TestClient) -> None:
    r1 = goals_client.get("/api/goals")
    etag = r1.headers["ETag"]
    r2 = goals_client.get("/api/goals", headers={"If-None-Match": etag})
    assert r2.status_code == 304
    assert r2.headers["ETag"] == etag


# ---------------------------------------------------------------------------
# GET /api/goals/{id} — rich detail с children
# ---------------------------------------------------------------------------


def test_goals_detail_shape_with_children(goals_client: TestClient) -> None:
    r = goals_client.get("/api/goals/g_root_a1")
    assert r.status_code == 200
    body = r.json()
    assert body["metadata"]["id"] == "g_root_a1"
    assert body["metadata"]["project"] == "alpha-labs"
    assert body["metadata"]["children_n"] == 2
    assert body["l2"].startswith("Rationale detail")
    assert len(body["l3"]) == 2
    assert "shipped as planned" in body["l4"]
    # Children list surfaces both child rows, oldest-first.
    assert len(body["children"]) == 2
    child_ids = [c["id"] for c in body["children"]]
    assert child_ids == ["g_child_a1", "g_child_a2"]


def test_goals_detail_leaf_no_children(goals_client: TestClient) -> None:
    r = goals_client.get("/api/goals/g_child_a1")
    assert r.status_code == 200
    body = r.json()
    assert body["metadata"]["children_n"] == 0
    assert body["children"] == []


def test_goals_detail_cyrillic_roundtrip(goals_client: TestClient) -> None:
    r = goals_client.get("/api/goals/g_root_m")
    assert r.status_code == 200
    body = r.json()
    # Cyrillic survives CSV → DuckDB → MD parse → JSON.
    assert "рекогниция" in body["metadata"]["goal_text"]
    assert "проверка" in body["metadata"]["success_comment"]
    assert "Матолимп" in body["l2"]
    assert any("Продолжай" in bullet for bullet in body["l3"])
    assert "Ничего не сломалось" in body["l4"]


def test_goals_detail_not_found(goals_client: TestClient) -> None:
    r = goals_client.get("/api/goals/g_deadbeef")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/goals — append + parent's children_n recomputed
# ---------------------------------------------------------------------------


def test_goals_post_appends_and_visible(
    goals_client: TestClient, goals_data_root: Path,
) -> None:
    payload = {
        "created_date": "2608-06",
        "project": "alpha-labs",
        "agent_id": "agent-followup",
        "goal_text": "SDK client generator (TS + Python)",
        "parent_goal_id": None,
        "time_est": "5 days",
        "confidence_pct": 60,
        "success_comment": "depends on stable OpenAPI",
        "status": "active",
        "l2": "Проверка path записи и структуры детали.",
        "l3": ["- subtask 1", "- subtask 2"],
        "l4": "_(no retro yet)_",
    }
    r = goals_client.post("/api/goals", json=payload)
    assert r.status_code == 201
    body = r.json()
    gid = body["metadata"]["id"]
    assert gid.startswith("g_") and len(gid) == 10
    assert body["l2"] == payload["l2"]

    # CSV grew by one row (header + 7 seed + 1 new)
    csv_lines = (goals_data_root / "goals.csv").read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(csv_lines) == 1 + 7 + 1

    # MD file landed AND contains cyrillic body
    md_path = goals_data_root / body["metadata"]["md_ref"]
    assert md_path.exists()
    md_body = md_path.read_text(encoding="utf-8")
    assert "Проверка" in md_body
    assert "subtask 1" in md_body

    # GET /api/goals now shows 8 rows
    r2 = goals_client.get("/api/goals")
    assert r2.json()["total"] == 8


def test_goals_post_updates_parent_children_n(
    goals_client: TestClient, goals_data_root: Path,
) -> None:
    """New child rolls up к parent.children_n on the next GET."""
    # Before: g_root_b1 has 1 child (g_child_b1).
    r0 = goals_client.get("/api/goals/g_root_b1")
    assert r0.json()["metadata"]["children_n"] == 1

    payload = {
        "created_date": "2608-06",
        "project": "beta-corp",
        "agent_id": "agent-explorer-2608-03",
        "goal_text": "Backfill validation script",
        "parent_goal_id": "g_root_b1",
        "time_est": "1 day",
        "confidence_pct": 80,
        "status": "active",
    }
    r = goals_client.post("/api/goals", json=payload)
    assert r.status_code == 201
    new_id = r.json()["metadata"]["id"]

    # After: parent shows children_n=2, list-by-parent returns both
    r1 = goals_client.get("/api/goals/g_root_b1")
    assert r1.json()["metadata"]["children_n"] == 2
    child_ids = [c["id"] for c in r1.json()["children"]]
    assert set(child_ids) == {"g_child_b1", new_id}

    r2 = goals_client.get("/api/goals?parent_goal_id=g_root_b1")
    assert r2.json()["total"] == 2


def test_goals_post_id_is_deterministic(goals_client: TestClient) -> None:
    """Same payload → same gid (idempotency-lite via content hash)."""
    payload = {
        "created_date": "2608-08",
        "project": "alpha-labs",
        "agent_id": "agent-dup",
        "goal_text": "Determinism check",
    }
    r1 = goals_client.post("/api/goals", json=payload)
    r2 = goals_client.post("/api/goals", json=payload)
    assert r1.status_code == 201
    assert r2.status_code == 200      # a repeat writes nothing new
    assert r1.json()["metadata"]["id"] == r2.json()["metadata"]["id"]
