"""The identity and argument refusals of tk_0b8a32d2 name every fault at once
(tk_90c1ba5f): the MCP translator's argument, stamp, project and nested
checks together with the lens's names and vocabulary; the gate's identity
check over HTTP, top level and nested; a lens create's stamped names; a way
in's fields. One fault reads as before, to the byte."""

from __future__ import annotations

import pytest

from backend import keeplib, mcp
from backend.entities import ENTITIES
from backend.entitylib import create_entity
from tests.conftest import make_chat
from tests.test_identity_http import B, agent  # noqa: F401 — the fixture
from tests.test_membership_tools import A, tree, world  # noqa: F401 — the fixture

pytestmark = pytest.mark.strict_membership


def _numbered(text: str) -> list[str]:
    head, *lines = text.split("\n")
    assert head.endswith("reasons, fix them all before sending again:"), text
    return [line.split(". ", 1)[1] for line in lines]


# -- the translator ----------------------------------------------------------

def test_write_entry_names_every_fault_of_its_arguments_at_once(world) -> None:  # noqa: F811
    tr, _c, root = world
    before = tree(root)
    with pytest.raises(mcp.ApiError) as exc:
        tr.call("write_entry", {"lens": "decision", "agent_id": B, "colour": "red",
                                "fields": {"decision": "x", "project": "ALPHA", "weight": "huge", "shade": 1}})
    got = _numbered(str(exc.value))
    assert got[0] == "agent_id is stamped by Slightly Parallel; leave it out"
    assert got[1].startswith("write_entry takes no argument colour — it takes: ")
    assert got[2].startswith("put project next to lens, not inside fields: ")
    assert got[3].startswith("decision has no field shade — it holds: ")
    assert got[4].startswith("decision.weight 'huge' is not a known value")
    assert len(got) == 5
    assert tree(root) == before


def test_every_identity_inside_the_objects_is_named(world) -> None:  # noqa: F811
    tr, c, _root = world
    task = c.post("/api/tasks", json={"project": "ALPHA", "title": "Seed", "status": "doing", "agent_id": "operator",
                                      "created_date": "2611-20", "created_time": "10:00"}).json()["metadata"]["id"]
    with pytest.raises(mcp.ApiError) as exc:
        tr.call("task_evidence", {"id": task, "extra": 1, "items": [
            {"kind": "text", "body": "b", "agent_id": B}, {"kind": "text", "body": "b", "session_id": "S"}]})
    got = _numbered(str(exc.value))
    assert got[0].startswith("task_evidence takes no argument extra")
    assert got[1:] == ["agent_id is stamped by Slightly Parallel; leave it out (inside items[0])",
                       "session_id is stamped by Slightly Parallel; leave it out (inside items[1])"]


def test_one_argument_fault_reads_as_before(world) -> None:  # noqa: F811
    tr, _c, _root = world
    with pytest.raises(mcp.ApiError) as exc:
        tr.call("tasks", {"session_id": "S"})
    assert str(exc.value) == "session_id is stamped by Slightly Parallel; leave it out"


def test_update_entry_names_a_stamped_change_and_a_bad_value(world) -> None:  # noqa: F811
    tr, _c, _root = world
    with pytest.raises(mcp.ApiError) as exc:
        tr.call("update_entry", {"lens": "decision", "id": "dc_x", "changes": {"actor": B, "weight": "huge"}})
    got = _numbered(str(exc.value))
    assert got[0] == "actor is stamped by Slightly Parallel; leave it out"
    assert got[-1].startswith("decision.weight 'huge' is not a known value")


# -- the gate, over HTTP -----------------------------------------------------

def test_the_gate_names_a_stamped_name_and_every_nested_one(agent) -> None:  # noqa: F811
    raw, _c, root, task, _tr = agent
    before = tree(root)
    r = raw.post(f"/api/tasks/{task}/evidence", json={"agent_id": A, "session_id": "FORGED", "items": [
        {"kind": "text", "body": "b", "agent_id": B}, {"kind": "text", "body": "b", "project": "GAMMA"}]})
    assert r.status_code == 422, r.text
    assert r.json()["detail"].split("\n") == [
        "session_id is stamped by Slightly Parallel; leave it out",
        "agent_id is stamped by Slightly Parallel; leave it out (inside items[0])",
        "put project next to the other fields, not inside items[1]"]
    assert tree(root) == before


# -- a lens create -----------------------------------------------------------

