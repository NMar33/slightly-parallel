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


def test_a_publish_message_is_a_card_with_its_text_and_nothing_guessed(pub: TestClient) -> None:
    page = _board(pub)
    assert [c["text"][:14] for c in page["cards"]] == ["Cores: the par", "The task windo"]   # newest first
    card = page["cards"][1]
    assert card["id"].startswith("pu_") and card["message"] == card["text"]
    assert not card["message"].startswith("#")
    # The chat named a task before the #publish: the server no longer takes it.
    assert card["tasks"] == [] and card["commits"] == [] and card["files"] == [] and card["images"] == []
    assert card["versions"] == [] and card["placements"] == [] and card["context"] == "" and card["rev"] == 0
    assert [s["kind"] for s in card["sources"]] == ["kept"] and card["sources"][0]["text"] == card["message"]
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


def test_a_cards_files_are_only_the_ones_attached(pub: TestClient, monkeypatch) -> None:
    """A task's work (files of another repository, uncommitted ones) never
    shows on a card: only what was attached to it."""
    from backend import taskwork
    monkeypatch.setattr(taskwork, "task_work", lambda store, tid: {
        "commit_list": [{"sha": "abc1234", "subject": "x", "at": "2026-11-04T10:00:00"}],
        "files": [{"path": "brand/video-ideas/LinkedIn.md", "lines_add": 12, "lines_del": 3}]})
    card = _board(pub)["cards"][1]
    r = pub.post(f"/api/publishing/cards/{card['id']}/write", json={"agent_id": AGENT, "tasks": [pub.tid]})
    assert r.status_code == 200, r.text
    got = _board(pub)["cards"][1]
    assert [t["id"] for t in got["tasks"]] == [pub.tid]
    assert got["files"] == [] and got["commits"] == []


def _capture(tmp_path: Path):
    import importlib.util
    import sys
    hooks = Path(__file__).resolve().parents[2] / "scripts" / "hooks"
    spec = importlib.util.spec_from_file_location("sp_capture_publish", hooks / "capture.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sp_capture_publish"] = mod
    spec.loader.exec_module(mod)
    root = tmp_path / "data"
    root.mkdir(exist_ok=True)
    return mod, root


def test_the_hook_asks_the_agent_to_write_the_card(tmp_path: Path) -> None:
    mod, root = _capture(tmp_path)
    cap = mod.TurnCapture(root, "alpha", "cc-abc12345")
    signals = cap.open_turn("#publish the window saves only what changed")
    assert [k["kind"] for k in signals["kept"]] == ["publish"]
    cid = signals["kept"][0]["id"]
    assert cid.startswith("pu_") and "near" not in signals["kept"][0]
    notice = mod.format_signals(signals)
    assert "write nothing" not in notice and f'publish_write {{id: "{cid}"}}' in notice
    assert "context" in notice and "never guessed" in notice


def test_the_hook_names_the_chats_card_of_the_last_hour(tmp_path: Path, monkeypatch) -> None:
    mod, root = _capture(tmp_path)
    clock = {"t": 1_800_000_000.0}
    monkeypatch.setattr(mod.shared, "now_epoch", lambda: clock["t"])
    cap = mod.TurnCapture(root, "alpha", "cc-abc12345")
    first = cap.open_turn("#publish time zones: a session's day stays put")["kept"][0]["id"]
    cap.complete_turn("kept")
    clock["t"] += 20 * 60
    second = cap.open_turn("#publish the timezone fix, again, shorter")
    k = second["kept"][0]
    assert k["near"] == {"id": first, "minutes": 20}
    notice = mod.format_signals(second)
    assert f'merge: "{k["id"]}"' in notice and first in notice
    cap.complete_turn("kept")
    clock["t"] += 2 * 3600                                  # past the hour: a new card, no hint
    assert "near" not in cap.open_turn("#publish another story")["kept"][0]


def test_the_hook_appends_to_a_card_named_after_the_tag(tmp_path: Path) -> None:
    mod, root = _capture(tmp_path)
    (root / "publish.csv").write_text("id,project\npu_0123abcd,alpha\npu_99999999,beta\n", encoding="utf-8")
    cap = mod.TurnCapture(root, "alpha", "cc-abc12345")
    signals = cap.open_turn("#publish pu_0123abcd add how it looks on a phone")
    k = signals["kept"][0]
    assert k["append_to"] == "pu_0123abcd"
    notice = mod.format_signals(signals)
    assert "pu_0123abcd" in notice and "only that" in notice and k["id"] not in notice
    cap.complete_turn("ok")
    # A card of another project is no card to append to: the message is a new card.
    other = cap.open_turn("#publish pu_99999999 more")["kept"][0]
    assert "append_to" not in other


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
    assert posted["path"] == "/api/publishing/cards/pu_x/write"                 # the alias forwards
    assert item["title"] == "shot" and item["ext"] == "png" and item["data_base64"] == PNG and "path" not in item
    assert item["source"] == str(img)
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


