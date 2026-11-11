"""Entry points over HTTP (routers/entrypoints.py): the desk, one topic's
context and briefing, the port check, and the writes — the operator's from
the page, an agent's (a stop, a way in, a shot, a task's topic) as the MCP
tools send them. Every refusal writes nothing."""

from __future__ import annotations

import base64
import hashlib
import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import entrypointlib as E
from backend.server import create_app
from tests.conftest import make_chat

AGENT = "cc-ep000001"      # the chat the operator kept the topic in (ALPHA)
WORKER = "cc-ep000002"     # a later chat of ALPHA that worked on its task
STRANGER = "cc-ep000003"   # a chat of BETA that names the same task id
RECORD = "## What\nThe install film, the first how-to.\n\n## How\n`npm run dev` then http://localhost:8120\n"
PNG = base64.b64encode(
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x02\x00\x00\x00\x03\x08\x06\x00\x00\x00" + b"\x00" * 40
).decode()


def _snapshot(root: Path) -> dict[str, str]:
    """Every file under the data root with its hash: a refusal must leave it as it was."""
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.name.endswith(".lock") and "projects" not in p.parts:
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


@pytest.fixture()
def world(data_root: Path):
    make_chat(data_root, "ALPHA", AGENT, [
        ("2026-09-01T10:00:00", "one", "a1"),
        ("2026-09-01T10:01:00", "#entrypoint the install film", "noted"),
    ])
    app = create_app(data_root=data_root, watch=False)
    with TestClient(app) as c:
        c.headers["X-SP-Via"] = "mcp"
        from tests.conftest import _mark_only_agent_writes
        c.event_hooks["request"].append(_mark_only_agent_writes)
        rows = c.get("/api/entrypoints?project=ALPHA").json()["entrypoints"]
        eid = rows[0]["id"]
        r = c.post(f"/api/entrypoints/{eid}/interpretation", json={"agent_id": AGENT, "text": RECORD})
        assert r.status_code == 200, r.text
        r = c.post("/api/tasks", json={"created_date": "2609-01", "created_time": "10:05", "project": "ALPHA",
                                      "agent_id": "operator", "title": "Voice the install film", "status": "todo"})
        assert r.status_code == 201, r.text
        tid = r.json()["metadata"]["id"]
        make_chat(data_root, "ALPHA", WORKER, [
            ("2026-09-02T09:00:00", "hello", "hi"),
            ("2026-09-02T09:05:00", f"work on {tid} now", "on it"),
            ("2026-09-02T09:30:00", "how is it going", "voiced, three takes"),
            ("2026-09-02T09:40:00", "something else entirely", "ok"),
        ])
        make_chat(data_root, "BETA", STRANGER, [("2026-09-03T09:00:00", f"look at {tid} too", "looked")])
        app.state.store.rebuild()
        yield c, data_root, eid, tid


def test_the_desk_lists_the_topic_with_its_state_ways_and_counts(world) -> None:
    c, _root, eid, tid = world
    desk = c.get("/api/entrypoints/desk?project=ALPHA").json()
    (t,) = desk["topics"]
    assert t["id"] == eid and t["state"] == "active" and t["name"] == "" and t["title"] == "the install film"
    assert t["what"] == "The install film, the first how-to." and t["ways"] == [] and t["stops_n"] == 0
    assert c.get("/api/entrypoints/desk?project=BETA").json()["topics"] == []
    # Static paths are not taken for an entry point id, and the lens still answers.
    assert c.get(f"/api/entrypoints/{eid}").json()["metadata"]["id"] == eid
    assert c.get("/api/entrypoints/desk").status_code == 200


def test_the_operator_names_it_sets_its_state_and_the_old_status_follows(world) -> None:
    c, _root, eid, _tid = world
    assert c.post(f"/api/entrypoints/{eid}/name", json={"name": "The install film"}).status_code == 200
    r = c.post(f"/api/entrypoints/{eid}/state", json={"state": "paused"})
    assert r.status_code == 200 and r.json()["entrypoint"]["status"] == "closed"
    t = c.get("/api/entrypoints/desk?project=ALPHA").json()["topics"][0]
    assert (t["name"], t["state"]) == ("The install film", "paused")
    assert c.post(f"/api/entrypoints/{eid}/state", json={"state": "active"}).json()["entrypoint"]["status"] == "open"


