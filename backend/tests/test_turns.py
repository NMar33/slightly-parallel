"""Task documents — a description, then the rounds it was asked again.

The format lives in ``backend/turns.py``: ``## Description`` for turn 1,
``## Turn N · date time`` for every later round. The API speaks
``description`` and ``turns``; ``l2`` on a task is refused. Documents in
the old L2-with-markers shape are read the same way and migrated once.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app
from backend.turns import (
    Turn, append_turn, build_task_doc, heading, migrate_task_docs, parse_ref,
    parse_task_doc, render_turns, replace_turn, turn_ref,
)


# --------------------------------------------------------------------------
# the format
# --------------------------------------------------------------------------


def test_headings() -> None:
    assert heading(1, "", "") == "## Description"
    assert heading(2, "2608-29", "22:55") == "## Turn 2 · 2608-29 22:55"


def test_a_document_round_trips_through_render_and_parse() -> None:
    turns = [Turn(1, "", "", "write the release"), Turn(2, "2608-29", "22:55", "now the press release")]
    text = build_task_doc("---\nid: tk_1\n---", turns)
    assert text == (
        "---\nid: tk_1\n---\n\n## Description\n\nwrite the release\n\n"
        "## Turn 2 · 2608-29 22:55\n\nnow the press release\n"
    )
    assert parse_task_doc(text) == turns


def test_a_plain_or_empty_body_is_one_turn_or_none() -> None:
    assert parse_task_doc("---\nid: x\n---\n\n## Description\n\njust the one\n") == [Turn(1, "", "", "just the one")]
    assert parse_task_doc("---\nid: x\n---\n") == []
    assert render_turns([]) == ""


def test_the_legacy_l2_with_markers_shape_is_read_as_turns() -> None:
    legacy = (
        "---\nid: tk_1\n---\n\n## L2\nwrite the release\n\n"
        "--- turn 2 · 2608-29 22:55 ---\n\nnow the press release\n\n"
        "--- turn 3 · 2608-30 09:00 ---\n\nand the anecdote\n"
    )
    assert [(t.n, t.date, t.time, t.text) for t in parse_task_doc(legacy)] == [
        (1, "", "", "write the release"),
        (2, "2608-29", "22:55", "now the press release"),
        (3, "2608-30", "09:00", "and the anecdote"),
    ]
    assert parse_task_doc("---\nid: tk_1\n---\n\n## L2\nonly\n") == [Turn(1, "", "", "only")]


def test_append_and_replace() -> None:
    turns = append_turn([], "the first thing", "2608-30", "09:00")
    assert turns == [Turn(1, "", "", "the first thing")]
    turns = append_turn(turns, "second", "2608-29", "22:55")
    assert turns[-1] == Turn(2, "2608-29", "22:55", "second")
    assert replace_turn(turns, "SECOND")[-1].text == "SECOND"
    assert replace_turn(turns, "FIRST", 1)[0].text == "FIRST"
    assert replace_turn(turns, "FIRST", 1)[1].text == "second"
    assert replace_turn([], "born", 1) == [Turn(1, "", "", "born")]
    with pytest.raises(ValueError, match="no turn 7"):
        replace_turn(turns, "x", 7)
    with pytest.raises(ValueError):
        append_turn(turns, "   ", "2608-30", "09:00")
    many = list(turns)
    for i in range(3, 201):
        many = append_turn(many, f"t{i}", "2608-30", "09:00")
    with pytest.raises(ValueError, match="at most"):
        append_turn(many, "too many", "2608-30", "09:00")


def test_turn_one_keeps_the_bare_id() -> None:
    assert turn_ref("tk_28b1b490", 1) == "tk_28b1b490"
    assert turn_ref("tk_28b1b490", 2) == "tk_28b1b490.2"
    assert parse_ref("tk_28b1b490.2") == ("tk_28b1b490", 2)
    assert parse_ref("tk_28b1b490") == ("tk_28b1b490", 1)


def test_migration_rewrites_legacy_documents_once(tmp_path: Path) -> None:
    folder = tmp_path / "task_details"
    folder.mkdir()
    legacy = folder / "a.md"
    legacy.write_text(
        "---\nid: tk_1\ntitle: a\n---\n\n## L2\nfirst\n\n--- turn 2 · 2608-29 22:55 ---\n\nsecond\n",
        encoding="utf-8",
    )
    fresh = folder / "b.md"
    fresh.write_text("---\nid: tk_2\n---\n\n## Description\n\nkept\n", encoding="utf-8")
    assert migrate_task_docs(tmp_path) == 1
    text = legacy.read_text(encoding="utf-8")
    assert text.startswith("---\nid: tk_1\ntitle: a\n---\n\n## Description\n\nfirst\n\n## Turn 2 · 2608-29 22:55\n\nsecond")
    assert fresh.read_text(encoding="utf-8").endswith("kept\n")
    assert migrate_task_docs(tmp_path) == 0


def test_the_migration_keeps_every_section(tmp_path: Path) -> None:
    """An old document with L3 and L4 keeps their text; one with nothing to read is left alone."""
    folder = tmp_path / "task_details"
    folder.mkdir()
    full = folder / "a.md"
    full.write_text(
        "---\nid: tk_a\n---\nabove\n\n## L2\nwhy\n\n## L3\n- rejected: slow\n\n## L4\nthe long text\n",
        encoding="utf-8",
    )
    only_l3 = folder / "b.md"
    only_l3.write_text("---\nid: tk_b\n---\n## L3\nonly this\n", encoding="utf-8")
    bare = folder / "c.md"
    bare.write_text("---\nid: tk_c\n---\n## L2\n\n", encoding="utf-8")
    assert migrate_task_docs(tmp_path) == 2
    text = full.read_text(encoding="utf-8")
    for piece in ("above", "why", "rejected: slow", "the long text", "## Description"):
        assert piece in text
    assert "only this" in only_l3.read_text(encoding="utf-8")
    assert bare.read_text(encoding="utf-8") == "---\nid: tk_c\n---\n## L2\n\n"
    assert migrate_task_docs(tmp_path) == 0


# --------------------------------------------------------------------------
# the endpoints
# --------------------------------------------------------------------------


@pytest.fixture()
def client(tmp_path: Path):
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    app = create_app(data_root=root, watch=False)
    with TestClient(app) as c:
        yield c


def _task(client: TestClient, **over) -> str:
    body = {
        "created_date": "2608-29", "created_time": "10:00", "project": "alpha",
        "agent_id": "operator", "title": "Short press release", "status": "todo",
        "description": "write the features table",
    }
    body.update(over)
    r = client.post("/api/tasks", json=body)
    assert r.status_code == 201, r.text
    return r.json()["metadata"]["id"]


def test_create_speaks_description_and_refuses_l2(client: TestClient) -> None:
    r = client.post("/api/tasks", json={
        "created_date": "2608-29", "created_time": "10:00", "project": "alpha",
        "agent_id": "cc-a", "title": "x", "status": "todo", "l2": "old shape",
    })
    assert r.status_code == 422 and "description" in r.json()["detail"]
    tid = _task(client)
    detail = client.get(f"/api/tasks/{tid}").json()
    assert detail["description"] == "write the features table"
    assert [t["n"] for t in detail["turns"]] == [1] and detail["turns_n"] == 1
    assert "l2" not in detail
    # the document on disk is in the new shape
    md = client.get(f"/api/tasks/{tid}").json()["metadata"]["md_ref"]
    assert md.startswith("task_details/")


def test_adding_a_turn_appends_and_names_the_reference(client: TestClient) -> None:
    tid = _task(client)
    r = client.post(f"/api/tasks/{tid}/turn", json={"text": "now the press release", "created_date": "2608-29", "created_time": "22:55"})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["turn"] == 2 and out["ref"] == f"{tid}.2"
    assert [t["text"] for t in out["turns"]] == ["write the features table", "now the press release"]

    detail = client.get(f"/api/tasks/{tid}").json()
    assert detail["description"] == "write the features table"
    assert detail["turns"][1] == {"n": 2, "date": "2608-29", "time": "22:55", "text": "now the press release"}

    r = client.post(f"/api/tasks/{tid}/turn", json={"text": "and the anecdote"})
    assert r.json()["turn"] == 3 and r.json()["ref"] == f"{tid}.3"


def test_update_rewords_the_description_or_one_turn(client: TestClient) -> None:
    tid = _task(client)
    client.post(f"/api/tasks/{tid}/turn", json={"text": "second", "created_date": "2608-29", "created_time": "22:55"})
    r = client.post(f"/api/tasks/{tid}/update", json={"description": "FIRST", "actor": "operator"})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/tasks/{tid}/update", json={"turn": {"text": "SECOND"}, "actor": "operator"})
    assert r.status_code == 200, r.text
    detail = client.get(f"/api/tasks/{tid}").json()
    assert [t["text"] for t in detail["turns"]] == ["FIRST", "SECOND"]
    assert detail["turns"][1]["date"] == "2608-29"  # the stamp survives an edit

    old = client.post(f"/api/tasks/{tid}/update", json={"l2": "nope", "actor": "operator"})
    assert old.status_code == 422 and "description" in old.json()["detail"]
    ghost = client.post(f"/api/tasks/{tid}/update", json={"turn": {"n": 9, "text": "x"}, "actor": "operator"})
    assert ghost.status_code == 422


def test_a_task_born_without_text_can_still_grow_turns(client: TestClient) -> None:
    tid = _task(client, description="")
    assert client.get(f"/api/tasks/{tid}").json()["turns"] == []
    r = client.post(f"/api/tasks/{tid}/turn", json={"text": "the first thing"})
    assert r.status_code == 201 and r.json()["turn"] == 1 and r.json()["ref"] == tid


def test_list_with_desc_attaches_the_text_and_the_last_turn(client: TestClient) -> None:
    tid = _task(client)
    client.post(f"/api/tasks/{tid}/turn", json={"text": "second", "created_date": "2608-29", "created_time": "22:55"})
    rows = client.get("/api/tasks?project=alpha&with_desc=1").json()["tasks"]
    row = next(r for r in rows if r["id"] == tid)
    assert row["description"] == "write the features table"
    assert row["turns_n"] == 2 and row["turn_last"]["text"] == "second"
    plain = client.get("/api/tasks?project=alpha").json()["tasks"]
    assert "description" not in plain[0]


def test_the_turn_lands_in_the_task_history(client: TestClient) -> None:
    tid = _task(client)
    client.post(f"/api/tasks/{tid}/turn", json={"text": "round two", "actor": "operator"})
    events = client.get(f"/api/tasks/{tid}/events").json()["events"]
    assert any(e["field"] == "turn" and e["new_value"] == "2" for e in events)


def test_event_ids_are_unique_within_a_batch_and_duplicates_collapse_on_read(client: TestClient, tmp_path: Path) -> None:
    tid = _task(client)
    # one update, two changes with the same value → two rows, two ids
    r = client.post(f"/api/tasks/{tid}/update", json={"description": "A", "turn": {"text": "A"}, "actor": "operator"})
    assert r.status_code == 200, r.text
    events = client.get(f"/api/tasks/{tid}/events").json()["events"]
    ids = [e["event_id"] for e in events]
    assert len(ids) == len(set(ids))
    # a duplicated id already in the log is served once
    log = tmp_path / "data" / "task_events.csv"
    lines = log.read_text(encoding="utf-8").splitlines()
    log.write_text("\n".join(lines + [lines[-1]]) + "\n", encoding="utf-8")
    client.post(f"/api/tasks/{tid}/update", json={"title": "touch", "actor": "operator"})
    events = client.get(f"/api/tasks/{tid}/events").json()["events"]
    ids = [e["event_id"] for e in events]
    assert len(ids) == len(set(ids))
