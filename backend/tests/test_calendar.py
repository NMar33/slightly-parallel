"""The calendar: one range read with facts per day, the operator's entries,
and milestones with the tasks that feed them."""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    r = tmp_path / "data"
    (r / "projects" / "alpha").mkdir(parents=True)
    return r


@pytest.fixture()
def client(root: Path):
    app = create_app(data_root=root, watch=False)
    with TestClient(app) as c:
        yield c


def _task(client: TestClient, title: str, status: str = "doing", **over) -> str:
    r = client.post("/api/tasks", json={
        "created_date": "2609-08", "created_time": "12:00", "project": "alpha",
        "agent_id": "operator", "title": title, "status": status, "description": "x", **over,
    })
    assert r.status_code == 201, r.text
    return r.json()["metadata"]["id"]


def test_range_read_normalises_dates_and_counts_days(client: TestClient) -> None:
    a = _task(client, "Ship the month view", due_date="2026-09-20")
    b = _task(client, "Old one", status="todo")
    r = client.post(f"/api/tasks/{b}/update", json={"status": "done", "actor": "operator"})
    assert r.status_code == 200, r.text
    # The task is done today: the range reaches today, whenever the test runs.
    to = max("2026-09-30", time.strftime("%Y-%m-%d"))
    r = client.get("/api/calendar", params={"project": "alpha", "from": "2026-09-01", "to": to})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["from"] == "2026-09-01" and d["to"] == to
    by = {t["id"]: t for t in d["tasks"]}
    assert by[a]["created"] == "2026-09-08" and by[a]["due"] == "2026-09-20" and by[a]["done"] == ""
    assert by[b]["status"] == "done" and by[b]["done"] == by[b]["done"][:10] and len(by[b]["done"]) == 10
    assert d["days"]["2026-09-08"]["tasks_created"] == 2
    assert d["days"][by[b]["done"]]["tasks_done"] == 1
    assert d["entries"] == [] and d["milestones"] == [] and d["sprints"] == []


def test_read_swaps_a_backwards_range_and_defaults_it(client: TestClient) -> None:
    r = client.get("/api/calendar", params={"project": "alpha", "from": "2026-09-30", "to": "2026-09-01"})
    assert r.json()["from"] == "2026-09-01"
    # "everything": a span wider than the session ledger's YYMM-DD years
    r = client.get("/api/calendar", params={"project": "alpha", "from": "1990-01-01", "to": "2100-01-01"})
    assert r.status_code == 200, r.text
    r = client.get("/api/calendar", params={"project": "alpha"})
    assert r.status_code == 200 and r.json()["from"] < r.json()["today"] < r.json()["to"]


def test_entries_live_on_the_axis(client: TestClient) -> None:
    r = client.post("/api/calendar/entries", json={
        "project": "alpha", "kind": "meeting", "date": "2026-09-12", "time": "14:00",
        "title": "Call with Anna", "people": "Anna",
    })
    assert r.status_code == 201, r.text
    e = r.json()["entry"]
    assert e["id"].startswith("ce_") and e["status"] == "open" and e["source"] == "calendar"
    # bad input is named, never swallowed
    assert client.post("/api/calendar/entries", json={"project": "alpha", "kind": "party", "date": "2026-09-12", "title": "x"}).status_code == 422
    assert client.post("/api/calendar/entries", json={"project": "alpha", "kind": "note", "date": "12.09.2026", "title": "x"}).status_code == 422
    assert client.post("/api/calendar/entries", json={"project": "alpha", "kind": "note", "date": "2026-09-12", "time": "2pm", "title": "x"}).status_code == 422
    assert client.post("/api/calendar/entries", json={"project": "alpha", "kind": "note", "date": "2026-09-12", "end_date": "2026-09-11", "title": "x"}).status_code == 422
    assert client.post("/api/calendar/entries", json={"project": "alpha", "kind": "note", "date": "2026-09-12", "title": ""}).status_code == 422
    # in range, out of range
    d = client.get("/api/calendar", params={"project": "alpha", "from": "2026-09-01", "to": "2026-09-30"}).json()
    assert [x["title"] for x in d["entries"]] == ["Call with Anna"]
    assert d["days"]["2026-09-12"]["entries"] == 1
    d = client.get("/api/calendar", params={"project": "alpha", "from": "2026-10-01", "to": "2026-10-30"}).json()
    assert d["entries"] == []
    # update, then delete
    r = client.post(f"/api/calendar/entries/{e['id']}/update", json={"status": "done", "date": "2026-09-13"})
    assert r.status_code == 200 and r.json()["entry"]["status"] == "done" and r.json()["entry"]["date"] == "2026-09-13"
    assert r.json()["entry"]["title"] == "Call with Anna"
    assert client.post(f"/api/calendar/entries/{e['id']}/update", json={"status": "gone"}).status_code == 422
    assert client.post("/api/calendar/entries/ce_nope/update", json={"title": "x"}).status_code == 404
    assert client.post(f"/api/calendar/entries/{e['id']}/delete").status_code == 200
    assert client.get("/api/calendar/entries", params={"project": "alpha", "from": "2026-09-01", "to": "2026-09-30"}).json()["entries"] == []


