"""Endpoint contract tests. Every route: shape + ETag + graceful-degrade."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# /api/health
# ---------------------------------------------------------------------------


def test_health_ok(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["projects"] == 2
    assert body["agents"] == 2
    assert "data_root" in body


# ---------------------------------------------------------------------------
# /api/snapshot — CEO overview
# ---------------------------------------------------------------------------


def test_snapshot_shape(client: TestClient) -> None:
    r = client.get("/api/snapshot")
    assert r.status_code == 200
    assert "ETag" in r.headers

    body = r.json()
    assert body["kpi"]["projects"] == 2
    assert body["kpi"]["agents"] == 2
    # ALPHA: tk_alpha_auth (doing) + BETA: tk_beta_x (todo) — done and
    # archived rows never count as open.
    assert body["kpi"]["open_tasks"] == 2
    assert body["kpi"]["tasks_done_7d"] >= 0
    assert isinstance(body["projects"], list)
    codes = {p["code"] for p in body["projects"]}
    assert codes == {"ALPHA", "BETA"}

    alpha = next(p for p in body["projects"] if p["code"] == "ALPHA")
    assert alpha["open_tasks"] == 1
    assert alpha["tasks_total"] == 2  # the archived one is out
    # The in-play list leads with what is moving.
    assert [t["id"] for t in body["open_tasks"]] == ["tk_alpha_auth", "tk_beta_x"]
    assert body["open_tasks"][0]["title"] == "Wire alpha auth"
    assert alpha["active_agents"] == 2
    assert alpha["l1_headline"]  # headline was picked

    # Recent activity present and ordered desc by date
    ra = body["recent_activity"]
    assert len(ra) >= 3
    dates = [a["created_date"] for a in ra]
    assert dates == sorted(dates, reverse=True)


def test_snapshot_etag_304(client: TestClient) -> None:
    r1 = client.get("/api/snapshot")
    etag = r1.headers["ETag"]
    r2 = client.get("/api/snapshot", headers={"If-None-Match": etag})
    assert r2.status_code == 304
    assert r2.headers["ETag"] == etag


# ---------------------------------------------------------------------------
# /api/project/{code}
# ---------------------------------------------------------------------------


def test_project_alpha_bundle(client: TestClient) -> None:
    r = client.get("/api/project/ALPHA")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == "ALPHA"
    assert "goals" not in body
    assert body["summary"]["open_tasks"] == 1
    assert body["summary"]["tasks_total"] == 2
    assert len(body["decisions"]) == 2
    assert len(body["activity"]) == 3
    assert len(body["agents"]) == 2


def test_project_missing_degrades(client: TestClient) -> None:
    """Missing project = empty bundle, not 404 (graceful degrade rule)."""
    r = client.get("/api/project/GHOST")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == "GHOST"
    assert body["summary"]["open_tasks"] == 0
    assert body["decisions"] == []


# ---------------------------------------------------------------------------
# /api/agent/{id}
# ---------------------------------------------------------------------------


def test_agent_detail(client: TestClient) -> None:
    r = client.get("/api/agent/alpha-lead-2608-01")
    assert r.status_code == 200
    body = r.json()
    assert body["agent"]["agent_id"] == "alpha-lead-2608-01"
    assert body["agent"]["l1_headline"].startswith("Alpha kickoff")
    assert body["chat_available"] is True
    assert body["chat_lines"] > 200
    # No underscore-prefixed private keys leaking through
    assert not any(k.startswith("_") for k in body["agent"].keys())


def test_agent_not_found(client: TestClient) -> None:
    r = client.get("/api/agent/nope")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# /api/chat/{id}?range=
# ---------------------------------------------------------------------------


def test_chat_slice(client: TestClient) -> None:
    r = client.get("/api/chat/alpha-lead-2608-01?range=10-20")
    assert r.status_code == 200
    body = r.json()
    assert body["start"] == 10
    assert body["end"] == 20
    assert len(body["lines"]) == 11
    assert body["total_lines"] > 200


def test_chat_default_range(client: TestClient) -> None:
    r = client.get("/api/chat/alpha-lead-2608-01")
    assert r.status_code == 200
    assert r.json()["start"] == 1


# ---------------------------------------------------------------------------
# /api/search
# ---------------------------------------------------------------------------


def test_search_latin(client: TestClient) -> None:
    r = client.get("/api/search?q=FastAPI")
    assert r.status_code == 200
    body = r.json()
    assert any("FastAPI" in d["decision_text"] for d in body["decisions"])


def test_search_cyrillic(client: TestClient) -> None:
    r = client.get("/api/search?q=рекогниция")
    assert r.status_code == 200
    body = r.json()
    assert any("рекогниция" in t["title"] for t in body["tasks"])
    assert body["tasks"][0]["project"] == "ALPHA"


def test_search_skips_archived_tasks(client: TestClient) -> None:
    r = client.get("/api/search?q=archived&types=tasks")
    assert r.status_code == 200
    assert r.json()["tasks"] == []


def test_search_empty_query(client: TestClient) -> None:
    r = client.get("/api/search?q=")
    assert r.status_code == 200
    body = r.json()
    assert body["tasks"] == []
    assert body["decisions"] == []
    assert body["agents"] == []


def test_search_agent(client: TestClient) -> None:
    r = client.get("/api/search?q=followup&types=agents")
    assert r.status_code == 200
    body = r.json()
    assert len(body["agents"]) >= 1


# ---------------------------------------------------------------------------
# /api/timeline
# ---------------------------------------------------------------------------


def test_timeline_all(client: TestClient) -> None:
    r = client.get("/api/timeline")
    assert r.status_code == 200
    body = r.json()
    assert len(body["lanes"]) == 2
    lead = next(l for l in body["lanes"] if l["agent_id"] == "alpha-lead-2608-01")
    assert lead["parent_agent_id"] is None
    followup = next(
        l for l in body["lanes"] if l["agent_id"] == "alpha-followup-2608-05"
    )
    assert followup["parent_agent_id"] == "alpha-lead-2608-01"
    assert len(lead["activities"]) == 3


def test_timeline_project_filter(client: TestClient) -> None:
    r = client.get("/api/timeline?project=BETA")
    assert r.status_code == 200
    assert r.json()["lanes"] == []


def test_timeline_date_range(client: TestClient) -> None:
    r = client.get("/api/timeline?from=2608-02&to=2608-02")
    assert r.status_code == 200
    body = r.json()
    lead = next(l for l in body["lanes"] if l["agent_id"] == "alpha-lead-2608-01")
    assert all(a["created_date"] == "2608-02" for a in lead["activities"])


# ---------------------------------------------------------------------------
# /api/heatmap
# ---------------------------------------------------------------------------


def test_heatmap(client: TestClient) -> None:
    r = client.get("/api/heatmap?project=ALPHA")
    assert r.status_code == 200
    body = r.json()
    files = {c["file"] for c in body["cells"]}
    assert "src/auth.py" in files
    assert "src/db.py" in files


# ---------------------------------------------------------------------------
# /api/decisions
# ---------------------------------------------------------------------------


def test_decisions_all(client: TestClient) -> None:
    r = client.get("/api/decisions")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert len(body["decisions"]) == 2


def test_decisions_source_filter(client: TestClient) -> None:
    r = client.get("/api/decisions?source=explicit")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["decisions"][0]["source"].startswith("explicit")


def test_decisions_project_filter(client: TestClient) -> None:
    r = client.get("/api/decisions?project=BETA")
    assert r.status_code == 200
    assert r.json()["total"] == 0


# ---------------------------------------------------------------------------
# OpenAPI + CORS
# ---------------------------------------------------------------------------


def test_openapi_docs(client: TestClient) -> None:
    r = client.get("/docs")
    assert r.status_code == 200


def test_openapi_schema(client: TestClient) -> None:
    r = client.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    # All named endpoints present
    for p in [
        "/api/snapshot",
        "/api/project/{code}",
        "/api/agent/{agent_id}",
        "/api/chat/{agent_id}",
        "/api/search",
        "/api/timeline",
        "/api/heatmap",
        "/api/decisions",
        "/api/health",
    ]:
        assert p in schema["paths"], f"missing endpoint: {p}"


def test_cors_headers(client: TestClient) -> None:
    r = client.options(
        "/api/snapshot",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_search_looks_in_every_kind_and_in_the_text(client: TestClient, data_root) -> None:
    """The old search read three CSVs and a few columns, so a word read on a
    scan or in a chat came back with nothing. One index over every kind now,
    the detail documents included (searchlib.py)."""
    import json

    from backend import searchlib

    store = client.app.state.store
    made = client.post("/api/scans", json={
        "created_date": "2609-21", "created_time": "10:00", "project": "ALPHA", "agent_id": "cc-a",
        "summary": "The lantern is lit", "why": "A word that sits only in the body: kaleidoscope.",
    })
    assert made.status_code == 201, made.text
    chat = Path(store.data_root) / "projects" / "ALPHA" / "chats" / "cc-search01"
    chat.mkdir(parents=True, exist_ok=True)
    (chat / "meta.json").write_text(json.dumps({"agent_id": "cc-search01"}), encoding="utf-8")
    (chat / "chat.md").write_text(
        "# Chat log\n\n---\n\n## Turn 1 · 2026-09-21T09:00:00\n**User**: what about the periscope?\n"
        "**Agent**: it works\n", encoding="utf-8")
    store.rebuild()
    searchlib.forget()

    got = client.get("/api/search?q=lantern").json()
    assert [h["kind"] for h in got["hits"]][:1] == ["scan"] and got["counts"]["scan"] >= 1
    assert got["hits"][0]["where"] == "title"

    body = client.get("/api/search?q=kaleidoscope").json()
    assert body["hits"] and body["hits"][0]["kind"] == "scan" and body["hits"][0]["where"] == "text"
    assert "kaleidoscope" in body["hits"][0]["snippet"]

    talk = client.get("/api/search?q=periscope").json()
    said = talk["hits"][0]
    assert [h["kind"] for h in talk["hits"]] == ["turn"]
    assert said["agent_id"] == "cc-search01" and said["role"] == "user" and said["turn"] == 1

    only = client.get("/api/search?q=lantern&types=standup").json()
    assert only["hits"] == [] and only["counts"] == {}
    assert client.get("/api/search?q=").json()["hits"] == []


def test_the_search_overview_counts_the_index_once_and_one_word_on_request(client: TestClient) -> None:
    """A search page with no query shows what is in there; the numbers come
    from the index, counted when it was built (searchlib.overview)."""
    from backend import searchlib

    searchlib.forget()
    whole = client.get("/api/search/overview").json()
    assert whole["query"] == "" and whole["rows"] > 0
    assert whole["kinds"] and isinstance(whole["kinds"][0], list)
    assert [b["bucket"] for b in whole["turn_lengths"]][0] == "0–10"
    assert whole["words"] and whole["words"][0]["n"] >= whole["words"][-1]["n"]
    assert all(w["word"] not in ("the", "and", "that") for w in whole["words"])  # stop words are out

    word = whole["words"][0]["word"]
    one = client.get(f"/api/search/overview?q={word}").json()
    assert one["query"] == word and 0 < one["rows"] <= whole["rows"]
    assert "near" in one and all(x["word"] != word for x in one["near"])
    assert client.get("/api/search/overview?q=zzqqxnothing").json()["rows"] == 0
