"""Next tasks offered after #done (nextlib.py, routers/done.py): the offer
through task_done, its similar tasks, the operator's answer, the tasks made,
and the record kept for the two-week check (tk_13318a92)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend import nextlib
from backend.server import create_app
from tests.refusals import changed, snapshot

AGENT = "cc-next0001"
OTHER = "cc-next0002"


def _chat(root: Path, turns: list[str], agent: str = AGENT, project: str = "alpha", helper: bool = False) -> None:
    d = root / "projects" / project / "chats" / agent
    d.mkdir(parents=True, exist_ok=True)
    meta: dict[str, Any] = {"agent_id": agent, "agent_name": "lead", "project": project,
                            "created_date": "2609-01", "last_active": "2026-09-01T11:00:00"}
    if helper:
        meta.update({"helper": True, "helper_kind": "claude-print"})
    (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    body = [f"# Chat log — {agent}\n"]
    for i, user in enumerate(turns, start=1):
        body.append(f"\n## Turn {i} · 2026-09-01T10:{i:02d}:00\n**User**: {user}\n**Agent**: ok\n")
    (d / "chat.md").write_text("".join(body), encoding="utf-8")


def _task(c: TestClient, title: str, project: str = "alpha", status: str = "todo", minute: int = 0) -> str:
    r = c.post("/api/tasks", json={
        "created_date": "2609-01", "created_time": f"09:{minute:02d}", "project": project,
        "agent_id": "operator", "title": title, "status": status,
    })
    assert r.status_code in (200, 201), r.text
    return r.json()["metadata"]["id"]


@pytest.fixture()
def env(tmp_path: Path):
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    (root / "projects" / "beta").mkdir(parents=True)
    (root / "done.json").write_text('{"since": "2000-01-01T00:00:00"}', encoding="utf-8")
    with TestClient(create_app(data_root=root, watch=False)) as c:
        work = _task(c, "Deploy the bewrite site", status="doing", minute=1)
        dns = _task(c, "Set up the www DNS record in Namecheap", minute=2)
        _task(c, "Kanban board colours", minute=3)
        yield c, root, work, dns


PROPOSALS = [{"title": "Set up www DNS for the site", "line": "the site is deployed; www has no DNS record yet"},
             {"title": "Check the deploy script on Windows", "line": "run on Linux only, the task asked for both"}]


def _offer(c: TestClient, root: Path, work: str, proposals: Any = PROPOSALS, extra: list[str] | None = None) -> dict:
    _chat(root, [f"{work} deploy it", "#done", *(extra or [])])
    c.get(f"/api/done-tags?agent_id={AGENT}")
    r = c.post("/api/done-tags", json={"agent_id": AGENT, "proposals": proposals})
    assert r.status_code == 200, r.text
    return r.json()


def _answer(root: Path, work: str, *answers: str) -> None:
    _chat(root, [f"{work} deploy it", "#done", *answers])


def _made(c: TestClient, numbers: Any) -> Any:
    return c.post("/api/next-tasks/make", json={"agent_id": AGENT, "numbers": numbers})


def _tasks(c: TestClient, project: str = "alpha") -> list[dict]:
    return c.get(f"/api/tasks?project={project}").json()["tasks"]


# ---------------------------------------------------------------------------
# task_done: without proposals as it was
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("empty", [None, [], ""])
def test_without_proposals_the_answer_is_the_same(env, empty) -> None:
    c, root, work, _ = env
    _chat(root, [f"{work} deploy it", "#done"])
    get = c.get(f"/api/done-tags?agent_id={AGENT}")
    body = {"agent_id": AGENT} if empty is None else {"agent_id": AGENT, "proposals": empty}
    post = c.post("/api/done-tags", json=body)
    assert post.status_code == get.status_code == 200
    assert post.content == c.get(f"/api/done-tags?agent_id={AGENT}").content
    assert get.json()["tasks"][0]["result"] == "moved"
    assert set(get.json()) == {"found", "turn", "tasks", "unnamed", "next"}
    assert not (root / nextlib.NEXT_CSV).exists()


# ---------------------------------------------------------------------------
# The offer
# ---------------------------------------------------------------------------


def test_the_offer_names_similar_open_tasks_and_the_line_to_show(env) -> None:
    c, root, work, dns = env
    got = _offer(c, root, work)
    assert [p["n"] for p in got["proposals"]] == [1, 2]
    assert [s["id"] for s in got["proposals"][0]["similar"]] == [dns]
    assert set(got["proposals"][0]["similar"][0]) == {"id", "title", "status", "score"}
    assert got["proposals"][1]["similar"] == []
    assert got["show"] == "Make these tasks? 1) Set up www DNS for the site 2) Check the deploy script on Windows"
    assert got["show"] in got["next"] and "next_tasks" in got["next"]
    assert got["tasks"][0]["id"] == work            # the done answer is all there
    row = nextlib.rows(c.app.state.store)[0]
    assert (row["state"], row["done_turn"], row["offered_turn"], row["closed"]) == ("offered", "2", "2", work)
    assert json.loads(row["proposals"])[0]["similar"][0]["id"] == dns


def test_the_task_just_closed_done_and_archived_tasks_never_match(env) -> None:
    c, root, work, dns = env
    gone = _task(c, "Set up www DNS for the site: done already", status="done", minute=5)
    archived = _task(c, "Set up www DNS for the site, archived", minute=6)
    c.post(f"/api/tasks/{archived}/archive", json={"actor": "operator"})
    c.post(f"/api/tasks/{dns}/update", json={"status": "done-archived", "actor": "operator"})
    got = _offer(c, root, work, [{"title": "Set up www DNS for the site", "line": ""}])
    ids = [s["id"] for s in got["proposals"][0]["similar"]]
    assert work not in ids and gone not in ids and dns not in ids
    assert archived not in ids
    assert c.get(f"/api/tasks/{archived}").json()["metadata"]["archived_at"]
    # Open again, the same task is found: the exclusion is what kept it out.
    c.post(f"/api/tasks/{archived}/restore", json={"actor": "operator"})
    again = c.post("/api/done-tags", json={"agent_id": AGENT, "proposals": [
        {"title": "Set up www DNS for the site", "line": ""}]}).json()
    assert archived in [s["id"] for s in again["proposals"][0]["similar"]]


def test_a_task_in_another_project_never_matches(env) -> None:
    c, root, work, _ = env
    other = _task(c, "Check the deploy script on Windows", project="beta", minute=7)
    got = _offer(c, root, work)
    assert other not in [s["id"] for p in got["proposals"] for s in p["similar"]]


def test_an_empty_board_answers_no_similar(env) -> None:
    c, root, work, dns = env
    c.post(f"/api/tasks/{dns}/update", json={"status": "done", "actor": "operator"})
    got = _offer(c, root, work, [{"title": "Set up www DNS", "line": ""}])
    assert got["proposals"][0]["similar"] == []


def test_offered_again_before_the_answer_replaces_it(env) -> None:
    c, root, work, _ = env
    _offer(c, root, work)
    got = c.post("/api/done-tags", json={"agent_id": AGENT, "proposals": PROPOSALS[1:]}).json()
    assert got["show"] == "Make these tasks? 1) Check the deploy script on Windows"
    rows = nextlib.rows(c.app.state.store)
    assert len(rows) == 1 and len(json.loads(rows[0]["proposals"])) == 1


@pytest.mark.parametrize("raw,count", [
    (["Set up www DNS for the site"], 1),                                   # a string item is a title
    (json.dumps(PROPOSALS), 2),                                             # the list as JSON text
    ([{"title": "  Set up\nwww DNS ", "line": None}], 1),                   # spaces and a newline folded
])
def test_agent_shaped_proposals_that_mean_the_right_thing(env, raw, count) -> None:
    c, root, work, _ = env
    got = _offer(c, root, work, raw)
    assert len(got["proposals"]) == count
    assert "\n" not in got["proposals"][0]["title"]


@pytest.mark.parametrize("raw,words", [
    ([{"title": f"Task {i}"} for i in range(4)], "at most three next tasks"),
    ({"title": "x"}, "not dict"),
    (5, "not int"),
    (True, "not bool"),
    ("not json", "not text"),
    ([["Set up DNS"]], "proposal 1 is an object"),
    ([3], "proposal 1 is an object"),
    ([{"title": "x", "tags": "ag_bug"}], "unknown field tags"),
    ([{"title": "x", "line": "y", "priority": 1, "status": "todo"}], "unknown field priority, status"),
    ([{"line": "no title"}], "title and line are text"),
    ([{"title": ""}], "needs a title"),
    ([{"title": "x" * 81}], "at most 80 characters"),
    ([{"title": "x", "line": "y" * 301}], "at most 300 characters"),
    ([{"title": "Same"}, {"title": "same"}], "repeats the title"),
    ([{"title": 5}], "title and line are text"),
])
def test_wrong_shapes_are_refused_and_write_nothing(env, raw, words) -> None:
    """Refused before the #done is applied: the data folder is as it was,
    though the chat holds a #done not applied yet (case 9)."""
    c, root, work, _ = env
    _chat(root, [f"{work} deploy it", "#done"])
    c.app.state.store.rebuild()
    before = snapshot(root)
    r = c.post("/api/done-tags", json={"agent_id": AGENT, "proposals": raw})
    assert r.status_code == 422 and words in r.json()["detail"], r.text
    assert changed(before, snapshot(root)) == []
    assert c.get(f"/api/tasks/{work}").json()["metadata"]["status"] == "doing"


