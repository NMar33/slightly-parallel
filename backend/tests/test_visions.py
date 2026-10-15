"""VISION endpoint tests — list, detail, POST round-trip, cyrillic-safe.

Mirrors test_standups.py 1:1 (SCAN-parallel schema).
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app


COLUMNS = [
    "id", "created_date", "created_time", "project", "agent_id",
    "l1", "category", "related_goal_id", "impact", "effort", "md_ref",
]


VISION_ROWS = [
    ("vs_v1111111", "2608-06", "10:15", "alpha-labs", "agent-genesis-2608-01",
     "AI-driven request replay on top of OpenAPI schema.",
     "product", "g_a1", "high", "medium",
     "vision_details/2608-06-1015__alpha-labs__v1111111.md"),
    ("vs_v2222222", "2608-06", "16:40", "alpha-labs", "agent-genesis-2608-01",
     "Multi-tenant billing surface via rate-limit counters.",
     "business", "g_a3", "high", "high",
     "vision_details/2608-06-1640__alpha-labs__v2222222.md"),
    ("vs_v3333333", "2608-05", "14:00", "beta-corp", "agent-explorer-2608-03",
     "Real-time analytics dashboard над Kafka pipeline.",
     "product", "g_b3", "high", "high",
     "vision_details/2608-05-1400__beta-corp__v3333333.md"),
    ("vs_v4444444", "2608-04", "18:27", "quizforge", "qf-content-sub",
     "матолимп — единая curriculum-vetter service.",  # cyrillic
     "product", "", "medium", "low",
     "vision_details/2608-04-1827__quizforge__v4444444.md"),
    ("vs_v5555555", "2608-05", "22:30", "_all", "",
     "Единый operational playbook across both projects.",
     "personal", "", "low", "low",
     "vision_details/2608-05-2230__all__v5555555.md"),
    ("vs_v6666666", "2608-03", "11:20", "alpha-labs", "agent-genesis-2608-01",
     "First-class CLI wrapper around the SDK.",
     "ux", "g_a4", "medium", "low",
     "vision_details/2608-03-1120__alpha-labs__v6666666.md"),
]


def _write_seed(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "vision_details").mkdir(exist_ok=True)
    (root / "projects").mkdir(exist_ok=True)

    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    w.writerow(COLUMNS)
    for r in VISION_ROWS:
        w.writerow(r)
    (root / "visions.csv").write_text(buf.getvalue(), encoding="utf-8")

    for row in VISION_ROWS:
        sid = row[0]
        md_ref = row[10]
        md_path = root / md_ref
        cyr = row[3] == "quizforge"
        l2 = ("Матолимп pipeline нуждается в едином курикулум-валидаторе."
              if cyr else f"Elaboration paragraph for {sid}.")
        l3_a = "Публиковать в docs" if cyr else "Prototype step 1"
        l3_b = "Согласовать с командой" if cyr else "Ship step 2"
        l4 = ("Обсуждали на ретро — kirill согласен."
              if cyr
              else f"Raw context and origin of {sid}.")
        md = (
            "---\n"
            f"id: {sid}\n"
            f'l1: "{row[5]}"\n'
            "---\n\n"
            "## L2 — Elaboration\n\n"
            f"{l2}\n\n"
            "## L3 — Implications / Next steps\n\n"
            f"- {l3_a}\n"
            f"- {l3_b}\n\n"
            "## L4 — Raw context\n\n"
            f"{l4}\n"
        )
        md_path.write_text(md, encoding="utf-8")


@pytest.fixture()
def visions_data_root(tmp_path: Path) -> Path:
    root = tmp_path / "00-agents"
    _write_seed(root)
    return root


@pytest.fixture()
def visions_client(visions_data_root: Path) -> TestClient:
    app = create_app(data_root=visions_data_root, watch=False)
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# GET /api/visions
# ---------------------------------------------------------------------------


def test_visions_list_all_six(visions_client: TestClient) -> None:
    r = visions_client.get("/api/visions")
    assert r.status_code == 200
    assert "ETag" in r.headers
    body = r.json()
    assert body["total"] == 6
    assert len(body["visions"]) == 6
    dates = [(v["created_date"], v["created_time"]) for v in body["visions"]]
    assert dates == sorted(dates, reverse=True)


def test_visions_list_project_filter(visions_client: TestClient) -> None:
    r = visions_client.get("/api/visions?project=alpha-labs")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    for v in body["visions"]:
        assert v["project"] == "alpha-labs"


def test_visions_list_category_filter(visions_client: TestClient) -> None:
    r = visions_client.get("/api/visions?category=business")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["visions"][0]["id"] == "vs_v2222222"


def test_visions_list_impact_filter(visions_client: TestClient) -> None:
    r = visions_client.get("/api/visions?impact=high")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert {v["impact"] for v in body["visions"]} == {"high"}


def test_visions_list_search(visions_client: TestClient) -> None:
    r = visions_client.get("/api/visions?search=kafka")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["visions"][0]["id"] == "vs_v3333333"


def test_visions_list_date_range(visions_client: TestClient) -> None:
    r = visions_client.get("/api/visions?from_date=2608-05&to_date=2608-06")
    assert r.status_code == 200
    body = r.json()
    # 2 rows на 2608-06, 2 rows on 2608-05
    assert body["total"] == 4


def test_visions_list_etag_304(visions_client: TestClient) -> None:
    r1 = visions_client.get("/api/visions")
    etag = r1.headers["ETag"]
    r2 = visions_client.get("/api/visions", headers={"If-None-Match": etag})
    assert r2.status_code == 304


# ---------------------------------------------------------------------------
# GET /api/visions/{id}
# ---------------------------------------------------------------------------


def test_visions_detail_shape(visions_client: TestClient) -> None:
    r = visions_client.get("/api/visions/vs_v1111111")
    assert r.status_code == 200
    body = r.json()
    assert body["metadata"]["id"] == "vs_v1111111"
    assert body["metadata"]["project"] == "alpha-labs"
    assert body["metadata"]["category"] == "product"
    assert body["l2"].startswith("Elaboration paragraph")
    assert body["l3"] == ["Prototype step 1", "Ship step 2"]
    assert "Raw context" in body["l4"]


def test_visions_detail_cyrillic_roundtrip(visions_client: TestClient) -> None:
    r = visions_client.get("/api/visions/vs_v4444444")
    assert r.status_code == 200
    body = r.json()
    assert "матолимп" in body["metadata"]["l1"].lower()
    assert "Матолимп" in body["l2"]
    assert body["l3"] == ["Публиковать в docs", "Согласовать с командой"]
    assert "kirill" in body["l4"]


def test_visions_detail_not_found(visions_client: TestClient) -> None:
    r = visions_client.get("/api/visions/vs_deadbeef")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/visions
# ---------------------------------------------------------------------------


def test_visions_post_appends_and_visible(
    visions_client: TestClient, visions_data_root: Path,
) -> None:
    payload = {
        "created_date": "2608-07",
        "created_time": "09:00",
        "project": "alpha-labs",
        "agent_id": "vs-new-sub",
        "l1": "Fresh vision — POST round-trip smoke test.",
        "category": "architecture",
        "related_goal_id": "g_a1",
        "impact": "high",
        "effort": "medium",
        "l2": "Elaboration of the fresh vision.",
        "l3": ["Prototype это", "Ship следующим спринтом"],
        "l4": "Raw context тестовый — captured from standup.",
    }
    r = visions_client.post("/api/visions", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert "metadata" in body
    sid = body["metadata"]["id"]
    assert sid.startswith("vs_") and len(sid) == 11
    assert body["l2"] == payload["l2"]
    assert body["l3"] == payload["l3"]
    assert body["l4"] == payload["l4"]

    # CSV grew by one
    csv_lines = (visions_data_root / "visions.csv").read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(csv_lines) == 1 + 6 + 1  # header + 6 seed + 1 new

    # MD file exists и carries cyrillic
    md_path = visions_data_root / body["metadata"]["md_ref"]
    assert md_path.exists()
    md_body = md_path.read_text(encoding="utf-8")
    assert "тестовый" in md_body

    # Round-trip via GET list + detail
    r2 = visions_client.get("/api/visions")
    assert r2.json()["total"] == 7
    r3 = visions_client.get(f"/api/visions/{sid}")
    assert r3.status_code == 200
    assert r3.json()["l4"] == payload["l4"]


def test_visions_post_id_is_deterministic(visions_client: TestClient) -> None:
    payload = {
        "created_date": "2608-08",
        "created_time": "12:00",
        "project": "beta-corp",
        "agent_id": "vs-dup",
        "l1": "Determinism check.",
        "category": "ux",
        "impact": "low",
        "effort": "low",
    }
    r1 = visions_client.post("/api/visions", json=payload)
    r2 = visions_client.post("/api/visions", json=payload)
    assert r1.status_code == 201
    assert r2.status_code == 200      # a repeat writes nothing new
    assert r1.json()["metadata"]["id"] == r2.json()["metadata"]["id"]
