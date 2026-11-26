"""The operator's latest message, read before the watcher has rebuilt the
store (tk_1cb0324a): the hook writes the turn to chat.md and announces the
card at once, and the agent's write arrives before the derived tables have
the new turn. The gate reads that message as it is on disk, never the
previous one."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app

AGENT = "cc-race0001"


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
    (root / "now.json").write_text('{"since": "2000-01-01T00:00:00"}', encoding="utf-8")
    (root / "done.json").write_text('{"since": "2000-01-01T00:00:00"}', encoding="utf-8")
    with TestClient(create_app(data_root=root, watch=False)) as c:
        yield c, root


def _cards(c: TestClient) -> list[dict]:
    c.app.state.store.rebuild()
    return c.get("/api/tasks?project=alpha").json()["tasks"]


def _write(c: TestClient, title: str, status: str = "") -> object:
    body = {"created_date": "2611-26", "created_time": "13:59", "project": "alpha",
            "agent_id": AGENT, "title": title, "tags": "ag_idea"}
    if status:
        body["status"] = status
    return c.post("/api/tasks", json=body)


def _text(c: TestClient, tid: str) -> str:
    return json.dumps(c.get(f"/api/tasks/{tid}").json())


def test_a_now_todo_written_before_the_rebuild_is_not_taken_for_the_previous_now(env) -> None:
    """The 26 Nov case: the previous #now has its card (the agent's), the
    operator types #now-todo, and the agent's todo write lands before the
    watcher ran. It was refused as "an agent creates tasks only in the
    `agent` column … the #now … already has its card"."""
    c, root = env
    first = (_at(-10), "#now build the export", "")
    _chat(root, [first])
    c.app.state.store.rebuild()
    assert _write(c, "Build the export").status_code == 201
    done = (first[0], first[1], "built")
    _chat(root, [done])
    assert len(_cards(c)) == 1
    # The hook appends the new turn, after the first card; the watcher has
    # not run. (Times are to the second: the new turn starts after the card.)
    time.sleep(1.1)
    _chat(root, [done, (_at(0), "#now-todo look at the import later", "")])
    r = _write(c, "Import: look again", "todo")
    assert r.status_code == 201, r.text
    card = r.json()["metadata"]
    assert card["status"] == "todo"
    assert "look at the import later" in _text(c, card["id"])     # the new message is its text
    assert "build the export" not in _text(c, card["id"])


def test_a_server_card_of_the_previous_now_is_not_the_new_messages_card(env) -> None:
    """Worse: the previous #now's card was the server's (now.csv). The late
    write refusal pointed the agent at that old card to retitle it, so the
    new message's card went missing and the old card took the new title."""
    c, root = env
    first = (_at(-10), "#now build the export", "built")
    _chat(root, [first])
    (old,) = _cards(c)                                   # the server wrote it
    _chat(root, [first, (_at(-1), "#now-todo look at the import later", "")])
    r = _write(c, "Import: look again", "todo")
    assert r.status_code == 201, r.text
    new = r.json()["metadata"]
    assert new["id"] != old["id"] and new["status"] == "todo"
    assert "look at the import later" in _text(c, new["id"])
    titles = {x["id"]: x["title"] for x in _cards(c)}
    assert titles[old["id"]] == old["title"]             # the old card is untouched
    assert len(titles) == 2


def test_a_previous_now_without_a_card_keeps_its_own_and_the_new_one_gets_its_own(env) -> None:
    """The previous #now was answered with no card, and nothing has adopted
    it yet: the agent's card is the new message's, the server's card the old
    one's — never the new text on the old turn, or one card for both."""
    c, root = env
    first = (_at(-10), "#now build the export", "built")
    _chat(root, [first])
    c.app.state.store.rebuild()                          # rebuilt, never adopted
    _chat(root, [first, (_at(-1), "#now-todo look at the import later", "")])
    r = _write(c, "Import: look again", "todo")
    assert r.status_code == 201, r.text
    new = r.json()["metadata"]
    assert "look at the import later" in _text(c, new["id"])
    cards = {x["id"]: x for x in _cards(c)}
    assert len(cards) == 2
    (old,) = [x for x in cards.values() if x["id"] != new["id"]]
    assert old["status"] == "doing" and "build the export" in _text(c, old["id"])
    assert "look at the import later" not in _text(c, old["id"])
    # The next finding of this turn is an agent card, as after any #now.
    r2 = _write(c, "A finding")
    assert r2.status_code == 201 and r2.json()["metadata"]["status"] == "agent", r2.text


def test_a_chat_the_store_has_not_seen_says_retry_not_agent_column(env, monkeypatch) -> None:
    """The adoption cannot see the chat at all (a brand-new chat whose first
    message is the #now, the rebuild failed): the refusal says the message is
    not captured yet and to retry, never "write an agent card"."""
    c, root = env
    store = c.app.state.store
    store.rebuild()
    monkeypatch.setattr(type(store), "rebuild", lambda self: (_ for _ in ()).throw(RuntimeError("busy")))
    _chat(root, [(_at(-1), "#now-todo look at the import later", "")])
    r = _write(c, "Import: look again", "todo")
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "not captured yet" in detail and "retry" in detail
    assert "`agent` column" not in detail
    # A tool without the hook never gets a chat: it is not left retrying.
    assert 'if the operator gave no #now, write it with status "agent"' in detail
