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
    assert [(t["id"], t["reason"]) for t in got["doubt"]] == [(t1, "history")]
    assert got["confirmation"] == f"#done {t1}"
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


@pytest.mark.parametrize("done_turn", ["#done", 'Compare with {other}; then the note says "#done".'])
@pytest.mark.parametrize("local_mentioned", [True, False])
def test_a_mention_in_another_project_is_not_a_done_target(env, done_turn: str, local_mentioned: bool) -> None:
    c, root, (local, _, _) = env
    (root / "projects" / "beta").mkdir()
    c.app.state.store.rebuild()
    response = c.post("/api/tasks", json={
        "created_date": "2609-01", "created_time": "09:00", "project": "beta",
        "agent_id": "operator", "title": "Other project's task", "status": "doing",
    })
    assert response.is_success, response.text
    other = response.json()["metadata"]["id"]
    turns = [f"Work on {local}"] if local_mentioned else []
    turns.extend([f"Compare with {other}", done_turn.format(other=other)])
    _chat(root, turns)
    got = c.get(f"/api/done-tags?agent_id={AGENT}").json()
    assert [t["id"] for t in got["tasks"]] == ([local] if local_mentioned else [])
    assert got["unnamed"] is not local_mentioned and "unknown" not in got
    assert _status(c, local) == ("done" if local_mentioned else "doing")
    assert _status(c, other) == "doing"

    # The operator can still name a task from another project directly.
    _chat(root, turns + [f"Review complete #done {other}"])
    got = c.get(f"/api/done-tags?agent_id={AGENT}").json()
    assert [t["id"] for t in got["tasks"]] == [other]
    assert _status(c, other) == "done"


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


def test_a_card_event_stamped_with_a_zone_finds_its_turn(env) -> None:
    """An event written as ``…+00:00`` is the same moment in local time: the
    card's turn is found, nothing raises (it compared naive with zoned)."""
    import csv
    from datetime import datetime, timedelta, timezone

    from backend import nowlib
    c, root, _ids = env
    now = datetime.now().replace(microsecond=0)
    _chat_at(root, [((now - timedelta(minutes=30)).isoformat(), "look"),
                    ((now - timedelta(minutes=20)).isoformat(), "#now build the export")])
    c.app.state.store.rebuild()
    tid = c.post("/api/tasks", json={
        "created_date": "2609-01", "created_time": "10:00", "project": "alpha",
        "agent_id": AGENT, "title": "Build the export", "tags": "ag_idea",
    }).json()["metadata"]["id"]
    path = root / "task_events.csv"
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        if r["task_id"] == tid:
            r["timestamp"] = (now - timedelta(minutes=10)).astimezone(timezone.utc).isoformat()
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    c.app.state.store.rebuild()
    assert (AGENT, 2, tid) in nowlib.card_turns(c.app.state.store, {AGENT}, ("started",))


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


@pytest.mark.parametrize("template", [
    "#done: ({a}); {b} и {c}",
    "#done\n{a},\n{b} and {c}",
    "#done {a}/{b}, {c}",
    "сделал ({a}, {b}; {c}). #done",
])
def test_done_closes_an_adjacent_chain_in_either_direction(env, template: str) -> None:
    c, root, ids = env
    _chat(root, [template.format(**dict(zip("abc", ids)))])
    got = c.get(f"/api/done-tags?agent_id={AGENT}").json()
    assert [t["id"] for t in got["tasks"]] == ids
    assert [_status(c, tid) for tid in ids] == ["done"] * 3


def test_done_stops_at_the_first_word_and_offers_a_copyable_command(env) -> None:
    c, root, (a, b, third) = env
    turns = [f"#done {a} because {b} depends on {third}"]
    _chat(root, turns)
    got = c.get(f"/api/done-tags?agent_id={AGENT}").json()
    assert [t["id"] for t in got["tasks"]] == [a]
    assert [(t["id"], t["reason"]) for t in got["doubt"]] == [(b, "mentioned"), (third, "mentioned")]
    assert got["confirmation"] == f"#done {b} {third}"
    _chat(root, turns + ["да"])
    c.get(f"/api/done-tags?agent_id={AGENT}")
    assert [_status(c, tid) for tid in (a, b, third)] == ["done", "doing", "doing"]
    _chat(root, turns + ["да", got["confirmation"]])
    closed = c.get(f"/api/done-tags?agent_id={AGENT}").json()
    assert [t["id"] for t in closed["tasks"]] == [b, third]


