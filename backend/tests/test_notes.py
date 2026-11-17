"""Notes (notelib.py, routers/notes.py) as an agent writes them through the
MCP tools and the operator reads, ticks and answers them on the Notes page:
the lens row and its versions, pictures, marks that survive a new version,
what waits on the operator, refusals before a request and at the server,
and the identity the tools stamp."""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import mcp
from backend import notelib as N
from backend import server as _server
from backend.csvio import read_rows
from backend.server import create_app
from tests.conftest import make_task
from tests.refusals import changed, snapshot
from tests.test_mcp_tools_pass_the_gate import _GatedApi

AGENT = "cc-notes001"
OTHER = "cc-notes002"


def _png(w: int = 8, h: int = 6, salt: bytes = b"") -> bytes:
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", w, h) + b"\x08\x02\x00\x00\x00" + salt


def _chat(root: Path, project: str, agent: str) -> None:
    d = root / "projects" / project / "chats" / agent
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps({
        "agent_id": agent, "agent_name": "lead", "project": project,
        "created_date": "2611-16", "last_active": "2026-11-16T11:00:00",
    }), encoding="utf-8")
    (d / "chat.md").write_text(f"# Chat log — {agent}\n\n## Turn 1 · 2026-11-16T10:00:00\n**User**: go\n**Agent**: ok\n",
                               encoding="utf-8")


BODY = """# Release checklist

What is left before the release.

## By hand

- [ ] Rotate the signing key
- [x] Write the store text
- [ ] Upload the build

## Text to paste

```copy The store text
A short app for the tide tables.
```

## Pick one

```choice Which icon?
1. The wave
2. The moon
```

Names tk_TASK and nothing else.
"""


@pytest.fixture()
def env(tmp_path: Path, monkeypatch):
    root = tmp_path / "data"
    for p in ("alpha", "beta"):
        (root / "projects" / p).mkdir(parents=True)
    _chat(root, "alpha", AGENT)
    _chat(root, "beta", OTHER)
    monkeypatch.setattr(_server.AgentsViaMcp, "_enforced", lambda self: True)
    who = {"project": "alpha", "agent_id": AGENT}
    monkeypatch.setattr(mcp.Translator, "identity", lambda self: dict(who))
    with TestClient(create_app(data_root=root, watch=False, run_monitor=False)) as c:
        c.app.state.store.rebuild()
        task = make_task(c, "Release the tide app", status="doing")
        tr = mcp.Translator(_GatedApi(c), cwd=str(root))
        tr.ensure()
        yield tr, c, root, task, who


def _write(tr: mcp.Translator, task: str, **more) -> dict:
    return tr.call("note_write", {"text": BODY.replace("tk_TASK", task), "kind": "actions", "task_id": task, **more})


def test_hash_matches_the_page() -> None:
    # The same vectors the frontend's render/model test holds.
    assert N.hash_of("hello") == "4f9f2cab"
    assert N.hash_of("Привет 👋") == "eb9ef6cd"


def test_a_note_is_written_through_the_tool_with_its_chat_and_task(env) -> None:
    tr, c, root, task, _who = env
    out = _write(tr, task)
    nid = out["id"]
    assert nid.startswith("nt_") and out["version"] == 1 and out["kind"] == "actions"
    assert out["title"] == "Release checklist"
    assert out["open"] == {"to_tick": 2, "ticked": 1, "to_answer": 1, "answered": 0, "to_copy": 0, "copies": 1}
    row = next(r for r in read_rows(root / "notes.csv") if r["id"] == nid)
    assert (row["agent_id"], row["project"], row["task_id"], row["versions_n"]) == (AGENT, "alpha", task, "1")
    v = read_rows(root / "note_versions.csv")
    assert [(x["note_id"], x["n"], x["agent_id"]) for x in v] == [(nid, "1", AGENT)]
    assert (root / v[0]["file"]).read_text(encoding="utf-8").startswith("# Release checklist")
    feed = c.get("/api/notes/feed?project=alpha").json()
    assert [n["id"] for n in feed["notes"]] == [nid]
    assert feed["entities"][task]["title"] == "Release the tide app"
    assert feed["entities"][task]["status"] == "doing"
    assert feed["notes"][0]["open"]["to_tick"] == 2
    # The lens detail and search still read it.
    c.app.state.store.rebuild()
    assert c.get(f"/api/notes/{nid}").status_code == 200
    by_task = c.get(f"/api/notes/feed?task={task}").json()["notes"]
    assert [n["id"] for n in by_task] == [nid]


