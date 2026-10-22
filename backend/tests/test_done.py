"""#done: the operator's verdict typed in the chat (donelib.py)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app
from backend.sessions import DONE_TAG_RE

AGENT = "cc-done0001"


def _chat(root: Path, turns: list[str]) -> None:
    d = root / "projects" / "alpha" / "chats" / AGENT
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps({
        "agent_id": AGENT, "agent_name": "lead", "project": "alpha",
        "created_date": "2609-01", "last_active": "2026-09-01T11:00:00",
    }), encoding="utf-8")
    body = [f"# Chat log — {AGENT}\n"]
    for i, user in enumerate(turns, start=1):
        body.append(f"\n## Turn {i} · 2026-09-01T10:{i:02d}:00\n**User**: {user}\n**Agent**: ok\n")
    (d / "chat.md").write_text("".join(body), encoding="utf-8")


@pytest.fixture()
def env(tmp_path: Path):
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    # Tags older than this moment are history; the test's chat is from 2026-09-01.
    (root / "done.json").write_text('{"since": "2000-01-01T00:00:00"}', encoding="utf-8")
    with TestClient(create_app(data_root=root, watch=False)) as c:
        ids = []
        for i, title in enumerate(("First", "Second", "Third")):
            r = c.post("/api/tasks", json={
                "created_date": "2609-01", "created_time": f"09:0{i}", "project": "alpha",
                "agent_id": "operator", "title": title, "status": "doing",
            })
            ids.append(r.json()["metadata"]["id"])
        yield c, root, ids


def _status(c: TestClient, tid: str) -> str:
    return c.get(f"/api/tasks/{tid}").json()["metadata"]["status"]


@pytest.mark.parametrize("text,hit", [
    ("#done", True), ("ok #DONE, next", True), ("#done tk_x", True),
    ("#done-ish", False), ("##done", False), ("x#done", False), ("# done", False), ("#doneness", False),
])
def test_the_tag(text, hit):
    assert bool(DONE_TAG_RE.search(text)) is hit


def test_done_closes_the_last_task_named_and_owns_its_stretch(env) -> None:
    c, root, (t1, t2, _t3) = env
    _chat(root, ["hello", f"{t1} let's build it", "more", "#done", f"now {t2}", "work", "#done ok"])
    got = c.get(f"/api/done-tags?agent_id={AGENT}").json()
    assert [(t["id"], t["result"]) for t in got["tasks"]] == [(t2, "moved")]
    assert got["tasks"][0]["stretch"]["start"] == 5 and got["tasks"][0]["stretch"]["end"] == 7
    assert _status(c, t1) == "done" and _status(c, t2) == "done"
    first = c.get(f"/api/tasks/{t1}/done").json()["stretches"]
    # #done belongs to the task it closes; the stretch starts at the chat's start.
    assert (first[0]["start"], first[0]["end"], first[0]["turns"]) == (1, 4, 4)
    events = [r for r in c.app.state.store.query(
        "SELECT actor, field, new_value FROM task_events_mutual WHERE task_id = ?", (t1,))]
    assert {"actor": "operator", "field": "done_in_chat", "new_value": f"{AGENT}#4"} in events


def test_a_named_task_and_one_applied_once(env) -> None:
    c, root, (t1, t2, t3) = env
    _chat(root, [f"{t1} and {t2}", f"#done {t3}"])
    got = c.get(f"/api/done-tags?agent_id={AGENT}").json()
    assert [t["id"] for t in got["tasks"]] == [t3]
    assert _status(c, t1) == "doing" and _status(c, t3) == "done"
    # The operator moves it back: the old #done is not applied again.
    c.post(f"/api/tasks/{t3}/update", json={"status": "doing", "actor": "operator"})
    c.get("/api/tasks?project=alpha")
    assert _status(c, t3) == "doing"
    assert c.get(f"/api/tasks/{t3}/done").json()["reopened"] is True


def test_a_mistyped_id_asks_and_closes_nothing(env) -> None:
    """#done with an id that is no task (a typo) closed the last task named
    before it instead."""
    c, root, (t1, _t2, _t3) = env
    _chat(root, [f"{t1} go", "#done tk_nosuch12"])
    got = c.get(f"/api/done-tags?agent_id={AGENT}").json()
    assert got["unnamed"] is True
    assert _status(c, t1) == "doing"


def test_no_task_named_asks(env) -> None:
    c, root, (t1, _t2, _t3) = env
    _chat(root, [f"{t1} go", "#done", "#done"])
    got = c.get(f"/api/done-tags?agent_id={AGENT}").json()
    assert got["unnamed"] is True and "Ask the operator" in got["next"]


def test_the_board_applies_it_without_an_agent(env) -> None:
    c, root, (t1, _t2, _t3) = env
    _chat(root, [f"{t1} go", "#done"])
    c.app.state.store.rebuild()
    c.get("/api/tasks?project=alpha")
    assert _status(c, t1) == "done"


def test_tags_from_before_the_feature_are_history(env) -> None:
    c, root, (t1, _t2, _t3) = env
    (root / "done.json").write_text('{"since": "2030-01-01T00:00:00"}', encoding="utf-8")
    _chat(root, [f"{t1} go", "we can add #done later"])
    c.get(f"/api/done-tags?agent_id={AGENT}")
    assert _status(c, t1) == "doing"


def test_statistics_count_the_stretch(env) -> None:
    c, root, (t1, t2, _t3) = env
    _chat(root, ["hello", f"{t1} let's build it", "more", "#done", f"now {t2}", "work"])
    c.get(f"/api/done-tags?agent_id={AGENT}")
    rows = {r["id"]: r for r in c.get("/api/stats/tasks?project=alpha").json()["tasks"]}
    one = rows[t1]
    assert (one["closed"], one["stretch"], one["messages"], one["chats"]) == ("#done", "done", 4, 1)
    assert rows[t2]["stretch"] == "estimated" and rows[t2]["done"] is False


def _chat_both(root: Path, turns: list[tuple[str, str]]) -> None:
    d = root / "projects" / "alpha" / "chats" / AGENT
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps({
        "agent_id": AGENT, "agent_name": "lead", "project": "alpha",
        "created_date": "2609-01", "last_active": "2026-09-01T11:00:00",
    }), encoding="utf-8")
    body = [f"# Chat log — {AGENT}\n"]
    for i, (user, agent) in enumerate(turns, start=1):
        body.append(f"\n## Turn {i} · 2026-09-01T10:{i:02d}:00\n**User**: {user}\n**Agent**: {agent}\n")
    (d / "chat.md").write_text("".join(body), encoding="utf-8")


def test_a_task_the_agent_mentioned_in_passing_is_not_the_one_closed(env) -> None:
    c, root, (t1, t2, _t3) = env
    _chat_both(root, [(f"work on {t1}", "on it"), ("go", f"done; note {t2} depends on this"), ("#done", "ok")])
    got = c.get(f"/api/done-tags?agent_id={AGENT}").json()
    assert [t["id"] for t in got["tasks"]] == [t1]
    assert _status(c, t1) == "done" and _status(c, t2) == "doing"


def test_done_in_the_chat_re_arms_a_repeating_task(env) -> None:
    c, root, (t1, _t2, _t3) = env
    c.post(f"/api/tasks/{t1}/update", json={"resurface_every_days": "7", "actor": "operator"})
    _chat(root, [f"{t1} weekly review", "#done"])
    c.get(f"/api/done-tags?agent_id={AGENT}")
    meta = c.get(f"/api/tasks/{t1}").json()["metadata"]
    assert meta["status"] == "done" and meta["resurface_on"]


def _chat_at(root: Path, turns: list[tuple[str, str]]) -> None:
    d = root / "projects" / "alpha" / "chats" / AGENT
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps({
        "agent_id": AGENT, "agent_name": "lead", "project": "alpha",
        "created_date": "2609-01", "last_active": "2026-09-01T11:00:00",
    }), encoding="utf-8")
    body = [f"# Chat log — {AGENT}\n"]
    for i, (at, user) in enumerate(turns, start=1):
        body.append(f"\n## Turn {i} · {at}\n**User**: {user}\n**Agent**: ok\n")
    (d / "chat.md").write_text("".join(body), encoding="utf-8")


def test_done_closes_the_task_the_operator_started_with_now(env) -> None:
    # #now names no id; the card the agent wrote in that turn is the one named.
    from datetime import datetime, timedelta
    c, root, (t1, _t2, _t3) = env
    past = lambda m: (datetime.now() - timedelta(minutes=m)).isoformat(timespec="seconds")
    later = lambda m: (datetime.now() + timedelta(minutes=m)).isoformat(timespec="seconds")
    head = [(past(30), f"{t1} first look"), (past(20), "#now build the export")]
    _chat_at(root, head)
    c.app.state.store.rebuild()  # the store learns the new chat, as the watcher would
    tid = c.post("/api/tasks", json={
        "created_date": "2609-01", "created_time": "10:00", "project": "alpha",
        "agent_id": AGENT, "title": "Build the export", "tags": "ag_idea",
    }).json()["metadata"]["id"]
    _chat_at(root, head + [(later(10), "work"), (later(20), "#done")])
    got = c.get(f"/api/done-tags?agent_id={AGENT}").json()
    assert [(t["id"], t["result"]) for t in got["tasks"]] == [(tid, "moved")]
    assert (got["tasks"][0]["stretch"]["start"], got["tasks"][0]["stretch"]["end"]) == (2, 4)
    assert _status(c, tid) == "done" and _status(c, t1) == "doing"
