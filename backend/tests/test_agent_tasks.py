"""/task — an agent's own card, gated.

1. An agent's create lands in the `agent` column: any other status is a
   422, no status means `agent`.
2. Tags: 1–3 from the closed ``ag_*`` set; the title is ≤ 80 characters.
3. Everything the operator owns is dropped and named back as ``ignored``.
4. The board (house actors) passes untouched.
5. "Drop it": the creating agent may archive its own `agent` card; every
   other status change by an agent stays refused.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app


@pytest.fixture()
def client(tmp_path: Path):
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    app = create_app(data_root=root, watch=False)
    with TestClient(app) as c:
        yield c


def _post(client: TestClient, expect: int = 201, **over) -> dict:
    body = {
        "created_date": "2609-01", "created_time": "21:10", "project": "alpha",
        "agent_id": "cc-a", "title": "Architecture form without a scan",
        "tags": "ag_followup",
        "description": "rn the form accepts an empty trigger_id.\nbackend/routers/architecture.py:architecture_form",
    }
    body.update(over)
    r = client.post("/api/tasks", json=body)
    assert r.status_code == expect, r.text
    return r.json()


def test_an_agent_task_lands_in_the_agent_column(client: TestClient) -> None:
    out = _post(client)
    assert out["metadata"]["status"] == "agent"
    assert out["metadata"]["tags"] == "ag_followup"
    assert out["description"].startswith("rn the form")
    assert "ignored" not in out
    explicit = _post(client, created_time="21:11", status="agent")
    assert explicit["metadata"]["status"] == "agent"
    wrong = _post(client, expect=422, created_time="21:12", status="todo")
    assert "agent" in wrong["detail"] and "todo" in wrong["detail"]


def test_tags_come_from_the_closed_set_one_to_three(client: TestClient) -> None:
    none = _post(client, expect=422, tags="")
    assert "ag_debt" in none["detail"]
    unknown = _post(client, expect=422, tags="ag_followup, urgent")
    assert "urgent" in unknown["detail"]
    many = _post(client, expect=422, tags="ag_debt,ag_bug,ag_idea,ag_decision")
    assert "at most 3" in many["detail"]
    three = _post(client, tags="ag_debt, ag_decision ,ag_idea")
    assert three["metadata"]["tags"] == "ag_debt,ag_decision,ag_idea"


def test_title_is_required_and_short(client: TestClient) -> None:
    assert "title" in _post(client, expect=422, title="")["detail"]
    long = _post(client, expect=422, title="x" * 81)
    assert "80" in long["detail"]


def test_operator_metadata_is_dropped_and_named(client: TestClient) -> None:
    out = _post(
        client, priority="high", impact="high", effort="L", sprint_id="sp_1",
        due_date="2609-09", position="7", auto_manage="yes", remember="yes",
    )
    assert out["ignored"] == [
        "auto_manage", "due_date", "effort", "impact", "position", "priority",
        "remember", "sprint_id",
    ]
    meta = out["metadata"]
    assert meta["priority"] in ("", None) and meta["sprint_id"] in ("", None)
    assert str(meta.get("auto_manage") or "") == ""


# ---------------------------------------------------------- the operator's message
# The column and the lane come from what the operator typed in the chat:
# ``#task`` → the agent column, ``#now`` → doing; ``{lane}`` names a lane the
# board has. The agent's own lane or assignee is dropped and named back.


def _chat(root: Path, agent: str, user_text: str) -> None:
    d = root / "projects" / "alpha" / "chats" / agent
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps({
        "agent_id": agent, "agent_name": "lead", "project": "alpha",
        "created_date": "2609-01", "last_active": "2026-09-01T11:00:00",
    }), encoding="utf-8")
    (d / "chat.md").write_text(
        f"# Chat log — {agent}\n\n## Turn 1 · 2026-09-01T10:01:00\n**User**: hello\n**Agent**: hi\n"
        f"\n## Turn 2 · 2026-09-01T10:02:00\n**User**: {user_text}\n", encoding="utf-8")


def _board(root: Path, user_text: str, lanes: tuple[str, ...] = ("Bugs", "Kanban Board")) -> TestClient:
    _chat(root, "cc-a", user_text)
    c = TestClient(create_app(data_root=root, watch=False))
    c.__enter__()
    for i, lane in enumerate(lanes):
        c.post("/api/tasks", json={"created_date": "2609-01", "created_time": f"08:0{i}", "project": "alpha",
                                   "agent_id": "operator", "title": f"a {lane} card", "status": "todo", "assignee": lane})
    return c


def test_task_takes_the_lane_the_operator_named_in_braces(tmp_path: Path) -> None:
    root = tmp_path / "data"
    c = _board(root, "#task {bugs} the form accepts an empty trigger_id")
    out = _post(c, assignee="Infra")
    meta = out["metadata"]
    assert meta["status"] == "agent"
    assert meta["lane"] == "Bugs" and meta["assignee"] == "Bugs"     # the board's spelling
    assert "assignee" in out["ignored"]                               # the agent's own naming is dropped
    c.__exit__(None, None, None)


def test_a_lane_the_board_does_not_have_is_refused_with_the_list(tmp_path: Path) -> None:
    root = tmp_path / "data"
    c = _board(root, "#task {ux} the form accepts an empty trigger_id")
    r = c.post("/api/tasks", json={"created_date": "2609-01", "created_time": "21:10", "project": "alpha",
                                   "agent_id": "cc-a", "title": "x", "tags": "ag_bug"})
    assert r.status_code == 422, r.text
    assert "'ux'" in r.text and "Bugs" in r.text and "Kanban Board" in r.text and "ask the operator" in r.text
    c.__exit__(None, None, None)


def test_now_starts_the_task_in_doing_in_its_own_lane_today(tmp_path: Path) -> None:
    from datetime import date
    root = tmp_path / "data"
    c = _board(root, "#now fix the login timeout")
    wrong = _post(c, expect=422, status="agent", description="")
    assert "doing" in wrong["detail"]
    out = _post(c, created_time="21:11", description="")
    meta = out["metadata"]
    # The text is the operator's message, as written; the agent only titles it.
    assert out["description"] == "#now fix the login timeout"
    assert meta["status"] == "doing" and meta["lane"] == "Now" and meta["assignee"] == "Now"
    assert meta["today_on"] == date.today().isoformat()
    events = c.get(f"/api/tasks/{meta['id']}/events").json()
    started = [e for e in (events.get("events") if isinstance(events, dict) else events) if e.get("field") == "started"]
    assert started and "#now" in started[0]["new_value"] and "cc-a" in started[0]["new_value"]
    c.__exit__(None, None, None)


def test_now_with_a_lane_and_the_lane_from_settings(tmp_path: Path) -> None:
    from backend import app_settings
    root = tmp_path / "data"
    c = _board(root, "#now {kanban board} the cards do not sort")
    assert _post(c, description="")["metadata"]["lane"] == "Kanban Board"
    c.__exit__(None, None, None)
    app_settings.save(root, {"tasks.now_lane": "Chat"})
    c = _board(root, "#now fix the login timeout", lanes=())
    assert _post(c, created_time="21:12", description="")["metadata"]["lane"] == "Chat"
    c.__exit__(None, None, None)


def test_a_now_task_text_written_by_the_agent_is_refused(tmp_path: Path) -> None:
    c = _board(tmp_path / "data", "#now fix the login timeout, it drops after ten minutes")
    r = _post(c, expect=422)            # the helper sends a description of its own
    assert "operator's message" in r["detail"] and "title and tags only" in r["detail"]
    c.__exit__(None, None, None)


@pytest.mark.parametrize(("command", "column"), [
    ("#now-todo", "todo"), ("#now-to-do", "todo"), ("#now-next", "next"), ("#now-backlog", "backlog"),
    ("#now-review", "review"), ("#now-parked", "parked"), ("#now-done", "done"), ("#now-doing", "doing"),
])
def test_now_with_a_column_files_the_message_there(tmp_path: Path, command: str, column: str) -> None:
    message = f"the login drops after ten minutes, look later {command}"
    c = _board(tmp_path / "data", message)
    wrong = _post(c, expect=422, status="doing" if column != "doing" else "todo", description="")
    assert column in wrong["detail"]
    out = _post(c, description="", created_time="21:13")
    meta = out["metadata"]
    assert meta["status"] == column and meta["lane"] == "Now" and out["description"] == message
    # Only the task the chat starts on is marked for today.
    assert bool(meta.get("today_on")) == (column == "doing")
    events = c.get(f"/api/tasks/{meta['id']}/events").json()
    events = events.get("events") if isinstance(events, dict) else events
    verb = "started" if column == "doing" else "filed"
    assert any(e.get("field") == verb for e in events)
    c.__exit__(None, None, None)


def test_without_a_command_the_card_is_an_agent_card_with_no_lane(tmp_path: Path) -> None:
    root = tmp_path / "data"
    c = _board(root, "a plain message, no command")
    out = _post(c, assignee="Bugs")
    assert out["metadata"]["status"] == "agent" and str(out["metadata"].get("lane") or "") == ""
    assert "assignee" in out["ignored"]
    c.__exit__(None, None, None)


def test_the_board_passes_untouched(client: TestClient) -> None:
    board = _post(client, agent_id="operator", status="todo", tags="", priority="high")
    assert board["metadata"]["status"] == "todo" and board["metadata"]["priority"] == "high"
    assert "ignored" not in board


def test_drop_it_archives_only_the_agents_own_agent_card(client: TestClient) -> None:
    tid = _post(client)["metadata"]["id"]
    # the creating agent may not move it anywhere else
    r = client.post(f"/api/tasks/{tid}/update", json={"status": "todo", "actor": "cc-a"})
    assert r.status_code == 422
    # another agent may not archive it
    r = client.post(f"/api/tasks/{tid}/update", json={"status": "done-archived", "actor": "cc-b"})
    assert r.status_code == 422
    # the creator may
    r = client.post(f"/api/tasks/{tid}/update", json={"status": "done-archived", "actor": "cc-a"})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/tasks/{tid}").json()["metadata"]["status"] == "done-archived"
    # once the operator has classified it, the exception is gone
    other = _post(client, created_time="21:30")["metadata"]["id"]
    client.post(f"/api/tasks/{other}/update", json={"status": "todo", "actor": "operator"})
    r = client.post(f"/api/tasks/{other}/update", json={"status": "done-archived", "actor": "cc-a"})
    assert r.status_code == 422


def test_agent_is_a_known_status_for_the_operator_too(client: TestClient) -> None:
    out = _post(client, agent_id="operator", status="agent", tags="")
    assert out["metadata"]["status"] == "agent"
    r = client.post(f"/api/tasks/{out['metadata']['id']}/update", json={"status": "next", "actor": "operator"})
    assert r.status_code == 200


def test_the_sprint_is_the_operators_on_update_too(client: TestClient) -> None:
    """The create gate drops `sprint_id` and the contract says sprints are the
    operator's; the update gate used to take it from an agent."""
    tid = _post(client)["metadata"]["id"]
    r = client.post(f"/api/tasks/{tid}/update", json={"sprint_id": "sp_1", "actor": "cc-a"})
    assert r.status_code == 422 and "task_report" in r.json()["detail"]
    assert client.get(f"/api/tasks/{tid}").json()["metadata"].get("sprint_id", "") in ("", None)
    # the operator still plans
    assert client.post(f"/api/tasks/{tid}/update",
                       json={"sprint_id": "sp_1", "actor": "operator"}).status_code == 200


