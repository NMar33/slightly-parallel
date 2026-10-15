"""SCAN endpoint tests — index, detail, cyrillic-safe, POST + view refresh."""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app


# ---------------------------------------------------------------------------
# Fixture: seed scans.csv + snapshots/ under a tmp data_root
# ---------------------------------------------------------------------------


SCANS_ROWS = [
    # (id, date, time, project, agent, l1, files, +, -, dec, scope, md_ref)
    ("sn_11111111", "2608-06", "09:14", "WT", "bw-firebase-sub",
     "Firebase Phase 1 GREEN — encrypted backup shipped.",
     12, 347, 89, 3, "120-app-mvp/lib/auth",
     "snapshots/2608-06-0914__wt__bw-firebase-sub.md"),
    ("sn_22222222", "2608-06", "07:42", "LedgerKit", "g_ae4c92f1",
     "Grade-6 module wobbles — half the problems miss curriculum bounds.",
     3, 58, 204, 2, "ledgerkit/generator/prompts",
     "snapshots/2608-06-0742__ledgerkit__g_ae4c92f1.md"),
    ("sn_33333333", "2608-05", "22:03", "PDR", "operator",
     "Pyramid is a snapshot, not a per-view navigation.",
     2, 142, 27, 5, "dashboard/docs/vision",
     "snapshots/2608-05-2203__pdr__operator.md"),
    ("sn_44444444", "2608-04", "18:27", "quizforge", "qf-content-sub",
     "матолимп week 4: calm and boring.",  # cyrillic — must round-trip
     8, 212, 44, 1, "quizforge/pipeline",
     "snapshots/2608-04-1827__quizforge__qf-content-sub.md"),
    ("sn_55555555", "2608-03", "15:51", "orbit", "orbit-state-check",
     "Journal parser rejects the new daily totals.",
     4, 89, 31, 4, "orbit/lib/parser",
     "snapshots/2608-03-1551__orbit__orbit-state-check.md"),
    ("sn_66666666", "2608-02", "11:08", "rekognitsiya", "rec-onboarding",
     "Onboarding funnel holds at 68%.",
     3, 67, 18, 2, "rekognitsiya/analytics/funnel",
     "snapshots/2608-02-1108__rekognitsiya__rec-onboarding.md"),
    ("sn_77777777", "2608-01", "19:34", "WT", "bw-auth-sub",
     "Anonymous-first login merged.",
     12, 518, 102, 3, "120-app-mvp/lib/auth+onboarding",
     "snapshots/2608-01-1934__wt__bw-auth-sub.md"),
]


COLUMNS = [
    "id", "created_date", "created_time", "project", "agent_id",
    "l1", "files_n", "lines_add", "lines_del", "decisions_n",
    "scope", "md_ref",
]


def _write_seed(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "snapshots").mkdir(exist_ok=True)
    (root / "projects").mkdir(exist_ok=True)  # ViewStore expects it

    # CSV
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    w.writerow(COLUMNS)
    for r in SCANS_ROWS:
        w.writerow(r)
    (root / "scans.csv").write_text(buf.getvalue(), encoding="utf-8")

    # MD files — minimal frontmatter + full L2/L3/L4 sections. Row 4
    # (quizforge) carries cyrillic text into L2 / L3 / L4 so we can prove
    # round-trip.
    for row in SCANS_ROWS:
        sid = row[0]
        md_ref = row[11]
        md_path = root / md_ref
        cyr = row[3] == "quizforge"
        l2 = ("Матолимп pipeline остаётся спокойным." if cyr
              else f"Detail paragraph for {sid}.")
        l3_a = "Ничего не сломалось" if cyr else "Ship green"
        l3_b = "Продолжаем работу" if cyr else "No blockers"
        l4 = ("> **kirill**: Ничего не сломалось. Продолжай." if cyr
              else f"> **agent**: Session close for {sid}.")
        md = (
            "---\n"
            f"id: {sid}\n"
            f'l1: "{row[5]}"\n'
            "---\n\n"
            "## L2\n\n"
            f"{l2}\n\n"
            "## L3\n\n"
            f"- {l3_a}\n"
            f"- {l3_b}\n\n"
            "## L4\n\n"
            f"{l4}\n"
        )
        md_path.write_text(md, encoding="utf-8")


@pytest.fixture()
def scans_data_root(tmp_path: Path) -> Path:
    root = tmp_path / "00-agents"
    _write_seed(root)
    return root


@pytest.fixture()
def scans_client(scans_data_root: Path) -> TestClient:
    app = create_app(data_root=scans_data_root, watch=False)
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# GET /api/scans — index
# ---------------------------------------------------------------------------


def test_scans_list_all_seven(scans_client: TestClient) -> None:
    r = scans_client.get("/api/scans")
    assert r.status_code == 200
    assert "ETag" in r.headers
    body = r.json()
    assert body["total"] == 7
    assert len(body["scans"]) == 7
    # Newest first
    dates = [(s["created_date"], s["created_time"]) for s in body["scans"]]
    assert dates == sorted(dates, reverse=True)
    # Types survived DuckDB (int, not str)
    first = body["scans"][0]
    assert isinstance(first["files_n"], int)
    assert isinstance(first["lines_add"], int)


def test_scans_list_project_filter(scans_client: TestClient) -> None:
    r = scans_client.get("/api/scans?project=WT")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert {s["agent_id"] for s in body["scans"]} == {
        "bw-firebase-sub", "bw-auth-sub"
    }


def test_scans_list_agent_filter(scans_client: TestClient) -> None:
    r = scans_client.get("/api/scans?agent_id=operator")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["scans"][0]["project"] == "PDR"


def test_scans_list_date_range(scans_client: TestClient) -> None:
    r = scans_client.get("/api/scans?from_date=2608-05&to_date=2608-06")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    for s in body["scans"]:
        assert "2608-05" <= s["created_date"] <= "2608-06"


