"""Moving a task between projects (tk_d1d25a4d step 3, note nt_258a7ed7 §3
«The move»): POST /api/tasks/{id}/move and MCP task_move.

Fixture: chat A from ALPHA joined BETA; GAMMA is no project of A's. The id
is kept, ``projects`` loses the old project and its board drops the card,
the history says «moved from A to B», the lane stays only where the new
board has it, a topic and a stack of the old project are let go. Refused
in one line, writing nothing: a level below 3, a project the agent is not
in, a done or archived task.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import mcp
from backend.server import create_app
from tests.conftest import choose_new_topic, make_chat

pytestmark = pytest.mark.strict_membership

A = "cc-aaaa1111"
VIA = {mcp.VIA_HEADER: mcp.VIA_VALUE}
TASK = "tk_alpha_auth"      # ALPHA, doing


def tree(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and not p.name.endswith(".lock")}


@pytest.fixture()
def world(data_root: Path):
    (data_root / "projects" / "GAMMA").mkdir(parents=True)
    make_chat(data_root, "ALPHA", A, [("2026-11-20T10:00:00", "start", "ok")])
    with TestClient(create_app(data_root=data_root, watch=False)) as c:
        assert c.post(f"/api/agents/{A}/membership", json={"op": "join", "project": "BETA"}).status_code == 200
        # Lanes: ALPHA's card in «ui»; BETA's board has «docs».
        assert c.post(f"/api/tasks/{TASK}/update", json={"actor": "operator", "lane": "ui"}).status_code == 200
        assert c.post("/api/tasks/tk_beta_x/update", json={"actor": "operator", "lane": "docs"}).status_code == 200
        yield c, data_root


def _level(c: TestClient, n: int) -> None:
    assert c.post(f"/api/agents/{A}/membership", json={"op": "level", "value": n}).status_code == 200


def _board(c: TestClient, project: str) -> set[str]:
    return {t["id"] for t in c.get("/api/tasks", params={"project": project}).json()["tasks"]}


def _events(c: TestClient, tid: str) -> list[dict]:
    got = c.get(f"/api/tasks/{tid}/events").json()
    return got.get("events", got) if isinstance(got, dict) else got


def test_the_operator_moves_a_task_and_it_keeps_its_id(world) -> None:
    c, _root = world
    assert TASK in _board(c, "ALPHA")
    r = c.post(f"/api/tasks/{TASK}/move", json={"actor": "operator", "to": "BETA"})
    assert r.status_code == 200, r.text
    got = r.json()
    assert (got["task_id"], got["from"], got["to"], got["projects"]) == (TASK, "ALPHA", "BETA", "BETA")
    assert got["lane_cleared"] and "its lane ui is not on BETA's board: cleared" in got["said"]
    assert TASK not in _board(c, "ALPHA") and TASK in _board(c, "BETA")
    row = c.get(f"/api/tasks/{TASK}").json()["metadata"]
    assert (row["id"], row["project"], row["status"], row["lane"] or "") == (TASK, "BETA", "doing", "")
    texts = [(e["field"], e.get("old_value") or "", e.get("new_value") or "") for e in _events(c, TASK)]
    assert ("project", "ALPHA", "BETA") in texts
    assert ("moved", "", "from ALPHA to BETA, by the operator") in texts


def test_a_lane_the_new_board_has_is_kept(world) -> None:
    c, _root = world
    assert c.post(f"/api/tasks/{TASK}/update", json={"actor": "operator", "lane": "Docs"}).status_code == 200
    got = c.post(f"/api/tasks/{TASK}/move", json={"actor": "operator", "to": "BETA"}).json()
    assert got["lane"] == "docs" and not got["lane_cleared"] and got["where"] == f"{TASK} → BETA · lane docs"


def test_a_stack_and_a_topic_of_the_old_project_are_let_go(world) -> None:
    c, root = world
    store = c.app.state.store
    ep = choose_new_topic(store, root, "ALPHA", A, [("2026-11-20T10:00:00", "start", "ok"),
                                                    ("2026-11-20T10:05:00", "#entrypoint the install film", "ok")])
    assert c.post(f"/api/tasks/{TASK}/topic", json={"entrypoint_id": ep}).status_code == 200
    assert c.post(f"/api/tasks/{TASK}/update", json={"actor": "operator", "stack_id": "st_alpha"}).status_code == 200
    got = c.post(f"/api/tasks/{TASK}/move", json={"actor": "operator", "to": "BETA"}).json()
    assert got["topic_dropped"] and got["stack_dropped"], got
    assert f"its topic {ep} is ALPHA's: let go" in got["said"] and "its stack st_alpha stays in ALPHA" in got["said"]
    assert c.get(f"/api/tasks/{TASK}").json()["metadata"].get("stack_id") in ("", None)


def test_an_agent_at_level_three_moves_between_its_projects(world) -> None:
    c, _root = world
    _level(c, 3)
    r = c.post(f"/api/tasks/{TASK}/move", json={"agent_id": A, "to": "BETA"}, headers=VIA)
    assert r.status_code == 200, r.text
    texts = [(e["field"], e.get("new_value") or "") for e in _events(c, TASK)]
    assert ("moved", f"from ALPHA to BETA, by {A}") in texts


@pytest.mark.parametrize("level,to,status,line", [
    (2, "BETA", 403, f"agent {A} may not move tasks (level 2); the operator raises it to level 3 on the agent card"),
    (1, "BETA", 403, f"agent {A} may not move tasks (level 1); the operator raises it to level 3 on the agent card"),
    (3, "GAMMA", 403, f"agent {A} is not a member of GAMMA; its projects: ALPHA, BETA. "
                      "The operator adds it on the agent card"),
    (3, "NOWHERE", 404, "no project «NOWHERE»"),
    (3, "ALPHA", 409, f"{TASK} is in ALPHA already"),
])
def test_refusals_write_nothing(world, level: int, to: str, status: int, line: str) -> None:
    c, root = world
    if level != 2:
        _level(c, level)
    before = tree(root)
    r = c.post(f"/api/tasks/{TASK}/move", json={"agent_id": A, "to": to}, headers=VIA)
    assert (r.status_code, r.json()["detail"]) == (status, line)
    assert tree(root) == before


@pytest.mark.parametrize("task", ["tk_alpha_cyr", "tk_alpha_old"])   # done; done and archived
def test_a_closed_task_is_not_moved(world, task: str) -> None:
    c, root = world
    before = tree(root)
    r = c.post(f"/api/tasks/{task}/move", json={"actor": "operator", "to": "BETA"})
    assert (r.status_code, r.json()["detail"]) == (409, f"{task} is done or archived: a closed task is not moved")
    assert tree(root) == before


def test_a_task_of_a_project_the_agent_is_not_in_is_not_moved(world) -> None:
    c, root = world
    _level(c, 3)
    assert c.post("/api/tasks/tk_beta_x/move", json={"actor": "operator", "to": "GAMMA"}).status_code == 200
    before = tree(root)
    r = c.post("/api/tasks/tk_beta_x/move", json={"agent_id": A, "to": "BETA"}, headers=VIA)
    assert (r.status_code, r.json()["detail"]) == (
        403, f"agent {A} is not a member of GAMMA; this task is GAMMA's. The operator adds it on the agent card")
    assert tree(root) == before


def test_a_task_shown_on_a_member_project_may_be_moved_by_a_member(world) -> None:
    # Answer (a) to B3: «member of both» is a member of the task's project or
    # of any of its projects, and of the target.
    c, _root = world
    _level(c, 3)
    assert c.post("/api/tasks/tk_beta_x/move", json={"actor": "operator", "to": "GAMMA"}).status_code == 200
    assert c.post("/api/tasks/tk_beta_x/update", json={"actor": "operator", "projects": "GAMMA,BETA"}).status_code == 200
    r = c.post("/api/tasks/tk_beta_x/move", json={"agent_id": A, "to": "ALPHA"}, headers=VIA)
    assert r.status_code == 200, r.text
    assert r.json()["from"] == "GAMMA" and r.json()["projects"] == "ALPHA,BETA"


def test_the_wrong_shape_of_to(world) -> None:
    c, root = world
    before = tree(root)
    for body in ({"actor": "operator", "to": ["BETA"]}, {"actor": "operator"}, {"actor": "operator", "to": 5}):
        r = c.post(f"/api/tasks/{TASK}/move", json=body)
        assert r.status_code == 422, r.text
    assert tree(root) == before


def test_the_rest_of_the_card_goes_with_it_or_is_let_go_and_said(world) -> None:
    # The critic of 54c217ee: the move left sprint_id, the milestone link and
    # the notes' and evidence's project on A, and a stack's next card was not
    # made its head.
    c, root = world
    store = c.app.state.store
    assert c.post(f"/api/tasks/{TASK}/update", json={"actor": "operator", "sprint_id": "sp_alpha"}).status_code == 200
    # A stack of two cards in one column: TASK and another ALPHA card.
    other = c.post("/api/tasks", json={"project": "ALPHA", "title": "Next in the stack", "status": "doing",
                                       "actor": "operator", "created_date": "2611-20", "created_time": "10:00"})
    other_id = other.json()["metadata"]["id"]
    for tid, pos in ((TASK, "1"), (other_id, "2")):
        r = c.post(f"/api/tasks/{tid}/update", json={"actor": "operator", "stack_id": "st_alpha", "position": pos})
        assert r.status_code == 200, r.text
    r = c.post("/api/milestones", json={"project": "ALPHA", "title": "Alpha out", "outcome": "x", "check": "x",
                                        "target_date": "2026-12-01", "tasks": [TASK]})
    assert r.status_code == 201, r.text
    mid = r.json()["milestone"]["id"]
    assert c.post(f"/api/tasks/{TASK}/notes", json={"type": "article", "body": "1) A note"}).status_code == 201
    got = c.post(f"/api/tasks/{TASK}/move", json={"actor": "operator", "to": "BETA"}).json()
    assert got["sprint_dropped"] and got["milestones_dropped"] == [mid] and got["stack_dropped"], got
    assert "its sprint sp_alpha is ALPHA's: let go" in got["said"]
    assert f"its milestone {mid} is ALPHA's: let go" in got["said"]
    row = store.query_one("SELECT sprint_id, stack_id FROM tasks_mutual WHERE id = ?", (TASK,))
    assert not row["sprint_id"] and not row["stack_id"]
    assert not store.query("SELECT * FROM milestone_tasks_mutual WHERE task_id = ?", (TASK,))
    assert {r["project"] for r in store.query("SELECT project FROM task_notes_mutual WHERE task_id = ?", (TASK,))} == {"BETA"}
    head = store.query_one("SELECT stack_head_at FROM tasks_mutual WHERE id = ?", (other_id,))
    assert head["stack_head_at"], "the next card of the stack became its head"