def test_a_column_suffix_belongs_to_now_only() -> None:
    """#task-done is not a #task: only #now takes a column."""
    from backend.sessions import task_command
    assert task_command("look later #task-done") == ("", "", "")
    assert task_command("look later #now-done {ui}") == ("now", "ui", "done")
    assert task_command("#task {ui} the cards") == ("task", "ui", "agent")


def test_comments_go_after_the_operators_text_which_stays_as_written(tmp_path: Path) -> None:
    c = _board(tmp_path / "data", "#now fix the login timeout")
    tid = _post(c, description="", title="Login timeout")["metadata"]["id"]
    up = lambda body: c.post(f"/api/tasks/{tid}/update", json={"actor": "cc-a", **body})  # noqa: E731
    assert up({"comment": "the timeout is in auth/session.py"}).status_code == 200
    assert up({"comment": "fixed: 30 min, a test added"}).status_code == 200
    assert c.get(f"/api/tasks/{tid}").json()["description"] == (
        "#now fix the login timeout\n\n--- comment from agent:\nthe timeout is in auth/session.py"
        "\n\n--- comment from agent:\nfixed: 30 min, a test added")
    refused = up({"description": "my own words"})
    assert refused.status_code == 422 and "comment" in refused.json()["detail"]
    assert up({"comment": "  "}).status_code == 422
    c.__exit__(None, None, None)


def test_the_same_task_twice_is_one_task_answered_200(client: TestClient) -> None:
    """tasklib.create_task: a repeat finds the task (existing, 200), for the
    board and for an agent's /task alike."""
    board = {"created_date": "2609-01", "created_time": "09:00", "project": "alpha",
             "agent_id": "operator", "title": "Same", "status": "todo"}
    first = client.post("/api/tasks", json=board)
    again = client.post("/api/tasks", json=board)
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json()["existing"] is True and again.json()["metadata"]["id"] == first.json()["metadata"]["id"]
    mine = _post(client)
    assert _post(client, expect=200)["metadata"]["id"] == mine["metadata"]["id"]
