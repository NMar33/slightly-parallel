"""The audit round of 2026-10-25 (docs/audit/rounds/2610-25.md): one test
per bug it found. Each failed before its fix.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from backend.db import ViewStore
from backend.entities import ENTITIES

_HEAD = "id,title,status,project\n"


def _replace(path: Path, text: str, mtime: float | None = None) -> None:
    tmp = path.with_name(path.name + ".new")
    tmp.write_text(text, encoding="utf-8")
    if mtime is not None:
        os.utime(tmp, (mtime, mtime))
    os.replace(tmp, path)


def test_a_write_during_a_rebuild_moves_the_next_stamp(tmp_path: Path, monkeypatch) -> None:
    """The mtime snapshot is taken before the tables are staged. Before, it
    came after: a write landing in between put its mtime into the stamp
    while the table held the old rows, and the next build (which rebuilt
    the table) moved no stamp — every ETag said 304 over the new rows."""
    tasks = tmp_path / ENTITIES["task"].csv
    tasks.write_text(_HEAD + "tk_1,v1,todo,x\n", encoding="utf-8")
    store = ViewStore(tmp_path)
    time.sleep(0.02)
    stage = ViewStore._stage
    fired: list[int] = []

    def racing(self, con, name, *rest):   # a write lands while the tasks table is built
        if name == ENTITIES["task"].view and not fired:
            fired.append(1)
            _replace(tasks, _HEAD + "tk_1,v2,todo,x\n")
        return stage(self, con, name, *rest)

    monkeypatch.setattr(ViewStore, "_stage", racing)
    _replace(tasks, _HEAD + "tk_1,v1,todo,x\n")   # a change, so the table is built again
    store.rebuild()
    assert fired
    first = store.stamps["tasks"]
    store.rebuild()
    assert store.query("select title from tasks_mutual") == [{"title": "v2"}]
    assert store.stamps["tasks"] != first


def test_a_file_restored_with_an_older_mtime_moves_the_stamp(tmp_path: Path) -> None:
    """A backup restore puts the archived mtime back, older than the stamp.
    The table is rebuilt (its signature changed); the stamp and view_mtime
    must move with it, or the browser keeps the live rows over the restored
    ones until the next write."""
    tasks = tmp_path / ENTITIES["task"].csv
    old = time.time() - 86400
    _replace(tasks, _HEAD + "tk_1,old,todo,x\n", mtime=old)
    store = ViewStore(tmp_path)
    _replace(tasks, _HEAD + "tk_1,new,todo,x\n")
    store.rebuild()
    assert store.query("select title from tasks_mutual") == [{"title": "new"}]
    stamp, version = store.stamps["tasks"], store.view_mtime
    _replace(tasks, _HEAD + "tk_1,old,todo,x\n", mtime=old)
    store.rebuild()
    assert store.query("select title from tasks_mutual") == [{"title": "old"}]
    assert store.stamps["tasks"] > stamp
    assert store.view_mtime > version
    # A rebuild that found nothing new keeps both.
    stamp, version = store.stamps["tasks"], store.view_mtime
    store.rebuild()
    assert (store.stamps["tasks"], store.view_mtime) == (stamp, version)


def test_a_csv_header_with_spaces_survives_a_rewrite(tmp_path: Path) -> None:
    """A hand-edited "id, title" header: the rows were keyed by the raw
    cell, so every title read "" and the first rewrite emptied the column."""
    from backend.csvio import read_rows, rewrite_rows

    p = tmp_path / "tasks.csv"
    p.write_text("id, title, status\ntk_1, keep me, todo\n", encoding="utf-8")
    assert read_rows(p)[0]["title"] == " keep me"

    def mutate(rows):
        rows[0]["status"] = "done"
        return True

    rewrite_rows(p, ["id", "title", "status"], mutate)
    assert read_rows(p) == [{"id": "tk_1", "title": " keep me", "status": "done"}]


def test_one_meta_json_that_is_not_an_object_skips_only_that_chat(tmp_path: Path) -> None:
    chats = tmp_path / "projects" / "alpha" / "chats"
    for name, meta in (("cc-good", '{"tool": "claude-code"}'), ("cc-list", "[]"), ("cc-null", "null")):
        (chats / name).mkdir(parents=True)
        (chats / name / "meta.json").write_text(meta, encoding="utf-8")
        (chats / name / "chat.md").write_text("# chat\n", encoding="utf-8")
    store = ViewStore(tmp_path)
    assert [a["agent_id"] for a in store.agents()] == ["cc-good"]


def test_the_backfill_keeps_a_hook_line_the_transcript_cannot_replace(tmp_path: Path) -> None:
    """A hook line without busy stretches (its measure failed) is measured
    again from the transcript; a turn the transcript does not have keeps the
    hook's end, the only one there is."""
    from backend import turntimes
    from tests.test_turntimes import _chat, _transcript

    folder = _chat(tmp_path, meta={"tool": "claude-code", "session_ref": "sess-1"})
    claude = _transcript(tmp_path)
    orphan = {"turn": 7, "start": "2026-09-29T10:30:00", "end": "2026-09-29T10:40:00", "source": "hook"}
    (folder / "turns.jsonl").write_text(json.dumps(orphan) + "\n", encoding="utf-8")
    assert turntimes.backfill(tmp_path / "data", claude_dir=claude) == 2
    lines = [json.loads(x) for x in (folder / "turns.jsonl").read_text(encoding="utf-8").splitlines()]
    assert orphan in lines
    assert {r["turn"] for r in lines} == {1, 2, 7}