def test_a_lens_create_names_a_stamped_name_and_a_missing_first_line(world) -> None:  # noqa: F811
    _tr, c, root = world
    before = tree(root)
    with pytest.raises(Exception) as exc:
        create_entity(c.app.state.store, ENTITIES["decision"], {
            "project": "ALPHA", "agent_id": A, "session_id": "FORGED", "created_date": "2611-20",
            "created_time": "10:00"})
    assert getattr(exc.value, "status_code", None) == 422
    assert str(getattr(exc.value, "detail", "")).split("\n") == [
        "session_id is stamped by Slightly Parallel; leave it out", "decision needs its first line: send decision"]
    assert tree(root) == before


# -- a way in ----------------------------------------------------------------

def _topic(c, root, tr) -> str:
    turns = [("2026-11-20T10:00:00", "work", "ok"), ("2026-11-20T10:01:00", "#entrypoint the install film", "ok")]
    make_chat(root, "ALPHA", A, turns)
    c.app.state.store.rebuild()
    keeplib.adopt(c.app.state.store)
    eid = keeplib.keep_id("entrypoint", "ALPHA", A, 2)
    tr.call("entrypoint_ask", {"id": eid, "name": "the install film"})
    make_chat(root, "ALPHA", A, [*turns, ("2026-11-20T10:02:00", "1", "ok")])
    c.app.state.store.rebuild()
    tr.call("entrypoint_answer", {"number": 1})
    return eid


def test_every_fault_of_a_way_in_is_named(agent) -> None:  # noqa: F811
    _raw, c, root, _task, tr = agent
    eid = _topic(c, root, tr)
    before = tree(root)
    r = c.post(f"/api/entrypoints/{eid}/ways", json={"way": {"name": "", "kind": "film", "url": "ftp://x",
                                                             "port": 0, "id": "ew_x"}})
    assert r.status_code == 422, r.text
    got = r.json()["detail"].split("\n")
    assert got[0].startswith("kind is one of ")
    assert got[1:] == ["url starts with http:// or https://", "name is required",
                       "port is a whole number from 1 to 65535",
                       f'put the way\'s id next to way: {{"id":"{eid}","way_id":"ew_x","way":{{…}}}}']
    assert len(r.json()["reasons"]) == 4 + 1
    assert tree(root) == before


def test_one_fault_of_a_way_in_reads_as_before(agent) -> None:  # noqa: F811
    _raw, c, root, _task, tr = agent
    eid = _topic(c, root, tr)
    r = c.post(f"/api/entrypoints/{eid}/ways", json={"way": {"name": "w", "kind": "page", "url": "ftp://x"}})
    assert (r.status_code, r.json()["detail"]) == (422, "url starts with http:// or https://")


def test_a_way_with_a_bad_kind_and_nowhere_to_open_hears_both() -> None:
    # The delta critic: another field's fault hid «needs where it opens».
    from backend import entrypointlib as E

    with pytest.raises(E.EntryRefused) as exc:
        E.checked_way({"kind": "bogus", "name": "x"})
    assert exc.value.lines[0].startswith("kind is one of ")
    assert exc.value.lines[1:] == ["a way in needs where it opens (url or path) or the command that starts it"]
    # A url refused for its scheme is not also "missing".
    with pytest.raises(E.EntryRefused) as exc:
        E.checked_way({"kind": "page", "name": "x", "url": "ftp://x"})
    assert exc.value.lines == ["url starts with http:// or https://"]


ITEMS = [{"kind": "text", "body": "b", "agent_id": B, "actor": B}, {"kind": "text", "body": "b", "session_id": "S"}]
GROUPED = ["actor, agent_id are stamped by Slightly Parallel; leave them out (inside items[0])",
           "session_id is stamped by Slightly Parallel; leave it out (inside items[1])"]


def test_the_translator_groups_nested_names_by_object(world) -> None:  # noqa: F811
    # The delta critic: one line per object, as the top level groups them.
    tr, c, _root = world
    task = c.post("/api/tasks", json={"project": "ALPHA", "title": "Seed", "status": "doing", "agent_id": "operator",
                                      "created_date": "2611-20", "created_time": "10:00"}).json()["metadata"]["id"]
    with pytest.raises(mcp.ApiError) as exc:
        tr.call("task_evidence", {"id": task, "items": ITEMS})
    assert _numbered(str(exc.value)) == GROUPED


def test_the_gate_groups_nested_names_by_object(agent) -> None:  # noqa: F811
    raw, _c, root, task, _tr = agent
    before = tree(root)
    r = raw.post(f"/api/tasks/{task}/evidence", json={"agent_id": A, "items": ITEMS})
    assert r.status_code == 422 and r.json()["detail"].split("\n") == GROUPED, r.text
    assert tree(root) == before
