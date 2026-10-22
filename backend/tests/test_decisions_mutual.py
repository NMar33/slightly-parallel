"""Mutual decisions endpoint tests — index, detail, POST, cyrillic-safe.

Seeds a self-contained ``{data_root}/decisions.csv`` +
``{data_root}/decision_details/*.md`` layout produced by
``scripts/migrate_decisions.py``, then hits the SCAN-parallel endpoints:

    GET  /api/decisions
    GET  /api/decisions/{id}
    POST /api/decisions
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app


DECISION_COLUMNS = [
    "id", "created_date", "created_time", "project", "agent_id",
    "decision_text", "rationale", "source", "related_goal_id",
    "files_affected_n", "alternatives_n", "md_ref",
]


# Six rows across three projects. Row 4 (quizforge) carries cyrillic text into
# decision_text AND the MD body so we can prove round-trip through CSV,
# DuckDB, MD parser, JSON.
DECISIONS_ROWS = [
    ("dc_11111111", "2608-06", "09:14", "WT", "bw-firebase-sub",
     "Chose PBKDF2 for key derivation over bcrypt",
     "constant-time comparison + wide language support",
     "explicit", "g_wt_e2e", 3, 2,
     "decision_details/260806__wt__11111111.md"),
    ("dc_22222222", "2608-06", "07:42", "LedgerKit", "g_ae4c92f1",
     "Cache prompt outputs at generator layer",
     "cuts token spend по half when regenerating variants",
     "auto", "g_sxp_cost", 1, 2,
     "decision_details/260806__ledgerkit__22222222.md"),
    ("dc_33333333", "2608-05", "22:03", "PDR", "operator",
     "Pyramid is a snapshot, not a per-view navigation",
     "single mental model won't fragment across screens",
     "explicit", None, 0, 2,
     "decision_details/260805__pdr__33333333.md"),
    ("dc_44444444", "2608-04", "18:27", "quizforge", "qf-content-sub",
     "Кириллица в decision_text — рекогниция pipelines",  # cyrillic anchor
     "проверка round-trip через CSV/DuckDB/JSON",
     "explicit", "g_qf_pipeline", 2, 2,
     "decision_details/260804__quizforge__44444444.md"),
    ("dc_55555555", "2608-03", "15:51", "orbit", "orbit-state-check",
     "Reject NhMM in favour of decimal fallback",
     "parser can't disambiguate 1.5h from 1h5m",
     "explicit", "g_orbit_parser", 1, 2,
     "decision_details/260803__orbit__55555555.md"),
    ("dc_66666666", "2608-02", "11:08", "WT", "bw-auth-sub",
     "Anonymous-first login",
     "reduces friction на onboarding funnel",
     "auto", "g_wt_onboard", 2, 2,
     "decision_details/260802__wt__66666666.md"),
]


def _write_seed(root: Path) -> None:
    """Materialise a data_root that mirrors what migrate_decisions.py emits."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "decision_details").mkdir(exist_ok=True)

    # Empty project folders — /api/project/{code} guards against unknown
    # codes by returning an empty bundle; make the codes known so the
    # mutual-decisions-by-project cross-endpoint test can prove routing.
    projects_root = root / "projects"
    projects_root.mkdir(exist_ok=True)
    for code in {row[3] for row in DECISIONS_ROWS}:
        (projects_root / code).mkdir(exist_ok=True)

    # Mutual CSV
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    w.writerow(DECISION_COLUMNS)
    for r in DECISIONS_ROWS:
        w.writerow(["" if v is None else v for v in r])
    (root / "decisions.csv").write_text(buf.getvalue(), encoding="utf-8")

    # MD details — full frontmatter + L2/L3/L4. Row 4 = cyrillic across
    # every section for the round-trip test.
    for row in DECISIONS_ROWS:
        did = row[0]
        md_ref = row[11]
        md_path = root / md_ref
        cyr = row[3] == "quizforge"
        l2 = (
            "Матолимп pipeline остаётся стабильным."
            if cyr else f"Rationale detail for {did}."
        )
        l3_a = "**Alt 1**: bcrypt — slower KDF" if not cyr else \
            "**Alt 1**: латиница — отказано ради консистентности"
        l3_b = "**Alt 2**: scrypt — memory-hard но overkill" if not cyr else \
            "**Alt 2**: транслит — проиграл по читаемости"
        l4 = (
            "> **kirill**: Ничего не сломалось. Продолжай."
            if cyr else f"> **agent**: Chat context for {did}."
        )
        md = (
            "---\n"
            f"id: {did}\n"
            "---\n\n"
            "## L2 — Rationale\n\n"
            f"{l2}\n\n"
            "## L3 — Alternatives considered\n\n"
            f"- {l3_a}\n"
            f"- {l3_b}\n\n"
            "## L4 — Raw context\n\n"
            f"{l4}\n"
        )
        md_path.write_text(md, encoding="utf-8")