def test_an_append_after_a_cut_off_line_starts_its_own_line(tmp_path: Path) -> None:
    from backend.hookshared import append_locked

    p = tmp_path / "turns.jsonl"
    p.write_text('{"turn": 1, "end": "2026-10-25T10:00:00"}\n{"turn": 2', encoding="utf-8")
    append_locked(p, json.dumps({"turn": 3}) + "\n")
    lines = p.read_text(encoding="utf-8").splitlines()
    assert lines[-1] == '{"turn": 3}'
    # A whole file, or an empty one, gets no extra line.
    q = tmp_path / "fresh.jsonl"
    append_locked(q, "a\n")
    append_locked(q, "b\n")
    assert q.read_text(encoding="utf-8") == "a\nb\n"


def test_a_now_cut_off_before_any_answer_counts_as_answered_by_the_next_session() -> None:
    from datetime import datetime

    from backend.sessions import Turn, group_sessions

    turns = [
        Turn(number=1, at=datetime(2026, 10, 25, 9, 0), line=1, user_summary="#now fix the build", agent_summary=""),
        Turn(number=2, at=datetime(2026, 10, 25, 10, 0), line=5, user_summary="still there?", agent_summary="yes"),
    ]
    first, second = group_sessions("alpha", "cc-a", turns, 30, 9)
    assert first.now_tags[0]["answered"] == "1"
    assert second.now_tags == []
    # Unanswered when nothing came after it at all.
    [alone] = group_sessions("alpha", "cc-a", turns[:1], 30, 4)
    assert alone.now_tags[0]["answered"] == ""


def test_a_done_whose_rewrite_fails_writes_no_history_for_other_cards(client, data_root: Path, monkeypatch) -> None:
    """The stack's next head is stamped inside the rewrite; its history
    line waits for the rewrite to land."""
    from backend import donelib
    from tests.conftest import make_task

    head = make_task(client, "head", stack_id="st_1", position="1")
    make_task(client, "next", stack_id="st_1", position="2")
    events = data_root / "task_events.csv"
    before = events.read_text(encoding="utf-8") if events.exists() else ""

    def refused(path, columns, mutate):
        from backend.csvio import read_rows
        mutate(read_rows(path))
        raise OSError("replace gave up")

    monkeypatch.setattr(donelib, "rewrite_rows", refused)
    tag = {"project": "alpha", "agent_id": "cc-a", "session_id": "ses_1", "at_ts": "2026-10-25T10:00:00", "excerpt": ""}
    try:
        donelib._move(client.app.state.store, [(head, "", 1)], {head: {"agent_id": "cc-a", "turn": 1, **tag}})
    except OSError:
        pass
    after = events.read_text(encoding="utf-8") if events.exists() else ""
    assert "stack_head_at" not in after[len(before):]


