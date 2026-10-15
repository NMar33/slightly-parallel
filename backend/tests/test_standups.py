"""STANDUP endpoint tests — index, detail, POST round-trip, cyrillic-safe.

Mirrors test_scans.py 1:1 (SCAN-parallel schema).
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app


# ---------------------------------------------------------------------------
# Fixture: seed standups.csv + standup_details/ under a tmp data_root
# ---------------------------------------------------------------------------


COLUMNS = [
    "id", "created_date", "created_time", "project", "agent_id",
    "l1", "goals_open_n", "goals_closed_n", "blockers_n",
    "hours_today", "md_ref",
]


STANDUP_ROWS = [
    # (id, date, time, project, agent, l1, open, closed, blockers, hours, md_ref)
    ("st_a1111111", "2608-06", "09:15", "WT", "bw-firebase-sub",
     "Firebase Phase 1 GREEN — encrypted backup shipped.",
     3, 2, 0, 4.5,
     "standup_details/2608-06-0915__wt__a1111111.md"),
    ("st_a2222222", "2608-06", "08:00", "LedgerKit", "g_ae4c92f1",
     "Grade-6 module wobbles — half the problems miss curriculum bounds.",
     4, 1, 1, 3.0,
     "standup_details/2608-06-0800__ledgerkit__a2222222.md"),
    ("st_a3333333", "2608-05", "22:03", "PDR", "",
     "Pyramid is a snapshot, not a per-view navigation.",
     2, 0, 0, 1.5,
     "standup_details/2608-05-2203__pdr__a3333333.md"),
    ("st_a4444444", "2608-04", "18:27", "quizforge", "qf-content-sub",
     "матолимп week 4: calm and boring.",  # cyrillic — must round-trip
     1, 3, 0, 2.0,
     "standup_details/2608-04-1827__quizforge__a4444444.md"),
    ("st_a5555555", "2608-05", "20:00", "_all", "",
     "Two-project split: WT shipping, PDR wrapping.",
     6, 4, 1, 1.0,
     "standup_details/2608-05-2000__all__a5555555.md"),
    ("st_a6666666", "2608-03", "09:30", "WT", "bw-auth-sub",
     "Anonymous-first login merged.",
     2, 1, 0, 5.0,
     "standup_details/2608-03-0930__wt__a6666666.md"),
]


def _write_seed(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "standup_details").mkdir(exist_ok=True)
    (root / "projects").mkdir(exist_ok=True)  # ViewStore expects it

    # CSV
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    w.writerow(COLUMNS)
    for r in STANDUP_ROWS:
        w.writerow(r)
    (root / "standups.csv").write_text(buf.getvalue(), encoding="utf-8")

    # MD files — full L2/L3/L4. Row 4 (quizforge) carries cyrillic prose
    # so we can prove round-trip through CSV → DuckDB → MD parse → JSON.
    for row in STANDUP_ROWS:
        sid = row[0]
        md_ref = row[10]
        md_path = root / md_ref
        cyr = row[3] == "quizforge"
        l2 = ("Матолимп pipeline остаётся спокойным — ничего не сломалось."
              if cyr else f"Since-last summary paragraph for {sid}.")
        l3_a = "goal-a · Ничего не сломалось · 90% · 3/5d" if cyr \
            else "goal-a · Ship green · 85% · 1/3d"
        l3_b = "goal-b · Продолжаем работу · 70% · 1/2d" if cyr \
            else "goal-b · No blockers · 75% · 0/1d"
        l4 = ("Goal focus: продолжай спокойно\nTime budget: 2h\nBlockers to unblock: none"
              if cyr
              else "Goal focus: ship next\nTime budget: 4h\nBlockers to unblock: none")
        md = (
            "---\n"
            f"id: {sid}\n"
            f'l1: "{row[5]}"\n'
            "---\n\n"
            "## L2 — Since last standup\n\n"
            f"{l2}\n\n"
            "## L3 — Open goals\n\n"
            f"- {l3_a}\n"
            f"- {l3_b}\n\n"
            "## L4 — Today's plan\n\n"
            f"{l4}\n"
        )
        md_path.write_text(md, encoding="utf-8")


@pytest.fixture()
def standups_data_root(tmp_path: Path) -> Path:
    root = tmp_path / "00-agents"
    _write_seed(root)
    return root


@pytest.fixture()
def standups_client(standups_data_root: Path) -> TestClient:
    app = create_app(data_root=standups_data_root, watch=False)
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# GET /api/standups — index
# ---------------------------------------------------------------------------


def test_standups_list_all_six(standups_client: TestClient) -> None:
    r = standups_client.get("/api/standups")
    assert r.status_code == 200
    assert "ETag" in r.headers
    body = r.json()
    assert body["total"] == 6
    assert len(body["standups"]) == 6
    # Newest first (DESC by date+time)
    dates = [(s["created_date"], s["created_time"]) for s in body["standups"]]
    assert dates == sorted(dates, reverse=True)
    # Types survived DuckDB
    first = body["standups"][0]
    assert isinstance(first["goals_open_n"], int)
    assert isinstance(first["hours_today"], float)


def test_standups_list_project_filter(standups_client: TestClient) -> None:
    r = standups_client.get("/api/standups?project=WT")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert {s["agent_id"] for s in body["standups"]} == {
        "bw-firebase-sub", "bw-auth-sub"
    }


def test_standups_list_cross_project_filter(standups_client: TestClient) -> None:
    """`project=_all` returns the operator's cross-project standups only."""
    r = standups_client.get("/api/standups?project=_all")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    row = body["standups"][0]
    assert row["project"] == "_all"
    # Operator-authored → agent_id nullable and null on the wire
    assert row["agent_id"] is None


