"""Audit round 3, the agent-to-task zone: the update gate, task_commits,
the MCP argument shapes, #done's answer, the hook's identity line."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import gitwork, mcp
from backend.actors import AGENT_REFUSED
from backend.hookshared import escape_content
from backend.sessions import task_command
from tests.conftest import git_env, git_repo
from tests.test_commit_tasks import _chat, _commit, _project, _task

AGENT = "cc-round3aud"
_HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"


def _mine(client: TestClient, title: str = "Mine") -> str:
    r = client.post("/api/tasks", json={"created_date": "2611-04", "created_time": "10:00", "project": "ALPHA",
                                        "agent_id": AGENT, "title": title, "tags": "ag_idea"})
    assert r.status_code == 201, r.text
    return r.json()["metadata"]["id"]


# -- the update gate ---------------------------------------------------------

@pytest.mark.parametrize("field,value", [
    ("lane", "Mine"), ("assignee", "Mine"), ("impact", "5"), ("effort", "1"),
    ("projects", "ALPHA,BETA"), ("position", "0"), ("novelty", "3"), ("tokens", "2"), ("remember", "x"),
])
def test_an_agent_does_not_place_or_plan_a_card(client: TestClient, field: str, value: str) -> None:
    tid = _mine(client)
    r = client.post(f"/api/tasks/{tid}/update", json={"agent_id": "cc-otheragent", field: value})
    assert r.status_code == AGENT_REFUSED and "operator's switch" in r.json()["detail"], r.text
    row = client.get(f"/api/tasks/{tid}").json()["metadata"]
    assert str(row.get(field) or "") in ("", "Now") or field == "projects"
    assert "BETA" not in str(row.get("projects") or "")


def test_an_agents_tags_stay_in_its_list(client: TestClient) -> None:
    tid = _mine(client)
    r = client.post(f"/api/tasks/{tid}/update", json={"agent_id": AGENT, "tags": "urgent"})
    assert r.status_code == AGENT_REFUSED and "ag_" in r.json()["detail"]
    assert client.post(f"/api/tasks/{tid}/update", json={"agent_id": AGENT, "tags": "ag_bug,ag_debt"}).status_code == 200
    assert client.get(f"/api/tasks/{tid}").json()["metadata"]["tags"] == "ag_bug,ag_debt"


def test_a_list_for_a_text_field_is_refused_not_stored_as_its_repr(client: TestClient) -> None:
    tid = _task(client, "Shapes")
    r = client.post(f"/api/tasks/{tid}/update", json={"title": ["x"]})
    assert r.status_code == 422 and "not a list" in r.json()["detail"]
    assert client.post(f"/api/tasks/{tid}/update", json={"tags": ["ag_bug"]}).status_code == 422
    assert client.get(f"/api/tasks/{tid}").json()["metadata"]["title"] == "Shapes"
    r = client.post(f"/api/tasks/{tid}/report", json={"agent_id": AGENT, "summary": ["x"]})
    assert r.status_code == 422 and "one line of text" in r.json()["detail"]


def test_the_turn_refusal_points_at_comment(client: TestClient) -> None:
    tid = _task(client, "Rounds")
    r = client.post(f"/api/tasks/{tid}/update", json={"agent_id": AGENT, "turn": {"n": 1, "text": "x"}})
    assert r.status_code == AGENT_REFUSED and "comment" in r.json()["detail"]


# -- task_commits -------------------------------------------------------------

def test_task_commits_links_only_commits_that_exist_and_are_the_writers(client: TestClient, data_root: Path) -> None:
    repo = _project(client, data_root)
    mine, other = _task(client, "Mine"), _task(client, "Other")
    t0 = datetime.now() - timedelta(minutes=30)
    home = data_root.parent
    plain = _commit(repo, "a.py", "a change", t0, home)
    theirs = _commit(repo, "b.py", "their change\n\nAgent: cc-someoneelse", t0 + timedelta(minutes=1), home)
    signed = _commit(repo, "c.py", f"signed\n\nTask: {other}\nAgent: {AGENT}", t0 + timedelta(minutes=2), home)
    gitwork.forget()
    me = {"agent_id": AGENT}
    r = client.post(f"/api/tasks/{mine}/commits", json={**me, "shas": ["deadbee"]})
    assert r.status_code == 422 and "not a commit of the project's repository" in r.json()["detail"]
    r = client.post(f"/api/tasks/{mine}/commits", json={**me, "shas": [theirs[:7]]})
    assert r.status_code == 422 and "cc-someoneelse" in r.json()["detail"]
    r = client.post(f"/api/tasks/{mine}/commits", json={**me, "shas": [signed]})
    assert r.status_code == 422 and other in r.json()["detail"]
    r = client.post(f"/api/tasks/{mine}/commits", json={**me, "shas": [plain[:7]]})
    assert r.status_code == 200 and r.json()["linked"] == [plain[:7]]
    # The operator links another chat's commit; a signed one still counts for its task only.
    assert client.post(f"/api/tasks/{mine}/commits", json={"shas": [theirs]}).status_code == 200
    assert client.post(f"/api/tasks/{mine}/commits", json={"shas": [signed]}).status_code == 422


# -- #done's answer -----------------------------------------------------------

def test_done_names_a_typed_id_that_is_no_task(client: TestClient, data_root: Path) -> None:
    repo = _project(client, data_root)
    (data_root / "done.json").write_text('{"since": "2000-01-01T00:00:00"}', encoding="utf-8")
    t0 = datetime.now() - timedelta(minutes=10)
    _chat(data_root, AGENT, repo, [(t0, "hello"), (t0 + timedelta(minutes=1), "#done tk_nosuch12")])
    client.app.state.store.rebuild()
    got = client.get(f"/api/done-tags?agent_id={AGENT}").json()
    assert got["unnamed"] is True and got["unknown"] == ["tk_nosuch12"]
    assert "tk_nosuch12 is not a task on the board" in got["next"]


def test_done_on_an_archived_task_asks_no_report(client: TestClient, data_root: Path) -> None:
    repo = _project(client, data_root)
    (data_root / "done.json").write_text('{"since": "2000-01-01T00:00:00"}', encoding="utf-8")
    tid = _task(client, "Gone")
    assert client.post(f"/api/tasks/{tid}/archive", json={}).status_code == 200
    t0 = datetime.now() - timedelta(minutes=10)
    _chat(data_root, AGENT, repo, [(t0, f"{tid} look"), (t0 + timedelta(minutes=1), "#done")])
    client.app.state.store.rebuild()
    got = client.get(f"/api/done-tags?agent_id={AGENT}").json()
    assert [t["result"] for t in got["tasks"]] == ["archived"]
    assert "no report" in got["next"] and "task_report" not in got["next"]


# -- #now and #task in one message --------------------------------------------

def test_now_wins_over_task_in_one_message() -> None:
    assert task_command("#now fix the login. And #task later: docs")[0] == "now"
    assert task_command("#task later: docs, then #now fix it")[0] == "now"
    assert task_command("#task later: docs")[0] == "task"
    assert task_command("#now-todo x and #task y") == ("now", "", "todo")


# -- the MCP translator's shapes ------------------------------------------------

def test_a_string_for_a_list_argument_is_one_item() -> None:
    assert mcp._list({"shas": "abc1234"}, "shas") == ["abc1234"]
    assert mcp._list({"shas": ["a", "b"]}, "shas") == ["a", "b"]
    assert mcp._list({}, "shas") == []
    with pytest.raises(mcp.ApiError):
        mcp._list({"shas": 5}, "shas")


def test_a_wrongly_shaped_argument_is_the_tools_answer_not_a_protocol_error() -> None:
    class Boom:
        def call(self, name, args):
            raise TypeError("'str' object is not a mapping")

        def _by_name(self, out):
            return out

    out = mcp.handle(Boom(), {"id": 1, "method": "tools/call", "params": {"name": "write_entry", "arguments": {"fields": "x"}}})
    assert out["result"]["isError"] is True and "wrong shape" in out["result"]["content"][0]["text"]
    out = mcp.handle(Boom(), {"id": 2, "method": "tools/call", "params": {"name": "tasks", "arguments": "x"}})
    assert out["result"]["isError"] is True and "object" in out["result"]["content"][0]["text"]


# -- the hook -------------------------------------------------------------------

def _capture():
    spec = importlib.util.spec_from_file_location("sp_capture_round3", _HOOKS / "capture.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sp_capture_round3"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_the_identity_line_comes_on_the_first_turn_the_model_sees(tmp_path: Path) -> None:
    capture = _capture()
    root = tmp_path / "data"
    root.mkdir()
    cap = capture.TurnCapture(root, "alpha", "cc-abc12345")
    assert cap.open_turn("#usage", quiet=True)["identity"] is None
    cap.complete_turn("")
    assert cap.open_turn("hello")["identity"]["agent_id"] == "cc-abc12345"
    cap.complete_turn("hi")
    assert cap.open_turn("more")["identity"] is None


def test_a_lone_surrogate_does_not_lose_the_turn(tmp_path: Path) -> None:
    capture = _capture()
    root = tmp_path / "data"
    root.mkdir()
    cap = capture.TurnCapture(root, "alpha", "cc-abc12345")
    signals = cap.open_turn("#now fix \ud83d it")
    assert signals["commands"] == ["now"]
    text = (cap.folder / "chat.md").read_text(encoding="utf-8")
    assert "#now fix ? it" in text
    assert escape_content("a\ud83db") == "a?b"


def test_the_contract_is_the_composition_of_its_parts() -> None:
    from backend import contract_parts
    repo = Path(__file__).resolve().parents[2]
    parts = contract_parts.load_parts(repo)
    assert contract_parts.compose(parts) == (repo / contract_parts.CONTRACT_FILE).read_text(encoding="utf-8")
    assert json.dumps(git_env()) and git_repo  # the helpers stay imported for the commit tests


# -- after the Codex review ---------------------------------------------------

def test_the_turn_route_is_the_operators_too(client: TestClient) -> None:
    tid = _task(client, "Rounds")
    r = client.post(f"/api/tasks/{tid}/turn", json={"agent_id": AGENT, "text": "a new round"})
    assert r.status_code == AGENT_REFUSED and "comment" in r.json()["detail"]
    assert client.post(f"/api/tasks/{tid}/turn", json={"text": "a new round"}).status_code == 201


def test_an_agents_tags_join_the_operators_and_replace_only_its_own(client: TestClient) -> None:
    tid = _task(client, "Tagged")
    assert client.post(f"/api/tasks/{tid}/update", json={"tags": "urgent,ag_idea"}).status_code == 200
    assert client.post(f"/api/tasks/{tid}/update", json={"agent_id": AGENT, "tags": "ag_bug"}).status_code == 200
    assert client.get(f"/api/tasks/{tid}").json()["metadata"]["tags"] == "urgent,ag_bug"
    assert client.post(f"/api/tasks/{tid}/update", json={"agent_id": AGENT, "tags": ""}).status_code == 200
    assert client.get(f"/api/tasks/{tid}").json()["metadata"]["tags"] == "urgent"


def test_a_task_without_text_gets_its_document_on_the_first_turn(client: TestClient) -> None:
    tid = _task(client, "Bare")
    r = client.post(f"/api/tasks/{tid}/turn", json={"text": "round two"})
    assert r.status_code == 201, r.text
    got = client.get(f"/api/tasks/{tid}").json()
    assert got["metadata"]["md_ref"] and "round two" in got["description"]


def test_a_done_whose_card_is_still_being_written_is_pending_not_the_one_before(client: TestClient, data_root: Path, monkeypatch) -> None:
    from backend import nowlib
    repo = _project(client, data_root)
    for name in ("now.json", "done.json"):
        (data_root / name).write_text('{"since": "2000-01-01T00:00:00"}', encoding="utf-8")
    t1 = _task(client, "First")
    t0 = datetime.now() - timedelta(minutes=30)
    _chat(data_root, AGENT, repo, [(t0, f"{t1} go"), (t0 + timedelta(minutes=1), "#done"),
                                   (t0 + timedelta(minutes=5), "#now build the export"), (t0 + timedelta(minutes=6), "#done")])
    client.app.state.store.rebuild()
    real = nowlib._write_card

    def flaky(store, tag):
        raise OSError("disk is busy")
    monkeypatch.setattr(nowlib, "_write_card", flaky)
    got = client.get(f"/api/done-tags?agent_id={AGENT}").json()
    assert got.get("pending") is True and got["tasks"] == [] and got["turn"] == 4
    monkeypatch.setattr(nowlib, "_write_card", real)
    client.app.state.store.rebuild()
    got = client.get(f"/api/done-tags?agent_id={AGENT}").json()
    assert got["turn"] == 4 and [t["result"] for t in got["tasks"]] == ["moved"]
    assert got["tasks"][0]["title"].startswith("build the export")


def test_a_stored_recurrence_past_the_calendar_does_not_block_done(client: TestClient) -> None:
    tid = _task(client, "Repeats")
    rows_path = client.app.state.store.data_root / "tasks.csv"
    text = rows_path.read_text(encoding="utf-8")
    header = text.splitlines()[0].split(",")
    i = header.index("resurface_every_days")
    lines = text.splitlines()
    for n, line in enumerate(lines[1:], 1):
        if line.startswith(tid):
            cells = line.split(",")
            cells[i] = "999999999"
            lines[n] = ",".join(cells)
    rows_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    client.app.state.store.rebuild()
    r = client.post(f"/api/tasks/{tid}/update", json={"status": "done"})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/tasks/{tid}").json()["metadata"]["status"] == "done"


def test_after_the_now_card_an_agent_files_findings_in_the_agent_column(client: TestClient, data_root: Path) -> None:
    """While the operator's #now is still the latest message, the agent's
    later creates were refused ("the operator's #now puts this task in
    doing"): the findings of the work could not go onto the board."""
    repo = _project(client, data_root)
    (data_root / "now.json").write_text('{"since": "2000-01-01T00:00:00"}', encoding="utf-8")
    t0 = datetime.now() - timedelta(minutes=10)
    _chat(data_root, AGENT, repo, [(t0, "#now audit the task code")])
    client.app.state.store.rebuild()
    mk = lambda title, **kw: client.post("/api/tasks", json={"created_date": "2611-04", "created_time": "10:00", "project": "ALPHA",
                                                           "agent_id": AGENT, "title": title, "tags": "ag_debt", **kw})
    r = mk("A finding", status="agent")
    assert r.status_code == AGENT_REFUSED and "#now puts this task" in r.json()["detail"]
    first = mk("Audit the task code")
    assert first.status_code == 201 and first.json()["metadata"]["status"] == "doing"
    client.app.state.store.rebuild()
    r = mk("A finding", status="agent")
    assert r.status_code == 201, r.text
    assert r.json()["metadata"]["status"] == "agent" and not r.json()["metadata"].get("lane")
