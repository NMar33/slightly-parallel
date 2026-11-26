"""#think: a task the operator thinks through himself (thinklib.py).

The mark is set from the chat (``#think tk_…``, or ``#think`` beside
``#now-todo`` / ``#now`` / ``#task`` for the card that message makes) or on
the board, and removed only by the operator. While it is on, the server
refuses an agent's moves on the task; the operator is never refused."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import thinklib
from backend.hookshared import command_text, think_targets
from backend.server import create_app

AGENT = "cc-think001"
OTHER = "cc-think002"


def _at(minutes: int) -> str:
    return (datetime.now() + timedelta(minutes=minutes)).isoformat(timespec="seconds")


def _chat(root: Path, turns: list[str], agent: str = AGENT, answered: bool = True) -> None:
    d = root / "projects" / "alpha" / "chats" / agent
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps({
        "agent_id": agent, "agent_name": "lead", "project": "alpha",
        "created_date": "2611-26", "last_active": _at(0),
    }), encoding="utf-8")
    body = [f"# Chat log — {agent}\n"]
    for i, user in enumerate(turns, start=1):
        body.append(f"\n## Turn {i} · {_at(i - len(turns) - 5)}\n**User**: {user}\n"
                    + ("**Agent**: ok\n" if answered or i < len(turns) else ""))
    (d / "chat.md").write_text("".join(body), encoding="utf-8")


@pytest.fixture()
def env(tmp_path: Path):
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    for name in ("think.json", "done.json", "now.json"):
        (root / name).write_text('{"since": "2000-01-01T00:00:00"}', encoding="utf-8")
    with TestClient(create_app(data_root=root, watch=False)) as c:
        ids = []
        for i, title in enumerate(("Pricing model", "Second", "Third")):
            r = c.post("/api/tasks", json={
                "created_date": "2611-26", "created_time": f"09:0{i}", "project": "alpha",
                "actor": "operator", "title": title, "status": "todo",
            })
            ids.append(r.json()["metadata"]["id"])
        yield c, root, ids


def _row(c: TestClient, tid: str) -> dict:
    return c.get(f"/api/tasks/{tid}").json()["metadata"]


def _read_board(c: TestClient) -> list[dict]:
    c.app.state.store.rebuild()
    return c.get("/api/tasks?project=alpha").json()["tasks"]


def _mark(c: TestClient, tid: str) -> None:
    r = c.post(f"/api/tasks/{tid}/update", json={"think": True, "actor": "operator"})
    assert r.status_code == 200, r.text
    assert _row(c, tid)["think_at"]


# ---------------------------------------------------------------------------
# The tag
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text,creates,want", [
    ("#think tk_aaa111 tk_bbb222 and tk_ccc333, then tk_ddd444 later", False,
     {"think": ["tk_aaa111", "tk_bbb222", "tk_ccc333"]}),
    ("tk_aaa111, tk_bbb222 #think", False, {"think": ["tk_bbb222", "tk_aaa111"]}),
    ("look at tk_aaa111 again, I will #think about it", False, {"think": []}),
    ("<pasted_content>the log names tk_aaa111 and tk_bbb222</pasted_content> #think", False, {"think": []}),
    ("#think tk_ccc333 <pasted_content>tk_aaa111 failed</pasted_content>", False, {"think": ["tk_ccc333"]}),
    ("#think tk_aaa111, no, #think-off tk_aaa111", False, {"think": [], "think-off": ["tk_aaa111"]}),
    ("#think-off tk_aaa111, then again #think tk_aaa111", False, {"think": ["tk_aaa111"], "think-off": []}),
    ("#think", False, {"think": []}),
    ("#now-todo rethink tk_aaa111 pricing #think", True, {"think": []}),
    ("#think-off tk_aaa111 #think tk_bbb222", False, {"think": ["tk_bbb222"], "think-off": ["tk_aaa111"]}),
    ("#thinking tk_aaa111", False, {}),
    ("##think tk_aaa111", False, {}),
    ("x#think tk_aaa111", False, {}),
])
def test_the_tasks_a_tag_names(text, creates, want) -> None:
    assert think_targets(command_text(text), creates) == want


def test_three_hashes_silence_think_and_mute_silences_all() -> None:
    assert think_targets(command_text("###now-todo the pricing #think tk_aaa111"), True) == {}
    assert think_targets(command_text("###think tk_aaa111 #now-todo"), False) == {"think": ["tk_aaa111"]}
    assert think_targets(command_text("#mute #think tk_aaa111"), False) == {}


# ---------------------------------------------------------------------------
# Setting and removing the mark from the chat
# ---------------------------------------------------------------------------


def test_think_with_ids_marks_those_tasks(env) -> None:
    c, root, (t1, t2, t3) = env
    _chat(root, ["hello", f"#think {t1} {t2}"])
    _read_board(c)
    got = {t: _row(c, t) for t in (t1, t2, t3)}
    assert got[t1]["think_at"] and got[t1]["think_by"] == "operator"
    assert got[t2]["think_at"] and not got[t3]["think_at"]
    events = c.app.state.store.query(
        "SELECT actor, field, new_value FROM task_events_mutual WHERE task_id = ? AND field = 'think'", (t1,))
    assert events and events[0]["actor"] == "operator" and f"{AGENT}#2" in events[0]["new_value"]


def test_the_mark_shows_in_the_task_list(env) -> None:
    c, root, (t1, _t2, _t3) = env
    _chat(root, [f"#think {t1}"])
    board = {t["id"]: t for t in _read_board(c)}
    assert board[t1]["think_at"] and board[t1]["think_by"] == "operator"


def test_think_alone_marks_nothing(env) -> None:
    c, root, ids = env
    _chat(root, ["let me #think"])
    _read_board(c)
    assert not any(_row(c, t)["think_at"] for t in ids)
    ledger = (root / "think.csv").read_text(encoding="utf-8")
    assert "unnamed" in ledger


def test_ids_away_from_the_tag_are_not_taken(env) -> None:
    """A pasted log or an earlier mention: only the ids beside the tag count."""
    c, root, (t1, t2, _t3) = env
    _chat(root, [f"<pasted_content>{t1} failed, {t2} too</pasted_content>\nI need to #think about this"])
    _read_board(c)
    assert not _row(c, t1)["think_at"] and not _row(c, t2)["think_at"]
    assert "unnamed" in (root / "think.csv").read_text(encoding="utf-8")


@pytest.mark.parametrize("order,on", [("think-first", False), ("off-first", True)])
def test_think_and_think_off_on_one_id_the_later_tag_wins(env, order, on) -> None:
    c, root, (t1, _t2, _t3) = env
    if not on:
        _mark(c, t1)
    text = (f"#think {t1}, no, #think-off {t1}" if order == "think-first"
            else f"#think-off {t1}, then again #think {t1}")
    _chat(root, [text])
    _read_board(c)
    assert bool(_row(c, t1)["think_at"]) is on


def test_three_hashes_on_another_tag_silence_think(env) -> None:
    c, root, (t1, _t2, _t3) = env
    _chat(root, [f"###pin this, and #think {t1}"])
    _read_board(c)
    assert not _row(c, t1)["think_at"]


def test_think_off_removes_it_and_the_old_tag_is_not_applied_again(env) -> None:
    c, root, (t1, t2, _t3) = env
    _chat(root, [f"#think {t1} {t2}"])
    _read_board(c)
    assert _row(c, t1)["think_at"] and _row(c, t2)["think_at"]
    _chat(root, [f"#think {t1} {t2}", f"#think-off {t1}"])
    _read_board(c)
    assert not _row(c, t1)["think_at"] and _row(c, t2)["think_at"]
    # The operator removes t2's on the board: the old #think stays history.
    c.post(f"/api/tasks/{t2}/update", json={"think": False, "actor": "operator"})
    _read_board(c)
    assert not _row(c, t2)["think_at"]


def test_a_helper_chats_prompt_sets_nothing(env) -> None:
    c, root, (t1, _t2, _t3) = env
    _chat(root, [f"#think {t1}"], agent=OTHER)
    meta = root / "projects" / "alpha" / "chats" / OTHER / "meta.json"
    data = json.loads(meta.read_text(encoding="utf-8"))
    data["helper"] = True
    meta.write_text(json.dumps(data), encoding="utf-8")
    _read_board(c)
    from backend.sessions import helper_ids
    if OTHER not in helper_ids(c.app.state.store):
        pytest.skip("this meta shape does not mark a helper here")
    assert not _row(c, t1)["think_at"]


# ---------------------------------------------------------------------------
# The card a #think message makes
# ---------------------------------------------------------------------------


def test_now_todo_with_think_marks_the_card_the_agent_writes(env) -> None:
    c, root, _ids = env
    _chat(root, ["#now-todo work out the pricing model #think"], answered=False)
    c.app.state.store.rebuild()
    r = c.post("/api/tasks", json={"project": "alpha", "agent_id": AGENT, "title": "Pricing model",
                                   "tags": "ag_decision", "status": "todo"})
    assert r.status_code == 201, r.text
    row = r.json()["metadata"]
    assert row["think_at"] and row["think_by"] == "operator" and row["status"] == "todo"


def test_task_with_think_marks_the_agent_card(env) -> None:
    c, root, _ids = env
    _chat(root, ["#task the pricing question we parked #think"], answered=False)
    c.app.state.store.rebuild()
    r = c.post("/api/tasks", json={"project": "alpha", "agent_id": AGENT, "title": "Pricing question",
                                   "tags": "ag_decision", "description": "which plan tiers"})
    assert r.status_code == 201, r.text
    assert r.json()["metadata"]["think_at"]


def test_a_card_without_think_is_not_marked(env) -> None:
    c, root, _ids = env
    _chat(root, ["#now-todo work out the pricing model"], answered=False)
    c.app.state.store.rebuild()
    r = c.post("/api/tasks", json={"project": "alpha", "agent_id": AGENT, "title": "Pricing model",
                                   "tags": "ag_decision", "status": "todo"})
    assert r.status_code == 201, r.text
    assert not r.json()["metadata"]["think_at"]


def test_an_agent_cannot_set_the_mark_on_create(env) -> None:
    c, root, _ids = env
    _chat(root, ["#task the export bug"], answered=False)
    c.app.state.store.rebuild()
    r = c.post("/api/tasks", json={"project": "alpha", "agent_id": AGENT, "title": "Export bug",
                                   "tags": "ag_bug", "think_at": "2026-11-26T10:00:00", "think_by": AGENT})
    assert r.status_code == 201, r.text
    assert not r.json()["metadata"]["think_at"]


def test_the_servers_now_card_carries_the_mark(env) -> None:
    c, root, _ids = env
    _chat(root, ["#now-todo work out the pricing model #think"])
    cards = [t for t in _read_board(c) if t["agent_id"] == AGENT]
    assert len(cards) == 1 and cards[0]["think_at"] and cards[0]["status"] == "todo"


# ---------------------------------------------------------------------------
# The gate: what an agent is refused, and what stays open
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["doing", "review", "review-later", "done", "done-archived"])
def test_an_agent_status_change_is_refused(env, status) -> None:
    c, _root, (t1, _t2, _t3) = env
    c.post(f"/api/tasks/{t1}/update", json={"auto_manage": "yes", "actor": "operator"})
    _mark(c, t1)
    r = c.post(f"/api/tasks/{t1}/update", json={"status": status, "agent_id": AGENT})
    assert r.status_code == 422 and "«think»" in r.json()["detail"], r.text
    assert "\n" not in r.json()["detail"]
    assert _row(c, t1)["status"] == "todo"


@pytest.mark.parametrize("field", ["lane", "assignee"])
def test_an_agent_lane_or_assignee_change_names_the_mark(env, field) -> None:
    c, _root, (t1, _t2, _t3) = env
    _mark(c, t1)
    r = c.post(f"/api/tasks/{t1}/update", json={field: "UI", "agent_id": AGENT})
    assert r.status_code == 422 and "«think»" in r.json()["detail"]


def test_the_same_status_again_is_not_a_change(env) -> None:
    c, _root, (t1, _t2, _t3) = env
    c.post(f"/api/tasks/{t1}/update", json={"auto_manage": "yes", "actor": "operator"})
    _mark(c, t1)
    r = c.post(f"/api/tasks/{t1}/update", json={"status": "todo", "agent_id": AGENT})
    assert r.status_code == 200, r.text


def test_an_agent_report_and_archive_are_refused(env) -> None:
    c, _root, (t1, _t2, _t3) = env
    _mark(c, t1)
    r = c.post(f"/api/tasks/{t1}/report", json={"agent_id": AGENT, "summary": "done"})
    assert r.status_code == 422 and "«think»" in r.json()["detail"]
    assert not _row(c, t1)["agent_done_at"]
    r = c.post(f"/api/tasks/{t1}/archive", json={"agent_id": AGENT})
    assert r.status_code == 422 and "«think»" in r.json()["detail"]
    assert not _row(c, t1)["archived_at"]


def test_an_agent_cannot_set_or_remove_the_mark(env) -> None:
    c, _root, (t1, t2, _t3) = env
    _mark(c, t1)
    r = c.post(f"/api/tasks/{t1}/update", json={"think": False, "agent_id": AGENT})
    assert r.status_code == 422 and "«think»" in r.json()["detail"]
    assert _row(c, t1)["think_at"]
    r = c.post(f"/api/tasks/{t2}/update", json={"think": True, "agent_id": AGENT})
    assert r.status_code == 422 and not _row(c, t2)["think_at"]


def test_an_agent_still_comments_adds_evidence_and_links(env) -> None:
    c, _root, (t1, t2, _t3) = env
    _mark(c, t1)
    r = c.post(f"/api/tasks/{t1}/update", json={"comment": "two options: per seat or per project", "agent_id": AGENT})
    assert r.status_code == 200, r.text
    r = c.post(f"/api/tasks/{t1}/evidence", json={
        "agent_id": AGENT, "items": [{"kind": "text", "title": "competitor prices", "body": "A: $10, B: $12"}]})
    assert r.status_code == 201, r.text
    r = c.post(f"/api/tasks/{t1}/link", json={"to": t2, "kind": "relates", "agent_id": AGENT})
    assert r.status_code in (200, 201), r.text
    row = _row(c, t1)
    assert row["status"] == "todo" and row["think_at"]


def test_the_operator_is_never_refused(env) -> None:
    c, _root, (t1, _t2, _t3) = env
    _mark(c, t1)
    for body in ({"status": "doing"}, {"lane": "UI"}, {"assignee": "UI"}):
        r = c.post(f"/api/tasks/{t1}/update", json={**body, "actor": "operator"})
        assert r.status_code == 200, r.text
    assert c.post(f"/api/tasks/{t1}/archive", json={"actor": "operator"}).status_code == 200
    assert c.post(f"/api/tasks/{t1}/restore", json={"actor": "operator"}).status_code == 200
    assert _row(c, t1)["status"] == "doing" and _row(c, t1)["think_at"]


def test_after_the_operator_removes_it_the_agent_may_move_again(env) -> None:
    c, _root, (t1, _t2, _t3) = env
    c.post(f"/api/tasks/{t1}/update", json={"auto_manage": "yes", "actor": "operator"})
    _mark(c, t1)
    assert c.post(f"/api/tasks/{t1}/update", json={"status": "doing", "agent_id": AGENT}).status_code == 422
    r = c.post(f"/api/tasks/{t1}/update", json={"think": False, "actor": "operator"})
    assert r.status_code == 200 and not _row(c, t1)["think_at"] and not _row(c, t1)["think_by"]
    r = c.post(f"/api/tasks/{t1}/update", json={"status": "doing", "agent_id": AGENT})
    assert r.status_code == 200, r.text
    assert c.post(f"/api/tasks/{t1}/report", json={"agent_id": AGENT, "summary": "done"}).status_code == 200


def test_a_think_typed_seconds_ago_is_enforced_at_once(env) -> None:
    """The agent's next call after the operator's #think: no board read in between."""
    c, root, (t1, _t2, _t3) = env
    c.post(f"/api/tasks/{t1}/update", json={"auto_manage": "yes", "actor": "operator"})
    _chat(root, [f"#think {t1}"], answered=False)
    r = c.post(f"/api/tasks/{t1}/update", json={"status": "doing", "agent_id": AGENT})
    assert r.status_code == 422 and "«think»" in r.json()["detail"]


