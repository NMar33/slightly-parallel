"""The readers left from step 2 read memberships (tk_d1d25a4d step 3, note
nt_258a7ed7 §7). Fixture: chat A from ALPHA joined BETA; chat B is BETA's.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import entrypointlib, mcp, termlib, undolib
from backend.routers import files_extra
from backend.server import create_app
from tests.conftest import choose_new_topic, make_chat

pytestmark = pytest.mark.strict_membership

A, B = "cc-aaaa1111", "cc-bbbb2222"
VIA = {mcp.VIA_HEADER: mcp.VIA_VALUE}


@pytest.fixture()
def world(data_root: Path):
    make_chat(data_root, "ALPHA", A, [("2026-11-20T10:00:00", "start on tk_beta_x", "ok")])
    make_chat(data_root, "BETA", B, [("2026-11-20T11:00:00", "beta work", "ok")])
    with TestClient(create_app(data_root=data_root, watch=False)) as c:
        assert c.post(f"/api/agents/{A}/membership", json={"op": "join", "project": "BETA"}).status_code == 200
        yield c, data_root


def test_two_chats_that_share_a_project_link_and_the_link_is_filed_there(world) -> None:
    c, _root = world
    r = c.post("/api/agents/links", json={"from": A, "to": B, "kind": "handoff"})
    assert r.status_code == 201, r.text
    assert r.json()["link"]["project"] == "BETA"          # A's home ALPHA is not B's
    r = c.post("/api/agents/links", json={"from": B, "to": "alpha-lead-2608-01", "kind": "handoff"})
    assert r.status_code == 422                            # no project in common


def test_a_member_chat_counts_on_a_topic_of_its_member_project(world) -> None:
    c, root = world
    store = c.app.state.store
    ep = choose_new_topic(store, root, "BETA", B, [("2026-11-20T11:00:00", "beta work", "ok"),
                                                   ("2026-11-20T11:05:00", "#entrypoint the install film", "ok")])
    r = c.post(f"/api/entrypoints/{ep}/stops", json={"agent_id": A, "text": "stopped at the voice"}, headers=VIA)
    assert r.status_code == 201, r.text
    row = entrypointlib.entry_of(store, ep)
    turns = entrypointlib.chat_turns(store, row, [], entrypointlib.stops_of(store, ep), [])
    assert A in turns, turns


def test_mentions_follow_the_tasks_project_and_projects(world) -> None:
    c, _root = world
    got = c.get("/api/tasks/mentions/summary", params={"project": "BETA"}).json()["mentions"]
    assert "tk_beta_x" in got                              # named in A's chat, filed in ALPHA
    got = c.get("/api/tasks/mentions/summary", params={"project": "ALPHA"}).json()["mentions"]
    assert "tk_beta_x" not in got


def test_a_checkpoint_finds_its_session_by_agent_and_day(world) -> None:
    c, _root = world
    lanes = files_extra._sessions_by_lane(c.app.state.store)
    day = next(k[2] for k in lanes if k[1] == A)
    assert files_extra._session_for(lanes, "BETA", A, day, "23:59")      # A's session is filed in ALPHA
    assert files_extra._session_for(lanes, "BETA", "cc-nobody00", day, "23:59") == ""


def test_the_terminal_list_shows_member_chats(world, monkeypatch) -> None:
    c, _root = world
    monkeypatch.setattr(termlib, "listing", lambda root, status: [
        {"id": "t1", "project": "ALPHA", "agent_id": A, "state": "working"},
        {"id": "t2", "project": "ALPHA", "agent_id": "", "state": "shell"},
        {"id": "t3", "project": "BETA", "agent_id": B, "state": "working"}])
    got = c.get("/api/terminal/sessions", params={"project": "BETA"},
                headers={"Sec-Fetch-Site": "same-origin"})
    assert got.status_code == 200, got.text
    assert [x["id"] for x in got.json()["sessions"]] == ["t1", "t3"]


def test_a_message_is_filed_in_the_senders_home_and_listed_in_its_members(world) -> None:
    c, _root = world
    r = c.post("/api/messages", json={"agent_id": A, "to": B, "text": "hello", "project": "BETA"}, headers=VIA)
    assert r.status_code in (200, 201), r.text
    got = c.get("/api/messages", params={"project": "ALPHA"}).json()["messages"]
    assert [m["project"] for m in got if m["from_agent"] == A] == ["ALPHA"]
    assert any(m["from_agent"] == A for m in c.get("/api/messages", params={"project": "BETA"}).json()["messages"])


def test_undo_finds_what_the_chat_wrote_in_a_member_project(world) -> None:
    c, root = world
    r = c.post("/api/decisions", json={"agent_id": A, "project": "BETA", "created_date": "2611-20",
                                       "created_time": "10:00", "decision": "chose sqlite", "why": "small"},
               headers=VIA)
    assert r.status_code == 201, r.text
    r = c.post("/api/visions", json={"created_date": datetime.now().strftime("%y%m-%d"), "created_time": "10:00",
                                     "project": "BETA", "agent_id": A, "l1": "A beta vision", "l2": "x"},
               headers=VIA)
    vid = r.json()["metadata"]["id"] if r.status_code == 201 else ""
    at = (datetime.now() - timedelta(minutes=1)).isoformat(timespec="seconds")
    make_chat(root, "ALPHA", A, [("2026-11-20T10:00:00", "start on tk_beta_x", "ok"),
                                 (at, "#undo the vision you just wrote", "")])
    c.app.state.store.rebuild()
    got = undolib.candidates(c.app.state.store, A)
    ids = {x["id"] for x in got.get("candidates", got.get("entries", []))}
    assert vid and vid in ids, got