def test_scans_list_etag_304(scans_client: TestClient) -> None:
    r1 = scans_client.get("/api/scans")
    etag = r1.headers["ETag"]
    r2 = scans_client.get("/api/scans", headers={"If-None-Match": etag})
    assert r2.status_code == 304
    assert r2.headers["ETag"] == etag


# ---------------------------------------------------------------------------
# GET /api/scans/{id} — rich detail
# ---------------------------------------------------------------------------


def test_scans_detail_shape(scans_client: TestClient) -> None:
    r = scans_client.get("/api/scans/sn_11111111")
    assert r.status_code == 200
    body = r.json()
    assert body["metadata"]["id"] == "sn_11111111"
    assert body["metadata"]["project"] == "WT"
    assert body["l2"].startswith("Detail paragraph")
    assert body["l3"] == ["Ship green", "No blockers"]
    assert "Session close" in body["l4"]


def test_scans_detail_cyrillic_roundtrip(scans_client: TestClient) -> None:
    r = scans_client.get("/api/scans/sn_44444444")
    assert r.status_code == 200
    body = r.json()
    # Cyrillic survives every layer: CSV, DuckDB, MD-parse, JSON.
    assert "матолимп" in body["metadata"]["l1"].lower()
    assert "Матолимп" in body["l2"]
    assert body["l3"] == ["Ничего не сломалось", "Продолжаем работу"]
    assert "kirill" in body["l4"]
    assert "Ничего не сломалось" in body["l4"]


def test_scans_detail_not_found(scans_client: TestClient) -> None:
    r = scans_client.get("/api/scans/sn_deadbeef")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/scans — append round-trip
# ---------------------------------------------------------------------------


def test_scans_post_appends_and_visible(scans_client: TestClient,
                                        scans_data_root: Path) -> None:
    payload = {
        "created_date": "2608-07",
        "created_time": "10:00",
        "project": "WT",
        "agent_id": "bw-new-sub",
        "l1": "Fresh SCAN entry — POST round-trip smoke test.",
        "files_n": 5,
        "lines_add": 100,
        "lines_del": 20,
        "decisions_n": 1,
        "scope": "120-app-mvp/lib/new",
        "l2": "Just checking the write path holds.",
        "l3": ["First bullet", "Second bullet"],
        "l4": "> **operator**: Test это тест.",
    }
    r = scans_client.post("/api/scans", json=payload)
    assert r.status_code == 201
    body = r.json()
    sid = body["metadata"]["id"]
    assert sid.startswith("sn_") and len(sid) == 11
    assert body["l2"] == payload["l2"]
    assert body["l3"] == payload["l3"]

    # CSV grew by one row
    csv_lines = (scans_data_root / "scans.csv").read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(csv_lines) == 1 + 7 + 1  # header + 7 seed + 1 new

    # MD file landed
    md_path = scans_data_root / body["metadata"]["md_ref"]
    assert md_path.exists()
    md_body = md_path.read_text(encoding="utf-8")
    assert "тест" in md_body
    assert "First bullet" in md_body

    # Now visible via GET /api/scans
    r2 = scans_client.get("/api/scans")
    assert r2.json()["total"] == 8
    r3 = scans_client.get(f"/api/scans/{sid}")
    assert r3.status_code == 200
    assert r3.json()["l4"] == payload["l4"]


def test_scans_post_id_is_deterministic(scans_client: TestClient) -> None:
    """Same payload → same sid (idempotency-lite via content hash)."""
    payload = {
        "created_date": "2608-08",
        "created_time": "12:00",
        "project": "WT",
        "agent_id": "bw-dup",
        "l1": "Determinism check.",
    }
    r1 = scans_client.post("/api/scans", json=payload)
    r2 = scans_client.post("/api/scans", json=payload)
    assert r1.status_code == 201
    assert r2.status_code == 200      # a repeat writes nothing new
    assert r1.json()["metadata"]["id"] == r2.json()["metadata"]["id"]


def test_a_scan_can_be_corrected_after_the_fact(client) -> None:
    """The id is minted from summary and minute, so "fix and write again"
    could not correct a scan. The update route rewrites its text and counters."""
    made = client.post("/api/scans", json={
        "created_date": "2609-22", "created_time": "10:00", "project": "ALPHA", "agent_id": "cc-a",
        "summary": "Agents write by name", "why": "The operator asked.", "deltas": ["one"], "proof": "tests",
        "files_n": 3, "lines_add": 10, "lines_del": 1})
    assert made.status_code == 201, made.text
    sid = made.json()["metadata"]["id"]
    fixed = client.post(f"/api/scans/{sid}/update", json={"deltas": ["one", "two"], "proof": "tests → passed", "files_n": 4})
    assert fixed.status_code == 200, fixed.text
    assert fixed.json()["text"]["deltas"] == ["one", "two"] and fixed.json()["metadata"]["files_n"] == 4
    assert fixed.json()["text"]["why"] == "The operator asked."          # untouched text stays
    again = client.get(f"/api/scans/{sid}").json()
    assert again["text"]["proof"] == "tests → passed" and again["metadata"]["lines_add"] == 10
    assert client.post(f"/api/scans/{sid}/update", json={"summary": "x"}).json()["metadata"]["l1"] == "x"
    assert client.post(f"/api/scans/{sid}/update", json={}).status_code == 422
    assert client.post("/api/scans/sn_nope/update", json={"proof": "x"}).status_code == 404
    # The translator offers update_entry for scans, standups and file entries now.
    schema = client.get("/api/schema").json()
    offered = {l["name"] for l in schema["lenses"] if l.get("mutable")}
    assert {"scan", "standup", "file"} <= offered