@pytest.fixture()
def dec_data_root(tmp_path: Path) -> Path:
    root = tmp_path / "00-agents"
    _write_seed(root)
    return root


@pytest.fixture()
def dec_client(dec_data_root: Path) -> TestClient:
    app = create_app(data_root=dec_data_root, watch=False)
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# GET /api/decisions — index
# ---------------------------------------------------------------------------


def test_decisions_list_all_six(dec_client: TestClient) -> None:
    r = dec_client.get("/api/decisions")
    assert r.status_code == 200
    assert "ETag" in r.headers
    body = r.json()
    assert body["total"] == 6
    assert len(body["decisions"]) == 6
    # Ordered newest-first by (date, time)
    dates = [(d["created_date"], d["created_time"]) for d in body["decisions"]]
    assert dates == sorted(dates, reverse=True)
    # SCAN-parallel columns survived DuckDB — ints stay ints, md_ref present
    top = body["decisions"][0]
    assert isinstance(top["files_affected_n"], int)
    assert isinstance(top["alternatives_n"], int)
    assert top["md_ref"].startswith("decision_details/")


def test_decisions_list_project_filter(dec_client: TestClient) -> None:
    r = dec_client.get("/api/decisions?project=WT")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert {d["agent_id"] for d in body["decisions"]} == {
        "bw-firebase-sub", "bw-auth-sub",
    }


def test_decisions_list_agent_id_filter(dec_client: TestClient) -> None:
    r = dec_client.get("/api/decisions?agent_id=operator")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["decisions"][0]["project"] == "PDR"


def test_decisions_list_source_filter(dec_client: TestClient) -> None:
    r = dec_client.get("/api/decisions?source=auto")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert all(d["source"] == "auto" for d in body["decisions"])


def test_decisions_list_related_goal_filter(dec_client: TestClient) -> None:
    r = dec_client.get("/api/decisions?related_goal_id=g_wt_e2e")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["decisions"][0]["id"] == "dc_11111111"


def test_decisions_list_date_range(dec_client: TestClient) -> None:
    r = dec_client.get("/api/decisions?from_date=2608-05&to_date=2608-06")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    for d in body["decisions"]:
        assert "2608-05" <= d["created_date"] <= "2608-06"


def test_decisions_list_etag_304(dec_client: TestClient) -> None:
    r1 = dec_client.get("/api/decisions")
    etag = r1.headers["ETag"]
    r2 = dec_client.get("/api/decisions", headers={"If-None-Match": etag})
    assert r2.status_code == 304
    assert r2.headers["ETag"] == etag


# ---------------------------------------------------------------------------
# GET /api/decisions/{id} — rich detail
# ---------------------------------------------------------------------------


def test_decisions_detail_shape(dec_client: TestClient) -> None:
    r = dec_client.get("/api/decisions/dc_11111111")
    assert r.status_code == 200
    body = r.json()
    assert body["metadata"]["id"] == "dc_11111111"
    assert body["metadata"]["project"] == "WT"
    assert body["metadata"]["files_affected_n"] == 3
    assert body["l2"].startswith("Rationale detail")
    assert len(body["l3"]) == 2
    assert body["l3"][0].startswith("**Alt 1**")
    assert "Chat context" in body["l4"]


