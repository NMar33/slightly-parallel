"""#now the agent did not write: the server writes the card (nowlib.py)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.nowlib import title_of
from backend.server import create_app

AGENT = "cc-now00001"


def _at(minutes: int) -> str:
    return (datetime.now() + timedelta(minutes=minutes)).isoformat(timespec="seconds")


def _chat(root: Path, turns: list[tuple[str, str, str]]) -> None:
    """(when, the operator's message, the agent's answer — "" for none yet)."""
    d = root / "projects" / "alpha" / "chats" / AGENT
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps({
        "agent_id": AGENT, "agent_name": "lead", "project": "alpha",
        "created_date": "2609-01", "last_active": "2026-09-01T11:00:00",
    }), encoding="utf-8")
    body = [f"# Chat log — {AGENT}\n"]
    for i, (at, user, agent) in enumerate(turns, start=1):
        body.append(f"\n## Turn {i} · {at}\n**User**: {user}\n" + (f"**Agent**: {agent}\n" if agent else ""))
    (d / "chat.md").write_text("".join(body), encoding="utf-8")


@pytest.fixture()
def env(tmp_path: Path):
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    # Tags older than these moments are history; the tests' chats are newer.
    (root / "now.json").write_text('{"since": "2000-01-01T00:00:00"}', encoding="utf-8")
    (root / "done.json").write_text('{"since": "2000-01-01T00:00:00"}', encoding="utf-8")
    with TestClient(create_app(data_root=root, watch=False)) as c:
        yield c, root


def _cards(c: TestClient) -> list[dict]:
    c.app.state.store.rebuild()
    return c.get("/api/tasks?project=alpha").json()["tasks"]


def _text(c: TestClient, tid: str) -> str:
    return json.dumps(c.get(f"/api/tasks/{tid}").json())


def test_the_server_writes_the_card_the_agent_left_out(env) -> None:
    c, root = env
    msg = "#now build a small notes page in the folder notes (it exists, empty): add a note, list the notes"
    _chat(root, [(_at(-5), msg, "built and committed")])
    (card,) = _cards(c)
    assert card["status"] == "doing" and card["agent_id"] == AGENT and card["lane"] == "Now"
    assert card["title"].startswith("build a small notes page") and len(card["title"]) <= 80
    assert "(it exists, empty)" in _text(c, card["id"])            # the message whole, as its text
    events = c.get(f"/api/tasks/{card['id']}/events").json()
    assert any("the server did" in json.dumps(e) for e in events.get("events", events))
    assert len(_cards(c)) == 1                                     # once, on every later read


def test_a_turn_still_running_is_left_to_the_agent(env) -> None:
    c, root = env
    _chat(root, [(_at(-1), "#now build the export", "")])
    assert _cards(c) == []


def test_a_message_sent_while_the_agent_works_is_not_the_end_of_its_turn(env) -> None:
    c, root = env
    _chat(root, [(_at(-5), "#now build the export", ""), (_at(-1), "go on", "")])
    assert _cards(c) == []


def test_a_turn_cut_off_counts_once_a_later_one_is_answered(env) -> None:
    c, root = env
    _chat(root, [(_at(-5), "#now build the export", ""), (_at(-1), "go on", "done")])
    assert [x["title"] for x in _cards(c)] == ["build the export"]


def test_a_write_that_stopped_half_way_is_not_written_twice(env) -> None:
    c, root = env
    _chat(root, [(_at(-5), "#now build the export", "built")])
    (card,) = _cards(c)
    (root / "now.csv").unlink()                  # the card was written, its ledger row was not
    c.app.state.store.__dict__.pop("_adopted_on", None)
    assert [x["id"] for x in _cards(c)] == [card["id"]]
    events = c.get(f"/api/tasks/{card['id']}/events").json()
    assert json.dumps(events).count("the server did") == 1


def test_the_agent_wrote_it_so_the_server_does_not(env) -> None:
    c, root = env
    head = [(_at(-20), "#now build the export", "")]
    _chat(root, head)
    c.app.state.store.rebuild()
    c.post("/api/tasks", json={"created_date": "2609-01", "created_time": "10:00", "project": "alpha",
                               "agent_id": AGENT, "title": "Build the export", "tags": "ag_idea"})
    _chat(root, [(head[0][0], head[0][1], "done"), (_at(10), "thanks", "ok")])
    assert [x["title"] for x in _cards(c)] == ["Build the export"]


def test_a_tag_that_needs_no_card_is_looked_at_once(env, monkeypatch) -> None:
    """The agent wrote the card: later reads do not read its chat again to
    find that out (they did, on every captured turn)."""
    from backend import nowlib
    c, root = env
    head = [(_at(-20), "#now build the export", "")]
    _chat(root, head)
    c.app.state.store.rebuild()
    c.post("/api/tasks", json={"created_date": "2609-01", "created_time": "10:00", "project": "alpha",
                               "agent_id": AGENT, "title": "Build the export", "tags": "ag_idea"})
    _chat(root, [(head[0][0], head[0][1], "done")])
    c.app.state.store.rebuild()
    calls: list[set[str]] = []
    real = nowlib.card_turns
    monkeypatch.setattr(nowlib, "card_turns", lambda store, agents, *a, **k: calls.append(agents) or real(store, agents, *a, **k))
    assert nowlib.adopt(c.app.state.store) == [] and len(calls) == 1
    assert nowlib.adopt(c.app.state.store) == [] and len(calls) == 1


def test_a_done_already_applied_reads_no_chat_again(env, monkeypatch) -> None:
    from backend import donelib, nowlib
    c, root = env
    tid = c.post("/api/tasks", json={"created_date": "2609-01", "created_time": "09:00", "project": "alpha",
                                     "agent_id": "operator", "title": "Export", "status": "doing"}).json()["metadata"]["id"]
    _chat(root, [(_at(-20), f"{tid} build it", "ok"), (_at(-10), "#done", "closed")])
    c.app.state.store.rebuild()
    assert [r["result"] for r in donelib.adopt(c.app.state.store)] == ["moved"]
    calls: list[int] = []
    monkeypatch.setattr(nowlib, "card_turns", lambda *a, **k: calls.append(1) or [])
    assert donelib.adopt(c.app.state.store) == [] and calls == []


def test_todo_files_it_in_its_column_and_a_late_write_is_pointed_at_it(env) -> None:
    c, root = env
    _chat(root, [(_at(-5), "#now-todo look at the import later", "noted"), (_at(-1), "and?", "")])
    (card,) = _cards(c)
    assert card["status"] == "todo" and card["title"] == "look at the import later"
    r = c.post("/api/tasks", json={"created_date": "2609-01", "created_time": "10:01", "project": "alpha",
                                   "agent_id": AGENT, "title": "Import", "status": "todo", "tags": "ag_idea"})
    assert r.status_code >= 400 and card["id"] in r.text and "task_update" in r.text


def test_a_lane_the_board_lacks_is_left_to_the_agent(env) -> None:
    c, root = env
    _chat(root, [(_at(-5), "#now {nowhere} build it", "which lane?")])
    assert _cards(c) == []


def test_done_closes_the_card_the_server_wrote(env) -> None:
    c, root = env
    _chat(root, [(_at(-10), "#now build the export", "built"), (_at(-5), "#done", "")])
    got = c.get(f"/api/done-tags?agent_id={AGENT}").json()
    assert [t["result"] for t in got["tasks"]] == ["moved"]
    assert _cards(c)[0]["status"] == "done"


def test_tags_from_before_the_feature_are_history(env) -> None:
    c, root = env
    (root / "now.json").write_text('{"since": "2030-01-01T00:00:00"}', encoding="utf-8")
    _chat(root, [(_at(-5), "#now build the export", "built")])
    assert _cards(c) == []


@pytest.mark.parametrize("message,title", [
    ("#now fix it", "fix it"),
    ("please #NOW {ui}  fix   the\nbutton", "please fix the button"),
    ("#now", "Task from this chat"),
    ("#now " + "word " * 30, ("word " * 16).strip() + "…"),
    # The operator's own words, not the paste; the paste when there are none.
    ('look at this <pasted_content id="5a">the #now card idea</pasted_content> and fix it',
     "look at this and fix it"),
    ('#now-todo <pasted_content id="5a">Nested reply: plan the refactor</pasted_content>',
     "Nested reply: plan the refactor"),
    ("###now-todo keep only this #skill", "keep only this"),
])
def test_the_title(message, title) -> None:
    assert title_of(message) == title


def test_a_message_that_names_a_task_on_the_board_is_about_that_task(env) -> None:
    c, root = env
    tid = c.post("/api/tasks", json={"created_date": "2609-01", "created_time": "09:00", "project": "alpha",
                                     "agent_id": "operator", "title": "Prompts axis", "status": "todo"}).json()["metadata"]["id"]
    _chat(root, [(_at(-5), f"{tid} · Prompts axis\n#now-todo the axis misleads. let's discuss it", "discussed")])
    assert [x["id"] for x in _cards(c)] == [tid]


def test_the_since_stamp_is_kept_and_a_failed_write_applies_nothing(tmp_path: Path, monkeypatch) -> None:
    from backend import nowlib
    path = tmp_path / "now.json"
    first = nowlib.since_stamp(path, "#now")
    assert first and json.loads(path.read_text(encoding="utf-8")) == {"since": first}
    assert nowlib.since_stamp(path, "#now") == first           # kept, not "now" again
    path.write_text('{"since": "not a time"}', encoding="utf-8")
    assert nowlib.since_stamp(path, "#now") not in (None, "not a time")
    path.unlink()

    def refuse(*_a, **_k):
        raise OSError("read-only")
    monkeypatch.setattr(nowlib, "atomic_write_json", refuse)
    # Unkept, the moment would be "now" on every call and pass every tag by.
    assert nowlib.since_stamp(path, "#now") is None