def test_standups_list_agent_filter(standups_client: TestClient) -> None:
    r = standups_client.get("/api/standups?agent_id=g_ae4c92f1")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["standups"][0]["project"] == "LedgerKit"


def test_standups_list_date_range(standups_client: TestClient) -> None:
    r = standups_client.get(
        "/api/standups?from_date=2608-05&to_date=2608-06"
    )
    assert r.status_code == 200
    body = r.json()
    # 2 rows on 2608-06 (WT + LedgerKit), 2 rows on 2608-05 (PDR + _all)
    assert body["total"] == 4
    for s in body["standups"]:
        assert "2608-05" <= s["created_date"] <= "2608-06"


def test_standups_list_etag_304(standups_client: TestClient) -> None:
    r1 = standups_client.get("/api/standups")
    etag = r1.headers["ETag"]
    r2 = standups_client.get(
        "/api/standups", headers={"If-None-Match": etag}
    )
    assert r2.status_code == 304
    assert r2.headers["ETag"] == etag


# ---------------------------------------------------------------------------
# GET /api/standups/{id} — rich detail
# ---------------------------------------------------------------------------


def test_standups_detail_shape(standups_client: TestClient) -> None:
    r = standups_client.get("/api/standups/st_a1111111")
    assert r.status_code == 200
    body = r.json()
    assert body["metadata"]["id"] == "st_a1111111"
    assert body["metadata"]["project"] == "WT"
    assert body["l2"].startswith("Since-last summary")
    assert body["l3"] == [
        "goal-a · Ship green · 85% · 1/3d",
        "goal-b · No blockers · 75% · 0/1d",
    ]
    assert "Goal focus" in body["l4"]


def test_standups_detail_cyrillic_roundtrip(standups_client: TestClient) -> None:
    r = standups_client.get("/api/standups/st_a4444444")
    assert r.status_code == 200
    body = r.json()
    # Cyrillic survives every layer: CSV, DuckDB, MD-parse, JSON.
    assert "матолимп" in body["metadata"]["l1"].lower()
    assert "Матолимп" in body["l2"]
    assert body["l3"] == [
        "goal-a · Ничего не сломалось · 90% · 3/5d",
        "goal-b · Продолжаем работу · 70% · 1/2d",
    ]
    assert "продолжай спокойно" in body["l4"]