def test_more_than_three_says_the_task_is_not_finished(env) -> None:
    c, root, work, _ = env
    _chat(root, [f"{work} deploy it", "#done"])
    r = c.post("/api/done-tags", json={"agent_id": AGENT, "proposals": ["a", "b", "c", "d"]})
    assert r.json()["detail"].startswith(nextlib.MORE_THAN_THREE)
    assert "(4 sent)" in r.json()["detail"]


def test_a_body_that_is_not_an_object(env) -> None:
    c, *_ = env
    for body in ([1], "x", None):
        assert c.post("/api/done-tags", json=body).status_code == 422


@pytest.mark.parametrize("turns,why", [
    (["hello", "#done"], "no task was closed"),                              # unnamed
    (["{work} go", "#done", "and one more thing"], "the operator has written since"),
])
def test_proposals_are_ignored_where_no_offer_belongs(env, turns, why) -> None:
    c, root, work, _ = env
    _chat(root, [t.format(work=work) for t in turns])
    got = c.post("/api/done-tags", json={"agent_id": AGENT, "proposals": PROPOSALS}).json()
    assert why in got["proposals_ignored"] and "proposals" not in got
    assert nextlib.rows(c.app.state.store) == []


def test_a_task_already_done_takes_no_offer(env) -> None:
    c, root, work, _ = env
    _chat(root, [f"{work} deploy it", "#done", f"#done {work}"])
    got = c.post("/api/done-tags", json={"agent_id": AGENT, "proposals": PROPOSALS}).json()
    assert got["tasks"][0]["result"] == "already" and "proposals_ignored" in got