def test_context_counts_the_topics_turns_and_never_another_projects_chat(world) -> None:
    c, root, eid, tid = world
    r = c.post(f"/api/tasks/{tid}/topic", json={"entrypoint_id": eid, "agent_id": WORKER})
    assert r.status_code == 200, r.text
    r = c.post(f"/api/entrypoints/{eid}/stops", json={"agent_id": WORKER, "text": "Voiced, three takes; not uploaded.", "task_id": tid})
    assert r.status_code == 201, r.text
    cx = c.get(f"/api/entrypoints/{eid}/context").json()
    ids = [ch["id"] for ch in cx["chats"]]
    assert ids == [AGENT, WORKER]                      # oldest first; BETA's chat is not here
    origin, worker = cx["chats"]
    assert origin["origin"] and origin["turns"] == [2] and origin["did"] == "made this entry point"
    # The operator named the task in turn 2; the stop was written at the chat's last turn (4).
    assert worker["turns"] == [2, 4] and worker["messages"] == 2
    assert worker["did"] == "Voiced, three takes; not uploaded."
    # The parts add up: every chat's messages are its turns, each once.
    assert sum(ch["messages"] for ch in cx["chats"]) == sum(len(set(ch["turns"])) for ch in cx["chats"])
    assert [k["id"] for k in cx["open"]] == [tid] and cx["done"] == []
    b = cx["briefing"]
    assert b.startswith("# the install film\n") and "## Where it stopped (newest first)" in b
    assert f"- {tid} (todo) Voice the install film" in b and "## Resume" in b and WORKER in b
    assert STRANGER not in b
    assert c.get(f"/api/entrypoints/{eid}/briefing").json()["text"] == b


def test_a_task_of_another_project_cannot_take_the_topic(world, data_root: Path) -> None:
    c, root, eid, _tid = world
    r = c.post("/api/tasks", json={"created_date": "2609-01", "created_time": "11:00", "project": "BETA",
                                  "agent_id": "operator", "title": "Elsewhere", "status": "todo"})
    other = r.json()["metadata"]["id"]
    before = _snapshot(root)
    r = c.post(f"/api/tasks/{other}/topic", json={"entrypoint_id": eid})
    assert r.status_code == 422 and "is a topic of ALPHA" in r.json()["detail"]
    assert _snapshot(root) == before
    assert c.post("/api/tasks/tk_nothere/topic", json={"entrypoint_id": eid}).status_code == 404
    assert c.post(f"/api/tasks/{other}/topic", json={"entrypoint_id": "ep_nothere"}).status_code == 404
    assert _snapshot(root) == before


def test_ways_in_are_checked_by_shape_and_an_agent_cannot_remove_or_overwrite_the_operators(world) -> None:
    c, root, eid, _tid = world
    way = {"name": "Text console", "kind": "page", "url": "http://localhost:8120", "command": "npm run dev",
           "folder": "tool/console", "port": 8120}
    r = c.post(f"/api/entrypoints/{eid}/ways", json={"way": way})
    assert r.status_code == 200, r.text
    wid = r.json()["way"]["id"]
    assert c.post(f"/api/entrypoints/{eid}/ways", json={"way": way}).json()["existing"] is True
    before = _snapshot(root)
    for bad, says in [
        ({"way": {**way, "port": True}}, "port is a whole number"),
        ({"way": {**way, "port": "80a"}}, "port is a whole number"),
        ({"way": {**way, "name": ["Text console"]}}, "name is text, not a list"),
        ({"way": {**way, "kind": "server"}}, "kind is one of"),
        ({"way": {**way, "url": "file:///etc/passwd"}}, "url starts with"),
        ({"way": {"name": "x", "kind": "page"}}, "a way in needs"),
        ({"way": ["Text console"]}, "way is an object"),
        (["way"], "JSON object"),
    ]:
        r = c.post(f"/api/entrypoints/{eid}/ways", json={**bad, "agent_id": AGENT} if isinstance(bad, dict) else bad)
        assert r.status_code == 422 and says in r.json()["detail"], (bad, r.text)
    r = c.post(f"/api/entrypoints/{eid}/ways", json={"id": wid, "way": {**way, "port": 9000}, "agent_id": AGENT})
    assert r.status_code == 422 and "written by the operator" in r.json()["detail"]
    r = c.post(f"/api/entrypoints/{eid}/ways/{wid}/remove", json={"agent_id": AGENT})
    assert r.status_code == 422
    assert _snapshot(root) == before
    assert c.post(f"/api/entrypoints/{eid}/ways/{wid}/remove", json={}).status_code == 200
    assert E.ways_of(root, eid) == []


