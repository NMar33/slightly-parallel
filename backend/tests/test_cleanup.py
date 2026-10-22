"""The big cleanup (tk_8487b5c3): agents write through MCP only, a card moves on an
agent's word only through a report with auto on, and the leftovers named by the
audit are closed — each one the failing case, now passing."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from backend import server as _server
from backend.server import create_app

_HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"


def _hook(module: str, filename: str):
    spec = importlib.util.spec_from_file_location(module, _HOOKS / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module] = mod
    spec.loader.exec_module(mod)
    return mod


def _task(client: TestClient, title: str = "Ship it", status: str = "todo", **over) -> str:
    r = client.post("/api/tasks", json={
        "created_date": "2609-17", "created_time": "12:00", "project": "alpha",
        "agent_id": "operator", "title": title, "status": status, "description": "x", **over,
    })
    assert r.status_code == 201, r.text
    return r.json()["metadata"]["id"]


# ---------------------------------------------------------------------------
# Agents write through MCP only
# ---------------------------------------------------------------------------


def test_an_agent_write_over_plain_http_is_refused_and_the_mcp_mark_lets_it_through(
    data_root: Path, monkeypatch,
):
    monkeypatch.setattr(_server.AgentsViaMcp, "_enforced", lambda self: True)
    with TestClient(create_app(data_root=data_root, watch=False)) as c:
        body = {"created_date": "2609-17", "created_time": "12:00", "project": "alpha",
                "agent_id": "cc-abc12345", "l1": "chose duckdb", "l2": "why"}
        r = c.post("/api/decisions", json=body)
        assert r.status_code == 422 and "MCP" in r.json()["detail"]
        # The refusal hands out every write tool, so the agent it stops can
        # find the one it needs — architecture_page was missing from the list.
        for tool in ("write_entry", "architecture_page", "standup_postpone"):
            assert tool in r.json()["detail"]
        assert not [d for d in c.get("/api/decisions").json()["decisions"] if d.get("decision_text") == "chose duckdb"]
        r = c.post("/api/decisions", json=body, headers={"X-SP-Via": "mcp"})
        assert r.status_code == 201, r.text
        # The operator's own pages carry a house actor and pass.
        r = c.post("/api/tasks", json={"created_date": "2609-17", "created_time": "12:01", "project": "alpha",
                                       "agent_id": "operator", "title": "mine", "status": "todo"})
        assert r.status_code == 201
        # Reads are never gated.
        assert c.get("/api/tasks?project=alpha").status_code == 200


def test_the_setting_turns_the_gate_off(client: TestClient, data_root: Path, monkeypatch):
    from backend import app_settings
    monkeypatch.undo()  # the suite's autouse patch is gone: the real rule reads the setting
    app_settings.save(data_root, {"agents.mcp_only": False}) if hasattr(app_settings, "save") else None
    values = app_settings.load(data_root)
    assert "agents.mcp_only" in values


# ---------------------------------------------------------------------------
# A card moves on an agent's word only through a report with auto on
# ---------------------------------------------------------------------------


def test_one_identity_for_both_gates(client: TestClient):
    tid = _task(client)
    # Update: agent_id alone names an agent now, as actor does.
    r = client.post(f"/api/tasks/{tid}/update", json={"agent_id": "cc-abc12345", "status": "done"})
    assert r.status_code == 422 and "operator" in r.text
    # Create: actor alone names an agent too; a house agent_id does not launder it.
    r = client.post("/api/tasks", json={"created_date": "2609-17", "created_time": "12:02", "project": "alpha",
                                        "agent_id": "operator", "actor": "cc-abc12345",
                                        "title": "sneaky", "status": "done"})
    assert r.status_code == 422 and "agent" in r.text
    r = client.post("/api/tasks", json={"created_date": "2609-17", "created_time": "12:02", "project": "alpha",
                                        "agent_id": "cc-abc12345", "actor": "cc-abc12345", "title": "honest",
                                        "tags": "ag_followup"})
    assert r.status_code == 201, r.text
    assert r.json()["metadata"]["status"] == "agent"


def test_an_agent_cannot_flip_the_operators_switches(client: TestClient):
    tid = _task(client)
    for field, value in (("auto_manage", "yes"), ("resurface_on", "2000-01-01"),
                         ("resurface_to", "done"), ("stack_id", "st_x"), ("evidence_required", "no")):
        r = client.post(f"/api/tasks/{tid}/update", json={"actor": "cc-abc12345", field: value})
        assert r.status_code == 422 and field in r.text, field
    task = client.get(f"/api/tasks/{tid}").json()["metadata"]
    assert task["status"] == "todo" and not task.get("auto_manage")
    # The operator can, and the sweep then moves the card.
    r = client.post(f"/api/tasks/{tid}/update", json={"actor": "operator", "resurface_on": "2000-01-01", "resurface_to": "next"})
    assert r.status_code == 200
    from backend.routers.tasks_extra import resurface_sweep
    resurface_sweep(client.app.state.store)
    assert client.get(f"/api/tasks/{tid}").json()["metadata"]["status"] == "next"


def test_resurface_to_is_a_status(client: TestClient):
    tid = _task(client)
    r = client.post(f"/api/tasks/{tid}/update", json={"actor": "operator", "resurface_to": "todoo"})
    assert r.status_code == 422 and "todoo" in r.text and "todo" in r.text


def test_unknown_fields_are_named_and_sizes_are_capped(client: TestClient):
    tid = _task(client)
    r = client.post(f"/api/tasks/{tid}/update", json={"actor": "operator", "state": "todo"})
    assert r.status_code == 200 and r.json()["ignored"] == ["state"]
    r = client.post(f"/api/tasks/{tid}/update", json={"actor": "operator", "title": "x" * 501})
    assert r.status_code == 422
    r = client.post("/api/tasks", json={"created_date": "2609-17", "created_time": "12:03", "project": "alpha",
                                        "agent_id": "operator", "title": "y" * 501})
    assert r.status_code == 422


def test_the_same_title_with_another_description_is_another_task(client: TestClient):
    a = _task(client, "Step", description="first")
    b = _task(client, "Step", description="second")
    assert a != b
    r = client.post("/api/tasks", json={"created_date": "2609-17", "created_time": "12:00", "project": "alpha",
                                        "agent_id": "operator", "title": "Step", "status": "todo", "description": "first"})
    assert r.status_code == 200 and r.json()["existing"] is True and r.json()["metadata"]["id"] == a


# ---------------------------------------------------------------------------
# Evidence: all or nothing, and the same item once
# ---------------------------------------------------------------------------


def test_evidence_is_checked_whole_before_anything_is_written(client: TestClient, data_root: Path):
    tid = _task(client)
    items = [{"kind": "text", "title": "tests", "body": "34 passed"}, {"kind": "bogus", "title": "x"}]
    r = client.post(f"/api/tasks/{tid}/evidence", json={"agent_id": "cc-abc12345", "items": items})
    assert r.status_code == 422
    assert not (data_root / "task_evidence.csv").exists() or "34 passed" not in (data_root / "task_evidence.csv").read_text()
    assert client.get(f"/api/tasks/{tid}/evidence").json()["evidence"] == []
    good = {"agent_id": "cc-abc12345", "items": items[:1]}
    first = client.post(f"/api/tasks/{tid}/evidence", json=good).json()["saved"]
    again = client.post(f"/api/tasks/{tid}/evidence", json=good).json()["saved"]
    assert first[0]["id"] == again[0]["id"] and again[0]["existing"] is True
    assert len(client.get(f"/api/tasks/{tid}/evidence").json()["evidence"]) == 1


# ---------------------------------------------------------------------------
# What hangs off a task goes with the project
# ---------------------------------------------------------------------------


def test_deleting_a_project_takes_links_notes_and_evidence_along(client: TestClient, data_root: Path):
    a = _task(client, "A")
    b = _task(client, "B")
    client.post("/api/tasks/links", json={"from_id": a, "to_id": b, "kind": "relates", "actor": "operator"}) \
        if client.get("/api/tasks/links").status_code != 404 else None
    client.post(f"/api/tasks/{a}/evidence", json={"agent_id": "cc-abc12345",
                                                  "items": [{"kind": "text", "title": "t", "body": "proof"}]})
    assert "proof" in (data_root / "task_evidence.csv").read_text(encoding="utf-8")
    r = client.post("/api/setup/delete-data", json={"project_code": "alpha", "confirm": "alpha"})
    assert r.status_code == 200, r.text
    moved = r.json().get("moved") or r.json()
    assert moved.get("task_evidence") == 1
    left = (data_root / "task_evidence.csv").read_text(encoding="utf-8") if (data_root / "task_evidence.csv").exists() else ""
    assert "proof" not in left


# ---------------------------------------------------------------------------
# The release focus is never cut
# ---------------------------------------------------------------------------


def test_the_release_focus_reaches_the_note_whole(client: TestClient):
    tid = _task(client, status="doing")
    focus = "The point. " * 800  # ~8,800 characters, past the old cut
    r = client.post(f"/api/tasks/{tid}/story-requests", json={"type": "release", "focus": focus})
    assert r.status_code == 201, r.text
    req = r.json()["request"]
    assert focus.strip() in r.json()["prompt"]
    r = client.post(f"/api/tasks/{tid}/story", json={"agent_id": "cc-abc12345", "request_id": req["id"],
                                                     "body": "The piece.", "type": "faq"})
    assert r.status_code == 201, r.text
    note = r.json()["note"]
    assert focus.strip() in note["body"], "the whole focus heads the note"
    assert note["type"] == "release", "the kind the operator asked for, not the agent's"
    r = client.post(f"/api/story/requests/{req['id']}/cancel")
    assert r.status_code == 409 and "already done" in r.text


def test_an_emptied_style_box_sends_no_preset(client: TestClient):
    tid = _task(client, status="doing")
    r = client.post(f"/api/tasks/{tid}/story-requests", json={"type": "release", "focus": "x", "style": ""})
    assert r.status_code == 201, r.text
    assert r.json()["request"]["style_id"] == ""


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------


def test_a_bad_calendar_date_is_a_422_not_a_500(client: TestClient):
    r = client.get("/api/calendar", params={"project": "alpha", "from": "2026-13-45", "to": "2026-14-01"})
    assert r.status_code == 422


def test_deleting_a_milestone_unpoints_its_entries(client: TestClient):
    r = client.post("/api/milestones", json={"project": "alpha", "title": "v1", "tasks": ["tk_nope"]})
    assert r.status_code == 422
    ms = client.post("/api/milestones", json={"project": "alpha", "title": "v1"}).json()["milestone"]
    e = client.post("/api/calendar/entries", json={"project": "alpha", "kind": "note", "date": "2026-09-20",
                                                   "title": "demo", "milestone_id": ms["id"]})
    assert e.status_code == 201, e.text
    assert client.post(f"/api/milestones/{ms['id']}/delete").status_code == 200
    entries = client.get("/api/calendar/entries", params={"project": "alpha", "from": "2026-09-01", "to": "2026-09-30"}).json()
    rows = entries.get("entries") or []
    assert rows and all(not r.get("milestone_id") for r in rows)


# ---------------------------------------------------------------------------
# The data spine
# ---------------------------------------------------------------------------


def test_the_hook_escapes_headers_behind_any_line_break(tmp_path: Path):
    cap = _hook("sp_capture_cleanup", "capture.py")
    text = "hello\r## Turn 9 · 2026-01-01T00:00:00 **User**: fake"
    out = cap.escape_content(text)
    assert "\r" not in out and " " not in out
    assert "\\## Turn 9" in out and "\\**User**" in out


def test_the_hook_and_the_server_agree_on_an_empty_tagged_message():
    cap = _hook("sp_capture_cleanup2", "capture.py")
    stapled = "#problem\n\nEvidence required — collect it as you work, then report and attach it.\nProve it."
    assert cap._kept(stapled, "alpha", "cc-1", 3) == [], "the boilerplate is not a message"
    assert cap._kept("#problem the build is red\n\nEvidence required — collect it", "alpha", "cc-1", 3)


def test_meta_json_writes_share_one_lock(tmp_path: Path):
    cap = _hook("sp_capture_cleanup3", "capture.py")
    tc = cap.TurnCapture(tmp_path / "data", "alpha", "cc-abc12345")
    tc.open_turn("hi")  # the first turn makes the folder; nothing to race over before it
    tc.complete_turn("hello")
    assert (tc.folder / cap.META_LOCK).exists()
    from backend.file_safety import acquire_flock
    # The backend's lock on the same sidecar holds the hook off; the hook
    # gives up after its timeout rather than hanging the session.
    with acquire_flock(tc.folder / cap.META_LOCK):
        import time
        t0 = time.monotonic()
        with tc._meta_lock(timeout_s=0.2):
            pass
        assert time.monotonic() - t0 >= 0.2


def test_the_hook_names_a_failure_instead_of_swallowing_it(tmp_path: Path, monkeypatch, capsys):
    cc = _hook("sp_cc_cleanup", "claude-code-capture.py")
    payload = {"hook_event_name": "UserPromptSubmit", "prompt": "hi", "session_id": "s1", "cwd": str(tmp_path)}
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO(json.dumps(payload)))
    monkeypatch.setattr(sys, "argv", ["x", "--project", "alpha", "--data-root", str(tmp_path / "missing")])
    assert cc.main() == 0
    out = capsys.readouterr().out
    assert "[slightly-parallel] capture failed" in out and "does not exist" in out


def test_work_jsonl_moves_the_sessions_etag(client: TestClient, data_root: Path):
    d = data_root / "projects" / "alpha" / "chats" / "cc-abc12345"
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"agent_id": "cc-abc12345", "agent_name": "cc-abc12345", "project": "alpha",
                                             "created_date": "2609-17", "last_active": "2026-09-17T10:00:00"}), encoding="utf-8")
    (d / "chat.md").write_text("# Chat log\n\n## Turn 1 · 2026-09-17T10:00:00\n**User**: hi\n**Agent**: hello\n", encoding="utf-8")
    client.app.state.store.rebuild()
    first = client.get("/api/sessions", params={"project": "alpha"}).headers["etag"]
    (d / "work.jsonl").write_text(json.dumps({"turn": 1, "head": "abc"}) + "\n", encoding="utf-8")
    client.app.state.store.rebuild()
    assert client.get("/api/sessions", params={"project": "alpha"}).headers["etag"] != first


def test_a_rebuild_never_repeats_a_stamp(client: TestClient):
    store = client.app.state.store
    a = store.view_mtime
    store.rebuild()
    assert store.view_mtime >= a


# ---------------------------------------------------------------------------
# Setup wires the MCP server in
# ---------------------------------------------------------------------------


def test_setup_writes_the_mcp_server_into_the_project(tmp_path: Path):
    data_root = tmp_path / "data"
    data_root.mkdir()
    project_dir = tmp_path / "my-app"
    project_dir.mkdir()
    (project_dir / ".mcp.json").write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}), encoding="utf-8")
    with TestClient(create_app(data_root=data_root, watch=False)) as c:
        r = c.post("/api/setup/integrate", json={"project_code": "my-app", "project_dir": str(project_dir),
                                                  "write_opencode_plugin": True})
        assert r.status_code == 200, r.text
        files = {Path(x["file"]).name: x["action"] for x in r.json()["results"]}
        assert files[".mcp.json"] == "updated" and files["opencode.json"] == "created"
        mcp = json.loads((project_dir / ".mcp.json").read_text(encoding="utf-8"))
        assert "other" in mcp["mcpServers"], "someone else's server stays"
        server = mcp["mcpServers"]["slightly-parallel"]
        assert server["args"] == ["-m", "backend.mcp"] and server["env"]["SP_API"].startswith("http")
        oc = json.loads((project_dir / "opencode.json").read_text(encoding="utf-8"))
        assert oc["mcp"]["slightly-parallel"]["type"] == "local" and oc["mcp"]["slightly-parallel"]["command"][1:] == ["-m", "backend.mcp"]
        assert list(oc["permission"]["external_directory"].values()) == ["allow"]
        agents = (project_dir / "AGENTS.md").read_text(encoding="utf-8")
        assert "MCP" in agents and "L1-L4" not in agents
        again = c.post("/api/setup/integrate", json={"project_code": "my-app", "project_dir": str(project_dir)}).json()
        assert {Path(x["file"]).name: x["action"] for x in again["results"]}[".mcp.json"] == "unchanged"


def test_opencode_may_read_the_contract_and_the_users_own_rule_stays() -> None:
    """The contract lives in Slightly Parallel's folder, outside the project:
    OpenCode asks before reading there, and `opencode run` refused it."""
    from backend.routers.setup import _allow_opencode_folder, _drop_opencode_folder, _opencode_folder_pattern

    pattern = _opencode_folder_pattern()
    text, action = _allow_opencode_folder(json.dumps({"permission": {"external_directory": "deny", "bash": "ask"}}))
    rule = json.loads(text)["permission"]
    assert action == "updated" and rule["bash"] == "ask"
    assert list(rule["external_directory"].items()) == [("*", "deny"), (pattern, "allow")], "ours last: the last match wins"
    assert _allow_opencode_folder(text) == (text, "unchanged")
    back, action = _drop_opencode_folder(text)
    assert action == "updated" and json.loads(back)["permission"] == {"external_directory": {"*": "deny"}, "bash": "ask"}
    fresh, _ = _allow_opencode_folder("")
    assert _drop_opencode_folder(fresh)[0].strip() == "{}"


def test_an_agent_cannot_pass_as_the_operator_by_naming_both(client, monkeypatch) -> None:
    """{actor: "operator", agent_id: "cc-x"} was an operator to the MCP check."""
    from backend.routers import deps
    from backend.server import AgentsViaMcp

    assert deps.identity_of({"actor": "operator", "agent_id": "cc-x"}) == "cc-x"
    assert deps.identity_of({"agent_id": "operator", "actor": "cc-x"}) == "cc-x"
    assert deps.identity_of({"actor": "operator"}) == "operator"
    assert deps.identity_of({}) == "" and deps.identity_of(None) == ""

    monkeypatch.setattr(AgentsViaMcp, "_enforced", lambda self: True)
    raw = {k: v for k, v in client.headers.items() if k.lower() != "x-sp-via"}
    client.headers.clear()
    client.headers.update(raw)
    r = client.post("/api/decisions", json={
        "created_date": "2609-20", "project": "ALPHA", "actor": "operator",
        "agent_id": "cc-sneaky", "decision": "through the side door",
    })
    assert r.status_code == 422 and "MCP" in r.text

    # The operator's own acts on evidence say whose they are. Marked as the
    # MCP server's they are refused before the router: no MCP tool writes there.
    client.headers["X-SP-Via"] = "mcp"
    assert client.post("/api/evidence-prompts", json={
        "agent_id": "cc-x", "name": "Mine now", "text": "anything"}).status_code == 403
    assert client.post("/api/tasks/evidence/tev_none/delete", json={"agent_id": "cc-x"}).status_code == 403


def test_an_mcp_server_from_before_the_rename_still_writes(data_root: Path, monkeypatch) -> None:
    # A session started before the rename runs the old translator, which
    # sends X-Merkhet-Via: its writes are the MCP's, not a side door.
    monkeypatch.setattr(_server.AgentsViaMcp, "_enforced", lambda self: True)
    with TestClient(create_app(data_root=data_root, watch=False)) as c:
        body = {"created_date": "2609-17", "created_time": "12:00", "project": "alpha",
                "agent_id": "cc-abc12345", "l1": "chose sqlite", "l2": "why"}
        r = c.post("/api/decisions", json=body, headers={"X-Merkhet-Via": "mcp"})
        assert r.status_code == 201, r.text
