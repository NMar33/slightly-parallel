"""Mutual activity endpoint tests — index, filters, detail, POST, cyrillic-safe.

Seeds a self-contained ``{data_root}/activity.csv`` +
``{data_root}/activity_details/*.md`` layout produced by
``scripts/migrate_activity.py``, then hits the SCAN-parallel endpoints:

    GET  /api/activity           (filters: project, agent_id, goal_id,
                                  activity_type, from_date, to_date,
                                  min_duration, max_duration)
    GET  /api/activity/{id}      (rich MD parsed из detail file)
    POST /api/activity           (atomic append + MD write)
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app


ACTIVITY_COLUMNS = [
    "id", "created_date", "start_time", "end_time", "duration_min",
    "project", "agent_id", "goal_id", "activity_type", "summary",
    "files_touched_n", "md_ref",
]


# Eight rows across three projects. Row for quizforge carries cyrillic
# через summary + MD body для round-trip test.
ACTIVITY_ROWS = [
    ("ac_11111111", "2608-06", "09:00", "12:00", 180, "WT",
     "bw-firebase-sub", "g_wt_e2e", "dev",
     "Wire Firebase auth end-to-end", 3,
     "activity_details/260806__wt__11111111.md"),
    ("ac_22222222", "2608-06", "13:00", "15:00", 120, "LedgerKit",
     "sx-generator", "g_sxp_cost", "research",
     "Prompt cache benchmarking", 2,
     "activity_details/260806__ledgerkit__22222222.md"),
    ("ac_33333333", "2608-05", "10:00", "18:00", 480, "PDR",
     "pdr-scaffold", "g_pdr_mvp", "dev",
     "FastAPI backend scaffold + endpoints", 6,
     "activity_details/260805__pdr__33333333.md"),
    ("ac_44444444", "2608-04", "18:00", "18:45", 45, "quizforge",
     "qf-content-sub", "g_qf_pipeline", "docs",
     "Кириллица в summary — рекогниция pipeline", 1,  # cyrillic anchor
     "activity_details/260804__quizforge__44444444.md"),
    ("ac_55555555", "2608-03", "14:00", "17:30", 210, "orbit",
     "orbit-parser", "g_orbit_parser", "test",
     "Parser fixture round-trip suite", 4,
     "activity_details/260803__orbit__55555555.md"),
    ("ac_66666666", "2608-02", "09:15", "10:45", 90, "WT",
     "bw-auth-sub", "g_wt_onboard", "dev",
     "Anonymous login handler", 2,
     "activity_details/260802__wt__66666666.md"),
    # Zero-duration edge (operator planning session, no timer) — filter test guard.
    ("ac_77777777", "2608-07", "11:00", "11:00", 0, "PDR",
     "operator", "", "admin",
     "Roadmap planning — no code", 0,
     "activity_details/260807__pdr__77777777.md"),
    # Long-session outlier (10 hours) — max_duration filter guard.
    ("ac_88888888", "2608-07", "08:00", "18:00", 600, "PDR",
     "pdr-marathon", "g_pdr_mvp", "dev",
     "Marathon integration session", 8,
     "activity_details/260807__pdr__88888888.md"),
]


def _write_seed(root: Path) -> None:
    """Materialise a data_root mirroring what migrate_activity.py emits."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "activity_details").mkdir(exist_ok=True)

    # Empty project folders — /api/project/{code} guards на unknown codes
    # by returning an empty bundle; make the codes known so cross-endpoint
    # routing tests can prove attribution.
    projects_root = root / "projects"
    projects_root.mkdir(exist_ok=True)
    for code in {row[5] for row in ACTIVITY_ROWS}:
        (projects_root / code).mkdir(exist_ok=True)

    # Mutual CSV
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    w.writerow(ACTIVITY_COLUMNS)
    for r in ACTIVITY_ROWS:
        w.writerow(["" if v is None else v for v in r])
    (root / "activity.csv").write_text(buf.getvalue(), encoding="utf-8")

    # MD details — full frontmatter + L2/L3/L4. quizforge row = cyrillic
    # across every section для round-trip test.
    for row in ACTIVITY_ROWS:
        aid = row[0]
        md_ref = row[11]
        md_path = root / md_ref
        cyr = row[5] == "quizforge"
        l2 = (
            "Матолимп pipeline остаётся стабильным."
            if cyr else f"Context detail for {aid}."
        )
        l3_a = "- `app/main.py` — entrypoint" if not cyr else \
            "- `content/parser.py` — рекогниция ядро"
        l3_b = "- `app/router.py` — v1 endpoints" if not cyr else \
            "- `content/tests.py` — фикстуры и проверки"
        l4 = (
            "> **kirill**: Ничего не сломалось. Продолжай."
            if cyr else f"> **agent**: Chat context for {aid}."
        )
        md = (
            "---\n"
            f"id: {aid}\n"
            "---\n\n"
            "## L2 — Context\n\n"
            f"{l2}\n\n"
            "## L3 — Files touched\n\n"
            f"{l3_a}\n"
            f"{l3_b}\n\n"
            "## L4 — Raw context\n\n"
            f"{l4}\n"
        )
        md_path.write_text(md, encoding="utf-8")


