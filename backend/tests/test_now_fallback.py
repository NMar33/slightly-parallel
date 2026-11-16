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
    # Claude Code closes the paste with the id too; the wrapper stayed in the title (2611-04).
    ('#now-todo {SP} list of ideas, wide (\n\n<pasted_content id="15fc">\nidea one\nidea two\n</pasted_content id="15fc">\n\n)',
     "list of ideas, wide ( )"),
])
def test_the_title(message, title) -> None:
    assert title_of(message) == title


def test_a_message_that_names_a_task_on_the_board_is_about_that_task(env) -> None:
    c, root = env
    tid = c.post("/api/tasks", json={"created_date": "2609-01", "created_time": "09:00", "project": "alpha",
                                     "agent_id": "operator", "title": "Prompts axis", "status": "todo"}).json()["metadata"]["id"]
    _chat(root, [(_at(-5), f"{tid} · Prompts axis\n#now-todo the axis misleads. let's discuss it", "discussed")])
    assert [x["id"] for x in _cards(c)] == [tid]


def test_a_message_over_the_text_limit_is_kept_whole_on_its_card(env) -> None:
    """A #now with a long paste (a 91 000-character message, 2611-04) made
    the card's text over the limit; the refusal came out of every task list
    and of #done as 422 until the chat was gone. Nothing is cut: the
    operator's message is the card's text, and the card's history says it
    is long. The card is still edited and commented on, only not made longer."""
    from backend.tasklib import DESCRIPTION_MAX
    c, root = env
    paste = "<pasted_content id=\"ab\">\n" + ("a line of the paste\n" * (DESCRIPTION_MAX // 10)) + "</pasted_content id=\"ab\">"
    msg = f"#now-todo list of ideas, wide, to review (\n\n{paste}\n\n)"
    _chat(root, [(_at(-5), msg, "filed")])
    (card,) = _cards(c)
    assert card["status"] == "todo" and card["title"] == "list of ideas, wide, to review ( )"
    text = c.get(f"/api/tasks/{card['id']}").json()["description"]
    assert text == msg                                              # whole, nothing cut
    events = json.dumps(c.get(f"/api/tasks/{card['id']}/events").json())
    assert "kept whole" in events and "over the board's usual" in events
    assert c.get("/api/tasks?project=alpha").status_code == 200
    op = {"agent_id": "operator"}
    assert c.post(f"/api/tasks/{card['id']}/update", json={**op, "comment": "read it"}).status_code == 200
    assert c.post(f"/api/tasks/{card['id']}/update", json={**op, "description": text[:-1]}).status_code == 200
    # The operator's words are never cut: they may add to their own card;
    # an agent edits an over-limit card, it does not make it longer.
    assert c.post(f"/api/tasks/{card['id']}/update", json={**op, "description": text + "\nand one more line"}).status_code == 200
    r = c.post(f"/api/tasks/{card['id']}/update", json={"agent_id": AGENT, "description": text + "x" * 100})
    assert r.status_code == 422                                        # the #now text is the operator's
    r = c.post(f"/api/tasks/{card['id']}/update", json={"agent_id": AGENT, "comment": "z" * 20_001})
    assert r.status_code == 422 and "a comment is at most" in r.json()["detail"]
    # A card under the limit is not pushed over it by a comment or an edit.
    small = c.post("/api/tasks", json={"created_date": "2609-01", "created_time": "09:00", "project": "alpha",
                                       **op, "title": "Small", "status": "todo", "description": "x" * (DESCRIPTION_MAX - 5)}).json()["metadata"]["id"]
    assert c.post(f"/api/tasks/{small}/update", json={**op, "comment": "y" * 20}).status_code == 422
    assert c.post(f"/api/tasks/{small}/update", json={**op, "description": "y" * (DESCRIPTION_MAX + 1)}).status_code == 422


def test_an_agents_now_card_for_a_long_message_is_not_refused(env) -> None:
    """The gate puts the operator's message in as the text; the agent sent
    none, so the limit on text written onto the board is not its concern."""
    from backend.tasklib import DESCRIPTION_MAX
    c, root = env
    _chat(root, [(_at(-5), "#now fix the login\n\n" + "x" * (DESCRIPTION_MAX + 10), "")])
    c.app.state.store.rebuild()
    r = c.post("/api/tasks", json={"created_date": "2609-01", "created_time": "10:00", "project": "alpha",
                                   "agent_id": AGENT, "title": "Fix the login", "tags": "ag_bug"})
    assert r.status_code == 201, r.text
    assert len(c.get(f"/api/tasks/{r.json()['metadata']['id']}").json()["description"]) > DESCRIPTION_MAX


def test_an_unchanged_text_sent_with_a_save_leaves_no_edit_in_the_history(env) -> None:
    c, root = env
    op = {"agent_id": "operator"}
    tid = c.post("/api/tasks", json={"created_date": "2609-01", "created_time": "09:00", "project": "alpha",
                                     **op, "title": "Same", "status": "todo", "description": "the text"}).json()["metadata"]["id"]
    assert c.post(f"/api/tasks/{tid}/update", json={**op, "priority": "high", "description": "the text"}).status_code == 200
    events = json.dumps(c.get(f"/api/tasks/{tid}/events").json())
    assert "(updated)" not in events
    assert c.post(f"/api/tasks/{tid}/update", json={**op, "description": "the text, changed"}).status_code == 200
    assert "(updated)" in json.dumps(c.get(f"/api/tasks/{tid}/events").json())


def test_a_task_file_that_cannot_be_read_is_not_written_over(env) -> None:
    """A BOM from a Windows editor reads fine; a file that does not start
    with its frontmatter, or cannot be decoded, refuses the edit instead of
    becoming the new text alone (the rounds in it would be gone)."""
    c, root = env
    op = {"agent_id": "operator"}
    tid = c.post("/api/tasks", json={"created_date": "2609-01", "created_time": "09:00", "project": "alpha",
                                     **op, "title": "Rounds", "status": "todo", "description": "round one"}).json()["metadata"]["id"]
    md = root / c.get(f"/api/tasks/{tid}").json()["metadata"]["md_ref"]
    md.write_bytes(b"\xef\xbb\xbf" + md.read_bytes())
    assert c.post(f"/api/tasks/{tid}/update", json={**op, "comment": "hi"}).status_code == 200
    text = c.get(f"/api/tasks/{tid}").json()["description"]
    assert "round one" in text and "hi" in text
    md.write_text("not a task document\n", encoding="utf-8")
    r = c.post(f"/api/tasks/{tid}/update", json={**op, "comment": "again"})
    assert r.status_code == 422 and "frontmatter" in r.json()["detail"]
    assert md.read_text(encoding="utf-8") == "not a task document\n"
    assert c.get(f"/api/tasks/{tid}").status_code == 200                # shown, without its text
    md.write_bytes(b"\xff\xfe\x00 broken")
    assert c.post(f"/api/tasks/{tid}/update", json={**op, "description": "new"}).status_code == 422
    assert c.get(f"/api/tasks/{tid}").status_code == 200


def test_a_write_that_failed_is_tried_again_and_the_done_after_it_applies(env, monkeypatch) -> None:
    """A lock held or a disk full is not a refusal: the card arrives on the
    next change, and the #done typed after it still closes it. Settling it
    on the first failure wrote a permanent 'unnamed' row instead."""
    from backend import nowlib
    c, root = env
    real = nowlib._write_card
    failing = {"on": True}

    def flaky(store, tag):
        if failing["on"]:
            raise OSError("disk is busy")
        return real(store, tag)
    monkeypatch.setattr(nowlib, "_write_card", flaky)
    _chat(root, [(_at(-20), "#now build the export", "built"), (_at(-10), "#done", "")])
    assert _cards(c) == []
    failing["on"] = False
    _chat(root, [(_at(-20), "#now build the export", "built"), (_at(-10), "#done", "closed")])
    (card,) = _cards(c)
    assert card["status"] == "done", card


def test_an_agents_card_the_operator_deleted_does_not_come_back_after_a_restart(env) -> None:
    from backend import nowlib
    from backend.routers import deps
    c, root = env
    head = [(_at(-20), "#now build the export", "")]
    _chat(root, head)
    c.app.state.store.rebuild()
    tid = c.post("/api/tasks", json={"created_date": "2609-01", "created_time": "10:00", "project": "alpha",
                                     "agent_id": AGENT, "title": "Build the export", "tags": "ag_idea"}).json()["metadata"]["id"]
    _chat(root, [(head[0][0], head[0][1], "done")])
    assert [x["id"] for x in _cards(c)] == [tid]
    assert c.post(f"/api/tasks/{tid}/delete", json={"agent_id": "operator"}).status_code == 200
    assert _cards(c) == []
    # A restart forgets what was settled in memory; the file remembers it.
    nowlib._settled.clear()
    c.app.state.store.__dict__.pop("_adopted_on", None)
    assert _cards(c) == []
    assert (root / nowlib.SETTLED).exists()
    assert deps  # the module stays imported for the restart line above


def test_a_failing_adoption_runs_once_per_change_of_the_data(env, monkeypatch) -> None:
    from backend import nowlib
    c, root = env
    _chat(root, [(_at(-5), "#now build the export", "built")])
    calls: list[int] = []

    def boom(store):
        calls.append(1)
        raise RuntimeError("a bug in the adoption")
    monkeypatch.setattr(nowlib, "adopt", boom)
    c.app.state.store.rebuild()
    for _ in range(3):
        assert c.get("/api/tasks?project=alpha").status_code == 200
    assert len(calls) == 1


def test_a_damaged_turn_cell_does_not_take_the_readers_down(env) -> None:
    c, root = env
    _chat(root, [(_at(-20), "#now build the export", "built"), (_at(-10), "#done", "closed")])
    (card,) = _cards(c)
    assert card["status"] == "done"
    for name in ("now.csv", "done.csv"):
        p = root / name
        lines = p.read_text(encoding="utf-8").splitlines()
        header = lines[0].split(",")
        cells = lines[1].split(",")
        cells[header.index("turn")] = "x"
        p.write_text("\n".join([lines[0], ",".join(cells)]) + "\n", encoding="utf-8")
    assert c.get(f"/api/done-tags?agent_id={AGENT}").status_code == 200
    assert c.get(f"/api/tasks/{card['id']}/done").status_code == 200
    assert c.get(f"/api/tasks/{card['id']}/mentions?full=1").status_code == 200
    assert c.get(f"/api/tasks/{card['id']}/work").status_code == 200


def test_done_tags_needs_the_chat_and_answers_when_an_adoption_fails(env, monkeypatch) -> None:
    from backend import donelib
    c, root = env
    assert c.get("/api/done-tags").status_code == 422
    assert c.get("/api/done-tags?agent_id=").status_code == 422
    _chat(root, [(_at(-20), "#now build the export", "built"), (_at(-10), "#done", "closed")])
    assert c.get(f"/api/done-tags?agent_id={AGENT}").json()["found"]

    def boom(store):
        raise RuntimeError("a bug in the adoption")
    monkeypatch.setattr(donelib, "adopt", boom)
    r = c.get(f"/api/done-tags?agent_id={AGENT}")
    assert r.status_code == 200 and r.json()["found"]


def test_an_unreadable_since_file_applies_nothing_and_is_kept(tmp_path: Path) -> None:
    from backend import nowlib
    path = tmp_path / "now.json"
    path.write_bytes(b"\xef\xbb\xbf" + b'{"since": "2000-01-01T00:00:00"}')
    assert nowlib.since_stamp(path, "#now") == "2000-01-01T00:00:00"      # a BOM reads
    path.write_text('{"since": "2000-01-01T00:00', encoding="utf-8")       # cut short
    assert nowlib.since_stamp(path, "#now") is None
    assert path.read_text(encoding="utf-8") == '{"since": "2000-01-01T00:00'


def test_a_card_the_server_cannot_write_does_not_fail_the_list(env, monkeypatch) -> None:
    from fastapi import HTTPException

    from backend import nowlib
    c, root = env
    _chat(root, [(_at(-5), "#now build the export", "built")])
    calls: list[int] = []

    def refuse(store, tag):
        calls.append(1)
        raise HTTPException(status_code=422, detail="refused on purpose")
    monkeypatch.setattr(nowlib, "_write_card", refuse)
    assert _cards(c) == [] and len(calls) == 1
    assert _cards(c) == [] and len(calls) == 1                     # looked at once


def test_an_adoption_that_raises_does_not_fail_the_list(env, monkeypatch) -> None:
    from backend import nowlib
    c, root = env
    _chat(root, [(_at(-5), "#now build the export", "built")])

    def boom(store):
        raise RuntimeError("a bug in the adoption")
    monkeypatch.setattr(nowlib, "adopt", boom)
    c.app.state.store.rebuild()
    r = c.get("/api/tasks?project=alpha")
    assert r.status_code == 200 and r.json()["tasks"] == []


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