def test_a_helper_chat_takes_no_offer(env) -> None:
    c, root, work, _ = env
    _chat(root, [f"{work} deploy it", "#done"], helper=True)
    got = c.post("/api/done-tags", json={"agent_id": AGENT, "proposals": PROPOSALS}).json()
    assert "proposals" not in got and nextlib.rows(c.app.state.store) == []


# ---------------------------------------------------------------------------
# The operator's answer
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text,kind,numbers", [
    ("2", "numbers", [2]), ("1, 2", "numbers", [1, 2]), ("1 и 2", "numbers", [1, 2]),
    ("1 and 2", "numbers", [1, 2]), ("make 1", "numbers", [1]), ("2 2", "numbers", [2]),
    ("yes", "all", [1, 2]), ("да, все", "all", [1, 2]), ("both please", "all", [1, 2]),
    ("1 and 3, not 2", "text", [1, 2]), ("skip", "text", []), ("нет", "text", []),
    ("why 2?", "question", []), ("#now fix the login", "command", []), ("2 #task {ui} later", "command", []),
    ("#done", "command", []), ("2026-11-11: only 1", "text", [1]), ("v1.2 is out", "text", []),
    ("tk_12345678 and 2", "text", [2]), ("10% of 1", "text", [1]), ("4", "text", []),
    ("12:30", "text", []), ("###now 2", "command", []), ("#mute 2 #now", "command", []),
])
def test_reading_the_answer(text, kind, numbers) -> None:
    assert nextlib.read_answer(text, 2) == {"kind": kind, "numbers": numbers}