@pytest.fixture()
def act_data_root(tmp_path: Path) -> Path:
    root = tmp_path / "00-agents"
    _write_seed(root)
    return root


@pytest.fixture()
def act_client(act_data_root: Path) -> TestClient:
    app = create_app(data_root=act_data_root, watch=False)
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# GET /api/activity — index + filters
# ---------------------------------------------------------------------------


def test_activity_list_all(act_client: TestClient) -> None:
    r = act_client.get("/api/activity")
    assert r.status_code == 200
    assert "ETag" in r.headers
    body = r.json()
    assert body["total"] == 8
    assert len(body["activity"]) == 8
    # Ordered newest-first by (date, start_time)
    stamps = [(a["created_date"], a["start_time"]) for a in body["activity"]]
    assert stamps == sorted(stamps, reverse=True)
    # Mutual columns survived — ints stay ints, md_ref present
    top = body["activity"][0]
    assert isinstance(top["files_touched_n"], int)
    assert isinstance(top["duration_min"], int)
    assert top["md_ref"].startswith("activity_details/")


def test_activity_list_project_filter(act_client: TestClient) -> None:
    r = act_client.get("/api/activity?project=WT")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert {a["agent_id"] for a in body["activity"]} == {
        "bw-firebase-sub", "bw-auth-sub",
    }


def test_activity_list_agent_filter(act_client: TestClient) -> None:
    r = act_client.get("/api/activity?agent_id=operator")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["activity"][0]["project"] == "PDR"


def test_activity_list_goal_filter(act_client: TestClient) -> None:
    r = act_client.get("/api/activity?goal_id=g_pdr_mvp")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert {a["id"] for a in body["activity"]} == {"ac_33333333", "ac_88888888"}


def test_activity_list_type_filter(act_client: TestClient) -> None:
    r = act_client.get("/api/activity?activity_type=dev")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 4
    assert all(a["activity_type"] == "dev" for a in body["activity"])


def test_activity_list_date_range(act_client: TestClient) -> None:
    r = act_client.get("/api/activity?from_date=2608-05&to_date=2608-06")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    for a in body["activity"]:
        assert "2608-05" <= a["created_date"] <= "2608-06"


def test_activity_list_min_duration(act_client: TestClient) -> None:
    """min_duration excludes short sessions (< 120min)."""
    r = act_client.get("/api/activity?min_duration=120")
    assert r.status_code == 200
    body = r.json()
    # 8 rows total; drop ac_44444444 (45m), ac_66666666 (90m), ac_77777777 (0m)
    assert body["total"] == 5
    for a in body["activity"]:
        assert a["duration_min"] >= 120


def test_activity_list_max_duration(act_client: TestClient) -> None:
    """max_duration caps outliers (a 10h marathon)."""
    r = act_client.get("/api/activity?max_duration=300")
    assert r.status_code == 200
    body = r.json()
    # Excludes ac_33333333 (480m) and ac_88888888 (600m)
    assert body["total"] == 6
    for a in body["activity"]:
        assert a["duration_min"] <= 300


def test_activity_list_combined_filters(act_client: TestClient) -> None:
    """Project + duration filter — pdr sessions ≥ 60m."""
    r = act_client.get("/api/activity?project=PDR&min_duration=60")
    assert r.status_code == 200
    body = r.json()
    # PDR has 3 rows: 480m, 0m, 600m. min=60 drops the 0m planning session.
    assert body["total"] == 2
    for a in body["activity"]:
        assert a["project"] == "PDR"
        assert a["duration_min"] >= 60


def test_activity_list_etag_304(act_client: TestClient) -> None:
    r1 = act_client.get("/api/activity")
    etag = r1.headers["ETag"]
    r2 = act_client.get("/api/activity", headers={"If-None-Match": etag})
    assert r2.status_code == 304
    assert r2.headers["ETag"] == etag


# ---------------------------------------------------------------------------
# GET /api/activity/{id} — rich detail
# ---------------------------------------------------------------------------


def test_activity_detail_shape(act_client: TestClient) -> None:
    r = act_client.get("/api/activity/ac_11111111")
    assert r.status_code == 200
    body = r.json()
    assert body["metadata"]["id"] == "ac_11111111"
    assert body["metadata"]["project"] == "WT"
    assert body["metadata"]["files_touched_n"] == 3
    assert body["metadata"]["duration_min"] == 180
    assert body["l2"].startswith("Context detail")
    assert len(body["l3"]) == 2
    assert body["l3"][0].startswith("`app/main.py`")
    assert "Chat context" in body["l4"]


def test_activity_detail_cyrillic_roundtrip(act_client: TestClient) -> None:
    r = act_client.get("/api/activity/ac_44444444")
    assert r.status_code == 200
    body = r.json()
    # Cyrillic survives CSV, DuckDB, MD-parse, JSON.
    assert "рекогниция" in body["metadata"]["summary"]
    assert "Матолимп" in body["l2"]
    assert any("рекогниция" in bullet for bullet in body["l3"])
    assert "kirill" in body["l4"]
    assert "Ничего не сломалось" in body["l4"]


