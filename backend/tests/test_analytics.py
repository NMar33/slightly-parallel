"""Analytics: the tables load, queries read them, and nothing else gets through."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app


@pytest.fixture()
def c(tmp_path: Path):
    root = tmp_path / "data"
    d = root / "projects" / "alpha" / "chats" / "cc-an000001"
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"agent_id": "cc-an000001", "agent_name": "lead", "project": "alpha",
                                             "created_date": "2609-01", "last_active": "2026-09-01T11:00:00"}))
    (d / "chat.md").write_text(
        "# Chat log\n\n## Turn 1 · 2026-09-01T10:01:00\n**User**: hello tk_abc12345 #vision\n**Agent**: one two three\n"
        "\n## Turn 2 · 2026-09-01T10:05:00\n**User**: <pasted_content id=\"1\">a b c d</pasted_content> ok\n**Agent**: fine\n",
        encoding="utf-8")
    with TestClient(create_app(data_root=root, watch=False)) as client:
        yield client


def test_the_tables_and_a_query(c) -> None:
    schema = c.get("/api/analytics/schema").json()
    rows = {t["name"]: t["rows"] for t in schema["tables"]}
    assert rows["messages"] == 2 and rows["chats"] == 1
    r = c.post("/api/analytics/query", json={"sql": "SELECT turn, words, pasted_words, answer_words, commands, tasks, agent_name FROM messages ORDER BY turn"}).json()
    assert r["rows"] == [[1, 3, 0, 3, "vision", "tk_abc12345", "lead"], [2, 1, 4, 1, "", "", "lead"]]
    assert len(schema["safety"]) >= 4
    for ex in schema["examples"]:
        assert c.post("/api/analytics/query", json={"sql": ex["sql"]}).status_code == 200, ex["title"]


@pytest.mark.parametrize("sql,why", [
    ("SELECT * FROM read_csv('/etc/passwd')", "disabled"), ("DELETE FROM tasks", "Only reading"),
    ("SELECT 1; SELECT 2", "One query"), ("", "Write a query"), ("SELECT nope FROM tasks", "nope"),
    ("WITH gone AS (DELETE FROM tasks RETURNING *) SELECT * FROM gone", "SELECT"),
    ("COPY tasks TO 'x.csv'", "Only reading"), ("ATTACH 'x.db'", "Only reading"),
    ("SELECT 1 -- ; DROP TABLE tasks", "1") ,
    ("SELECT * FROM read_text('/etc/hostname')", "disabled"),
])
def test_what_is_refused(c, sql, why) -> None:
    r = c.post("/api/analytics/query", json={"sql": sql})
    if sql.startswith("SELECT 1 --"):
        assert r.status_code == 200          # a comment is only a comment
    else:
        assert r.status_code == 422 and why in r.json()["detail"]
    # Whatever was tried, the tables hold what they held.
    counts = {t["name"]: t["rows"] for t in c.get("/api/analytics/schema").json()["tables"]}
    assert counts["messages"] == 2 and counts["chats"] == 1


def test_queries_side_by_side(c) -> None:
    """Many queries at once — the previews do this — each gets its own answer."""
    import concurrent.futures as cf
    sqls = ["SELECT count(*) FROM messages", "SELECT count(*) FROM chats", "SELECT max(turn) FROM messages"] * 15
    with cf.ThreadPoolExecutor(8) as ex:
        got = list(ex.map(lambda q: c.post("/api/analytics/query", json={"sql": q}), sqls))
    assert all(r.status_code == 200 for r in got)
    assert {tuple(r.json()["rows"][0]) for r in got} == {(2,), (1,), (2,)}


def test_a_comment_first_and_the_from_first_form_are_readings(c) -> None:
    assert c.post("/api/analytics/query", json={"sql": "-- per task\nSELECT count(*) FROM tasks"}).status_code == 200
    assert c.post("/api/analytics/query", json={"sql": "FROM tasks SELECT count(*)"}).status_code == 200


def test_a_huge_answer_is_refused_not_carried(c) -> None:
    r = c.post("/api/analytics/query", json={"sql": "SELECT repeat('x', 200000) FROM range(500)"})
    assert r.status_code == 422 and "MB of text" in r.json()["detail"]


def test_nothing_spills_to_disk(c) -> None:
    r = c.post("/api/analytics/query", json={"sql": "SELECT current_setting('temp_directory') AS t, current_setting('max_temp_directory_size') AS m"})
    assert r.status_code == 200
    t, m = r.json()["rows"][0]
    assert t == "" and m.startswith("0")
