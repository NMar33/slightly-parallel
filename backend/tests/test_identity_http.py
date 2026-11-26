"""An agent's own HTTP body (agents.mcp_only off) names who it is by agent_id
or actor, and nothing else of identity (tk_0b8a32d2): identity the routers
used to drop without a word is refused by name, and a writer Slightly
Parallel has no chat of is refused wherever it writes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend import keeplib
from backend import server as _server
from tests.conftest import make_chat
from tests.test_membership_tools import A, tree, world  # noqa: F401 — the fixture

pytestmark = pytest.mark.strict_membership

B = "cc-bbbb2222"


@pytest.fixture()
def agent(world, monkeypatch):  # noqa: F811
    tr, c, root = world
    make_chat(root, "ALPHA", B, [("2026-11-20T10:00:00", "hello", "ok")])
    c.app.state.store.rebuild()
    task = c.post("/api/tasks", json={"project": "ALPHA", "title": "Seed task", "status": "doing",
                                      "agent_id": "operator", "created_date": "2611-20",
                                      "created_time": "10:00"}).json()["metadata"]["id"]
    monkeypatch.setattr(_server.AgentsViaMcp, "_enforced", lambda self: False)
    raw = TestClient(c.app)
    raw.cookies.clear()      # an agent's own request: no operator cookie, no MCP mark
    return raw, c, root, task, tr


@pytest.mark.parametrize("field", ["session_id", "from", "created_by", "created_date"])
def test_identity_in_an_agents_body_is_refused_by_name(agent, field) -> None:
    raw, _c, root, task, _tr = agent
    before = tree(root)
    r = raw.post(f"/api/tasks/{task}/update", json={"actor": A, "comment": "a note", field: "FORGED"})
    assert r.status_code == 422 and r.json()["detail"] == f"{field} is stamped by Slightly Parallel; leave it out"
    assert tree(root) == before
    r = raw.post("/api/messages", json={"agent_id": A, "to": B, "text": "hi", field: "FORGED"})
    assert r.status_code == 422 and tree(root) == before
    assert raw.post(f"/api/tasks/{task}/update", json={"actor": A, "comment": "a note"}).status_code == 200


@pytest.mark.parametrize(("path", "body"), [
    ("/api/messages", {"to": B, "text": "as nobody"}),
    ("/api/usage/prices", {"models": {"m": {"input": 1, "write_5m": 1, "write_1h": 1, "read": 1, "output": 1}},
                           "sources": ["https://example.org"], "note": "n"}),
])
def test_a_writer_slightly_parallel_has_no_chat_of_is_refused(agent, path, body) -> None:
    raw, _c, root, _task, _tr = agent
    before = tree(root)
    r = raw.post(path, json={**body, "agent_id": "cc-nobody99"})
    assert r.status_code == 403 and "not a chat Slightly Parallel has recorded" in r.json()["detail"], r.text
    assert tree(root) == before


def test_identity_inside_a_way_in_is_refused_over_http_too(agent) -> None:
    raw, c, root, _task, tr = agent
    turns = [("2026-11-20T10:00:00", "work", "ok"), ("2026-11-20T10:01:00", "#entrypoint the install film", "ok")]
    make_chat(root, "ALPHA", A, turns)
    c.app.state.store.rebuild()
    keeplib.adopt(c.app.state.store)
    eid = keeplib.keep_id("entrypoint", "ALPHA", A, 2)
    tr.call("entrypoint_ask", {"id": eid, "name": "the install film"})
    make_chat(root, "ALPHA", A, [*turns, ("2026-11-20T10:02:00", "1", "ok")])
    c.app.state.store.rebuild()
    tr.call("entrypoint_answer", {"number": 1})
    before = tree(root)
    way = {"name": "w", "kind": "page", "url": "http://127.0.0.1:8130/"}
    for inner, said in (({"agent_id": B}, "agent_id is stamped"), ({"project": "GAMMA"}, "no project of its own")):
        r = raw.post(f"/api/entrypoints/{eid}/ways", json={"agent_id": A, "way": {**way, **inner}})
        assert r.status_code >= 400 and said in r.json()["detail"], r.text
    assert tree(root) == before