def test_an_agent_attaches_to_a_card_nobody_has_opened_yet(client: TestClient, data_root: Path) -> None:
    """The hook gives the id at #publish; the card is made on adoption. The
    attach adopts first, so it never answers 404 for a card not yet read."""
    from backend import keeplib
    make_chat(data_root, "ALPHA", AGENT, [("2026-11-04T10:30:00", "#publish Time zones: a session's day stays put after a flight.", "kept")])
    client.app.state.store.rebuild()
    cid = keeplib.keep_id("publish", "ALPHA", AGENT, 1)
    r = client.post(f"/api/publishing/cards/{cid}/attach", json={"agent_id": AGENT, "links": [{"title": "docs", "url": "https://example.org/d"}]})
    assert r.status_code == 201, r.text
    assert r.json()["card"]["links"][0]["url"] == "https://example.org/d"


def _write(c: TestClient, cid: str, **body) -> dict:
    r = c.post(f"/api/publishing/cards/{cid}/write", json={"agent_id": AGENT, **body})
    assert r.status_code == 200, r.text
    return r.json()


def test_the_agent_writes_text_and_context_in_versions(pub: TestClient) -> None:
    card = _board(pub)["cards"][0]
    got = _write(pub, card["id"], context="Before: a title fix cleared the report. After: only the title is sent.")
    assert got["wrote"] == ["context"] and got["rev"] == 1
    c = got["card"]
    assert c["text"] == c["message"] and c["versions"] == []           # the operator's text stays
    assert c["context_versions"][0]["by"] == AGENT and c["context"].startswith("Before:")
    # The message as the text again is no version; a written text is, by the agent.
    assert _write(pub, card["id"], text=c["message"], base=1)["wrote"] == []
    got = _write(pub, card["id"], text="Cores keep the program's parts in view.", base=1, note="shorter")
    assert got["rev"] == 2 and got["card"]["versions"][0]["by"] == AGENT
    # A stale base writes nothing.
    r = pub.post(f"/api/publishing/cards/{card['id']}/write", json={"agent_id": AGENT, "context": "x", "base": 1})
    assert r.status_code == 422 and "rev 2" in r.json()["detail"]
    # The operator edits the context on the page: a version by the operator.
    r = pub.post(f"/api/publishing/cards/{card['id']}/write", json={**OP, "context": "Only the title is sent now."})
    assert r.status_code == 200 and r.json()["card"]["context_versions"][-1]["by"] == "operator"
    hist = [h["what"] for h in pub.get(f"/api/publishing/cards/{card['id']}").json()["history"]]
    assert hist.count("context") == 2 and "written" in hist


def test_tasks_attach_by_id_from_any_project_and_unknown_ones_are_refused(pub: TestClient) -> None:
    beta = pub.post("/api/tasks", json={"created_date": "2611-04", "created_time": "10:00", "project": "BETA",
                                        "agent_id": "operator", "title": "Tracker export", "status": "todo"}).json()["metadata"]["id"]
    card = _board(pub)["cards"][0]
    r = pub.post(f"/api/publishing/cards/{card['id']}/write", json={"agent_id": AGENT, "tasks": [pub.tid, "tk_00000000"],
                                                                     "context": "never written"})
    assert r.status_code == 422 and "tk_00000000 is not a task" in r.json()["detail"]
    assert _board(pub)["cards"][0]["context"] == ""                     # a refusal writes nothing
    got = _write(pub, card["id"], tasks=[pub.tid, beta])["card"]
    assert [(t["id"], t["project"]) for t in got["tasks"]] == [(pub.tid, "ALPHA"), (beta, "BETA")]
    # Again is the same links; the operator removes one.
    again = _write(pub, card["id"], tasks=[beta])
    assert again["attached"][0]["existing"] is True and len(again["card"]["tasks"]) == 2
    aid = got["tasks"][1]["attachment_id"]
    assert pub.post(f"/api/publishing/attachments/{aid}/remove", json=OP).json()["removed"] is True
    assert [t["id"] for t in _board(pub)["cards"][0]["tasks"]] == [pub.tid]