def test_a_span_entry_shows_on_every_day_it_touches(client: TestClient) -> None:
    client.post("/api/calendar/entries", json={"project": "alpha", "kind": "event", "date": "2026-09-28", "end_date": "2026-10-02", "title": "Conference"})
    d = client.get("/api/calendar", params={"project": "alpha", "from": "2026-10-01", "to": "2026-10-31"}).json()
    assert [x["title"] for x in d["entries"]] == ["Conference"]


def test_milestones_hold_tasks_and_count_them(client: TestClient) -> None:
    a = _task(client, "MVP usable by a stranger")
    b = _task(client, "Write the article", status="done")
    r = client.post("/api/milestones", json={
        "project": "alpha", "title": "Article out", "outcome": "A stranger reads why it exists",
        "check": "the article is published", "target_date": "2026-10-01", "tasks": [a, b],
    })
    assert r.status_code == 201, r.text
    m = r.json()["milestone"]
    assert m["id"].startswith("ms_") and m["status"] == "planned" and m["position"] == 1
    assert sorted(m["tasks"]) == sorted([a, b]) and m["tasks_n"] == 2 and m["done_n"] == 1
    # a task serves one milestone: the second takes it from the first
    r2 = client.post("/api/milestones", json={"project": "alpha", "title": "30 stars", "tasks": [a]})
    assert r2.json()["milestone"]["position"] == 2
    ms = {x["id"]: x for x in client.get("/api/milestones", params={"project": "alpha"}).json()["milestones"]}
    assert ms[m["id"]]["tasks"] == [b] and ms[r2.json()["milestone"]["id"]]["tasks"] == [a]
    # the calendar read carries the link on the task
    d = client.get("/api/calendar", params={"project": "alpha"}).json()
    assert {t["id"]: t["milestone_id"] for t in d["tasks"]}[b] == m["id"]
    # reached stamps a date; leaving reached clears it
    r = client.post(f"/api/milestones/{m['id']}/update", json={"status": "reached"})
    assert r.status_code == 200 and len(r.json()["milestone"]["reached_date"]) == 10
    r = client.post(f"/api/milestones/{m['id']}/update", json={"status": "active"})
    assert r.json()["milestone"]["reached_date"] == ""
    assert client.post(f"/api/milestones/{m['id']}/update", json={"status": "won"}).status_code == 422
    # add / remove tasks; unknown task is named
    r = client.post(f"/api/milestones/{m['id']}/tasks", json={"add": [a], "remove": [b]})
    assert r.status_code == 200 and r.json()["milestone"]["tasks"] == [a]
    assert client.post(f"/api/milestones/{m['id']}/tasks", json={"add": ["tk_nope"]}).status_code == 422
    # delete drops the links too
    assert client.post(f"/api/milestones/{m['id']}/delete").status_code == 200
    d = client.get("/api/calendar", params={"project": "alpha"}).json()
    assert {t["id"]: t["milestone_id"] for t in d["tasks"]}[a] == ""
    assert client.post("/api/milestones/ms_nope/update", json={"title": "x"}).status_code == 404


