"""Story notes, Storyboard docs, the three-layer pack, versions, doc mentions."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    r = tmp_path / "data"
    (r / "projects" / "alpha").mkdir(parents=True)
    return r


@pytest.fixture()
def client(root: Path):
    app = create_app(data_root=root, watch=False)
    with TestClient(app) as c:
        yield c


def _task(client: TestClient, title: str, l2: str = "", t: str = "10:00") -> str:
    r = client.post("/api/tasks", json={
        "created_date": "2608-19", "created_time": t, "project": "alpha",
        "agent_id": "operator", "title": title, "status": "doing", "description": l2,
    })
    assert r.status_code == 201, r.text
    return r.json()["metadata"]["id"]


def _note(client: TestClient, tid: str, ntype: str, body: str, template: str = "note") -> dict:
    r = client.post(f"/api/tasks/{tid}/notes", json={"type": ntype, "body": body, "template": template})
    assert r.status_code == 201, r.text
    return r.json()["note"]


def test_notes_crud_and_wall(client: TestClient) -> None:
    tid = _task(client, "Links between tasks", l2="Edges as a ledger.")
    a = _note(client, tid, "article", "Git knows *that*; the agent knows *why*.", "problem-insight")
    _note(client, tid, "prompt", "Audience: engineers. No marketing tone.")
    assert client.post(f"/api/tasks/{tid}/notes", json={"type": "song", "body": "x"}).status_code == 422
    assert client.post(f"/api/tasks/{tid}/notes", json={"type": "post", "body": "  "}).status_code == 422
    assert client.post("/api/tasks/tk_nope/notes", json={"type": "post", "body": "x"}).status_code == 404

    mine = client.get(f"/api/tasks/{tid}/notes").json()
    assert [n["type"] for n in mine["notes"]] == ["article", "prompt"]
    wall = client.get("/api/tasks/notes?project=alpha").json()
    assert wall["total"] == 2 and wall["notes"][0]["task_title"] == "Links between tasks"
    assert client.get("/api/tasks/notes?project=alpha&type=prompt").json()["total"] == 1
    assert client.get("/api/tasks/notes/summary?project=alpha").json()["notes"][tid] == 2

    upd = client.post(f"/api/tasks/notes/{a['id']}/update", json={"body": "Sharper line."}).json()["note"]
    assert upd["body"] == "Sharper line." and upd["updated_at"] >= a["created_at"]
    # Note creation shows in the task's history.
    ev = client.get(f"/api/tasks/{tid}/events").json()["events"]
    assert any(e["field"] == "note" and e["new_value"] == "article" for e in ev)
    assert client.post(f"/api/tasks/notes/{a['id']}/delete").json() == {"deleted": a["id"]}
    assert client.get(f"/api/tasks/{tid}/notes").json()["total"] == 1


def test_docs_items_reorder_and_pack(client: TestClient, root: Path, monkeypatch) -> None:
    t1 = _task(client, "Files lens", l2="Agent judgment, git mechanics.")
    t2 = _task(client, "Task links", l2="An edge ledger.", t="10:05")
    n1 = _note(client, t1, "article", "Paragraph about the files lens.")
    n2 = _note(client, t2, "article", "Paragraph about links.")
    _note(client, t2, "release", "Links shipped.")
    _note(client, t1, "prompt", "Write for Habr, technical, no hype.")

    doc = client.post("/api/docs", json={"project": "alpha", "kind": "article", "title": "How Slightly Parallel sees work"}).json()["doc"]
    did = doc["id"]
    assert did.startswith("dc_")
    assert client.post("/api/docs", json={"project": "alpha", "kind": "poem", "title": "x"}).status_code == 422

    client.post(f"/api/docs/{did}/items", json={"note_id": n2["id"]})
    client.post(f"/api/docs/{did}/items", json={"text": "Intro: why observe agents at all."}, )
    client.post(f"/api/docs/{did}/items", json={"note_id": n1["id"]})
    d = client.get(f"/api/docs/{did}").json()
    ids = [it["id"] for it in d["items"]]
    assert [it.get("note_id") or "text" for it in d["items"]] == [n2["id"], "text", n1["id"]]

    # Move the intro first.
    client.post(f"/api/docs/{did}/reorder", json={"item_ids": [ids[1], ids[0], ids[2]]})
    d = client.get(f"/api/docs/{did}").json()
    assert (d["items"][0]["text"].startswith("Intro")) and d["items"][1]["note_id"] == n2["id"]
    client.post(f"/api/docs/{did}/items/{ids[1]}/update", json={"text": "Intro, sharper."})
    assert client.get(f"/api/docs/{did}").json()["items"][0]["text"] == "Intro, sharper."

    pack = client.get(f"/api/docs/{did}/pack").text
    assert pack.startswith("# How Slightly Parallel sees work")
    assert "## The document" in pack and "Intro, sharper." in pack
    assert "L1" not in pack and "POST /api" not in pack
    assert "Paragraph about links." in pack and "Paragraph about the files lens." in pack
    assert "## Instructions (prompt notes)" in pack and "Write for Habr" in pack
    assert "## Context" in pack and "An edge ledger." in pack and "*release*: Links shipped." in pack
    assert "## Connections" in pack
    assert f'doc_version {{id: "{did}", body, note}}' in pack
    assert "the operator pastes it in" in pack

    # An agent's raw HTTP write is refused by the MCP gate; the operator's
    # pasted version comes back, dated and signed, and the doc moves to drafted.
    from backend import server as _server
    monkeypatch.setattr(_server.AgentsViaMcp, "_enforced", lambda self: True)
    refused = client.post(f"/api/docs/{did}/versions", json={"body": "# Final\n...", "agent_id": "cc-writer"})
    assert refused.status_code == 422 and "doc_version" in refused.json()["detail"]
    v = client.post(f"/api/docs/{did}/versions", json={"body": "# Final\n...", "agent_id": "operator"}).json()["version"]
    d = client.get(f"/api/docs/{did}").json()
    assert d["versions"][0]["id"] == v["id"] and d["doc"]["status"] == "drafted"
    assert client.get("/api/docs?project=alpha").json()["docs"][0]["items_n"] == 3

    # Deleting a note leaves a placeholder item; deleting the doc clears its rows.
    client.post(f"/api/tasks/notes/{n1['id']}/delete")
    d = client.get(f"/api/docs/{did}").json()
    assert any(it["text"] == "(note removed)" for it in d["items"])
    client.post(f"/api/docs/{did}/delete")
    assert client.get(f"/api/docs/{did}").status_code == 404
    assert client.get("/api/docs?project=alpha").json()["total"] == 0


def test_doc_ids_are_found_in_chats(client: TestClient, root: Path) -> None:
    did = client.post("/api/docs", json={"project": "alpha", "kind": "release", "title": "v0.3"}).json()["doc"]["id"]
    d = root / "projects" / "alpha" / "chats" / "cc-writer01"
    d.mkdir(parents=True)
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    (d / "chat.md").write_text(
        f"# Chat log — cc-writer01\n\n---\n\n## Turn 1 · {now}\n**User**: /story {did}\n**Agent**: drafted {did}, posted a version\n",
        encoding="utf-8",
    )
    (d / "meta.json").write_text(json.dumps({"agent_id": "cc-writer01"}), encoding="utf-8")
    client.app.state.store.rebuild()
    m = client.get(f"/api/docs/{did}").json()["mentions"]
    assert [x["role"] for x in m] == ["agent", "user"]
    assert m[0]["agent_id"] == "cc-writer01"
    assert "templates" in client.get("/api/story/templates").json()


def _translator(client: TestClient, agent: str = "cc-writer01"):
    """The MCP translator over this app, as an agent's session would drive it."""
    from backend import mcp as mcp_mod
    calls: list[tuple[str, dict]] = []

    class FakeApi:
        def get(self, path):
            if path.startswith("/api/schema"):
                return client.get("/api/schema").json()
            return {"agent_id": agent, "project": "alpha"}

        def post(self, path, body):
            calls.append((path, body))
            r = client.post(path, json=body, headers={"X-SP-Via": "mcp"})
            if r.status_code >= 400:
                raise mcp_mod.ApiError(f"{r.status_code}: {r.json().get('detail')}")
            return r.json()

    return mcp_mod.Translator(FakeApi(), "/tmp"), calls


