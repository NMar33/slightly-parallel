"""PROBLEM endpoint tests — list, detail, POST round-trip, cyrillic-safe."""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app


COLUMNS = [
    "id", "created_date", "created_time", "project", "agent_id",
    "l1", "severity", "status", "related_goal_id", "resolved_date", "md_ref",
]


PROBLEM_ROWS = [
    ("pb_p1111111", "2608-06", "11:05", "alpha-labs", "agent-genesis-2608-01",
     "Rate-limit counters wiped на Redis restart.",
     "major", "investigating", "g_a3", "",
     "problem_details/2608-06-1105__alpha-labs__p1111111.md"),
    ("pb_p2222222", "2608-06", "15:47", "alpha-labs", "agent-genesis-2608-01",
     "OpenAPI schema drift between v1 API и v0 SDK.",
     "minor", "open", "g_a1", "",
     "problem_details/2608-06-1547__alpha-labs__p2222222.md"),
    ("pb_p3333333", "2608-05", "10:30", "alpha-labs", "agent-genesis-2608-01",
     "TS SDK types leak internal enums.",
     "nit", "resolved", "g_a4", "2608-06",
     "problem_details/2608-05-1030__alpha-labs__p3333333.md"),
    ("pb_p4444444", "2608-04", "09:12", "beta-corp", "agent-explorer-2608-03",
     "pgloader off-by-hour on TIMESTAMPTZ.",
     "critical", "resolved", "g_b1", "2608-05",
     "problem_details/2608-04-0912__beta-corp__p4444444.md"),
    ("pb_p5555555", "2608-05", "17:22", "quizforge", "qf-content-sub",
     "матолимп: pipeline упал на нестандартном PDF.",  # cyrillic
     "major", "open", "", "",
     "problem_details/2608-05-1722__quizforge__p5555555.md"),
    ("pb_p6666666", "2608-03", "20:00", "_all", "",
     "Read-replica creds blocked ops handoff.",
     "minor", "resolved", "g_b1", "2608-05",
     "problem_details/2608-03-2000__all__p6666666.md"),
]


def _write_seed(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "problem_details").mkdir(exist_ok=True)
    (root / "projects").mkdir(exist_ok=True)

    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    w.writerow(COLUMNS)
    for r in PROBLEM_ROWS:
        w.writerow(r)
    (root / "problems.csv").write_text(buf.getvalue(), encoding="utf-8")

    for row in PROBLEM_ROWS:
        sid = row[0]
        md_ref = row[10]
        md_path = root / md_ref
        cyr = row[3] == "quizforge"
        l2 = ("Матолимп парсер сломался на PDF с нестандартными шрифтами."
              if cyr else f"Problem context paragraph for {sid}.")
        l3_a = "Проверить fontconfig" if cyr else "Attempt 1 — diagnose"
        l3_b = "Обновить парсер" if cyr else "Attempt 2 — workaround"
        l4 = ("Резолюция: обновили pdfminer до 20240706 — kirill проверил."
              if cyr
              else f"Resolution or raw discussion for {sid}.")
        md = (
            "---\n"
            f"id: {sid}\n"
            f'l1: "{row[5]}"\n'
            "---\n\n"
            "## L2 — Problem context\n\n"
            f"{l2}\n\n"
            "## L3 — Attempts / workarounds\n\n"
            f"- {l3_a}\n"
            f"- {l3_b}\n\n"
            "## L4 — Resolution / raw discussion\n\n"
            f"{l4}\n"
        )
        md_path.write_text(md, encoding="utf-8")


@pytest.fixture()
def problems_data_root(tmp_path: Path) -> Path:
    root = tmp_path / "00-agents"
    _write_seed(root)
    return root


@pytest.fixture()
def problems_client(problems_data_root: Path) -> TestClient:
    app = create_app(data_root=problems_data_root, watch=False)
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# GET /api/problems
# ---------------------------------------------------------------------------


def test_problems_list_all_six(problems_client: TestClient) -> None:
    r = problems_client.get("/api/problems")
    assert r.status_code == 200
    assert "ETag" in r.headers
    body = r.json()
    assert body["total"] == 6
    assert len(body["problems"]) == 6
    dates = [(p["created_date"], p["created_time"]) for p in body["problems"]]
    assert dates == sorted(dates, reverse=True)


def test_problems_list_severity_filter(problems_client: TestClient) -> None:
    r = problems_client.get("/api/problems?severity=critical")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["problems"][0]["id"] == "pb_p4444444"