def test_ids_pasted_in_the_message_do_not_attach(client: TestClient, data_root: Path) -> None:
    other = client.post("/api/tasks", json={"created_date": "2611-04", "created_time": "10:00", "project": "BETA",
                                            "agent_id": "operator", "title": "Writing tracker", "status": "todo"}).json()["metadata"]["id"]
    mine = client.post("/api/tasks", json={"created_date": "2611-04", "created_time": "10:00", "project": "ALPHA",
                                           "agent_id": "operator", "title": "Mine", "status": "todo"}).json()["metadata"]["id"]
    make_chat(data_root, "ALPHA", AGENT, [
        ("2026-11-04T10:00:00", f"{mine} start", "ok"),
        ("2026-11-04T10:30:00", f"#publish Notes ship. Pasted from the tracker: \"{other} export\".", "kept")])
    client.app.state.store.rebuild()
    card = _board(client)["cards"][0]
    assert card["tasks"] == []


def test_a_publish_with_a_card_id_appends_to_that_card(client: TestClient, data_root: Path) -> None:
    from backend import keeplib
    make_chat(data_root, "ALPHA", AGENT, [("2026-11-04T10:30:00", "#publish Time zones: a day stays put after a flight.", "kept")])
    client.app.state.store.rebuild()
    cid = _board(client)["cards"][0]["id"]
    make_chat(data_root, "ALPHA", "cc-pub00002", [
        ("2026-11-05T09:00:00", f"#publish {cid} add how it looks on a phone", "ok"),
        ("2026-11-05T09:10:00", "#publish pu_ffffffff a card that is not there", "new card")])
    client.app.state.store.rebuild()
    cards = _board(client)["cards"]
    assert len(cards) == 2                                    # the unknown id made a card; the known one did not
    card = next(c for c in cards if c["id"] == cid)
    assert [(s["kind"], s["text"]) for s in card["sources"]] == [
        ("kept", "Time zones: a day stays put after a flight."), ("appended", "add how it looks on a phone")]
    # The appended message's own id (the hook's keep id) leads to the card.
    sid = keeplib.keep_id("publish", "ALPHA", "cc-pub00002", 1)
    r = client.post(f"/api/publishing/cards/{sid}/write", json={"agent_id": "cc-pub00002", "context": "On a phone: one column."})
    assert r.status_code == 200 and r.json()["id"] == cid
    # The operator drops the appended message.
    assert client.post(f"/api/publishing/sources/{sid}/remove", json=OP).json()["removed"] is True
    assert [s["kind"] for s in next(c for c in _board(client)["cards"] if c["id"] == cid)["sources"]] == ["kept"]


def test_a_duplicate_is_merged_and_taken_back(pub: TestClient) -> None:
    page = _board(pub)
    new, old = page["cards"][0], page["cards"][1]
    _write(pub, new["id"], links=[{"title": "docs", "url": "https://example.org/d"}])
    # The agent folds its own chat's card in; another chat's agent may not.
    r = pub.post(f"/api/publishing/cards/{old['id']}/write", json={"agent_id": "cc-other999", "merge": new["id"]})
    assert r.status_code == 422
    got = _write(pub, old["id"], merge=new["id"])
    assert got["wrote"] == ["merge"] and got["card"]["merged_from"] == [new["id"]]
    assert [s["kind"] for s in got["card"]["sources"]] == ["kept", "merged"]
    assert got["card"]["links"][0]["url"] == "https://example.org/d"     # the merged card's attachments come along
    assert [c["id"] for c in _board(pub)["cards"]] == [old["id"]]
    # A write to the merged card's id lands on the card it went into.
    assert _write(pub, new["id"], context="One story.")["id"] == old["id"]
    # The operator takes it back: both cards again.
    sid = got["card"]["sources"][1]["id"]
    assert pub.post(f"/api/publishing/sources/{sid}/remove", json=OP).status_code == 200
    assert len(_board(pub)["cards"]) == 2
    # The operator merges on the page; an agent may not use that route.
    assert pub.post(f"/api/publishing/cards/{new['id']}/merge", json={"agent_id": AGENT, "into": old["id"]}).status_code == AGENT_REFUSED
    r = pub.post(f"/api/publishing/cards/{new['id']}/merge", json={**OP, "into": old["id"]})
    assert r.status_code == 200 and r.json()["card"]["id"] == old["id"]
    assert pub.post(f"/api/publishing/cards/{old['id']}/merge", json={**OP, "into": old["id"]}).status_code == 422