def test_a_shot_is_an_image_of_one_of_its_ways_and_replacing_keeps_the_history(world) -> None:
    c, root, eid, _tid = world
    wid = c.post(f"/api/entrypoints/{eid}/ways", json={"way": {"name": "Console", "kind": "page", "url": "http://localhost:8120"}}).json()["way"]["id"]
    before = _snapshot(root)
    for bad, says in [
        ({"way_id": wid, "data_base64": base64.b64encode(b"<svg onload=x>").decode()}, "not a PNG"),
        ({"way_id": wid, "data_base64": "%%%"}, "not valid base64"),
        ({"way_id": "ew_other", "data_base64": PNG}, "is not a way in of"),
        ({"way_id": wid, "data_base64": [PNG]}, "base64 text"),
    ]:
        r = c.post(f"/api/entrypoints/{eid}/shots", json={**bad, "agent_id": AGENT})
        assert r.status_code == 422 and says in r.json()["detail"], r.text
    assert _snapshot(root) == before
    r = c.post(f"/api/entrypoints/{eid}/shots", json={"way_id": wid, "data_base64": PNG, "caption": "first", "agent_id": AGENT, "ext": "gif"})
    assert r.status_code == 201, r.text
    shot = r.json()["shot"]
    # The kind is read from the bytes; the file name has no colon (Windows).
    assert shot["file"].endswith(".png") and ":" not in shot["file"] and shot["agent_id"] == AGENT
    assert (shot["width"], shot["height"]) == ("2", "3")
    got = c.get(f"/api/entrypoints/shots/{shot['id']}/file")
    assert got.status_code == 200 and got.headers["content-type"] == "image/png"
    other = base64.b64encode(base64.b64decode(PNG) + b"\x01").decode()
    r = c.post(f"/api/entrypoints/{eid}/shots", json={"way_id": wid, "data_base64": other, "replaces": shot["id"]})
    assert r.status_code == 201 and r.json()["shot"]["author"] == "operator"
    assert [s["id"] for s in E.shots_of(root, eid)] == [r.json()["shot"]["id"]]
    assert c.get("/api/entrypoints/shots/eh_nothere/file").status_code == 404


def test_stops_are_one_message_per_text_and_task_and_shape_checked(world) -> None:
    c, root, eid, tid = world
    c.post(f"/api/tasks/{tid}/topic", json={"entrypoint_id": eid})
    one = c.post(f"/api/entrypoints/{eid}/stops", json={"agent_id": WORKER, "text": "Stopped at the voice.", "task_id": tid})
    again = c.post(f"/api/entrypoints/{eid}/stops", json={"agent_id": WORKER, "text": "Stopped  at the voice.", "task_id": tid})
    assert one.status_code == 201 and again.status_code == 200 and again.json()["existing"] is True
    before = _snapshot(root)
    for bad in ({"text": ["Stopped"]}, {"text": ""}, {"text": "x" * 1001}, {"text": "ok", "task_id": "tk_other"}):
        r = c.post(f"/api/entrypoints/{eid}/stops", json={**bad, "agent_id": WORKER})
        assert r.status_code == 422, r.text
    # A chat of another project writes nothing on this topic.
    r = c.post(f"/api/entrypoints/{eid}/stops", json={"agent_id": STRANGER, "text": "from BETA"})
    assert r.status_code == 422 and "this chat is in BETA" in r.json()["detail"]
    assert c.post("/api/entrypoints/ep_nothere/stops", json={"text": "x"}).status_code == 404
    assert _snapshot(root) == before
    sid = one.json()["stop"]["id"]
    assert c.post(f"/api/entrypoints/{eid}/stops/{sid}/remove", json={"agent_id": WORKER}).status_code == 422
    assert c.post(f"/api/entrypoints/{eid}/stops/{sid}/remove", json={}).status_code == 200
    assert E.stops_of(root, eid) == []