def test_decisions_detail_cyrillic_roundtrip(dec_client: TestClient) -> None:
    r = dec_client.get("/api/decisions/dc_44444444")
    assert r.status_code == 200
    body = r.json()
    # Cyrillic survives CSV, DuckDB, MD-parse, JSON.
    assert "рекогниция" in body["metadata"]["decision_text"]
    assert "Матолимп" in body["l2"]
    assert any("латиница" in bullet for bullet in body["l3"])
    assert "kirill" in body["l4"]
    assert "Ничего не сломалось" in body["l4"]


def test_decisions_detail_not_found(dec_client: TestClient) -> None:
    r = dec_client.get("/api/decisions/dc_deadbeef")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/decisions — append round-trip
# ---------------------------------------------------------------------------


def test_decisions_post_appends_and_visible(
    dec_client: TestClient, dec_data_root: Path,
) -> None:
    payload = {
        "created_date": "2608-07",
        "created_time": "10:00",
        "project": "WT",
        "agent_id": "bw-new-sub",
        "decision_text": "Switch к Argon2id",
        "rationale": "OWASP now recommends Argon2 over PBKDF2 для greenfield",
        "source": "explicit",
        "related_goal_id": "g_wt_e2e",
        "files_affected_n": 4,
        "alternatives_n": 2,
        "l2": "Проверка path записи и рекогниция полей.",
        "l3": ["**Alt 1**: keep PBKDF2 — status quo", "**Alt 2**: scrypt — memory-hard"],
        "l4": "> **operator**: тест round-trip через POST.",
    }
    r = dec_client.post("/api/decisions", json=payload)
    assert r.status_code == 201
    body = r.json()
    did = body["metadata"]["id"]
    assert did.startswith("dc_") and len(did) == 11
    assert body["l2"] == payload["l2"]
    assert body["l3"] == payload["l3"]

    # CSV grew by one row (header + 6 seed + 1 new)
    csv_lines = (dec_data_root / "decisions.csv").read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(csv_lines) == 1 + 6 + 1

    # MD file landed AND contains cyrillic body + bullets
    md_path = dec_data_root / body["metadata"]["md_ref"]
    assert md_path.exists()
    md_body = md_path.read_text(encoding="utf-8")
    assert "рекогниция" in md_body
    assert "тест" in md_body
    assert "**Alt 1**: keep PBKDF2" in md_body

    # GET /api/decisions now shows 7 rows
    r2 = dec_client.get("/api/decisions")
    assert r2.json()["total"] == 7

    # GET /api/decisions/{new_id} returns the rich content
    r3 = dec_client.get(f"/api/decisions/{did}")
    assert r3.status_code == 200
    assert r3.json()["l4"] == payload["l4"]


def test_decisions_post_id_is_deterministic(dec_client: TestClient) -> None:
    """Same payload → same did (idempotency-lite via content hash)."""
    payload = {
        "created_date": "2608-08",
        "created_time": "12:00",
        "project": "WT",
        "agent_id": "bw-dup",
        "decision_text": "Determinism check",
    }
    r1 = dec_client.post("/api/decisions", json=payload)
    r2 = dec_client.post("/api/decisions", json=payload)
    assert r1.status_code == 201
    assert r2.status_code == 200      # a repeat writes nothing new
    assert r1.json()["metadata"]["id"] == r2.json()["metadata"]["id"]


# ---------------------------------------------------------------------------
# Cross-endpoint: /api/project/{code} decisions field reads mutual view
# ---------------------------------------------------------------------------


def test_project_bundle_reads_mutual_decisions(dec_client: TestClient) -> None:
    r = dec_client.get("/api/project/WT")
    assert r.status_code == 200
    body = r.json()
    # WT has 2 decisions in the mutual csv; per-project files don't exist.
    assert len(body["decisions"]) == 2
    assert {d["id"] for d in body["decisions"]} == {"dc_11111111", "dc_66666666"}