def test_scope_is_one_project_a_board_or_all(client: TestClient, root: Path) -> None:
    (root / "projects" / "beta").mkdir(parents=True)
    a = _task(client, "Alpha work")
    r = client.post("/api/tasks", json={
        "created_date": "2609-08", "created_time": "12:00", "project": "beta",
        "agent_id": "operator", "title": "Beta work", "status": "doing", "description": "x",
    })
    b = r.json()["metadata"]["id"]
    client.post("/api/calendar/entries", json={"project": "beta", "kind": "note", "date": "2026-09-12", "title": "beta note"})
    one = client.get("/api/calendar", params={"project": "alpha", "from": "2026-09-01", "to": "2026-09-30"}).json()
    assert [t["id"] for t in one["tasks"]] == [a] and one["projects"] == ["alpha"] and one["entries"] == []
    both = client.get("/api/calendar", params={"project": "alpha,beta", "from": "2026-09-01", "to": "2026-09-30"}).json()
    assert sorted(t["id"] for t in both["tasks"]) == sorted([a, b]) and both["projects"] == ["alpha", "beta"]
    assert {t["id"]: t["project"] for t in both["tasks"]}[b] == "beta"
    assert both["days"]["2026-09-08"]["tasks_created"] == 2 and [e["title"] for e in both["entries"]] == ["beta note"]
    every = client.get("/api/calendar", params={"project": "all", "from": "2026-09-01", "to": "2026-09-30"}).json()
    assert every["projects"] == ["alpha", "beta"] and len(every["tasks"]) == 2
    assert client.get("/api/milestones", params={"project": "all"}).status_code == 200


def test_reason_and_proof(client: TestClient) -> None:
    assert client.get("/api/projects/alpha/reason").json() == {"project": "alpha", "kind": "", "text": "", "updated_at": ""}
    r = client.post("/api/projects/alpha/reason", json={"kind": "attention", "text": "an open-source tool people find"})
    assert r.status_code == 200 and r.json()["kind"] == "attention"
    assert client.get("/api/projects/alpha/reason").json()["text"] == "an open-source tool people find"
    assert client.post("/api/projects/alpha/reason", json={"kind": "fame"}).status_code == 422
    m = client.post("/api/milestones", json={"project": "alpha", "title": "Article out"}).json()["milestone"]
    r = client.post(f"/api/milestones/{m['id']}/update", json={"status": "reached", "proof": "https://example.org/post"})
    assert r.status_code == 200 and r.json()["milestone"]["proof"] == "https://example.org/post" and len(r.json()["milestone"]["reached_date"]) == 10


def test_a_ledger_written_before_a_column_existed_still_reads(client: TestClient, root: Path) -> None:
    # A milestones.csv from before `proof` was a column.
    (root / "milestones.csv").write_text(
        "id,project,title,outcome,check,target_date,reached_date,status,position,created_at,updated_at,actor\n"
        "ms_old00001,alpha,Older row,,,2026-09-15,,planned,1,2026-09-10T13:11:24,2026-09-10T13:11:24,operator\n",
        encoding="utf-8",
    )
    r = client.post("/api/calendar/entries", json={"project": "alpha", "kind": "note", "date": "2026-09-12", "title": "poke"})
    assert r.status_code == 201  # the rebuild after a write registers the views again
    ms = client.get("/api/milestones", params={"project": "alpha"}).json()["milestones"]
    assert [m["id"] for m in ms] == ["ms_old00001"] and ms[0]["proof"] == ""
    r = client.post("/api/milestones/ms_old00001/update", json={"proof": "now it has one"})
    assert r.status_code == 200 and r.json()["milestone"]["proof"] == "now it has one"
    assert "proof" in (root / "milestones.csv").read_text(encoding="utf-8").splitlines()[0]


