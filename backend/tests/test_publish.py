"""Publish — #publish cards, the documents and their versions (publishlib.py, docs/publish.md)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.actors import AGENT_REFUSED
from tests.conftest import make_chat

AGENT = "cc-pub00001"
OP = {"actor": "operator"}


@pytest.fixture()
def pub(client: TestClient, data_root: Path) -> TestClient:
    tid = client.post("/api/tasks", json={"created_date": "2611-04", "created_time": "10:00", "project": "ALPHA",
                                          "agent_id": "operator", "title": "Task window saves what changed", "status": "done"}).json()["metadata"]["id"]
    make_chat(data_root, "ALPHA", AGENT, [
        ("2026-11-04T10:00:00", f"{tid} let's fix the window", "on it"),
        ("2026-11-04T10:30:00", "#publish The task window now sends only what changed: a title fix no longer clears the agent's report.", "kept"),
        ("2026-11-04T11:00:00", "#publish Cores: the parts of the program kept in view, each with its story.", "kept"),
        ("2026-11-04T11:10:00", "#publish", "a tag alone keeps nothing"),
    ])
    client.app.state.store.rebuild()
    client.tid = tid  # type: ignore[attr-defined]
    return client


def _board(c: TestClient) -> dict:
    r = c.get("/api/publishing?project=ALPHA")
    assert r.status_code == 200, r.text
    return r.json()


def test_a_publish_message_is_a_card_with_its_text_and_its_task(pub: TestClient) -> None:
    page = _board(pub)
    assert [c["text"][:14] for c in page["cards"]] == ["Cores: the par", "The task windo"]   # newest first
    card = page["cards"][1]
    assert card["id"].startswith("pu_") and card["message"] == card["text"]
    assert not card["message"].startswith("#")
    assert [t["id"] for t in card["tasks"]] == [pub.tid]                                   # the chat's task at that turn
    assert card["versions"] == [] and card["placements"] == []
    assert page["docs"] == []
    # The lens list has the same cards; an agent cannot make one.
    assert len(pub.get("/api/publish?project=ALPHA").json()["publish"]) == 2
    r = pub.post("/api/publish", json={"created_date": "2611-04", "created_time": "10:00", "project": "ALPHA",
                                        "agent_id": AGENT, "l1": "x", "l4": "y"})
    assert r.status_code == AGENT_REFUSED and "#publish message" in r.json()["detail"]


def test_the_operator_edits_the_text_in_versions(pub: TestClient) -> None:
    card = _board(pub)["cards"][1]
    r = pub.post(f"/api/publishing/cards/{card['id']}/text", json={**OP, "text": "The task window saves only what you changed."})
    assert r.status_code == 200, r.text
    got = r.json()["card"]
    assert got["text"] == "The task window saves only what you changed." and len(got["versions"]) == 1
    assert got["versions"][0]["at"].startswith("20") and "T" in got["versions"][0]["at"]      # ISO, as the page reads
    assert got["message"].startswith("The task window now sends")                          # the original stays
    # The same text again is no version; an agent may not edit.
    pub.post(f"/api/publishing/cards/{card['id']}/text", json={**OP, "text": "The task window saves only what you changed."})
    assert len(pub.get(f"/api/publishing/cards/{card['id']}").json()["versions"]) == 1
    r = pub.post(f"/api/publishing/cards/{card['id']}/text", json={"agent_id": AGENT, "text": "mine"})
    assert r.status_code == AGENT_REFUSED
    assert [h["what"] for h in pub.get(f"/api/publishing/cards/{card['id']}").json()["history"]] == ["kept", "edited"]


def test_documents_versions_and_placements(pub: TestClient) -> None:
    page = _board(pub)
    a, b = page["cards"][1], page["cards"][0]
    r = pub.post("/api/publishing/docs", json={**OP, "project": "ALPHA", "name": "Release 0.9"})
    assert r.status_code == 201, r.text
    doc = r.json()["doc"]
    assert doc["current"] == 1 and doc["versions"][0]["items"] == []
    assert pub.post("/api/publishing/docs", json={**OP, "project": "ALPHA", "name": "release 0.9"}).status_code == 200  # the same name
    # Place a, then b before a; the text defaults to the card's current text.
    r = pub.post(f"/api/publishing/docs/{doc['id']}/items", json={**OP, "card_id": a["id"]})
    assert r.status_code == 201 and r.json()["item"]["text"] == a["text"] and r.json()["item"]["changed"] is False
    first = r.json()["item"]["id"]
    r = pub.post(f"/api/publishing/docs/{doc['id']}/items", json={**OP, "card_id": b["id"], "before": first})
    assert r.status_code == 201
    assert pub.post(f"/api/publishing/docs/{doc['id']}/items", json={**OP, "card_id": b["id"]}).status_code == 200  # once per version
    page = _board(pub)
    v1 = page["docs"][0]["versions"][0]
    assert [i["card_id"] for i in v1["items"]] == [b["id"], a["id"]]
    assert [p["doc_name"] for p in page["cards"][1]["placements"]] == ["Release 0.9"]
    # Edit the item in the document: the card says the text changed there.
    item = v1["items"][1]["id"]
    assert pub.post(f"/api/publishing/items/{item}/update", json={**OP, "text": "Shorter."}).json()["item"]["changed"] is True
    assert _board(pub)["cards"][1]["placements"][0]["changed"] is True
    # The next version copies the items; a removal in v2 leaves v1 as it was.
    r = pub.post(f"/api/publishing/docs/{doc['id']}/versions", json={**OP, "note": "second pass"})
    assert r.status_code == 201 and r.json()["doc"]["current"] == 2
    v2 = r.json()["doc"]["versions"][1]
    assert [i["card_id"] for i in v2["items"]] == [b["id"], a["id"]] and v2["note"] == "second pass"
    assert pub.post(f"/api/publishing/items/{v2['items'][0]['id']}/remove", json=OP).json()["removed"] is True
    page = _board(pub)
    assert len(page["docs"][0]["versions"][0]["items"]) == 2 and len(page["docs"][0]["versions"][1]["items"]) == 1
    md = pub.get(f"/api/publishing/docs/{doc['id']}/markdown?n=1").text
    assert md.startswith("# Release 0.9") and "Shorter." in md and b["text"] in md
    hist = [h["what"] for h in pub.get(f"/api/publishing/cards/{b['id']}").json()["history"]]
    assert hist == ["kept", "placed", "placed", "removed from"]
    # Rename and archive; an agent may not.
    assert pub.post(f"/api/publishing/docs/{doc['id']}/update", json={**OP, "name": "Release 1.0"}).json()["doc"]["name"] == "Release 1.0"
    assert pub.post(f"/api/publishing/docs/{doc['id']}/update", json={"agent_id": AGENT, "name": "x"}).status_code == AGENT_REFUSED
    assert pub.post("/api/publishing/docs", json={**OP, "project": "ALPHA", "name": "x" * 81}).status_code == 422
    assert pub.post(f"/api/publishing/docs/{doc['id']}/items", json={**OP, "card_id": "pu_nope"}).status_code == 422


def test_a_cards_files_carry_their_line_counts(pub: TestClient, monkeypatch) -> None:
    from backend import taskwork
    monkeypatch.setattr(taskwork, "task_work", lambda store, tid: {
        "commit_list": [], "files": [{"path": "a.py", "lines_add": 12, "lines_del": 3}]})
    card = _board(pub)["cards"][1]
    assert card["files"] == [{"path": "a.py", "add": 12, "del": 3}]


def test_the_hook_names_the_card_and_asks_nothing(tmp_path: Path) -> None:
    import importlib.util
    import sys
    hooks = Path(__file__).resolve().parents[2] / "scripts" / "hooks"
    spec = importlib.util.spec_from_file_location("sp_capture_publish", hooks / "capture.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sp_capture_publish"] = mod
    spec.loader.exec_module(mod)
    root = tmp_path / "data"
    root.mkdir()
    cap = mod.TurnCapture(root, "alpha", "cc-abc12345")
    signals = cap.open_turn("#publish the window saves only what changed")
    assert [k["kind"] for k in signals["kept"]] == ["publish"]
    assert signals["kept"][0]["id"].startswith("pu_")
    notice = mod.format_signals(signals)
    assert "write nothing" in notice and "publish_attach" in notice and signals["kept"][0]["id"] in notice


PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


def test_images_and_links_are_attached_by_the_operator_or_the_agent(pub: TestClient) -> None:
    card = _board(pub)["cards"][1]
    r = pub.post(f"/api/publishing/cards/{card['id']}/attach", json={
        "agent_id": AGENT,
        "images": [{"title": "The window", "ext": "png", "data_base64": PNG}],
        "links": [{"title": "The commit", "url": "https://example.org/c/abc"}]})
    assert r.status_code == 201, r.text
    got = r.json()
    assert [a["kind"] for a in got["attached"]] == ["image", "link"] and not any(a["existing"] for a in got["attached"])
    img = next(i for i in got["card"]["images"] if i.get("from") == "attached")
    assert img["label"] == "The window" and img["by"] == AGENT
    assert pub.get(img["url"]).status_code == 200 and pub.get(img["url"]).headers["content-type"].startswith("image/")
    assert got["card"]["links"][0]["url"] == "https://example.org/c/abc"
    # The same image again is the existing attachment; a bad link is refused; the operator removes.
    r = pub.post(f"/api/publishing/cards/{card['id']}/attach", json={**OP, "images": [{"title": "x", "ext": "png", "data_base64": PNG}]})
    assert r.status_code == 201 and r.json()["attached"][0]["existing"] is True
    assert pub.post(f"/api/publishing/cards/{card['id']}/attach", json={**OP, "links": [{"url": "ftp://x"}]}).status_code == 422
    assert pub.post(f"/api/publishing/cards/{card['id']}/attach", json={**OP}).status_code == 422
    aid = img["id"]
    assert pub.post(f"/api/publishing/attachments/{aid}/remove", json={"agent_id": AGENT}).status_code == AGENT_REFUSED
    assert pub.post(f"/api/publishing/attachments/{aid}/remove", json=OP).json()["removed"] is True
    assert not any(i.get("from") == "attached" for i in _board(pub)["cards"][1]["images"])
    assert pub.get(f"/api/publishing/attachments/{aid}/file").status_code == 200   # the file stays; the card no longer lists it


def test_the_agents_tool_attaches_through_the_gate(client: TestClient, data_root: Path, monkeypatch) -> None:
    from backend import mcp, server as _server
    from backend.server import create_app
    from tests.test_mcp_tools_pass_the_gate import _GatedApi
    make_chat(data_root, "ALPHA", AGENT, [("2026-11-04T10:30:00", "#publish The window saves what changed.", "kept")])
    monkeypatch.setattr(_server.AgentsViaMcp, "_enforced", lambda self: True)
    monkeypatch.setattr(mcp.Translator, "identity", lambda self: {"project": "ALPHA", "agent_id": AGENT})
    with TestClient(create_app(data_root=data_root, watch=False, run_monitor=False)) as c:
        tr = mcp.Translator(_GatedApi(c), cwd=str(data_root))
        card = c.get("/api/publishing?project=ALPHA").json()["cards"][0]
        out = tr.call("publish_attach", {"id": card["id"], "links": [{"title": "docs", "url": "https://example.org/docs"}]})
        assert out["attached"][0]["kind"] == "link" and out["card"]["links"][0]["by"] == AGENT


def test_the_tool_reads_an_image_from_a_path(tmp_path: Path) -> None:
    import base64
    from backend import mcp
    img = tmp_path / "shot.png"
    img.write_bytes(base64.b64decode(PNG))
    posted: dict = {}

    class Api:
        def get(self, path):
            return {"lenses": [], "vocabularies": {}}

        def post(self, path, body):
            posted["path"], posted["body"] = path, body
            return {"attached": []}
    tr = mcp.Translator(Api(), cwd=str(tmp_path))  # type: ignore[arg-type]
    tr.identity = lambda: {"project": "ALPHA", "agent_id": AGENT}  # type: ignore[method-assign]
    tr.call("publish_attach", {"id": "pu_x", "images": [{"path": str(img)}]})
    item = posted["body"]["images"][0]
    assert posted["path"] == "/api/publishing/cards/pu_x/attach"
    assert item["title"] == "shot" and item["ext"] == "png" and item["data_base64"] == PNG and "path" not in item
    with pytest.raises(mcp.ApiError):
        tr.call("publish_attach", {"id": "pu_x", "images": [{"path": str(tmp_path / "none.png")}]})


def test_a_card_written_by_hand_on_the_page(pub: TestClient) -> None:
    r = pub.post("/api/publishing/cards", json={**OP, "project": "ALPHA", "text": "Sprints: a board per week.\nMore below."})
    assert r.status_code == 201, r.text
    card = r.json()["card"]
    assert card["message"] == "Sprints: a board per week.\nMore below." and card["text"] == card["message"]
    assert card["agent_id"] == "operator" and card["tasks"] == []
    assert pub.post("/api/publishing/cards", json={**OP, "project": "ALPHA", "text": "Sprints: a board per week.\nMore below."}).status_code == 200
    assert pub.post("/api/publishing/cards", json={"agent_id": AGENT, "project": "ALPHA", "text": "mine"}).status_code == AGENT_REFUSED
    assert pub.post("/api/publishing/cards", json={**OP, "project": "ALPHA", "text": ""}).status_code == 422
    assert [c["id"] for c in _board(pub)["cards"]][0] == card["id"]
    assert pub.post(f"/api/publishing/cards/{card['id']}/text", json={**OP, "text": "Sprints: one board per week."}).status_code == 200