def test_an_agent_posts_a_version_with_doc_version(client: TestClient) -> None:
    from backend.mcp import ApiError
    did = client.post("/api/docs", json={"project": "alpha", "kind": "post", "title": "Launch post"}).json()["doc"]["id"]
    tr, calls = _translator(client)
    tool = next(t for t in tr.tool_defs() if t["name"] == "doc_version")
    assert tool["inputSchema"]["required"] == ["id", "body"]
    assert set(tool["inputSchema"]["properties"]) == {"id", "body", "note"}

    out = tr.call("doc_version", {"id": did, "body": "# Launch\n\nFirst draft.", "note": "first pass",
                                  "agent_id": "cc-someone-else"})
    assert calls[-1][0] == f"/api/docs/{did}/versions"
    # Identity is stamped, never taken from the arguments.
    assert out["version"]["agent_id"] == "cc-writer01" and out["n"] == 1
    tr.call("doc_version", {"id": did, "body": "# Launch\n\nSecond draft, tighter."})

    d = client.get(f"/api/docs/{did}").json()
    assert [v["body"].splitlines()[-1] for v in d["versions"]] == ["Second draft, tighter.", "First draft."]
    assert [v["note"] for v in d["versions"]] == ["", "first pass"]
    assert d["doc"]["status"] == "drafted"
    assert client.get("/api/docs?project=alpha").json()["docs"][0]["versions_n"] == 2

    # The same text again in the same minute is the same version.
    again = tr.call("doc_version", {"id": did, "body": "# Launch\n\nSecond draft, tighter."})
    assert again.get("existing") is True
    assert len(client.get(f"/api/docs/{did}").json()["versions"]) == 2

    with pytest.raises(ApiError, match="body is required"):
        tr.call("doc_version", {"id": did, "body": "   "})
    with pytest.raises(ApiError, match="id is required"):
        tr.call("doc_version", {"body": "x"})