def test_the_chosen_tasks_land_in_the_agent_column(env) -> None:
    c, root, work, _ = env
    _offer(c, root, work)
    _answer(root, work, "2")
    got = _made(c, [2])
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["chosen"] == [2] and len(body["made"]) == 1 and body["skipped"] is False
    made = c.get(f"/api/tasks/{body['made'][0]}").json()
    meta = made["metadata"]
    assert (meta["title"], meta["status"], meta["tags"], meta["project"], meta["agent_id"]) == (
        "Check the deploy script on Windows", "agent", "ag_followup", "alpha", AGENT)
    assert not meta.get("lane") and not meta.get("assignee")
    assert made["description"].startswith("run on Linux only")
    assert work in made["description"] and "number 2" in made["description"]
    row = nextlib.rows(c.app.state.store)[0]
    assert (row["state"], row["chosen"], row["made"], row["answered_turn"], row["answer"]) == (
        "made", "2", body["made"][0], "3", "numbers")
    assert body["made"][0] in [t["id"] for t in _tasks(c) if t["status"] == "agent"]


def test_a_later_command_does_not_move_the_made_tasks(env) -> None:
    """The #task gate reads the operator's latest message: a later #now or a
    lane in braces would have put the card in doing or in a lane."""
    c, root, work, _ = env
    _task(c, "lane holder", minute=9)
    _offer(c, root, work)
    _answer(root, work, "1 2", "#task {ui} later the colours")
    body = _made(c, [1, 2]).json()
    for tid in body["made"]:
        meta = c.get(f"/api/tasks/{tid}").json()["metadata"]
        assert meta["status"] == "agent" and not meta.get("lane")


def test_a_retry_answers_the_same_tasks(env) -> None:
    c, root, work, _ = env
    _offer(c, root, work)
    _answer(root, work, "1, 2")
    first = _made(c, [1, 2]).json()
    again = _made(c, [1, 2]).json()
    assert again["made"] == first["made"] and again["existing"] is True
    titles = [t["title"] for t in _tasks(c)]
    assert titles.count("Set up www DNS for the site") == 1


def test_a_failure_halfway_leaves_the_first_task_once(env, monkeypatch) -> None:
    c, root, work, _ = env
    _offer(c, root, work)
    _answer(root, work, "1 2")
    from backend import tasklib
    real = tasklib.create_task
    calls = {"n": 0}

    def flaky(store, body, **kw):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disk full")
        return real(store, body, **kw)
    monkeypatch.setattr(tasklib, "create_task", flaky)
    with pytest.raises(OSError):
        _made(c, [1, 2])
    row = nextlib.rows(c.app.state.store)[0]
    assert row["state"] == "offered" and len(row["made"].split(",")) == 1
    monkeypatch.setattr(tasklib, "create_task", real)
    body = _made(c, [1, 2]).json()
    assert len(body["made"]) == 2
    titles = [t["title"] for t in _tasks(c)]
    assert titles.count("Set up www DNS for the site") == 1


def test_no_answer_yet_is_refused_and_writes_nothing(env) -> None:
    c, root, work, _ = env
    _offer(c, root, work)
    before = snapshot(root)
    r = _made(c, [1])
    assert r.status_code == 409 and "not answered" in r.json()["detail"] and "do not ask again" in r.json()["detail"]
    assert changed(before, snapshot(root)) == []


def test_a_tool_turn_is_not_the_answer(env) -> None:
    c, root, work, _ = env
    _offer(c, root, work)
    _answer(root, work, "<task-notification>a helper finished</task-notification>", "1")
    assert _made(c, [1]).json()["chosen"] == [1]