def test_a_code_is_matched_whole_and_rows_need_a_real_code(client: TestClient, root: Path) -> None:
    (root / "projects" / "seo").mkdir(parents=True)
    (root / "projects" / "seo-fight").mkdir(parents=True)
    for code, title in (("seo", "short"), ("seo-fight", "long")):
        r = client.post("/api/tasks", json={
            "created_date": "2609-08", "created_time": "12:00", "project": code,
            "agent_id": "operator", "title": title, "status": "doing", "description": "x",
        })
        assert r.status_code == 201
    one = client.get("/api/calendar", params={"project": "seo", "from": "2026-09-01", "to": "2026-09-30"}).json()
    assert [t["title"] for t in one["tasks"]] == ["short"]
    assert client.get("/api/calendar", params={"project": "%", "from": "2026-09-01", "to": "2026-09-30"}).json()["tasks"] == []
    for bad in ("all", "alpha,seo", "%", ""):
        assert client.post("/api/calendar/entries", json={"project": bad, "kind": "note", "date": "2026-09-12", "title": "x"}).status_code == 422, bad
        assert client.post("/api/milestones", json={"project": bad, "title": "x"}).status_code == 422, bad
    assert client.post("/api/calendar/entries", json={"project": "alpha", "kind": "meeting", "date": "2026-09-12", "time": "15:00", "end_time": "14:00", "title": "x"}).status_code == 422
    assert client.post("/api/calendar/entries", json={"project": "alpha", "kind": "meeting", "date": "2026-09-12", "end_date": "2026-09-13", "time": "15:00", "end_time": "09:00", "title": "overnight"}).status_code == 201
    assert client.post("/api/milestones", json={"project": "alpha", "title": "x", "position": -5}).status_code == 422
    assert client.post("/api/calendar/entries/nope/delete").status_code == 404


def test_a_task_born_done_has_a_done_day_and_merged_entries_keep_time_order(client: TestClient, root: Path) -> None:
    (root / "projects" / "beta").mkdir(parents=True)
    r = client.post("/api/tasks", json={
        "created_date": "2609-03", "created_time": "12:00", "project": "alpha",
        "agent_id": "operator", "title": "Born done", "status": "done", "description": "x",
    })
    assert r.status_code == 201
    d = client.get("/api/calendar", params={"project": "alpha", "from": "2026-09-01", "to": "2026-09-30"}).json()
    assert d["tasks"][0]["done"] == "2026-09-03" and d["days"]["2026-09-03"]["tasks_done"] == 1
    client.post("/api/calendar/entries", json={"project": "beta", "kind": "note", "date": "2026-09-20", "title": "late"})
    client.post("/api/calendar/entries", json={"project": "alpha", "kind": "note", "date": "2026-09-10", "title": "early"})
    client.post("/api/calendar/entries", json={"project": "alpha", "kind": "note", "date": "2026-09-25", "title": "later"})
    both = client.get("/api/calendar", params={"project": "beta,alpha", "from": "2026-09-01", "to": "2026-09-30"}).json()
    assert [e["title"] for e in both["entries"]] == ["early", "late", "later"]


def test_links_move_in_one_pass(client: TestClient) -> None:
    a = _task(client, "one")
    b = _task(client, "two")
    m1 = client.post("/api/milestones", json={"project": "alpha", "title": "first", "tasks": [a, b]}).json()["milestone"]
    m2 = client.post("/api/milestones", json={"project": "alpha", "title": "second", "tasks": [a]}).json()["milestone"]
    ms = {m["id"]: m for m in client.get("/api/milestones", params={"project": "alpha"}).json()["milestones"]}
    assert ms[m1["id"]]["tasks"] == [b] and ms[m2["id"]]["tasks"] == [a]
    r = client.post(f"/api/milestones/{m2['id']}/tasks", json={"add": [b, a]})
    assert sorted(r.json()["milestone"]["tasks"]) == sorted([a, b])
    assert client.get("/api/milestones", params={"project": "alpha"}).json()["milestones"][0]["tasks"] == []
