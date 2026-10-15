"""Integrate: a saved set written into a project's AGENTS.md, kept current, taken out."""

from __future__ import annotations

from pathlib import Path

from backend import keeplib
from tests.conftest import make_chat

AGENT = "alpha-lead-2608-01"
OWN = "# Proj\n\nOwn notes.\n"


def _project(root: Path, tmp_path: Path) -> Path:
    folder = tmp_path / "proj"
    folder.mkdir()
    (folder / "AGENTS.md").write_text(OWN, encoding="utf-8")
    (root / "integrations.csv").write_text(f"project,path,created_date\nALPHA,{folder},2609-01\n", encoding="utf-8")
    return folder


def _statuses(client, set_id: str) -> list[str]:
    return [i["status"] for i in client.get(f"/api/sets/{set_id}/integrations").json()["integrations"]]


def test_a_set_is_written_kept_current_and_taken_out(client, tmp_path):
    root = Path(client.app.state.store.data_root)
    folder = _project(root, tmp_path)
    make_chat(root, "ALPHA", AGENT, [("2026-09-01T10:00:00", "#vision Keep the board calm.", "ok")])
    client.app.state.store.rebuild()
    vid = keeplib.keep_id("vision", "ALPHA", AGENT, 1)
    client.post(f"/api/visions/{vid}/interpretation", json={"agent_id": "cc-abc12345", "text": "The board shows only live work."})
    s = client.post("/api/sets", json={"name": "Board", "kind": "vision", "items": [vid]}).json()

    assert [t["project"] for t in client.get("/api/integrations/targets").json()["targets"]] == ["ALPHA"]

    dry = client.post(f"/api/sets/{s['id']}/integrate", json={"project": "ALPHA", "dry_run": True}).json()
    assert dry["action"] == "appended" and "The board shows only live work." in dry["content"]
    assert (folder / "AGENTS.md").read_text(encoding="utf-8") == OWN, "a preview writes nothing"
    assert _statuses(client, s["id"]) == []

    done = client.post(f"/api/sets/{s['id']}/integrate", json={"project": "ALPHA"}).json()
    assert done["action"] == "appended"
    text = (folder / "AGENTS.md").read_text(encoding="utf-8")
    assert text.startswith(OWN) and f"<!-- sp:set {s['id']} -->" in text and "## Board" in text
    assert _statuses(client, s["id"]) == ["fresh"]

    client.post(f"/api/visions/{vid}/interpretation", json={"actor": "operator", "text": "Only live work on the board."})
    assert _statuses(client, s["id"]) == ["stale"]

    again = client.post(f"/api/sets/{s['id']}/integrate", json={"project": "ALPHA"}).json()
    assert again["action"] == "updated"
    text = (folder / "AGENTS.md").read_text(encoding="utf-8")
    assert "Only live work on the board." in text and text.count("<!-- sp:set ") == 1
    assert _statuses(client, s["id"]) == ["fresh"]

    gone = client.post(f"/api/sets/{s['id']}/integrate/remove", json={"project": "ALPHA"}).json()
    assert gone["action"] == "removed"
    assert (folder / "AGENTS.md").read_text(encoding="utf-8") == OWN
    assert _statuses(client, s["id"]) == []


def test_rules_are_written_as_one_numbered_list(client, tmp_path):
    root = Path(client.app.state.store.data_root)
    folder = _project(root, tmp_path)
    make_chat(root, "ALPHA", AGENT, [
        ("2026-09-01T10:00:00", "#rule never install anything", "ok"),
        ("2026-09-01T10:05:00", "#rule never deploy", "ok"),
    ])
    client.app.state.store.rebuild()
    a, b = (keeplib.keep_id("rule", "ALPHA", AGENT, n) for n in (1, 2))
    client.post(f"/api/rules/{a}/interpretation", json={"agent_id": "cc-x", "text": "Ask before installing anything."})
    client.post(f"/api/rules/{b}/interpretation", json={"agent_id": "cc-x", "text": "Deploy only when asked."})
    s = client.post("/api/sets", json={"name": "Safety", "kind": "rule", "items": [b, a]}).json()
    client.post(f"/api/sets/{s['id']}/integrate", json={"project": "ALPHA"})
    text = (folder / "AGENTS.md").read_text(encoding="utf-8")
    assert "1. Deploy only when asked.\n2. Ask before installing anything." in text


def test_integrate_writes_only_into_a_project_set_up_in_setup(client, tmp_path):
    root = Path(client.app.state.store.data_root)
    _project(root, tmp_path)
    s = client.post("/api/sets", json={"name": "Board", "kind": "vision"}).json()
    assert client.post(f"/api/sets/{s['id']}/integrate", json={"project": "NOPE"}).status_code == 409
    assert client.post(f"/api/sets/{s['id']}/integrate", json={"project": ""}).status_code == 409
    assert client.post("/api/sets/ks_00000000/integrate", json={"project": "ALPHA"}).status_code == 404


