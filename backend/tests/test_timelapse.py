"""The timelapse source: a project's whole life in one read.

The film replays the board rather than storing frames, so the payload has
to carry the status a card was *born* with (the first status event's old
value), every later move, and the river of sessions on the same clock.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _mk(client: TestClient, title: str, **fields) -> str:
    r = client.post("/api/tasks", json={
        "created_date": "2608-14", "created_time": "15:32",
        "project": "ALPHA", "agent_id": "operator", "title": title,
        "status": "unclassified", **fields,
    })
    assert r.status_code in (200, 201), r.text
    return r.json()["metadata"]["id"]


def test_source_carries_birth_and_moves(client: TestClient) -> None:
    tid = _mk(client, "A card with a life", lane="Kanban Board")
    client.post(f"/api/tasks/{tid}/update", json={"status": "doing", "actor": "operator"})
    client.post(f"/api/tasks/{tid}/update", json={"status": "done", "actor": "operator"})

    r = client.get("/api/timelapse?project=ALPHA")
    assert r.status_code == 200, r.text
    body = r.json()

    card = next(c for c in body["cards"] if c["id"] == tid)
    assert card["born"] == "2026-08-14T15:32:00"
    assert card["lane"] == "Kanban Board"
    # Born unclassified even though the row now says done: the film needs the
    # status at the start, not the status at the end.
    assert card["status0"] == "unclassified"
    assert [m["status"] for m in card["moves"]] == ["doing", "done"]
    assert body["span"]["start"] <= card["born"] <= body["span"]["end"]


def test_marks_hold_the_agent_moments(client: TestClient) -> None:
    tid = _mk(client, "Reported on", status="doing", auto_manage="yes")
    client.post(f"/api/tasks/{tid}/report", json={
        "agent_id": "a1", "note": "did the thing",
    })
    body = client.get("/api/timelapse?project=ALPHA").json()
    kinds = {m["kind"] for m in body["marks"] if m["task_id"] == tid}
    assert "report" in kinds


def test_unknown_project_is_an_empty_film(client: TestClient) -> None:
    body = client.get("/api/timelapse?project=NOPE").json()
    assert body["cards"] == []
    assert body["span"] == {"start": "", "end": ""}


def test_stats_always_carry_turns_and_never_fail_on_git(client: TestClient) -> None:
    _mk(client, "Something to count")
    stats = client.get("/api/timelapse?project=ALPHA").json()["stats"]
    # Turns are always known; git is best effort — a fixture with no captured
    # cwd simply has no commit count, and the request still succeeds.
    assert "turns" in stats
    assert isinstance(stats["turns"], int)
    if "commits" in stats:
        assert stats["commits"] > 0


def test_git_detail_is_absent_without_a_repository(client: TestClient) -> None:
    _mk(client, "No repo behind this one")
    body = client.get("/api/timelapse?project=ALPHA").json()
    # Best effort throughout: a fixture has no captured cwd, so there is no
    # git block — and the film's default river needs none.
    assert body["git"] in ({}, None) or not body["git"].get("commits")


def test_area_and_graph_shape(client: TestClient) -> None:
    from backend.routers.timelapse import _area, _git_detail

    assert _area("frontend/src/App.tsx") == "frontend"
    assert _area("backend/tests/test_x.py") == "tests"      # before "backend"
    assert _area("backend/backend/db.py") == "backend"
    assert _area("docs/api.md") == "docs"
    assert _area("random.txt") == "other"

    log = [
        "C1\t2026-08-14T10:00:00",
        "10\t2\tfrontend/a.tsx",
        "5\t1\tfrontend/b.tsx",
        "C2\t2026-08-13T09:00:00",
        "40\t0\tfrontend/a.tsx",
        "3\t0\tbackend/backend/x.py",
    ]
    detail = _git_detail(log)
    assert [c["at"] for c in detail["commits"]] == [
        "2026-08-13T09:00:00", "2026-08-14T10:00:00",
    ]
    names = {n["path"]: n for n in detail["graph"]["nodes"]}
    # git log runs newest first, so the earliest stamp is the file's birth.
    assert names["frontend/a.tsx"]["born"] == "2026-08-13T09:00:00"
    assert names["frontend/a.tsx"]["churn"] == 52
    assert detail["areas"] == ["frontend", "backend"]
    assert len(detail["graph"]["edges"]) == 2


def test_a_project_with_no_repository_has_no_git_section(client: TestClient) -> None:
    """`{}` is a shape every reader has to remember to look inside; the film
    read `git.commits.length` on it and the whole page crashed."""
    _mk(client, "no repo here")
    body = client.get("/api/timelapse?project=ALPHA").json()
    assert body["git"] is None
    assert "commits" not in (body["stats"] or {})