def test_marks_survive_a_new_version_for_items_that_did_not_change(env) -> None:
    tr, c, _root, task, _who = env
    nid = _write(tr, task)["id"]
    items = N.parse(nid, c.get(f"/api/notes/{nid}/full").json()["body"])["items"]
    key = next(i["id"] for i in items if i["type"] == "check" and i["text"] == "Rotate the signing key")
    upload = next(i["id"] for i in items if i["type"] == "check" and i["text"] == "Upload the build")
    choice = next(i["id"] for i in items if i["type"] == "choice")
    copy = next(i["id"] for i in items if i["type"] == "copy")
    assert c.post(f"/api/notes/{nid}/marks", json={"item": key, "kind": "tick", "value": True}).status_code == 200
    assert c.post(f"/api/notes/{nid}/marks", json={"item": upload, "kind": "tick", "value": True}).status_code == 200
    assert c.post(f"/api/notes/{nid}/marks", json={"item": choice, "kind": "answer", "value": 1}).status_code == 200
    assert c.post(f"/api/notes/{nid}/marks", json={"item": copy, "kind": "copy"}).status_code == 200
    back = tr.call("notes", {"id": nid})
    asked = next(x for x in back["operator"] if "question" in x)
    assert asked["answer"] == {"number": 2, "option": "The moon"}
    assert {x["item"]: x["ticked"] for x in back["operator"] if "item" in x} == {
        "Rotate the signing key": True, "Write the store text": True, "Upload the build": True}
    # v2 changes one item's text: its tick goes, the others stay.
    text2 = BODY.replace("tk_TASK", task).replace("Upload the build", "Upload the signed build")
    with pytest.raises(mcp.ApiError, match="is at v1 now, not v3"):
        tr.call("note_write", {"id": nid, "text": text2, "kind": "actions", "base": 3})
    out = tr.call("note_write", {"id": nid, "text": text2, "kind": "actions", "base": 1})
    assert out["version"] == 2
    assert out["open"]["to_tick"] == 1 and out["open"]["answered"] == 1
    full = c.get(f"/api/notes/{nid}/full").json()
    assert full["versions"] == 2 and [h["n"] for h in full["history"]] == [1, 2]
    assert full["task"] == task  # kept from v1
    old = c.get(f"/api/notes/{nid}/full?v=1").json()
    assert "Upload the build" in old["body"] and old["version"] == 1


def test_the_operator_marks_and_an_agent_cannot(env) -> None:
    tr, c, root, task, _who = env
    nid = _write(tr, task)["id"]
    items = N.parse(nid, c.get(f"/api/notes/{nid}/full").json()["body"])["items"]
    choice = next(i["id"] for i in items if i["type"] == "choice")
    before = snapshot(root, skip=("logs/",))
    for body, says in [
        ({"item": choice, "kind": "answer", "value": 5}, "option's index"),
        ({"item": f"{nid}:k:00000000", "kind": "tick", "value": True}, "is not a check"),
        ({"item": choice, "kind": "tick", "value": True}, "is not a check"),
        ({"item": choice, "kind": "smile"}, "kind is one of"),
    ]:
        r = c.post(f"/api/notes/{nid}/marks", json=body)
        assert r.status_code == 422 and says in r.json()["detail"], r.text
    r = c.post(f"/api/notes/{nid}/marks", json={"item": choice, "kind": "answer", "value": 0, "agent_id": AGENT})
    assert r.status_code in (403, 422)
    assert not changed(before, snapshot(root, skip=("logs/",)))
    # Taking an answer back clears it.
    c.post(f"/api/notes/{nid}/marks", json={"item": choice, "kind": "answer", "value": 0})
    c.post(f"/api/notes/{nid}/marks", json={"item": choice, "kind": "answer", "value": ""})
    assert choice not in c.get("/api/notes/feed").json()["marks"]["answers"]


