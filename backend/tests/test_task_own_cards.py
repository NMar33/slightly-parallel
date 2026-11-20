"""An agent changes the title, the text and the day of a task only on a card
it created (tasklib.own_card_refusal). The operator's card and another
agent's are refused, naming the creator; a comment stays open to every
agent; the operator edits everything. The task made from a message keeps
its exception (test_task_titles.py), the #now card its own (test_now_fallback.py)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app

AGENT = "cc-own00001"
OTHER = "cc-own00002"


@pytest.fixture()
def c(tmp_path: Path):
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    with TestClient(create_app(data_root=root, watch=False)) as client:
        yield client


def _agent_card(c: TestClient, agent: str = AGENT, title: str = "Form without a scan") -> str:
    r = c.post("/api/tasks", json={"project": "alpha", "agent_id": agent, "title": title,
                                   "tags": "ag_followup", "description": "the agent's text"})
    assert r.status_code == 201, r.text
    return r.json()["metadata"]["id"]


def _operator_card(c: TestClient) -> str:
    r = c.post("/api/tasks", json={"project": "alpha", "actor": "operator", "title": "the operator's",
                                   "status": "todo", "description": "the operator's text"})
    assert r.status_code == 201, r.text
    return r.json()["metadata"]["id"]


def _task(c: TestClient, tid: str) -> dict:
    return c.get(f"/api/tasks/{tid}").json()


def _update(c: TestClient, tid: str, **body: object):
    return c.post(f"/api/tasks/{tid}/update", json=body)


def test_an_agent_edits_its_own_card(c) -> None:
    tid = _agent_card(c)
    r = _update(c, tid, actor=AGENT, title="Architecture form without a scan",
                description="the agent's text, sharper", today_on="2026-11-18")
    assert r.status_code == 200, r.text
    got = _task(c, tid)
    assert got["metadata"]["title"] == "Architecture form without a scan"
    assert got["metadata"]["today_on"] == "2026-11-18"
    assert got["description"] == "the agent's text, sharper"


@pytest.mark.parametrize("field,value", [
    ("title", "the agent's name for it"),
    ("description", "the agent's words instead"),
    ("today_on", "2026-11-18"),
])
def test_the_operators_card_is_refused(c, field, value) -> None:
    tid = _operator_card(c)
    before = _task(c, tid)
    r = _update(c, tid, actor=AGENT, **{field: value})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert field in detail and "created by the operator" in detail and "the operator's" in detail
    assert "comment" in detail                                         # what to do instead
    after = _task(c, tid)
    assert after["metadata"]["title"] == before["metadata"]["title"]
    assert after["metadata"]["today_on"] == before["metadata"]["today_on"]
    assert after["description"] == "the operator's text"


def test_update_entry_shape_is_refused_the_same(c) -> None:
    """MCP update_entry posts the changes with ``agent_id``, task_update with
    ``actor``: both reach the same gate."""
    tid = _operator_card(c)
    r = _update(c, tid, agent_id=AGENT, title="through update_entry")
    assert r.status_code == 422 and "created by the operator" in r.json()["detail"]
    assert _task(c, tid)["metadata"]["title"] == "the operator's"


def test_another_agents_card_is_refused_naming_its_creator(c) -> None:
    tid = _agent_card(c, agent=OTHER, title="the other agent's card")
    r = _update(c, tid, actor=AGENT, title="mine now", description="mine")
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert f"created by {OTHER}" in detail and "that agent's" in detail and "title, description" in detail
    assert _task(c, tid)["metadata"]["title"] == "the other agent's card"


def test_a_comment_on_the_operators_card_is_open_to_any_agent(c) -> None:
    tid = _operator_card(c)
    r = _update(c, tid, actor=AGENT, comment="found the cause in tasks_extra.py")
    assert r.status_code == 200, r.text
    text = _task(c, tid)["description"]
    assert text.startswith("the operator's text")                       # kept as written
    assert "--- comment from agent:\nfound the cause in tasks_extra.py" in text


def test_the_operator_edits_any_card(c) -> None:
    mine = _operator_card(c)
    theirs = _agent_card(c)
    for tid in (mine, theirs):
        r = _update(c, tid, actor="operator", title="renamed by the operator",
                    description="the operator's words", today_on="2026-11-19")
        assert r.status_code == 200, r.text
        got = _task(c, tid)
        assert got["metadata"]["title"] == "renamed by the operator"
        assert got["description"] == "the operator's words"
    # A body with no actor at all is the board's.
    assert _update(c, theirs, title="from the board").status_code == 200


def test_other_fields_on_the_operators_card_keep_their_rules(c) -> None:
    """Tags (ag_*) on any card stay the agent's, as before."""
    tid = _operator_card(c)
    assert _update(c, tid, actor=AGENT, tags="ag_bug").status_code == 200