def test_standups_detail_not_found(standups_client: TestClient) -> None:
    r = standups_client.get("/api/standups/st_deadbeef")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/standups — append round-trip
# ---------------------------------------------------------------------------


def test_standups_post_appends_and_visible(
    standups_client: TestClient, standups_data_root: Path,
) -> None:
    payload = {
        "created_date": "2608-07",
        "created_time": "09:00",
        "project": "WT",
        "agent_id": "bw-new-sub",
        "l1": "Fresh standup — POST round-trip smoke test.",
        "goals_open_n": 3,
        "goals_closed_n": 1,
        "blockers_n": 0,
        "hours_today": 4.0,
        "l2": "Since last standup: shipped X, unblocked Y.",
        "l3": [
            "g_new1 · Ship feature · 80% · 1/3d",
            "g_new2 · Wire tests · 75% · 0/1d",
        ],
        "l4": "Goal focus: g_new1\nTime budget: 4h\nBlockers to unblock: тестовый — none",
    }
    r = standups_client.post("/api/standups", json=payload)
    assert r.status_code == 201
    body = r.json()
    sid = body["metadata"]["id"]
    assert sid.startswith("st_") and len(sid) == 11
    assert body["l2"] == payload["l2"]
    assert body["l3"] == payload["l3"]

    # CSV grew by one row
    csv_lines = (standups_data_root / "standups.csv").read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(csv_lines) == 1 + 6 + 1  # header + 6 seed + 1 new

    # MD file landed
    md_path = standups_data_root / body["metadata"]["md_ref"]
    assert md_path.exists()
    md_body = md_path.read_text(encoding="utf-8")
    assert "тестовый" in md_body
    assert "g_new1 · Ship feature" in md_body

    # Now visible via GET /api/standups
    r2 = standups_client.get("/api/standups")
    assert r2.json()["total"] == 7
    r3 = standups_client.get(f"/api/standups/{sid}")
    assert r3.status_code == 200
    assert r3.json()["l4"] == payload["l4"]


def test_standups_post_cross_project_nick_authored(
    standups_client: TestClient, standups_data_root: Path,
) -> None:
    """project=_all + agent_id omitted → operator-authored cross-project standup."""
    payload = {
        "created_date": "2608-08",
        "created_time": "20:00",
        "project": "_all",
        # agent_id intentionally omitted
        "l1": "Cross-project weekly: two shipping, one blocked.",
        "goals_open_n": 5,
        "goals_closed_n": 3,
        "blockers_n": 1,
        "hours_today": 1.5,
        "l2": "WT + LedgerKit on track; quizforge waiting on the operator.",
        "l3": ["WT · g_a1 · 85%", "LedgerKit · g_s1 · 70%"],
        "l4": "Goal focus: unblock quizforge\nTime budget: 2h\nBlockers to unblock: operator call",
    }
    r = standups_client.post("/api/standups", json=payload)
    assert r.status_code == 201
    body = r.json()
    sid = body["metadata"]["id"]
    assert body["metadata"]["project"] == "_all"
    assert body["metadata"]["agent_id"] is None
    # Filename slug for `_all` folds к `all` (matches server._slug_project).
    assert "__all__" in body["metadata"]["md_ref"]

    # Round-trip via list
    r2 = standups_client.get("/api/standups?project=_all")
    assert r2.status_code == 200
    ids = [s["id"] for s in r2.json()["standups"]]
    assert sid in ids


def test_standups_post_id_is_deterministic(standups_client: TestClient) -> None:
    """Same payload → same sid (idempotency-lite via content hash)."""
    payload = {
        "created_date": "2608-08",
        "created_time": "12:00",
        "project": "WT",
        "agent_id": "bw-dup",
        "l1": "Determinism check.",
    }
    r1 = standups_client.post("/api/standups", json=payload)
    r2 = standups_client.post("/api/standups", json=payload)
    assert r1.status_code == 201
    assert r2.status_code == 200      # a repeat writes nothing new
    assert r1.json()["metadata"]["id"] == r2.json()["metadata"]["id"]