def test_a_fresh_install_enforces_a_think_typed_before_anyone_opens_the_board(tmp_path: Path) -> None:
    """No since-stamp: the server makes it at its start, so the first
    #think counts even when no list was ever read."""
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    with TestClient(create_app(data_root=root, watch=False)) as c:
        for name in ("think.json", "now.json", "done.json"):
            assert (root / name).exists(), name
        tid = c.post("/api/tasks", json={"created_date": "2611-26", "created_time": "09:00", "project": "alpha",
                                         "actor": "operator", "title": "Pricing", "status": "todo"}).json()["metadata"]["id"]
        c.post(f"/api/tasks/{tid}/update", json={"auto_manage": "yes", "actor": "operator"})
        d = root / "projects" / "alpha" / "chats" / AGENT
        d.mkdir(parents=True)
        (d / "meta.json").write_text(json.dumps({"agent_id": AGENT, "project": "alpha", "created_date": "2611-26",
                                                 "last_active": _at(1)}), encoding="utf-8")
        (d / "chat.md").write_text(f"# Chat log — {AGENT}\n\n## Turn 1 · {_at(1)}\n**User**: #think {tid}\n",
                                   encoding="utf-8")
        r = c.post(f"/api/tasks/{tid}/update", json={"status": "doing", "agent_id": AGENT})
        assert r.status_code == 422 and "«think»" in r.json()["detail"], r.text