# ---------------------------------------------------------------- the API --

from fastapi.testclient import TestClient  # noqa: E402

from tests.conftest import make_chat, make_task  # noqa: E402

AGENT = "cc-abc12345"


def test_a_commit_named_in_a_file_entry_is_a_revision_not_an_option() -> None:
    """``commit_to: "--output=/any/path"`` reached ``git diff`` as an argument
    and wrote a file wherever the server could."""
    import pytest

    from backend.file_entries import _checked_rev

    for rev in ("HEAD", "HEAD~2", "v1.2.3", "a" * 40, "feature/x", "main^{commit}", "release+fix", "@", "@{upstream}"):
        assert _checked_rev({"commit_to": rev}, "commit_to") == rev
    for bad in ("--output=/tmp/x", "-p", "HEAD; rm -rf", "a b", "x\n"):
        with pytest.raises(ValueError, match="commit_to is not a commit or ref"):
            _checked_rev({"commit_to": bad}, "commit_to")
    assert _checked_rev({}, "commit_to") == ""


def test_the_terminal_token_is_handed_only_to_the_operators_pages(client: TestClient) -> None:
    """A GET from any program on this computer read the token that opens
    the socket typing into a shell."""
    assert client.get("/api/terminal/state").status_code == 200
    plain = TestClient(client.app, base_url="http://127.0.0.1:8123")
    plain.cookies.clear()
    r = plain.get("/api/terminal/state")
    assert r.status_code == 403 and r.json()["detail"] == "only the operator's pages read the terminal's state"


def test_an_agent_does_not_rewrite_the_operators_kept_message(client: TestClient, data_root: Path) -> None:
    from backend import keeplib

    make_chat(data_root, "alpha", AGENT, [("2026-09-01T10:00:00", "#vision Everything runs on the laptop.", "ok")])
    client.app.state.store.rebuild()
    vid = keeplib.keep_id("vision", "alpha", AGENT, 1)
    client.get("/api/visions")
    before = client.get(f"/api/visions/{vid}").json()
    r = client.post(f"/api/visions/{vid}/update", json={"agent_id": AGENT, "detail": "AGENT REWROTE"})
    assert r.status_code == 422
    assert r.json()["detail"].startswith("a vision's text is the operator's own message, kept as it was written")
    after = client.get(f"/api/visions/{vid}").json()
    assert after["l4"] == before["l4"] and after["kept"]["message"] == before["kept"]["message"]
    # The operator's page still edits it; an agent still changes a lifecycle field.
    assert client.post(f"/api/visions/{vid}/update", json={"detail": "the operator's edit"}).status_code == 200
    assert client.post(f"/api/visions/{vid}/update", json={"agent_id": AGENT, "status": "active"}).status_code == 200


def test_an_agent_restores_only_what_undo_archived_in_its_chat(client: TestClient) -> None:
    r = client.post("/api/rules", json={"created_date": "2609-01", "created_time": "10:00", "project": "alpha",
                                        "l1": "Never push", "status": "active"})
    rid = r.json()["metadata"]["id"]
    assert client.post(f"/api/rules/{rid}/update", json={"status": "archived"}).status_code == 200
    r = client.post("/api/undo/restore", json={"agent_id": AGENT, "id": rid})
    assert r.status_code == 409 and "not archived by #undo in this chat" in r.json()["detail"]
    assert client.get(f"/api/rules/{rid}").json()["metadata"]["status"] == "archived"
    # The operator's page brings anything back.
    assert client.post("/api/undo/restore", json={"id": rid}).status_code == 200
    assert client.get(f"/api/rules/{rid}").json()["metadata"]["status"] == "active"