@pytest.mark.parametrize("answer,sent,words", [
    ("1", [2], "the operator chose 1"),
    ("1 2", [1], "the operator chose 1, 2"),
    ("1 2", [], "the operator chose 1, 2"),
    ("yes", [1], "the operator chose 1, 2 (all)"),
    ("only 1 for now", [2], "2 is not in the operator's answer"),
    ("2", [3], "the offer has 2 tasks"),
    ("2", [0], "the offer has 2 tasks"),
])
def test_numbers_the_operator_did_not_choose_are_refused(env, answer, sent, words) -> None:
    c, root, work, _ = env
    _offer(c, root, work)
    _answer(root, work, answer)
    c.app.state.store.rebuild()
    before = snapshot(root)
    r = _made(c, sent)
    assert r.status_code == 409 and words in r.json()["detail"], r.text
    assert changed(before, snapshot(root)) == []


@pytest.mark.parametrize("numbers", [True, {"n": 1}, [1.5], ["one"], [True]])
def test_numbers_in_a_wrong_shape(env, numbers) -> None:
    c, root, work, _ = env
    _offer(c, root, work)
    _answer(root, work, "1")
    r = _made(c, numbers)
    assert r.status_code == 422 and "numbers is a list such as [1, 3]" in r.json()["detail"]


@pytest.mark.parametrize("numbers", ["1", "[1]", ["1"], 1, [1, 1]])
def test_numbers_in_shapes_that_mean_one(env, numbers) -> None:
    c, root, work, _ = env
    _offer(c, root, work)
    _answer(root, work, "1")
    assert _made(c, numbers).json()["chosen"] == [1]


@pytest.mark.parametrize("answer", ["#now fix the login", "why is 2 needed?", "#done"])
def test_a_command_or_a_question_chooses_nothing(env, answer) -> None:
    c, root, work, _ = env
    _offer(c, root, work)
    _answer(root, work, answer)
    count = len(_tasks(c))
    body = _made(c, [2]).json()
    assert body["skipped"] is True and body["made"] == []
    assert len(_tasks(c)) <= count + 1     # a #now card the server may write is not ours
    assert nextlib.rows(c.app.state.store)[0]["state"] == "skipped"
    assert _made(c, [2]).status_code == 409   # a skipped offer is closed


def test_the_operator_skips(env) -> None:
    c, root, work, _ = env
    _offer(c, root, work)
    _answer(root, work, "no, let's go on with the docs")
    body = _made(c, []).json()
    assert body["skipped"] is True
    row = nextlib.rows(c.app.state.store)[0]
    assert (row["state"], row["answered_turn"], row["made"]) == ("skipped", "3", "")


def test_no_offer_in_this_chat(env) -> None:
    c, *_ = env
    r = _made(c, [1])
    assert r.status_code == 409 and "no next tasks were offered" in r.json()["detail"]
    assert c.post("/api/next-tasks/make", json={"numbers": [1]}).status_code == 422


def test_an_offer_made_into_tasks_is_not_offered_again(env) -> None:
    c, root, work, _ = env
    _offer(c, root, work)
    _answer(root, work, "1")
    _made(c, [1])
    _chat(root, [f"{work} deploy it", "#done"])          # the same #done as the latest operator turn
    got = c.post("/api/done-tags", json={"agent_id": AGENT, "proposals": PROPOSALS}).json()
    assert "made into tasks" in got["proposals_ignored"]


def test_a_new_done_gets_its_own_offer(env) -> None:
    c, root, work, dns = env
    _offer(c, root, work)
    _answer(root, work, "1")
    first = _made(c, [1]).json()["made"]
    _chat(root, [f"{work} deploy it", "#done", "1", f"{dns} now this", "#done"])
    got = c.post("/api/done-tags", json={"agent_id": AGENT,
                                         "proposals": [{"title": "Check DNS propagation", "line": "TTL"}]}).json()
    assert got["offer"] != nextlib.rows(c.app.state.store)[0]["id"]
    _chat(root, [f"{work} deploy it", "#done", "1", f"{dns} now this", "#done", "1"])
    second = _made(c, [1]).json()["made"]
    assert second != first and len(nextlib.rows(c.app.state.store)) == 2


# ---------------------------------------------------------------------------
# The record, for the two-week check
# ---------------------------------------------------------------------------