def test_pictures_are_stored_and_the_text_names_them_by_id(env, tmp_path: Path) -> None:
    tr, c, root, task, _who = env
    shot = tmp_path / "shots" / "home.png"
    shot.parent.mkdir()
    shot.write_bytes(_png())
    text = "# Review\n\n```gallery\n![The home page](home.png)\n```\n"
    out = tr.call("note_write", {"text": text, "kind": "review", "images": [{"path": str(shot), "caption": "Home"}]})
    nid = out["id"]
    full = c.get(f"/api/notes/{nid}/full").json()
    img = full["images"][0]
    assert img["id"].startswith("ni_") and (img["width"], img["height"]) == (8, 6)
    assert f"![The home page]({img['id']})" in full["body"]
    assert out["unknown_images"] == []
    r = c.get(img["src"])
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    other = tmp_path / "shots" / "menu.png"
    other.write_bytes(_png(salt=b"x"))
    got = tr.call("note_image", {"id": nid, "path": str(other), "caption": "The menu"})
    assert got["markdown"] == f"![The menu]({got['image']['id']})"
    assert len(c.get(f"/api/notes/{nid}/full").json()["images"]) == 2
    bad = tmp_path / "shots" / "fake.png"
    bad.write_bytes(b"not a picture")
    with pytest.raises(mcp.ApiError, match="not a PNG"):
        tr.call("note_image", {"id": nid, "path": str(bad)})


def test_the_first_option_is_an_answer_and_a_gallery_does_not_stop_a_mark(env, tmp_path: Path) -> None:
    """The page sends the option's index, 0 for the first; and a note with
    pictures above its choice and steps is marked like any other (the
    gallery has no id: a mark used to answer 404 there)."""
    tr, c, _root, _task, _who = env
    shot = tmp_path / "one.png"
    shot.write_bytes(_png())
    text = ("# Layouts\n\n```gallery\n![One page](one.png)\n```\n\n"
            "```choice Which layout ships?\n1. One page\n2. Two steps\n```\n\n- [ ] Tell the team\n")
    nid = tr.call("note_write", {"text": text, "kind": "review", "images": [{"path": str(shot)}]})["id"]
    items = N.parse(nid, c.get(f"/api/notes/{nid}/full").json()["body"])["items"]
    choice = next(i["id"] for i in items if i["type"] == "choice")
    step = next(i["id"] for i in items if i["type"] == "check")
    assert c.post(f"/api/notes/{nid}/marks", json={"item": choice, "kind": "answer", "value": 0}).status_code == 200
    assert c.post(f"/api/notes/{nid}/marks", json={"item": step, "kind": "tick", "value": True}).status_code == 200
    marks = c.get("/api/notes/feed").json()["marks"]
    assert marks["answers"][choice] == 0 and marks["ticks"][step] is True
    asked = next(x for x in tr.call("notes", {"id": nid})["operator"] if "question" in x)
    assert asked["answer"] == {"number": 1, "option": "One page"}


def test_shapes_an_agent_sends_wrong_are_refused_before_a_request(env) -> None:
    tr, _c, root, task, _who = env
    before = snapshot(root, skip=("logs/",))
    calls = len(tr.api.calls)
    for args, says in [
        ({"text": ["# x"], "kind": "plan"}, "text is text, not a list"),
        ({"kind": "plan"}, "text is required"),
        ({"text": "# x"}, "kind is required"),
        ({"text": "# x", "kind": "plan", "images": "a.png"}, "images is a list"),
        ({"text": "# x", "kind": "plan", "images": [{"path": str(root / "nothere.png")}]}, "is not a file"),
        ({"text": "# x", "kind": "plan", "base": True}, "base is the version number"),
        ({"text": "# x", "kind": "plan", "task_id": [task]}, "task_id is text"),
    ]:
        with pytest.raises(mcp.ApiError, match=says):
            tr.call("note_write", args)
    assert len(tr.api.calls) == calls
    assert not changed(before, snapshot(root, skip=("logs/",)))