def test_restoring_a_live_task_writes_no_archived_line(client: TestClient) -> None:
    tid = make_task(client, "live")
    assert client.post("/api/undo/restore", json={"id": tid}).status_code == 200
    events = client.get(f"/api/tasks/{tid}/events").json()["events"]
    assert [e for e in events if e["field"] == "archived"] == []


def test_time_entries_and_prompt_ratings_are_the_operators(client: TestClient) -> None:
    r = client.post("/api/time-entries", json={
        "created_date": "2610-25", "created_time": "10:00", "project": "alpha", "agent_id": AGENT,
        "started_at": "2026-10-25T10:00:00",
    })
    assert r.status_code == 422 and "time entries are the operator's timer" in r.json()["detail"]
    r = client.post("/api/prompt-runs", json={
        "created_date": "2610-25", "created_time": "10:00", "project": "alpha", "agent_id": AGENT,
        "prompt_id": "pm_x", "rating": "5",
    })
    assert r.status_code == 422 and "a prompt's rating is the operator's" in r.json()["detail"]


def test_an_agent_sets_neither_priority_nor_due_date(client: TestClient) -> None:
    tid = make_task(client, "planned")
    for field, value in (("priority", "high"), ("due_date", "2026-12-01")):
        r = client.post(f"/api/tasks/{tid}/update", json={"agent_id": AGENT, field: value})
        assert r.status_code == 422 and f"{field} is the operator's switch" in r.json()["detail"], r.text
    assert client.post(f"/api/tasks/{tid}/update", json={"priority": "high"}).status_code == 200


def test_who_writes_is_read_one_way_in_a_report(client: TestClient) -> None:
    """``{actor: agent, agent_id: "operator"}`` passed the gate as the agent
    and was recorded as the operator's report."""
    tid = make_task(client, "reported", status="doing")
    r = client.post(f"/api/tasks/{tid}/report", json={"actor": AGENT, "agent_id": "operator", "summary": "done"})
    assert r.status_code == 200
    t = next(t for t in client.get("/api/tasks?project=alpha").json()["tasks"] if t["id"] == tid)
    assert t["agent_done_by"] == AGENT


def test_a_number_where_a_list_is_expected_is_422_not_500(client: TestClient) -> None:
    did = client.post("/api/docs", json={"project": "alpha", "kind": "article", "title": "x"}).json()["doc"]["id"]
    assert client.post(f"/api/docs/{did}/reorder", json={"item_ids": 5}).status_code == 422
    m = client.post("/api/milestones", json={"project": "alpha", "title": "m", "due_date": "2026-12-01"})
    assert m.status_code == 201, m.text
    mid = m.json()["milestone"]["id"]
    assert client.post(f"/api/milestones/{mid}/tasks", json={"add": 5}).status_code == 422
    assert client.post("/api/milestones", json={"project": "alpha", "title": "n", "due_date": "2026-12-01",
                                                "tasks": True}).status_code == 422
    for bad in (5, True, "x"):
        r = client.post("/api/map", json={"project": "ALPHA", "agent_id": "cc-m",
                                          "map": {"template": "tool", "rows": [], "relations": bad}})
        assert r.status_code == 422, (bad, r.status_code)


# ------------------------------------------------------- works for everyone --


def test_codex_config_keeps_an_indented_table_after_ours_and_crlf_ends() -> None:
    from backend.integration_text import _upsert_codex_mcp

    block = '[mcp_servers.slightly-parallel]\ncommand = "new"\n'
    text = '[mcp_servers.slightly-parallel]\ncommand = "old"\n  [mcp_servers.mine]\n  command = "keep"\n'
    out, action = _upsert_codex_mcp(text, block)
    assert action == "updated" and 'command = "new"' in out and '[mcp_servers.mine]\n  command = "keep"' in out
    crlf = '[mcp_servers.slightly-parallel]\r\ncommand = "old"\r\n\r\n[other]\r\nx = 1\r\n'
    out, action = _upsert_codex_mcp(crlf, block)
    assert action == "updated" and 'command = "new"' in out and "[other]\r\nx = 1" in out
    assert _upsert_codex_mcp(block, block) == (block, "unchanged")


