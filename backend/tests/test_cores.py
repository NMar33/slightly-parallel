"""Cores: the program's core elements the operator keeps in view (corelib.py,
routers/cores.py), their notes, links, tracking and the hook's notice."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import corelib
from tests.conftest import make_task

AGENT = "cc-core12345"


def _core(client: TestClient, name: str = "Chat capture", **more) -> dict:
    r = client.post("/api/cores", json={
        "project": "ALPHA", "name": name, "type": "capability", "agent_id": AGENT,
        "text": f"#core-new {name}, the core of the product", "comment": "named from this chat",
        "anchors": ["scripts/hooks/capture.py", "backend/hookshared.py:command_text"], **more,
    })
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_a_core_is_made_once_with_its_founding_note_and_anchors(client: TestClient) -> None:
    got = _core(client)
    core = got["core"]
    assert core["id"].startswith("cr_") and core["status"] == "view" and core["type"] == "capability"
    again = _core(client)
    assert again["existing"] is True and again["core"]["id"] == core["id"]
    d = client.get(f"/api/cores/{core['id']}").json()
    assert [n["kind"] for n in d["notes"]] == ["founding"]
    assert d["notes"][0]["text"].startswith("#core-new") and d["notes"][0]["comment"] == "named from this chat"
    # An agent's founding note waits for approval; the operator's would not.
    assert d["notes"][0]["approved"] is False
    assert sorted(l["target"] for l in d["links"] if l["kind"] == "anchor") == [
        "backend/hookshared.py:command_text", "scripts/hooks/capture.py"]
    assert d["tracking"] == {"on": False, "until": "", "days_left": None, "expired": False}
    lst = client.get("/api/cores?project=ALPHA").json()
    assert [c["name"] for c in lst["cores"]] == ["Chat capture"] and len(lst["cores"][0]["grid"]) == 30
    assert lst["types"][0] == "capability"


def test_a_core_needs_a_project_a_name_and_a_known_type(client: TestClient) -> None:
    bad = client.post("/api/cores", json={"project": "ALPHA", "name": "x", "type": "thing", "text": "t"})
    assert bad.status_code == 422 and "type must be one of" in bad.json()["detail"]
    assert client.post("/api/cores", json={"project": "ALPHA", "name": "", "type": "feature", "text": "t"}).status_code == 422
    assert client.post("/api/cores", json={"project": "nope", "name": "x", "type": "feature", "text": "t"}).status_code == 422
    assert client.post("/api/cores", json={"project": "ALPHA", "name": "x" * 61, "type": "feature", "text": "t"}).status_code == 422


def test_notes_tell_the_operator_from_the_agent_and_approval_keeps_the_author(client: TestClient) -> None:
    cid = _core(client)["core"]["id"]
    mine = client.post(f"/api/cores/{cid}/notes", json={"text": "#core-note turns.jsonl is under the lock now"})
    assert mine.status_code == 201 and mine.json()["note"]["approved_at"] and mine.json()["note"]["author"] == "operator"
    theirs = client.post(f"/api/cores/{cid}/notes", json={
        "agent_id": AGENT, "text": "#core-note check it on Windows", "comment": "linked the task", "task_id": ""})
    assert theirs.status_code == 201
    nid = theirs.json()["note"]["id"]
    assert theirs.json()["note"]["approved_at"] == "" and theirs.json()["note"]["author"] == AGENT
    # An agent cannot approve; the operator can, and the author stays.
    r = client.post(f"/api/cores/{cid}/notes/{nid}/approve", json={"agent_id": AGENT})
    assert r.status_code == 422 and "approving a note is the operator's" in r.json()["detail"]
    r = client.post(f"/api/cores/{cid}/notes/{nid}/approve", json={})
    assert r.status_code == 200 and r.json()["note"]["approved_by"] == "operator" and r.json()["note"]["author"] == AGENT
    d = client.get(f"/api/cores/{cid}").json()
    assert [n["approved"] for n in d["notes"]] == [False, True, True]
    assert client.get("/api/cores?project=ALPHA").json()["cores"][0]["pending_n"] == 1


def test_an_auto_note_needs_tracking_on_and_tracking_is_the_operators(client: TestClient) -> None:
    cid = _core(client)["core"]["id"]
    r = client.post(f"/api/cores/{cid}/notes", json={"agent_id": AGENT, "kind": "auto", "comment": "stdin now"})
    assert r.status_code == 422 and "tracking is off for Chat capture" in r.json()["detail"]
    r = client.post(f"/api/cores/{cid}/tracking", json={"agent_id": AGENT, "on": True})
    assert r.status_code == 422 and "switching tracking is the operator's" in r.json()["detail"]
    r = client.post(f"/api/cores/{cid}/tracking", json={"on": True, "span": "week"})
    assert r.status_code == 200
    until = (date.today() + timedelta(days=6)).isoformat()
    assert r.json()["tracking"] == {"on": True, "until": until, "days_left": 7, "expired": False}
    r = client.post(f"/api/cores/{cid}/notes", json={"agent_id": AGENT, "kind": "auto", "comment": "stdin now", "task_id": ""})
    assert r.status_code == 201 and r.json()["note"]["kind"] == "auto"
    # The hook reads the same file: this core is named to the agent.
    assert corelib.tracked(client.app.state.store.data_root, "ALPHA") == [{"id": cid, "name": "Chat capture", "until": until}]
    # Expired: read as off, told to nobody.
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    corelib._rewrite(client.app.state.store, cid, {"tracking_until": yesterday})
    assert corelib.tracking_state(corelib.core_of(client.app.state.store, cid))["expired"] is True
    assert corelib.tracked(client.app.state.store.data_root, "ALPHA") == []
    r = client.post(f"/api/cores/{cid}/tracking", json={"on": False})
    assert r.json()["tracking"]["on"] is False
    assert client.post(f"/api/cores/{cid}/tracking", json={"on": True, "until": "2020-01-01"}).status_code == 422
    assert client.post(f"/api/cores/{cid}/tracking", json={"on": True, "span": "month"}).status_code == 422


def test_links_tasks_messages_and_what_the_tasks_bring(client: TestClient) -> None:
    cid = _core(client)["core"]["id"]
    tid = make_task(client, "turns.jsonl under the lock", status="doing")
    r = client.post(f"/api/cores/{cid}/links", json={"agent_id": AGENT, "kind": "task", "target": tid})
    assert r.status_code == 200 and r.json()["link"]["kind"] == "task"
    assert client.post(f"/api/cores/{cid}/links", json={"agent_id": AGENT, "kind": "task", "target": tid}).json()["existing"] is True
    assert client.post(f"/api/cores/{cid}/links", json={"kind": "task", "target": "tk_nope"}).status_code == 422
    assert client.post(f"/api/cores/{cid}/links", json={"kind": "anchor", "target": "../etc/passwd"}).status_code == 422
    assert client.post(f"/api/cores/{cid}/links", json={"agent_id": AGENT, "kind": "message", "target": f"{AGENT}#4"}).status_code == 200
    d = client.get(f"/api/cores/{cid}").json()
    assert [t["id"] for t in d["tasks"]] == [tid] and d["tasks"][0]["status"] == "doing"
    lst = client.get("/api/cores?project=ALPHA").json()["cores"][0]
    assert lst["tasks_n"] == 1 and lst["open_n"] == 1
    # A note that names a task links it too.
    client.post(f"/api/cores/{cid}/notes", json={"text": "done with it", "task_id": tid})
    assert sum(1 for l in client.get(f"/api/cores/{cid}").json()["links"] if l["kind"] == "task") == 1
    link_id = next(l["id"] for l in d["links"] if l["kind"] == "message")
    assert client.post(f"/api/cores/{cid}/links", json={"agent_id": AGENT, "remove": link_id}).status_code == 422
    assert client.post(f"/api/cores/{cid}/links", json={"remove": link_id}).json()["removed"] is True


def test_the_operator_changes_a_core_and_an_agent_takes_it_out_of_view(client: TestClient) -> None:
    cid = _core(client)["core"]["id"]
    r = client.post(f"/api/cores/{cid}/update", json={"agent_id": AGENT, "name": "x"})
    assert r.status_code == 422 and "changing a core is the operator's" in r.json()["detail"]
    r = client.post(f"/api/cores/{cid}/update", json={"name": "Capture", "type": "internals", "reason": "core", "position": "3"})
    assert r.status_code == 200 and r.json()["core"]["type"] == "internals" and r.json()["core"]["position"] == "3"
    assert client.post(f"/api/cores/{cid}/update", json={"status": "gone"}).status_code == 422
    assert client.post(f"/api/cores/{cid}/update", json={}).status_code == 422
    # #core-off, run by the agent after the operator's confirmation.
    r = client.post(f"/api/cores/{cid}/off", json={"agent_id": AGENT})
    assert r.status_code == 200 and r.json()["core"]["status"] == "off" and r.json()["core"]["off_at"]
    # Out of view: a note is refused, the story stays, the operator brings it back.
    assert client.post(f"/api/cores/{cid}/notes", json={"text": "late"}).status_code == 422
    assert len(client.get(f"/api/cores/{cid}").json()["notes"]) == 1
    assert client.post(f"/api/cores/{cid}/update", json={"status": "view"}).json()["core"]["off_at"] == ""
    assert client.get("/api/cores/nope").status_code == 404
    assert client.get("/api/cores?project=zzz").status_code == 404


def test_the_hook_names_the_tracked_cores_and_knows_the_commands(data_root: Path) -> None:
    root = data_root
    import importlib.util
    import sys

    hooks = Path(__file__).resolve().parents[2] / "scripts" / "hooks"
    spec = importlib.util.spec_from_file_location("sp_capture_cores", hooks / "capture.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sp_capture_cores"] = mod
    spec.loader.exec_module(mod)
    for cmd in ("core-new", "core-note", "core", "core-off"):
        assert mod._COMMANDS[cmd][0] == "keep-a-core"
    # A core-new is not read as #core, and #core-note as #core.
    found = [m.group(1).lower() for m in mod._COMMAND_RE.finditer("#core-new x #core-note y #core #core-off z")]
    assert found == ["core-new", "core-note", "core", "core-off"]
    (root / "cores.csv").write_text(
        "id,project,name,type,reason,status,position,tracking_on,tracking_until,created_at,updated_at,actor,off_at\n"
        f"cr_1,ALPHA,Chat capture,capability,,view,1,1,{(date.today() + timedelta(days=2)).isoformat()},,,operator,\n"
        "cr_2,ALPHA,Old,feature,,view,2,1,2020-01-01,,,operator,\n"
        "cr_3,ALPHA,Off,feature,,off,3,1,,,,operator,\n", encoding="utf-8")
    cap = mod.TurnCapture(root, "ALPHA", "cc-core12345")
    signals = cap.open_turn("hello")
    assert [c["id"] for c in signals["cores_tracking"]] == ["cr_1"]
    note = mod.format_signals(signals)
    assert "cores tracked in this project: Chat capture (cr_1, until" in note and "core_note" in note
    assert "cores tracked" not in mod.format_signals(cap.open_turn("second"))   # the first turn and refreshes only


def test_the_mcp_tools_reach_the_routes(data_root: Path, monkeypatch) -> None:
    from backend import mcp as mcp_mod

    class FakeApi:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, dict | None]] = []

        def get(self, path: str):
            self.calls.append(("GET", path, None))
            return {"ok": True}

        def post(self, path: str, body: dict):
            self.calls.append(("POST", path, body))
            return {"ok": True}

    tr = mcp_mod.Translator.__new__(mcp_mod.Translator)
    tr.api = FakeApi()
    tr.cwd = str(data_root)
    tr.schema, tr.lenses, tr.vocab = {"lenses": [], "vocabularies": {}}, {}, {}
    monkeypatch.setattr(mcp_mod.Translator, "identity", lambda self: {"agent_id": AGENT, "project": "ALPHA"})
    tr.call("cores", {})
    tr.call("core_new", {"name": "Capture", "type": "capability", "text": "#core-new capture", "anchors": ["a.py", ""]})
    tr.call("core_note", {"id": "cr_1", "comment": "stdin", "kind": "auto", "task_id": "tk_1"})
    tr.call("core_attach", {"id": "cr_1", "turn": 4, "task_id": "tk_1"})
    tr.call("core_off", {"id": "cr_1"})
    paths = [(m, p) for m, p, _ in tr.api.calls]
    assert paths == [("GET", "/api/cores?project=ALPHA"), ("POST", "/api/cores"), ("POST", "/api/cores/cr_1/notes"),
                     ("POST", "/api/cores/cr_1/links"), ("POST", "/api/cores/cr_1/links"), ("POST", "/api/cores/cr_1/off")]
    assert tr.api.calls[1][2]["anchors"] == ["a.py"] and tr.api.calls[1][2]["agent_id"] == AGENT
    assert tr.api.calls[3][2]["target"] == f"{AGENT}#4"
    with pytest.raises(mcp_mod.ApiError):
        tr.call("core_attach", {"id": "cr_1"})
    # Every write the translator makes is one the server lets a marked agent reach.
    from backend.server import mcp_may_write
    for p in ("/api/cores", "/api/cores/cr_1/notes", "/api/cores/cr_1/links", "/api/cores/cr_1/off"):
        assert mcp_may_write(p), p
    assert not mcp_may_write("/api/cores/cr_1/tracking") and not mcp_may_write("/api/cores/cr_1/update")
    assert json.loads(json.dumps(tr.api.calls[2][2]))["kind"] == "auto"


def test_the_timeline_puts_notes_tasks_and_tracking_on_their_days(client: TestClient) -> None:
    cid = _core(client)["core"]["id"]
    tid = make_task(client, "turns.jsonl under the lock", status="doing")
    client.post(f"/api/cores/{cid}/links", json={"kind": "task", "target": tid})
    client.post(f"/api/cores/{cid}/notes", json={"text": "checked on Windows"})
    client.post(f"/api/tasks/{tid}/update", json={"status": "done", "actor": "operator"})
    client.post(f"/api/cores/{cid}/tracking", json={"on": True, "span": "week"})
    r = client.get("/api/cores/timeline?project=ALPHA&days=14")
    assert r.status_code == 200, r.text
    d = r.json()
    today = date.today().isoformat()
    assert len(d["days"]) == 14 and d["last"] == today and d["releases"] == []
    lane = next(l for l in d["lanes"] if l["id"] == cid)
    day = lane["days"][today]
    # The founding note is the agent's (it waits); the second is yours.
    assert [(n["operator"], n["approved"]) for n in day["notes"]] == [(False, False), (True, True)]
    assert [t["id"] for t in day["done"]] == [tid]
    assert lane["tracking_spans"] == [{"from": today, "to": today}]
    assert lane["totals"]["notes"] == 2 and lane["totals"]["done"] == 1
    assert client.get("/api/cores/timeline?project=ALPHA&days=3").status_code == 422
    # Switching off closes the span; the events ledger keeps both switches.
    client.post(f"/api/cores/{cid}/tracking", json={"on": False})
    lane = next(l for l in client.get("/api/cores/timeline?project=ALPHA&days=14").json()["lanes"] if l["id"] == cid)
    assert lane["tracking_spans"] == [{"from": today, "to": today}] and lane["tracking"]["on"] is False
    kinds = [e["kind"] for e in corelib._rows(client.app.state.store, corelib.EVENTS_FILE) if e["core_id"] == cid]
    assert kinds == ["created", "tracking_on", "tracking_off"]
    # The core's page reads the same switches with the core.
    assert [e["kind"] for e in client.get(f"/api/cores/{cid}").json()["events"]] == ["created", "tracking_on", "tracking_off"]


def test_the_operator_sets_a_tasks_cores_and_the_board_reads_them(client: TestClient) -> None:
    a = _core(client, "Chat capture")["core"]["id"]
    b = _core(client, "Kanban", type="interface")["core"]["id"]
    tid = make_task(client, "drop renumbers in tens")
    r = client.post(f"/api/tasks/{tid}/cores", json={"cores": [a, b]})
    assert r.status_code == 200 and {c["id"] for c in r.json()["cores"]} == {a, b}
    assert {c["id"] for c in client.get(f"/api/tasks/{tid}/cores").json()["cores"]} == {a, b}
    idx = client.get("/api/cores/tasks?project=ALPHA").json()["tasks"]
    assert {c["name"] for c in idx[tid]} == {"Chat capture", "Kanban"}
    # Naming one drops the other; an agent is refused; unknown ids are named.
    assert [c["id"] for c in client.post(f"/api/tasks/{tid}/cores", json={"cores": [b]}).json()["cores"]] == [b]
    r = client.post(f"/api/tasks/{tid}/cores", json={"cores": [a], "agent_id": AGENT})
    assert r.status_code == 422 and "core_attach" in r.json()["detail"]
    assert client.post(f"/api/tasks/{tid}/cores", json={"cores": ["cr_nope"]}).status_code == 422
    assert client.post(f"/api/tasks/{tid}/cores", json={"cores": "x"}).status_code == 422
    assert client.post("/api/tasks/tk_nope/cores", json={"cores": []}).status_code == 404
    # A core out of view leaves the board's index.
    client.post(f"/api/cores/{b}/off", json={})
    assert tid not in client.get("/api/cores/tasks?project=ALPHA").json()["tasks"]


def test_the_map_overlay_says_which_core_claims_a_part_and_how(client: TestClient) -> None:
    from backend import repomap
    from tests.test_repomap import MAP

    store = client.app.state.store
    assert client.get("/api/cores/map?project=ALPHA").json()["rows"] == []
    repomap.write(store, "ALPHA", "cc-m", MAP)
    cid = client.post("/api/cores", json={"project": "ALPHA", "name": "Renaming", "type": "capability",
                                          "anchors": ["core/rename.py"]}).json()["core"]["id"]
    client.post(f"/api/cores/{cid}/links", json={"kind": "map", "target": "commands"})
    d = client.get("/api/cores/map?project=ALPHA").json()
    by = {r["name"]: r["cores"] for r in d["rows"]}
    assert by["core"] == [{"id": cid, "how": "files"}]        # its anchor lives under the module's folder
    assert [(c["id"], c["how"]) for c in by["commands"]] == [(cid, "linked")]   # set by the operator
    assert by["commands"][0]["link_id"].startswith("cl_")         # what a click removes
    assert by["pytest"] == []
    assert d["cores"][0]["rows"] == 2 and d["unclaimed"] == len(MAP["rows"]) - 2


def test_switching_tracking_off_after_its_end_keeps_the_span_at_its_end() -> None:
    core = {"created_at": "2026-10-01T09:00:00", "tracking_on": "", "tracking_until": ""}
    events = [{"at": "2026-10-01T09:00:00", "kind": "tracking_on", "value": "2026-10-07"},
              {"at": "2026-10-20T10:00:00", "kind": "tracking_off", "value": ""}]
    assert corelib._spans(events, core, "2026-09-26", "2026-10-25") == [{"from": "2026-10-01", "to": "2026-10-07"}]
    # On again later, still on: the open span runs to its own end.
    events.append({"at": "2026-10-22T10:00:00", "kind": "tracking_on", "value": "2026-10-23"})
    assert corelib._spans(events, core, "2026-09-26", "2026-10-25")[-1] == {"from": "2026-10-22", "to": "2026-10-23"}


def test_replacing_a_tasks_cores_is_one_write(client: TestClient, monkeypatch) -> None:
    a = _core(client, "Chat capture")["core"]["id"]
    b = _core(client, "Kanban", type="interface")["core"]["id"]
    tid = make_task(client, "drop renumbers")
    client.post(f"/api/tasks/{tid}/cores", json={"cores": [a]})
    calls = []
    real = corelib.rewrite_rows
    monkeypatch.setattr(corelib, "rewrite_rows", lambda *args, **kw: calls.append(args[0].name) or real(*args, **kw))
    out = client.post(f"/api/tasks/{tid}/cores", json={"cores": [b, b]}).json()["cores"]
    assert [c["id"] for c in out] == [b]                     # the duplicate is one link
    assert calls.count("core_links.csv") == 1                # removed and added in one rewrite
    links = [l for l in corelib._rows(client.app.state.store, corelib.LINKS_FILE) if l["target"] == tid]
    assert [l["core_id"] for l in links] == [b]


def test_a_core_lists_its_commits_and_the_agents_that_worked_on_it(client: TestClient, data_root: Path) -> None:
    import subprocess
    from datetime import datetime, timedelta

    from backend import gitwork
    from tests.conftest import git_env, git_repo

    gitwork.forget()
    repo = git_repo(data_root.parent / "proj")
    (data_root / "integrations.csv").write_text(f"project,path\nALPHA,{repo}\n", encoding="utf-8")
    cid = _core(client)["core"]["id"]
    tid = make_task(client, "lock turns", project="ALPHA")
    client.post(f"/api/cores/{cid}/links", json={"kind": "task", "target": tid})
    when = (datetime.now() - timedelta(minutes=5)).astimezone().isoformat()
    (repo / "t.py").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", f"lock it\n\nTask: {tid}\nAgent: cc-signer", "--date", when],
                   cwd=repo, check=True, env=git_env(GIT_COMMITTER_DATE=when, HOME=str(data_root.parent)))
    client.app.state.store.rebuild()
    d = client.get(f"/api/cores/{cid}").json()
    assert [(c["subject"], c["how"], c["agent"], c["tasks"]) for c in d["commits"]] == [("lock it", "signed", "cc-signer", [tid])]
    assert d["commits_n"] == 1 and d["files"][0]["tasks"] == [tid]
    agents = {a["agent_id"]: a for a in d["agents"]}
    assert agents["cc-signer"]["commits"] == 1 and agents["cc-signer"]["tasks"] == [tid]
    assert agents[AGENT]["notes"] == 1          # the founding note was the agent's


def test_an_agent_that_only_names_a_task_in_its_answer_did_not_work_on_it(client: TestClient, data_root: Path) -> None:
    import json as _json

    cid = _core(client)["core"]["id"]
    tid = make_task(client, "import old chats", project="ALPHA")
    client.post(f"/api/cores/{cid}/links", json={"kind": "task", "target": tid})
    turns_dir = data_root / "projects" / "ALPHA" / "chats"
    for agent, user, answer in (("cc-lister", "what is left?", f"Left in To do: {tid}"),
                                ("cc-worker", f"take {tid}", "on it"),
                                ("cc-filer", f"#now-todo later {tid}", "filed")):
        chat = turns_dir / agent
        chat.mkdir(parents=True, exist_ok=True)
        (chat / "meta.json").write_text(_json.dumps({"agent_id": agent}), encoding="utf-8")
        (chat / "chat.md").write_text(f"# Chat log — {agent}\n\n---\n\n## Turn 1 · 2026-10-25T10:00:00\n**User**: {user}\n**Agent**: {answer}\n\n",
                                      encoding="utf-8")
    client.app.state.store.rebuild()
    agents = {a["agent_id"]: a for a in client.get(f"/api/cores/{cid}").json()["agents"]}
    assert agents["cc-worker"]["tasks"] == [tid] and agents["cc-worker"]["turns"] == 1
    assert "cc-lister" not in agents          # named it in its own answer only
    assert "cc-filer" not in agents           # the operator only filed it