def test_a_pasted_report_does_not_close_its_five_cards(env) -> None:
    c, root, ids = env
    for index in range(2):
        response = c.post("/api/tasks", json={
            "created_date": "2609-01", "created_time": "09:04", "project": "alpha",
            "agent_id": "operator", "title": f"Pasted task {index}", "status": "doing",
        })
        ids.append(response.json()["metadata"]["id"])
    lines = ["голого #done во вставке было достаточно. Вот список:"]
    lines.extend(f"Задача {tid} попала в отчёт." for tid in ids)
    _chat(root, [f"Work on {ids[0]}", "\n".join(lines)])
    got = c.get(f"/api/done-tags?agent_id={AGENT}").json()
    assert got["tasks"] == []
    assert [t["id"] for t in got["doubt"]] == ids
    assert got["confirmation"] == "#done " + " ".join(ids)
    assert [_status(c, tid) for tid in ids] == ["doing"] * 5


def test_dns_paste_leaves_the_other_project_in_doubt(env) -> None:
    c, root, (local, _, _) = env
    (root / "projects" / "writing-tracker").mkdir()
    c.app.state.store.rebuild()
    response = c.post("/api/tasks", json={
        "created_date": "2609-01", "created_time": "09:00", "project": "writing-tracker",
        "agent_id": "operator", "title": "DNS for www", "status": "doing",
    })
    other = response.json()["metadata"]["id"]
    _chat(root, [f"Work on {local}", f"Compare with {other}",
                 f"При #done не пишем план.\nЗавёл задачу {local}, она в doing.\n"
                 f"После #done сервер пишет: похоже на {other} www DNS."])
    got = c.get(f"/api/done-tags?agent_id={AGENT}").json()
    assert [t["id"] for t in got["tasks"]] == [local]
    assert [(t["id"], t["reason"]) for t in got["doubt"]] == [(other, "other_project")]
    assert got["confirmation"] == f"#done {other}"
    assert _status(c, other) == "doing"


def test_bare_done_closes_only_the_latest_local_task_and_lists_earlier_ones(env) -> None:
    c, root, (a, b, third) = env
    _chat(root, [f"Previously {a}", f"Compare {b} and {third}", "#done"])
    got = c.get(f"/api/done-tags?agent_id={AGENT}").json()
    assert [t["id"] for t in got["tasks"]] == [third]
    assert [(t["id"], t["reason"]) for t in got["doubt"]] == [(a, "history"), (b, "history")]
    assert got["confirmation"] == f"#done {a} {b}"


def test_the_hook_looks_up_its_captured_turn_on_the_matching_server(env) -> None:
    c, root, (a, b, _) = env
    first = f"#done {a} because {b} is still open"
    _chat(root, [first])
    wrong = c.get("/api/done-tags/capture", params={
        "agent_id": AGENT, "capture_root": str(root / "elsewhere"), "capture_turn": 1,
    })
    assert wrong.status_code == 409
    assert _status(c, a) == "doing" and _status(c, b) == "doing"
    right = c.get("/api/done-tags/capture", params={"agent_id": AGENT, "capture_root": str(root), "capture_turn": 1})
    assert right.is_success
    assert [t["id"] for t in right.json()["tasks"]] == [a]
    assert right.json()["confirmation"] == f"#done {b}"
    _chat(root, [first, f"#done {b}"])
    latest = c.get(f"/api/done-tags?agent_id={AGENT}").json()
    assert [t["id"] for t in latest["tasks"]] == [b]
    earlier = c.get("/api/done-tags/capture", params={"agent_id": AGENT, "capture_root": str(root), "capture_turn": 1}).json()
    assert [t["id"] for t in earlier["tasks"]] == [a]
    assert "doubt" not in earlier and "confirmation" not in earlier


def test_bare_done_excludes_finished_and_archived_tasks_from_history(env) -> None:
    c, root, (finished, archived, target) = env
    assert c.post(f"/api/tasks/{finished}/update", json={"status": "done", "actor": "operator"}).is_success
    assert c.post(f"/api/tasks/{archived}/archive", json={}).is_success
    _chat(root, [f"Review {finished} and {archived}", f"Work on {target}", "#done"])
    got = c.get(f"/api/done-tags?agent_id={AGENT}").json()
    assert [(t["id"], t["result"]) for t in got["tasks"]] == [(target, "moved")]
    assert "doubt" not in got and "confirmation" not in got


@pytest.mark.parametrize("command", ["#done", "#done {target}"])
def test_done_ignores_incoming_agent_messages_when_selecting_tasks(env, command: str) -> None:
    c, root, (target, first, second) = env
    incoming = (
        '<sp-message from="cc-coordinator" id="msg_test">\n'
        f"Check progress on {first} and {second}.\n</sp-message>"
    )
    _chat_both(root, [
        (f"Work on {target}", f"Related work includes {first}."),
        (incoming, "Received"),
        (command.format(target=target), "ok"),
    ])
    got = c.get(f"/api/done-tags?agent_id={AGENT}").json()
    assert [(t["id"], t["result"]) for t in got["tasks"]] == [(target, "moved")]
    assert "doubt" not in got and "confirmation" not in got
    assert _status(c, first) == _status(c, second) == "doing"