def test_the_operators_done_closes_a_think_task_and_clears_the_mark(env) -> None:
    c, root, (t1, _t2, _t3) = env
    _mark(c, t1)
    _chat(root, [f"#done {t1}"])
    got = c.get(f"/api/done-tags?agent_id={AGENT}").json()
    assert [(t["id"], t["result"]) for t in got["tasks"]] == [(t1, "moved")]
    row = _row(c, t1)
    assert row["status"] == "done" and not row["think_at"] and not row["think_by"]
    events = c.app.state.store.query(
        "SELECT actor, new_value FROM task_events_mutual WHERE task_id = ? AND field = 'think'", (t1,))
    assert {"actor": "operator", "new_value": "think mark cleared by #done"} in events
    # The report #done asks of the agent goes through.
    r = c.post(f"/api/tasks/{t1}/report", json={"agent_id": AGENT, "summary": "the pricing note is written"})
    assert r.status_code == 200, r.text


def test_an_unreadable_ledger_never_fails_the_agents_write(env) -> None:
    c, root, (t1, t2, t3) = env
    for t in (t1, t2):
        c.post(f"/api/tasks/{t}/update", json={"auto_manage": "yes", "actor": "operator"})
    _mark(c, t1)
    (root / "think.csv").write_bytes(b"\xff\xfe\x00garbage\x80\x81")
    # A new #think, so the adoption reads the ledger and fails on it.
    _chat(root, [f"#think {t3}"])
    c.app.state.store.rebuild()
    with pytest.raises(UnicodeDecodeError):
        thinklib.adopt(c.app.state.store)
    r = c.post(f"/api/tasks/{t2}/update", json={"status": "doing", "agent_id": AGENT})
    assert r.status_code == 200, r.text
    r = c.post(f"/api/tasks/{t2}/report", json={"agent_id": AGENT, "summary": "done"})
    assert r.status_code == 200, r.text
    # The mark on the row still decides.
    r = c.post(f"/api/tasks/{t1}/update", json={"status": "doing", "agent_id": AGENT})
    assert r.status_code == 422 and "«think»" in r.json()["detail"]