def test_a_settings_file_with_a_byte_order_mark_is_valid_json() -> None:
    from backend.integration_text import _upsert_hooks, _upsert_json_key

    text, action = _upsert_hooks('\ufeff{"permissions": {}}', "python3 x.py")
    assert action == "updated" and '"permissions"' in text and "\ufeff" not in text
    text, action = _upsert_json_key("\ufeff{}", "mcpServers", "sp", {"command": "x"})
    assert action == "updated" and text.startswith("{")


def test_an_agents_md_that_is_not_utf8_is_named_not_a_500(tmp_path: Path) -> None:
    from backend.server import create_app

    data_root = tmp_path / "data"
    data_root.mkdir()
    project_dir = tmp_path / "my-app"
    project_dir.mkdir()
    (project_dir / "AGENTS.md").write_bytes("# Mine\n".encode("utf-16"))   # PowerShell 5.1's echo > file
    with TestClient(create_app(data_root=data_root, watch=False)) as client:
        r = client.post("/api/setup/integrate", json={"project_code": "my-app", "project_dir": str(project_dir)})
    assert r.status_code == 422 and "cannot read" in r.json()["detail"] and "AGENTS.md" in r.json()["detail"]


def test_the_opencode_adapter_sends_text_times_and_touched_on_stdin(tmp_path: Path) -> None:
    import subprocess
    import sys

    cli = Path(__file__).resolve().parents[2] / "scripts" / "hooks" / "capture-cli.py"
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    base = [sys.executable, str(cli), "--project", "alpha", "--data-root", str(root), "--agent", "oc-abc12345",
            "--json-stdin", "--tool", "opencode", "--session", "ses_1", "--cwd", str(tmp_path)]
    long_text = "x" * 200_000   # past any command line
    done = subprocess.run([*base, "--phase", "open"], input=json.dumps({"text": long_text}), capture_output=True,
                          text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    folder = root / "projects" / "alpha" / "chats" / "oc-abc12345"
    assert long_text in (folder / "chat.md").read_text(encoding="utf-8")
    now_ms = int(time.time() * 1000)
    payload = {"text": "the answer", "times": {"points": [now_ms - 5000, now_ms], "helpers": []}, "touched": ["a.py"]}
    done = subprocess.run([*base, "--phase", "complete", "--close-if-missing"], input=json.dumps(payload),
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert "the answer" in (folder / "chat.md").read_text(encoding="utf-8")
    lines = [json.loads(x) for x in (folder / "turns.jsonl").read_text(encoding="utf-8").splitlines()]
    assert lines and lines[-1]["turn"] == 1 and "end" in lines[-1]
    assert "a.py" in (folder / "work.jsonl").read_text(encoding="utf-8")


def test_a_setting_written_into_an_env_that_is_not_utf8_leaves_it_as_it_was(tmp_path: Path) -> None:
    """The read failed, the text was taken as empty, and the file was
    written again with the one new line: every other setting gone."""
    import pytest
    from fastapi import HTTPException

    from backend.routers.setup import _upsert_env_line

    env = tmp_path / ".env"
    raw = "SP_PORT=8123\n# Jörg's machine\n".encode("cp1252")
    env.write_bytes(raw)
    with pytest.raises(HTTPException) as got:
        _upsert_env_line(env, "SP_DATA_ROOT", "/data")
    assert got.value.status_code == 422 and "not UTF-8" in got.value.detail
    assert env.read_bytes() == raw
    # A BOM is read past, and the setting lands with the rest kept.
    env.write_bytes("\ufeffSP_PORT=8123\n".encode("utf-8"))
    _upsert_env_line(env, "SP_DATA_ROOT", "/data")
    assert env.read_text(encoding="utf-8").splitlines() == ["SP_PORT=8123", 'SP_DATA_ROOT="/data"']