def test_doc_version_refuses_an_unknown_doc_and_names_a_decision(client: TestClient) -> None:
    from backend.mcp import ApiError
    tr, _ = _translator(client)
    with pytest.raises(ApiError, match=r"404: doc not found: dc_nothere1 — the doc id"):
        tr.call("doc_version", {"id": "dc_nothere1", "body": "# Text"})
    # Decisions mint dc_ ids too: the refusal says which it was.
    dec = client.post("/api/decisions", json={
        "created_date": "2608-19", "created_time": "10:00", "project": "alpha", "agent_id": "operator",
        "decision": "Keep versions append-only", "why": "history", "alternatives": "",
    })
    assert dec.status_code == 201, dec.text
    dec_id = dec.json()["metadata"]["id"]
    assert dec_id.startswith("dc_")
    with pytest.raises(ApiError, match="is a decision, not a Storyboard document"):
        tr.call("doc_version", {"id": dec_id, "body": "# Text"})


def test_the_operator_pastes_a_version(client: TestClient, root: Path) -> None:
    did = client.post("/api/docs", json={"project": "alpha", "kind": "faq", "title": "FAQ"}).json()["doc"]["id"]
    # A version file written before the note column existed still reads.
    (root / "doc_versions.csv").write_text(
        f"id,doc_id,created_at,agent_id,body\ndv_old00001,{did},2026-10-01T10:00:00,operator,Old text\n",
        encoding="utf-8")
    r = client.post(f"/api/docs/{did}/versions", json={"body": "**Q:** why?\n\n**A:** because.",
                                                      "note": "  pasted from\na chat  ", "agent_id": "operator"})
    assert r.status_code == 201, r.text
    v = r.json()["version"]
    assert v["agent_id"] == "operator" and v["note"] == "pasted from a chat"
    d = client.get(f"/api/docs/{did}").json()
    assert [x["id"] for x in d["versions"]] == [v["id"], "dv_old00001"]
    assert d["versions"][1]["note"] == ""
    assert client.post(f"/api/docs/{did}/versions", json={"body": "x", "note": "n" * 401}).status_code == 422
    assert client.post("/api/docs/dc_nothere1/versions", json={"body": "x"}).status_code == 404