def test_a_file_is_copied_onto_the_card(client: TestClient, data_root: Path, tmp_path: Path, monkeypatch) -> None:
    from backend import mcp, server as _server
    from backend.server import create_app
    from tests.test_mcp_tools_pass_the_gate import _GatedApi
    make_chat(data_root, "ALPHA", AGENT, [("2026-11-04T10:30:00", "#publish The load test report.", "kept")])
    report = tmp_path / "elsewhere" / "load-test.txt"
    report.parent.mkdir()
    report.write_bytes(b"p95 180 ms at 400 rps\n")             # as bytes: Windows would write \r\n
    shot = tmp_path / "elsewhere" / "chart.png"
    import base64
    shot.write_bytes(base64.b64decode(PNG))
    monkeypatch.setattr(_server.AgentsViaMcp, "_enforced", lambda self: True)
    monkeypatch.setattr(mcp.Translator, "identity", lambda self: {"project": "ALPHA", "agent_id": AGENT})
    with TestClient(create_app(data_root=data_root, watch=False, run_monitor=False)) as c:
        tr = mcp.Translator(_GatedApi(c), cwd=str(data_root))
        cid = c.get("/api/publishing?project=ALPHA").json()["cards"][0]["id"]
        out = tr.call("publish_write", {"id": cid, "context": "400 rps for ten minutes.",
                                        "files": [{"path": str(report), "title": "Load test report"}],
                                        "images": [{"path": str(shot), "title": "p95 chart"}]})
        f = out["card"]["files"][0]
        assert f["name"] == "Load test report" and f["path"] == str(report) and f["size"] == report.stat().st_size
        got = c.get(f["url"])
        assert got.status_code == 200 and got.text == "p95 180 ms at 400 rps\n"
        assert out["card"]["images"][0]["label"] == "p95 chart"
        report.unlink()                                         # the card keeps its copy
        assert c.get(f["url"]).status_code == 200
        with pytest.raises(mcp.ApiError):
            tr.call("publish_write", {"id": cid, "files": [{"path": str(tmp_path / "none.txt")}]})
        # The older tool forwards to the new one.
        out = tr.call("publish_attach", {"id": cid, "links": [{"title": "docs", "url": "https://example.org/docs"}]})
        assert out["attached"][0]["kind"] == "link"


def test_a_commit_is_attached_with_its_repository(pub: TestClient, tmp_path: Path) -> None:
    import subprocess
    repo = tmp_path / "repo"
    repo.mkdir()
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.org", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.org", "HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=env)
    (repo / "a.txt").write_text("a", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True, env=env)
    subprocess.run(["git", "commit", "-qm", "The window sends only what changed"], cwd=repo, check=True, env=env)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
    card = _board(pub)["cards"][0]
    got = _write(pub, card["id"], commits=[{"sha": sha[:9], "repo": str(repo)}])["card"]
    assert got["commits"][0]["sha"] == sha[:12] and got["commits"][0]["subject"] == "The window sends only what changed"
    assert got["commits"][0]["repo"] == str(repo)
    r = pub.post(f"/api/publishing/cards/{card['id']}/write", json={"agent_id": AGENT, "commits": [{"sha": "deadbeef1", "repo": str(repo)}]})
    assert r.status_code == 422 and "not a commit" in r.json()["detail"]


def test_the_migration_keeps_a_guessed_task_only_of_the_cards_project(pub: TestClient, data_root: Path) -> None:
    from backend import publishlib
    store = pub.app.state.store
    beta = pub.post("/api/tasks", json={"created_date": "2611-04", "created_time": "10:00", "project": "BETA",
                                        "agent_id": "operator", "title": "Elsewhere", "status": "todo"}).json()["metadata"]["id"]
    make_chat(data_root, "ALPHA", "cc-pub00003", [("2026-11-06T10:00:00", f"#publish Pasted: {beta} export.", "kept")])
    store.rebuild()
    _board(pub)
    (data_root / publishlib.MIGRATION_FILE).unlink()          # the start of the app wrote it on the empty root
    got = publishlib.migrate(store)
    assert got == {"frozen": 2, "dropped": 1}                 # both ALPHA cards of the chat that named the task
    cards = {c["message"][:5]: c for c in _board(pub)["cards"]}
    assert [t["id"] for t in cards["The t"]["tasks"]] == [pub.tid] and cards["Paste"]["tasks"] == []
    assert any(p.name.startswith("publish-migration-") for p in (data_root.parent).rglob("publish-migration-*"))
    assert publishlib.migrate(store) == {"frozen": 0, "dropped": 0}   # once
