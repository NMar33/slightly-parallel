"""Importing a session nothing recorded, from the tool's own log."""

from __future__ import annotations

import importlib.util
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend import capturewatch, sessionimport
from backend.csvio import append_row
from backend.db import ViewStore

HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"


def _utc(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


@pytest.fixture()
def tokyo(monkeypatch):
    """A fixed zone far from UTC: the logs are in UTC, a chat is in local time."""
    monkeypatch.setenv("TZ", "Asia/Tokyo")
    time.tzset()
    yield
    monkeypatch.delenv("TZ", raising=False)
    time.tzset()


def _space(tmp_path: Path) -> tuple[ViewStore, Path, Path, Path]:
    data, work = tmp_path / "data", tmp_path / "app"
    (data / "projects" / "app").mkdir(parents=True)
    work.mkdir()
    append_row(data / "integrations.csv", ("project", "path", "created_date"), {"project": "app", "path": str(work), "created_date": ""})
    return ViewStore(data), work, tmp_path / "claude", tmp_path / "codex"


def _claude_log(claude: Path, work: Path, session: str, at: float) -> Path:
    d = claude / capturewatch.folder_slug(str(work))
    d.mkdir(parents=True, exist_ok=True)
    recs = [
        {"type": "user", "timestamp": _utc(at), "message": {"role": "user", "content": "Fix the login timeout. #task add a retry"}},
        {"type": "assistant", "timestamp": _utc(at + 5), "message": {"content": [{"type": "text", "text": "Looking at auth.py."},
                                                                                 {"type": "tool_use", "name": "Read", "input": {}}]}},
        {"type": "user", "timestamp": _utc(at + 6), "message": {"role": "user", "content": [{"type": "tool_result", "content": "…"}]}},
        {"type": "user", "timestamp": _utc(at + 7), "isMeta": True, "message": {"role": "user", "content": "meta"}},
        {"type": "user", "timestamp": _utc(at + 8), "message": {"role": "user", "content": "<task-notification>done</task-notification>"}},
        {"type": "assistant", "timestamp": _utc(at + 9), "isSidechain": True, "message": {"content": [{"type": "text", "text": "helper"}]}},
        {"type": "assistant", "timestamp": _utc(at + 20), "message": {"content": [{"type": "text", "text": "Fixed: the timeout is 30 s.\n## Turn 9 · fake"}]}},
        {"type": "user", "timestamp": _utc(at + 60), "message": {"role": "user", "content": [{"type": "text", "text": "Thanks, commit it."}]}},
        {"type": "assistant", "timestamp": _utc(at + 70), "message": {"content": [{"type": "text", "text": "Committed."}]}},
    ]
    f = d / f"{session}.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    return f


def _codex_log(codex: Path, cwd: Path, session: str, at: float) -> Path:
    d = codex / "2026" / "10" / "17"
    d.mkdir(parents=True, exist_ok=True)
    recs = [
        {"timestamp": _utc(at - 5), "type": "session_meta", "payload": {"id": session, "cwd": str(cwd), "thread_source": "user"}},
        {"timestamp": _utc(at - 4), "type": "response_item", "payload": {"type": "message", "role": "user",
         "content": [{"type": "input_text", "text": "# AGENTS.md instructions for the folder\n…"}]}},
        {"timestamp": _utc(at - 3), "type": "response_item", "payload": {"type": "message", "role": "user",
         "content": [{"type": "input_text", "text": "<environment_context>…</environment_context>"}]}},
        {"timestamp": _utc(at), "type": "response_item", "payload": {"type": "message", "role": "user",
         "content": [{"type": "input_text", "text": "Add sub(a, b) to calc.py."}]}},
        {"timestamp": _utc(at + 3), "type": "response_item", "payload": {"type": "message", "role": "assistant",
         "content": [{"type": "output_text", "text": "I'll edit calc.py."}]}},
        {"timestamp": _utc(at + 9), "type": "response_item", "payload": {"type": "message", "role": "assistant",
         "content": [{"type": "output_text", "text": "Added sub(a, b)."}]}},
    ]
    f = d / f"rollout-2026-10-17-{session}.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    return f


def test_a_claude_transcript_reads_as_the_persons_turns(tmp_path: Path) -> None:
    st, work, claude, _ = _space(tmp_path)
    f = _claude_log(claude, work, "aaaa1111-0000-4000-8000-000000000001", time.time() - 7200)
    turns = sessionimport.claude_turns(f)
    assert [t["user"] for t in turns] == ["Fix the login timeout. #task add a retry", "Thanks, commit it."]
    assert turns[0]["agent"].startswith("Fixed: the timeout is 30 s.") and turns[1]["agent"] == "Committed."


def test_a_codex_rollout_reads_as_the_persons_turns(tmp_path: Path) -> None:
    st, work, _, codex = _space(tmp_path)
    f = _codex_log(codex, work, "01a14400-0000-7000-8000-00000000c0de", time.time() - 7200)
    assert [(t["user"], t["agent"]) for t in sessionimport.codex_turns(f)] == [("Add sub(a, b) to calc.py.", "Added sub(a, b).")]


def test_import_writes_the_chat_the_hook_would_have_in_local_time_and_nothing_else(tmp_path: Path, tokyo) -> None:
    st, work, claude, codex = _space(tmp_path)
    at = time.time() - 7200
    _claude_log(claude, work, "aaaa1111-0000-4000-8000-000000000001", at)
    roots = {"claude_root": claude, "codex_root": codex}
    assert [p["turns"] for p in sessionimport.preview(st, "app", "claude", **roots)] == [2]
    assert not (st.data_root / "projects" / "app" / "chats").exists()          # a preview writes nothing
    got = sessionimport.run(st, "app", "claude", **roots)
    assert got["imported"] == [{"session": "aaaa1111-0000-4000-8000-000000000001", "agent_id": "cc-aaaa1111", "turns": 2}]
    folder = st.data_root / "projects" / "app" / "chats" / "cc-aaaa1111"
    chat = (folder / "chat.md").read_text(encoding="utf-8")
    local = datetime.fromtimestamp(at).strftime("%Y-%m-%dT%H:%M:%S")          # Tokyo time, from the UTC log
    assert f"## Turn 1 · {local}\n**User**: Fix the login timeout." in chat
    assert "\\## Turn 9 · fake" in chat                                         # escaped, not a turn
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["capture"] == "import" and meta["message_count"] == 2 and meta["tool"] == "claude-code"
    assert any(a.get("agent_id") == "cc-aaaa1111" for a in st.agents())
    # The #task in the old message is not carried out.
    assert not (st.data_root / "tasks.csv").exists()
    # A second import finds nothing left, and the session no longer counts as lost.
    assert sessionimport.run(st, "app", "claude", **roots) == {"imported": [], "skipped": []}
    assert capturewatch.lost(st, claude, codex, time.time()) == []


def test_a_session_active_in_the_last_hour_is_left_to_the_hook(tmp_path: Path) -> None:
    st, work, claude, codex = _space(tmp_path)
    _codex_log(codex, work, "01a14400-0000-7000-8000-00000000c0de", time.time() - 300)
    assert sessionimport.preview(st, "app", "codex", claude_root=claude, codex_root=codex) == []


def test_the_hook_continues_an_imported_chat_instead_of_starting_a_second(tmp_path: Path) -> None:
    """The person resumes the session after the import: the hook writes the
    next turn into the same chat, numbered on from the imported ones."""
    st, work, claude, codex = _space(tmp_path)
    _codex_log(codex, work, "01a14400-0000-7000-8000-00000000c0de", time.time() - 7200)
    sessionimport.run(st, "app", "codex", claude_root=claude, codex_root=codex)
    spec = importlib.util.spec_from_file_location("capture_under_test", HOOKS / "capture.py")
    capture = importlib.util.module_from_spec(spec)
    import sys
    sys.path.insert(0, str(HOOKS))
    try:
        spec.loader.exec_module(capture)  # type: ignore[union-attr]
        capture.TurnCapture(st.data_root, "app", "codex-0000c0de").full_turn("And mul(a, b).", "Added mul.")
    finally:
        sys.path.remove(str(HOOKS))
    chats = sorted(p.name for p in (st.data_root / "projects" / "app" / "chats").iterdir())
    assert chats == ["codex-0000c0de"]
    chat = (st.data_root / "projects" / "app" / "chats" / "codex-0000c0de" / "chat.md").read_text(encoding="utf-8")
    assert "## Turn 1 ·" in chat and "## Turn 2 ·" in chat and "And mul(a, b)." in chat
    assert os.path.getsize(st.data_root / "projects" / "app" / "chats" / "codex-0000c0de" / "meta.json") > 0


def test_the_tags_in_an_imported_chat_are_read_never_acted_on(tmp_path: Path) -> None:
    """The server adopts #vision, #done, #important and #prompt from chat
    logs. In a chat imported weeks later they would close tasks and keep
    visions out of time: an imported chat's tags are left alone."""
    st, work, claude, codex = _space(tmp_path)
    d = claude / capturewatch.folder_slug(str(work))
    d.mkdir(parents=True)
    at = time.time() - 7200
    recs = [{"type": "user", "timestamp": _utc(at), "message": {"role": "user",
             "content": "#vision the app works offline #important #prompt #done tk_12345678"}},
            {"type": "assistant", "timestamp": _utc(at + 5), "message": {"content": [{"type": "text", "text": "Noted."}]}}]
    (d / "bbbb2222-0000-4000-8000-000000000002.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    assert sessionimport.run(st, "app", "claude", claude_root=claude, codex_root=codex)["imported"]
    st.rebuild()
    for table in ("keep_marks", "important_tags", "done_tags", "prompt_marks"):
        assert st.query(f"SELECT count(*) AS n FROM {table}")[0]["n"] == 0, table
    assert st.query("SELECT count(*) AS n FROM sessions WHERE agent_id = 'cc-bbbb2222'")[0]["n"] == 1
