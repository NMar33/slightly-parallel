"""Entry points through the MCP tools, as an agent calls them: the shapes an
agent sends are refused before any request and nothing is written; the
#done answer names the task's topic and asks for one "where it stopped"
message per topic; the offer checks for a matching topic first."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import entrypointlib as E
from backend import mcp
from backend import server as _server
from backend.server import create_app
from tests.refusals import changed, snapshot
from tests.test_mcp_tools_pass_the_gate import _GatedApi

AGENT = "cc-epmcp001"


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
def env(tmp_path: Path, monkeypatch):
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    (root / "done.json").write_text('{"since": "2000-01-01T00:00:00"}', encoding="utf-8")
    monkeypatch.setattr(_server.AgentsViaMcp, "_enforced", lambda self: True)
    monkeypatch.setattr(mcp.Translator, "identity", lambda self: {"project": "alpha", "agent_id": AGENT})
    with TestClient(create_app(data_root=root, watch=False, run_monitor=False)) as c:
        ids = []
        for i, title in enumerate(("Voice the install film", "Upload the install film", "Unrelated")):
            r = c.post("/api/tasks", json={"created_date": "2609-01", "created_time": f"09:0{i}", "project": "alpha",
                                          "agent_id": "operator", "title": title, "status": "doing"})
            ids.append(r.json()["metadata"]["id"])
        _chat(root, ["#entrypoint the install film and its voice"])
        c.app.state.store.rebuild()
        eid = c.get("/api/entrypoints?project=alpha").json()["entrypoints"][0]["id"]
        tr = mcp.Translator(_GatedApi(c), cwd=str(root))
        tr.ensure()
        yield tr, c, root, eid, ids


def test_agent_shaped_inputs_are_refused_before_a_request_and_write_nothing(env) -> None:
    tr, _c, root, eid, (t1, _t2, _t3) = env
    before = snapshot(root, skip=("logs/",))
    calls = len(tr.api.calls)
    for name, args, says in [
        ("entrypoint_stop", {"id": eid, "text": ["stopped"]}, "text is text, not a list"),
        ("entrypoint_stop", {"id": eid}, "text is required"),
        ("entrypoint_way", {"id": eid, "way": ["page"]}, "way is an object"),
        ("entrypoint_way", {"id": eid, "way": {"name": "x", "kind": "page"}, "way_id": ["ew_1"]}, "way_id is text"),
        ("entrypoint_shot", {"id": eid, "way_id": "ew_1", "path": str(root / "nothere.png")}, "is not a file"),
        ("entrypoint_offer", {"name": {"x": 1}}, "name is text"),
        ("task_topic", {"id": t1, "topic": [eid]}, "topic is text, not a list"),
    ]:
        with pytest.raises(mcp.ApiError, match=says):
            tr.call(name, args)
    assert len(tr.api.calls) == calls
    # Shapes only the server can judge are refused there, and still write nothing.
    for name, args in [
        ("entrypoint_way", {"id": eid, "way": {"name": "x", "kind": "page", "port": True, "url": "http://localhost:1"}}),
        ("entrypoint_way", {"id": eid, "way": {"name": ["x"], "kind": "page", "url": "http://localhost:1"}}),
        ("entrypoint_stop", {"id": eid, "text": "x", "task_id": t1}),        # t1 is not a task of the topic yet
        ("task_topic", {"id": t1, "topic": "ep_nothere"}),
    ]:
        with pytest.raises(mcp.ApiError):
            tr.call(name, args)
    assert changed(before, snapshot(root, skip=("logs/",))) == []


def test_done_names_the_topic_and_asks_one_message_per_topic(env) -> None:
    tr, c, root, eid, (t1, t2, t3) = env
    for t in (t1, t2):
        tr.call("task_topic", {"id": t, "topic": eid})
    _chat(root, ["#entrypoint the install film and its voice", f"{t1} {t2} {t3} voice and upload", f"#done {t1} {t2} {t3}"])
    got = tr.call("task_done", {})
    by = {t["id"]: t for t in got["tasks"]}
    assert by[t1]["topic"]["id"] == eid and by[t3]["topic"] is None
    nxt = got["next"]
    assert nxt.count(f'entrypoint_stop {{id: "{eid}"') == 1           # one message for the topic, not one per task
    assert f"{t3} has no topic" in nxt and "entrypoint_offer first" in nxt
    # The agent's message lands on the topic, tied to the task; a second call is the same message.
    tr.call("entrypoint_stop", {"id": eid, "task_id": t1, "text": "Voiced and uploaded; the pinned comment is left."})
    tr.call("entrypoint_stop", {"id": eid, "task_id": t1, "text": "Voiced and uploaded; the pinned comment is left."})
    (stop,) = E.stops_of(root, eid)
    assert stop["author"] == AGENT and stop["task_id"] == t1 and stop["turn"] == "3"
    # Asked again (the answer read twice): tasks already done are asked nothing.
    again = c.get(f"/api/done-tags?agent_id={AGENT}").json()
    assert all(t["result"] == "moved" for t in again["tasks"])      # the same #done, still the latest


def test_the_offer_checks_for_a_matching_topic_first(env) -> None:
    tr, _c, root, eid, _ids = env
    got = tr.call("entrypoint_offer", {"name": "install film voice", "why": "a new page to listen to the takes"})
    assert got["similar"][0]["id"] == eid and "entrypoint_way" in got["next"]
    got = tr.call("entrypoint_offer", {"name": "billing dashboard", "why": "a page with the invoices"})
    assert got["similar"] == [] and "#entrypoint" in got["next"]
    assert not (root / E.STOPS_FILE).exists() and not (root / E.WAYS_FILE).exists()


def test_an_agent_adds_a_way_and_a_shot_and_lists_the_topics(env, tmp_path: Path) -> None:
    tr, _c, root, eid, _ids = env
    way = tr.call("entrypoint_way", {"id": eid, "way": {"name": "Voice takes", "kind": "page",
                                                        "url": "http://127.0.0.1:8130/", "command": "python3 serve.py", "port": 8130}})["way"]
    png = tmp_path / "takes.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x04\x00\x00\x00\x02\x08\x06\x00\x00\x00" + b"\x00" * 20)
    shot = tr.call("entrypoint_shot", {"id": eid, "way_id": way["id"], "path": str(png)})["shot"]
    assert shot["caption"] == "takes" and shot["agent_id"] == AGENT
    listed = tr.call("entrypoints", {})["topics"]
    assert listed[0]["id"] == eid and listed[0]["ways"][0]["name"] == "Voice takes"
    # The agent changes its own way; it cannot remove it (no tool), nor change the state.
    tr.call("entrypoint_way", {"id": eid, "way_id": way["id"], "way": {**{k: way[k] for k in ("name", "kind", "url")}, "port": 8131}})
    assert E.ways_of(root, eid)[0]["port"] == "8131"
    with pytest.raises(mcp.ApiError):
        tr.call("update_entry", {"lens": "entrypoint", "id": eid, "changes": {"status": "closed"}})


def test_an_agent_names_the_topic_through_update_entry_and_cannot_make_one(env) -> None:
    tr, _c, root, eid, _ids = env
    tools = {t["name"]: t for t in tr.tool_defs()}
    assert "entrypoint" in tools["update_entry"]["inputSchema"]["properties"]["lens"]["enum"]
    assert "entrypoint" not in tools["write_entry"]["inputSchema"]["properties"]["lens"]["enum"]
    tr.call("update_entry", {"lens": "entrypoint", "id": eid, "changes": {"topic": "The install film"}})
    assert E.entry_of(tr.api.client.app.state.store, eid)["topic"] == "The install film"