def test_activity_detail_not_found(act_client: TestClient) -> None:
    r = act_client.get("/api/activity/ac_deadbeef")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/activity — append round-trip
# ---------------------------------------------------------------------------


def test_activity_post_appends_and_visible(
    act_client: TestClient, act_data_root: Path,
) -> None:
    payload = {
        "created_date": "2608-08",
        "start_time": "10:00",
        "end_time": "14:00",
        "duration_min": 240,
        "project": "WT",
        "agent_id": "bw-new-sub",
        "goal_id": "g_wt_e2e",
        "activity_type": "dev",
        "summary": "Argon2id migration + backfill script",
        "files_touched_n": 4,
        "l2": "Проверка path записи и рекогниция полей.",
        "l3": ["`app/auth.py` — Argon2id path", "`scripts/backfill.py` — reencode"],
        "l4": "> **operator**: тест round-trip через POST.",
    }
    r = act_client.post("/api/activity", json=payload)
    assert r.status_code == 201
    body = r.json()
    aid = body["metadata"]["id"]
    assert aid.startswith("ac_") and len(aid) == 11
    assert body["l2"] == payload["l2"]
    assert body["l3"] == payload["l3"]

    # CSV grew by one row (header + 8 seed + 1 new)
    csv_lines = (act_data_root / "activity.csv").read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(csv_lines) == 1 + 8 + 1

    # MD file landed AND contains cyrillic body + bullets
    md_path = act_data_root / body["metadata"]["md_ref"]
    assert md_path.exists()
    md_body = md_path.read_text(encoding="utf-8")
    assert "Проверка" in md_body
    assert "тест" in md_body
    assert "`app/auth.py`" in md_body

    # GET /api/activity now shows 9 rows
    r2 = act_client.get("/api/activity")
    assert r2.json()["total"] == 9

    # GET /api/activity/{new_id} returns the rich content
    r3 = act_client.get(f"/api/activity/{aid}")
    assert r3.status_code == 200
    assert r3.json()["l4"] == payload["l4"]


def test_activity_post_id_is_deterministic(act_client: TestClient) -> None:
    """Same payload → same aid (idempotency-lite via content hash)."""
    payload = {
        "created_date": "2608-09",
        "start_time": "09:00",
        "end_time": "10:00",
        "duration_min": 60,
        "project": "WT",
        "agent_id": "bw-dup",
        "summary": "Determinism check",
    }
    r1 = act_client.post("/api/activity", json=payload)
    r2 = act_client.post("/api/activity", json=payload)
    assert r1.status_code == 201
    assert r2.status_code == 200 and r2.json()["existing"] is True   # a repeat writes nothing new
    assert r1.json()["metadata"]["id"] == r2.json()["metadata"]["id"]


# ---------------------------------------------------------------------------
# Cross-endpoint: /api/project/{code}, /api/snapshot, /api/timeline all read
# from activity_mutual (consolidation guard).
# ---------------------------------------------------------------------------


def test_project_bundle_reads_mutual_activity(act_client: TestClient) -> None:
    r = act_client.get("/api/project/WT")
    assert r.status_code == 200
    body = r.json()
    # WT has 2 activity rows in the mutual csv; per-project files don't exist.
    assert len(body["activity"]) == 2
    assert {a["id"] for a in body["activity"]} == {"ac_11111111", "ac_66666666"}


def test_snapshot_reads_mutual_activity(act_client: TestClient) -> None:
    r = act_client.get("/api/snapshot")
    assert r.status_code == 200
    body = r.json()
    # Recent activity list draws directly from the mutual view.
    ids = {a["id"] for a in body["recent_activity"]}
    assert "ac_11111111" in ids
    assert "ac_44444444" in ids


def test_timeline_reads_mutual_activity(act_data_root: Path) -> None:
    """Timeline joins mutual-view activity onto agent lanes.

    Seed meta.json for a WT agent BEFORE the app boots — the store loads
    agents once at startup (watch=False in tests). Then verify the mutual
    view feeds `activities` для that lane.
    """
    import json

    meta = {
        "agent_id": "bw-firebase-sub",
        "agent_name": "bw-firebase",
        "project": "WT",
        "created_date": "2608-06",
        "last_active": "2608-06T12:00:00",
    }
    chat_dir = act_data_root / "projects" / "WT" / "chats" / "bw-firebase-sub"
    chat_dir.mkdir(parents=True, exist_ok=True)
    (chat_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    app = create_app(data_root=act_data_root, watch=False)
    with TestClient(app) as c:
        r = c.get("/api/timeline?project=WT")
    assert r.status_code == 200
    body = r.json()
    all_ids = {
        a["id"] for lane in body["lanes"] for a in lane["activities"]
    }
    # ac_11111111 (bw-firebase-sub) surfaces once the lane exists.
    assert "ac_11111111" in all_ids