def test_rules_for_all_agents_are_kept_written_into_every_project(client, tmp_path):
    root = Path(client.app.state.store.data_root)
    a_dir, b_dir = tmp_path / "a", tmp_path / "b"
    a_dir.mkdir()
    b_dir.mkdir()
    (a_dir / "AGENTS.md").write_text(OWN, encoding="utf-8")
    (root / "integrations.csv").write_text(
        f"project,path,created_date\nALPHA,{a_dir},2609-01\nBETA,{b_dir},2609-01\n", encoding="utf-8")
    make_chat(root, "ALPHA", AGENT, [
        ("2026-09-01T10:00:00", "#rule never install anything", "ok"),
        ("2026-09-01T10:05:00", "#rule never deploy", "ok"),
    ])
    client.app.state.store.rebuild()
    r1, r2 = (keeplib.keep_id("rule", "ALPHA", AGENT, n) for n in (1, 2))
    client.post(f"/api/rules/{r1}/interpretation", json={"agent_id": "cc-x", "text": "Ask before installing anything."})
    client.post(f"/api/rules/{r2}/interpretation", json={"agent_id": "cc-x", "text": "Deploy only when asked."})
    mark = "<!-- sp:set all-rules -->"
    files = lambda: [(d / "AGENTS.md").read_text(encoding="utf-8") if (d / "AGENTS.md").exists() else "" for d in (a_dir, b_dir)]
    assert all(mark not in f for f in files()), "nothing is written before a rule is for all agents"

    assert client.post(f"/api/rules/{r1}/update", json={"auto": "yes", "agent_id": "cc-x"}).status_code == 422
    client.post(f"/api/rules/{r1}/update", json={"auto": "yes", "actor": "operator"})
    a, b = files()
    assert a.startswith(OWN) and "1. Ask before installing anything." in a
    assert mark in b and "1. Ask before installing anything." in b
    state = client.get("/api/integrations/all-rules").json()
    assert state["items"] == [r1] and [p["status"] for p in state["projects"]] == ["fresh", "fresh"]

    client.post(f"/api/rules/{r2}/update", json={"auto": "yes", "actor": "operator"})
    client.post(f"/api/rules/{r1}/interpretation", json={"actor": "operator", "text": "Ask before you install."})
    assert "1. Ask before you install.\n2. Deploy only when asked." in files()[0]

    client.post(f"/api/rules/{r1}/update", json={"status": "archived", "actor": "operator"})
    assert "Ask before you install." not in files()[0] and "1. Deploy only when asked." in files()[0]
    assert client.post(f"/api/rules/{r1}/update", json={"status": "off"}).status_code == 422
    client.post(f"/api/rules/{r1}/update", json={"status": "active", "actor": "operator"})
    assert "1. Ask before you install." in files()[0]

    for rid in (r1, r2):
        client.post(f"/api/rules/{rid}/update", json={"auto": "", "actor": "operator"})
    a, b = files()
    assert a == OWN and mark not in b
    assert [e for e in client.get("/api/integrations").json()["integrations"] if e["set_id"] == "all-rules"] == []


def test_an_archived_rule_leaves_a_written_set_on_its_next_update(client, tmp_path):
    root = Path(client.app.state.store.data_root)
    folder = _project(root, tmp_path)
    make_chat(root, "ALPHA", AGENT, [("2026-09-01T10:00:00", "#rule never deploy", "ok")])
    client.app.state.store.rebuild()
    rid = keeplib.keep_id("rule", "ALPHA", AGENT, 1)
    client.post(f"/api/rules/{rid}/interpretation", json={"agent_id": "cc-x", "text": "Deploy only when asked."})
    s = client.post("/api/sets", json={"name": "Safety", "kind": "rule", "items": [rid]}).json()
    client.post(f"/api/sets/{s['id']}/integrate", json={"project": "ALPHA"})
    client.post(f"/api/rules/{rid}/update", json={"status": "archived", "actor": "operator"})
    assert _statuses(client, s["id"]) == ["stale"]
    client.post(f"/api/sets/{s['id']}/integrate", json={"project": "ALPHA"})
    assert "Deploy only when asked." not in (folder / "AGENTS.md").read_text(encoding="utf-8")


def test_a_block_fenced_before_the_rename_is_the_same_block(client, tmp_path):
    # Until 2026-10-14 the fence said merkhet:set. A file written then is
    # read as fresh, the next write fences it anew, and remove takes it out.
    root = Path(client.app.state.store.data_root)
    folder = _project(root, tmp_path)
    make_chat(root, "ALPHA", AGENT, [("2026-09-01T10:00:00", "#vision Keep the board calm.", "ok")])
    client.app.state.store.rebuild()
    vid = keeplib.keep_id("vision", "ALPHA", AGENT, 1)
    client.post(f"/api/visions/{vid}/interpretation", json={"agent_id": "cc-abc12345", "text": "The board shows only live work."})
    s = client.post("/api/sets", json={"name": "Board", "kind": "vision", "items": [vid]}).json()
    client.post(f"/api/sets/{s['id']}/integrate", json={"project": "ALPHA"})
    text = (folder / "AGENTS.md").read_text(encoding="utf-8")
    (folder / "AGENTS.md").write_text(text.replace("<!-- sp:set", "<!-- merkhet:set"), encoding="utf-8")
    assert _statuses(client, s["id"]) == ["fresh"]

    again = client.post(f"/api/sets/{s['id']}/integrate", json={"project": "ALPHA"}).json()
    assert again["action"] == "updated"
    text = (folder / "AGENTS.md").read_text(encoding="utf-8")
    assert text.count("<!-- sp:set ") == 1 and "merkhet:set" not in text

    (folder / "AGENTS.md").write_text(text.replace("<!-- sp:set", "<!-- merkhet:set"), encoding="utf-8")
    gone = client.post(f"/api/sets/{s['id']}/integrate/remove", json={"project": "ALPHA"}).json()
    assert gone["action"] == "removed" and (folder / "AGENTS.md").read_text(encoding="utf-8") == OWN