def test_the_list_shows_offers_and_answers_and_writes_nothing(env) -> None:
    c, root, work, _ = env
    _offer(c, root, work)
    _answer(root, work, "2")
    c.app.state.store.rebuild()
    before = snapshot(root)
    got = c.get("/api/next-tasks?project=alpha").json()
    assert changed(before, snapshot(root)) == []
    assert got["total"] == 1
    offer = got["offers"][0]
    assert offer["state"] == "offered" and offer["answer_in_chat"] == {"turn": 3, "kind": "numbers", "numbers": [2]}
    assert offer["closed"] == [work] and offer["proposals"][0]["title"] == PROPOSALS[0]["title"]
    _made(c, [2])
    offer = c.get(f"/api/next-tasks?agent_id={AGENT}").json()["offers"][0]
    assert offer["state"] == "made" and offer["chosen"] == [2] and len(offer["made"]) == 1
    assert "answer_in_chat" not in offer
    assert c.get("/api/next-tasks?project=beta").json()["total"] == 0


def test_an_unanswered_offer_reads_as_waiting(env) -> None:
    c, root, work, _ = env
    _offer(c, root, work)
    assert c.get("/api/next-tasks").json()["offers"][0]["answer_in_chat"] is None


def test_a_damaged_proposals_cell_still_lists(env) -> None:
    c, root, work, _ = env
    _offer(c, root, work)
    path = root / nextlib.NEXT_CSV
    text = path.read_text(encoding="utf-8")
    row = nextlib.rows(c.app.state.store)[0]
    path.write_text(text.replace(row["proposals"].replace('"', '""'), "{broken"), encoding="utf-8")
    got = c.get("/api/next-tasks").json()["offers"][0]
    assert got["proposals"] == []


@pytest.mark.parametrize("tz", ["UTC", "America/Los_Angeles", "Asia/Kolkata"])
def test_the_made_task_is_stamped_with_the_answer_whatever_the_zone(env, monkeypatch, tz) -> None:
    """The task's date is the operator's answer as chat.md wrote it (local),
    not this moment: a retry the next day mints the same id."""
    import time
    c, root, work, _ = env
    monkeypatch.setenv("TZ", tz)
    if hasattr(time, "tzset"):
        time.tzset()
    try:
        _offer(c, root, work)
        _answer(root, work, "1")
        tid = _made(c, [1]).json()["made"][0]
        meta = c.get(f"/api/tasks/{tid}").json()["metadata"]
        assert (meta["created_date"], meta["created_time"]) == ("2609-01", "10:03")
    finally:
        monkeypatch.undo()
        if hasattr(time, "tzset"):
            time.tzset()


# ---------------------------------------------------------------------------
# The rule agents read
# ---------------------------------------------------------------------------


_REPO = Path(__file__).resolve().parents[2]


def _skill() -> str:
    from backend import skilllib
    base = _REPO / "templates" / "skills"
    return skilllib._with_writing_rules((base / "finish-a-task" / "SKILL.md").read_text(encoding="utf-8"), base)


def test_the_skill_carries_the_step_and_the_examples() -> None:
    text = _skill()
    assert "{{part:" not in text
    step5, step6 = text.index("\n5. "), text.index("\n6. ")
    assert step5 < step6 and "#decision" in text[step5:step6]
    six = text[step6:text.index("\n\n", step6)]
    assert "task_done" in six and "next_tasks" in six and "show" in six
    assert text.count("   - yes:") == 2 and text.count("   - no:") == 2
    assert "Never write them with `write_entry`" in text
    assert "not finished" in text and "At most three" in text


def test_the_contract_is_composed_from_the_parts() -> None:
    from backend import contract_parts
    composed = contract_parts.compose(contract_parts.load_parts(_REPO))
    assert (_REPO / "SLIGHTLY-PARALLEL.md").read_text(encoding="utf-8") == composed
    assert "next_tasks" in composed and "unfinished without them" in composed


def test_the_server_sentence_and_the_rule_name_the_same_limit() -> None:
    """Three in the rule, three in the refusal, three in the tool's schema."""
    assert nextlib.PROPOSALS_MAX == 3 and "at most three" in nextlib.MORE_THAN_THREE
    assert "at most three" in _skill().lower()