def test_the_operators_fields_are_refused_to_an_agent_on_every_path(world) -> None:
    c, root, eid, _tid = world
    before = _snapshot(root)
    for path, body in [
        (f"/api/entrypoints/{eid}/state", {"state": "dead"}),
        (f"/api/entrypoints/{eid}/name", {"name": "Mine"}),
        (f"/api/entrypoints/{eid}/update", {"status": "closed"}),
        (f"/api/entrypoints/{eid}/update", {"state": "dead"}),
        ("/api/entrypoints", {"project": "ALPHA", "l1": "a topic", "created_date": "2609-01", "created_time": "10:00"}),
        (f"/api/entrypoints/{eid}/interpretation", {"text": "## What\nmine"}),
    ]:
        r = c.post(path, json={**body, "agent_id": WORKER})
        assert r.status_code == 422, (path, r.text)
    assert _snapshot(root) == before
    # The chat that kept it still writes its record, and names it from the operator's words.
    assert c.post(f"/api/entrypoints/{eid}/interpretation", json={"agent_id": AGENT, "text": RECORD + "\n## State\nvoiced\n"}).status_code == 200
    assert c.post(f"/api/entrypoints/{eid}/update", json={"agent_id": AGENT, "topic": "The install film"}).status_code == 200


def _listening() -> tuple[socket.socket, int]:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    return s, s.getsockname()[1]


def test_the_port_check_answers_open_closed_and_never_a_foreign_host(monkeypatch) -> None:
    s, port = _listening()
    closed_sock = socket.socket()
    closed_sock.bind(("127.0.0.1", 0))
    closed = closed_sock.getsockname()[1]
    closed_sock.close()
    seen: list[tuple[str, int]] = []
    real = E._connect1
    monkeypatch.setattr(E, "_connect1", lambda a, p, t: (seen.append((a, p)), real(a, p, t))[1])
    try:
        got = E.check_ports([
            {"id": "up", "url": f"http://127.0.0.1:{port}/app"},
            {"id": "down", "url": f"http://localhost:{closed}"},
            {"id": "foreign", "url": f"http://example.com:{port}"},
            {"id": "rebind", "url": f"http://127.0.0.1.nip.io:{port}"},
            {"id": "file", "path": "docs/a.md"},
            {"id": "portonly", "port": str(port)},
        ])
    finally:
        s.close()
    by = {g["id"]: g for g in got}
    assert by["up"]["up"] is True and by["portonly"]["up"] is True
    assert by["down"]["up"] is False
    assert by["foreign"]["up"] is None and by["foreign"]["why"] == "not a local address"
    assert by["rebind"]["up"] is None and by["file"]["why"] == "nothing to check"
    assert all(a in ("127.0.0.1", "::1") for a, _ in seen)


def test_the_port_check_is_bounded_when_a_port_never_answers(monkeypatch) -> None:
    import time as _t
    monkeypatch.setattr(E, "_connect1", lambda a, p, t: (_t.sleep(3), True)[1])
    t0 = _t.monotonic()
    got = E.check_ports([{"id": "slow", "url": "http://127.0.0.1:9"}], deadline=0.3)
    assert _t.monotonic() - t0 < 1.5
    assert got[0]["up"] is False and got[0]["why"] == "no answer in time"


def test_the_ports_route_reads_the_topics_ways(world) -> None:
    c, _root, eid, _tid = world
    c.post(f"/api/entrypoints/{eid}/ways", json={"way": {"name": "Site", "kind": "site", "url": "https://example.com"}})
    got = c.get(f"/api/entrypoints/{eid}/ports").json()
    assert got["ways"][0]["up"] is None and got["ways"][0]["why"] == "not a local address"


def test_similar_finds_the_topic_by_its_words(world) -> None:
    c, _root, eid, _tid = world
    got = c.get("/api/entrypoints/similar", params={"project": "ALPHA", "text": "install film how-to"}).json()
    assert got["similar"] and got["similar"][0]["id"] == eid and "entrypoint_way" in got["next"]
    got = c.get("/api/entrypoints/similar", params={"project": "ALPHA", "text": "database migration tool"}).json()
    assert got["similar"] == [] and "#entrypoint" in got["next"]
    assert c.get("/api/entrypoints/similar", params={"project": "ALPHA", "text": "  "}).status_code == 422


def test_the_desk_keeps_an_entrypoint_typed_a_moment_ago(data_root: Path) -> None:
    make_chat(data_root, "ALPHA", "cc-ep000009", [("2026-09-04T10:00:00", "#entrypoint the release notes", "noted")])
    with TestClient(create_app(data_root=data_root, watch=False)) as c:
        topics = c.get("/api/entrypoints/desk?project=ALPHA").json()["topics"]
    assert [t["title"] for t in topics] == ["the release notes"]