def test_the_server_refuses_what_it_cannot_keep(env) -> None:
    tr, c, root, task, who = env
    before = snapshot(root, skip=("logs/",))
    for args, says in [
        ({"text": "# x", "kind": "memo"}, "kind is one of"),
        ({"text": "no title here", "kind": "plan"}, "a note has a title"),
        ({"text": "# x", "kind": "plan", "task_id": "tk_00000000"}, "is not a task"),
        ({"text": "# x", "kind": "plan", "entrypoint_id": "ep_00000000"}, "is not an entry point"),
        ({"text": "# x", "kind": "plan", "id": "nt_00000000"}, "is not a note"),
        ({"text": "# x", "kind": "plan", "replaces": "nt_00000000"}, "is not an older note"),
    ]:
        with pytest.raises(mcp.ApiError, match=says):
            tr.call("note_write", args)
    assert not changed(before, snapshot(root, skip=("logs/",)))
    nid = _write(tr, task)["id"]
    # A chat of another project does not write this note's next version.
    who.update({"project": "beta", "agent_id": OTHER})
    c.app.state.store.rebuild()
    with pytest.raises(mcp.ApiError, match="is a note of alpha"):
        tr.call("note_write", {"id": nid, "text": "# x", "kind": "plan"})


def test_an_agent_writing_over_plain_http_is_refused(env) -> None:
    _tr, c, root, _task, _who = env
    before = snapshot(root, skip=("logs/",))
    r = c.post("/api/notes/write", json={"agent_id": AGENT, "project": "alpha", "text": "# x", "kind": "plan"})
    assert r.status_code == 422 and "MCP" in r.json()["detail"]
    r = c.post("/api/notes", json={"agent_id": AGENT, "project": "alpha", "title": "x",
                                   "created_date": "2611-16", "created_time": "10:00"})
    assert r.status_code == 422
    assert not changed(before, snapshot(root, skip=("logs/",)))


def test_the_operator_archives_and_a_newer_note_replaces(env) -> None:
    tr, c, _root, task, _who = env
    old = _write(tr, task)["id"]
    new = tr.call("note_write", {"text": "# Release checklist, second\n\nNewer.", "kind": "actions", "replaces": old})["id"]
    feed = {n["id"]: n for n in c.get("/api/notes/feed").json()["notes"]}
    assert feed[old]["replaced_by"] == new and feed[new]["replaces"] == [old]
    assert c.post(f"/api/notes/{old}/archive", json={"archived": True}).status_code == 200
    assert [n["id"] for n in c.get("/api/notes/feed").json()["notes"]] == [new]
    assert [n["id"] for n in c.get("/api/notes/feed?archived=true").json()["notes"]] == [old]
    with pytest.raises(mcp.ApiError, match="archived"):
        tr.call("note_write", {"id": old, "text": "# x", "kind": "plan"})
    listed = tr.call("notes", {})
    assert [n["id"] for n in listed["notes"]] == [new]


def test_a_note_of_the_old_library_lens_still_reads(env) -> None:
    _tr, c, root, _task, _who = env
    (root / "note_details").mkdir(exist_ok=True)
    (root / "note_details" / "old.md").write_text("---\nid: nt_al_curl\n---\n## L2\nCurl for the auth flow.\n", encoding="utf-8")
    (root / "notes.csv").write_text(
        "id,created_date,created_time,project,agent_id,title,tags,md_ref\n"
        "nt_al_curl,2608-02,16:00,alpha,cc-old,Curl commands,auth,note_details/old.md\n", encoding="utf-8")
    n = c.get("/api/notes/feed").json()["notes"][0]
    assert (n["id"], n["kind"], n["title"], n["versions"]) == ("nt_al_curl", "context", "Curl commands", 1)
    assert "Curl for the auth flow." in n["body"]


def test_parse_mirrors_the_page() -> None:
    p = N.parse("nt_00000001", BODY)
    assert p["title"] == "Release checklist"
    assert p["sections"] == ["By hand", "Text to paste", "Pick one"]
    kinds = [(i["type"], i.get("text") or i.get("question") or i.get("title")) for i in p["items"]]
    assert kinds == [("check", "Rotate the signing key"), ("check", "Write the store text"), ("check", "Upload the build"),
                     ("copy", "The store text"), ("choice", "Which icon?")]
    assert p["items"][0]["id"] == f"nt_00000001:k:{N.hash_of('Rotate the signing key')}"
    assert N._escaped("## L4 cache\n## l2") == "## ​L4 cache\n## ​l2"