# ---------------------------------------------------------------------------
# The hook's notice
# ---------------------------------------------------------------------------


def _hook():
    path = Path(__file__).resolve().parents[2] / "scripts" / "hooks" / "capture.py"
    spec = importlib.util.spec_from_file_location("sp_capture_think", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sp_capture_think"] = mod
    spec.loader.exec_module(mod)
    return mod


def _notice(capture, text: str, where: dict | None = None) -> str:
    said = command_text(text)
    commands = list(dict.fromkeys(" ".join(m.group(1).lower().split()) for m in capture._COMMAND_RE.finditer(said)))
    return capture.format_signals({"commands": commands, "turn_number": 1, "task_where": where,
                                   "think": think_targets(said),
                                   "think_card": capture._think_card(said, where)})


def test_refused_braces_make_no_card_and_the_notice_says_so() -> None:
    capture = _hook()
    where = {"now": {"project": "", "lane": "", "refusal": "two projects in braces (a, b): name one"}, "task": None}
    out = _notice(capture, "#now-todo {a} {b} the pricing model #think", where)
    think = next(line for line in out.splitlines() if line.startswith("[slightly-parallel] #think"))
    assert "no card is made and nothing gets the think mark" in think
    assert "carries the think mark" not in think


def test_the_card_is_picked_as_the_server_picks_it() -> None:
    capture = _hook()
    # #now and #task in one message: the #now is the card (pick_task_hit).
    assert capture._think_card(command_text("#task the docs, and #now the pricing #think"), None) == {
        "creates": True, "doing": True, "refused": False}
    assert capture._think_card(command_text("#task the pricing #think"), None)["doing"] is False
    assert capture._think_card(command_text("let me #think"), None)["creates"] is False


def test_the_notice_names_the_tasks_and_the_rule() -> None:
    capture = _hook()
    out = _notice(capture, "#think tk_aaa111 tk_bbb222")
    assert "[slightly-parallel] #think — the server marks tk_aaa111, tk_bbb222" in out
    assert "refuses" in out and "comment" in out and "#think-off" in out


def test_the_notice_with_now_todo_says_the_card_gets_the_mark() -> None:
    out = _notice(_hook(), "#now-todo the pricing model #think")
    assert "the task this message makes carries the think mark" in out and "Do not start it" in out
    assert "[slightly-parallel] #now-todo" in out


def test_the_notice_with_now_says_doing_and_ask_first() -> None:
    out = _notice(_hook(), "#now the pricing model #think")
    think = next(line for line in out.splitlines() if line.startswith("[slightly-parallel] #think"))
    assert "goes to doing, as #now asks" in think and "ask the operator before acting" in think
    assert "Do not start it" not in think


def test_the_notice_for_a_pasted_id_asks_which_task() -> None:
    out = _notice(_hook(), "<pasted_content>tk_aaa111 failed</pasted_content> let me #think")
    assert "no task named: ask the operator which one" in out and "tk_aaa111" not in out


def test_the_notice_alone_asks_which_task() -> None:
    out = _notice(_hook(), "let me #think")
    assert "no task named: ask the operator which one" in out
    off = _notice(_hook(), "#think-off")
    assert "[slightly-parallel] #think-off — no task named" in off


def test_three_hashes_leave_no_think_notice() -> None:
    out = _notice(_hook(), "###now-todo the pricing model #think tk_aaa111")
    assert "#think" not in out and "[slightly-parallel] #now-todo" in out