def test_problems_list_status_filter(problems_client: TestClient) -> None:
    r = problems_client.get("/api/problems?status=open")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert {p["id"] for p in body["problems"]} == {"pb_p2222222", "pb_p5555555"}


def test_problems_list_project_filter(problems_client: TestClient) -> None:
    r = problems_client.get("/api/problems?project=alpha-labs")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3


def test_problems_list_search(problems_client: TestClient) -> None:
    r = problems_client.get("/api/problems?search=pgloader")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["problems"][0]["id"] == "pb_p4444444"


def test_problems_list_date_range(problems_client: TestClient) -> None:
    r = problems_client.get("/api/problems?from_date=2608-05&to_date=2608-06")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 4


def test_problems_list_etag_304(problems_client: TestClient) -> None:
    r1 = problems_client.get("/api/problems")
    etag = r1.headers["ETag"]
    r2 = problems_client.get("/api/problems", headers={"If-None-Match": etag})
    assert r2.status_code == 304


# ---------------------------------------------------------------------------
# GET /api/problems/{id}
# ---------------------------------------------------------------------------


def test_problems_detail_shape(problems_client: TestClient) -> None:
    r = problems_client.get("/api/problems/pb_p1111111")
    assert r.status_code == 200
    body = r.json()
    assert body["metadata"]["id"] == "pb_p1111111"
    assert body["metadata"]["severity"] == "major"
    assert body["metadata"]["status"] == "investigating"
    assert body["l2"].startswith("Problem context paragraph")
    assert body["l3"] == ["Attempt 1 — diagnose", "Attempt 2 — workaround"]
    assert "Resolution" in body["l4"]


def test_problems_detail_cyrillic_roundtrip(problems_client: TestClient) -> None:
    r = problems_client.get("/api/problems/pb_p5555555")
    assert r.status_code == 200
    body = r.json()
    assert "матолимп" in body["metadata"]["l1"].lower()
    assert "Матолимп" in body["l2"]
    assert body["l3"] == ["Проверить fontconfig", "Обновить парсер"]
    assert "kirill" in body["l4"]


def test_problems_detail_not_found(problems_client: TestClient) -> None:
    r = problems_client.get("/api/problems/pb_deadbeef")
    assert r.status_code == 404


def test_problems_detail_resolved_carries_date(problems_client: TestClient) -> None:
    r = problems_client.get("/api/problems/pb_p3333333")
    assert r.status_code == 200
    assert r.json()["metadata"]["resolved_date"] == "2608-06"


# ---------------------------------------------------------------------------
# POST /api/problems
# ---------------------------------------------------------------------------


def test_problems_post_appends_and_visible(
    problems_client: TestClient, problems_data_root: Path,
) -> None:
    payload = {
        "created_date": "2608-07",
        "created_time": "09:00",
        "project": "alpha-labs",
        "agent_id": "pb-new-sub",
        "l1": "Fresh problem — POST round-trip smoke test.",
        "severity": "minor",
        "status": "open",
        "related_goal_id": "g_a1",
        "resolved_date": "",
        "l2": "Something сломалось on cold start.",
        "l3": ["Attempt one тестовый", "Attempt two backup"],
        "l4": "Discussion snippet ниже.",
    }
    r = problems_client.post("/api/problems", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert "metadata" in body
    sid = body["metadata"]["id"]
    assert sid.startswith("pb_") and len(sid) == 11
    assert body["l2"] == payload["l2"]
    assert body["l3"] == payload["l3"]

    csv_lines = (problems_data_root / "problems.csv").read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(csv_lines) == 1 + 6 + 1

    md_path = problems_data_root / body["metadata"]["md_ref"]
    assert md_path.exists()
    assert "тестовый" in md_path.read_text(encoding="utf-8")

    r2 = problems_client.get("/api/problems")
    assert r2.json()["total"] == 7
    r3 = problems_client.get(f"/api/problems/{sid}")
    assert r3.status_code == 200
    assert r3.json()["l4"] == payload["l4"]


def test_problems_post_id_is_deterministic(problems_client: TestClient) -> None:
    payload = {
        "created_date": "2608-08",
        "created_time": "12:00",
        "project": "beta-corp",
        "agent_id": "pb-dup",
        "l1": "Determinism check.",
        "severity": "nit",
        "status": "open",
    }
    r1 = problems_client.post("/api/problems", json=payload)
    r2 = problems_client.post("/api/problems", json=payload)
    assert r1.status_code == 201
    assert r2.status_code == 200      # a repeat writes nothing new
    assert r1.json()["metadata"]["id"] == r2.json()["metadata"]["id"]
