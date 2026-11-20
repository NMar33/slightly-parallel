"""A message typed while the agent works is the operator's turn, in order.

Claude Code (2.1.3xx) writes a message the operator types while the agent is
busy not as a "user" record but as an ``attachment`` of type
``queued_command`` (``origin.kind`` "human", ``commandMode`` "prompt"); the
prompt hook fires for it when it is typed. Another session's message, a
background task's notification and a helper's report arrive the same way
with their own origin, and are never the operator. These tests drive the
prompt hook, the Stop hook, the importer and the capture check with records
of the shapes found in the local transcripts (the words are made up).

Also here: a chat imported from the log and then resumed acts from its first
live turn on (``live_from``), and a ``cursor-agent -p`` run is a helper chat.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend import capturewatch, hookshared, sessionimport
from backend.csvio import append_row
from backend.db import ViewStore

HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"
CC_HOOK = HOOKS / "claude-code-capture.py"
TAGS = "Card fixes are due. #publish #vision offline first #done tk_12345678 #now #pin #important"
HUMAN = {"turnOrigin": "human", "origin": {"kind": "human"}, "promptSource": "typed"}


def _utc(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _user(text: str, at: float | None = None, **marks) -> dict:
    rec = {"type": "user", "message": {"role": "user", "content": text}, "isSidechain": False, **marks}
    if at is not None:
        rec["timestamp"] = _utc(at)
    return rec


def _reply(text: str, at: float) -> dict:
    return {"type": "assistant", "timestamp": _utc(at), "isSidechain": False,
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def _queued(prompt: str, at: float, kind: str | None = "human", mode: str | None = "prompt", **extra) -> dict:
    """A queued_command attachment as Claude Code 2.1.300-2.1.325 writes it."""
    a: dict = {"type": "queued_command", "prompt": prompt, "source_uuid": "8e008773-0000-4000-8000-000000000001",
               "delivery_id": "f284ab42-0000-4000-8000-000000000002", "timestamp": _utc(at)}
    if mode is not None:
        a["commandMode"] = mode
    if kind is not None:
        a["origin"] = {"kind": kind}
    if kind == "human":
        a["humanTurn"] = True
    if kind == "peer":
        a["isMeta"] = True
    a.update(extra)
    return {"parentUuid": "a1f86528-0000-4000-8000-000000000003", "isSidechain": False, "attachment": a,
            "type": "attachment", "uuid": f"97352957-0000-4000-8000-{int(at) % 10**12:012d}", "timestamp": _utc(at),
            "renderedRole": "system", "userType": "external", "entrypoint": "cli", "version": "2.1.300"}


#: The tool's own queued messages, each as found in the transcripts.
TOOL_QUEUED = {
    "task notification": dict(prompt=f"<task-notification>\n<task-id>b2becmco7</task-id>\n<status>completed</status>\n"
                                     f"<summary>{TAGS}</summary>\n</task-notification>", kind="task-notification",
                              mode="task-notification"),
    "helper stopped (no origin)": dict(prompt=f'Background agent "Audit {TAGS}" was stopped by the user.',
                                       kind=None, mode="task-notification"),
    "another session": dict(prompt=f'<cross-session-message from="uds:/run/user/1000/cc-socks/1.sock" '
                                   f'from-name="wt-app-manager" from-mode="prompting">\n{TAGS}\n</cross-session-message>',
                            kind="peer", mode="prompt"),
    "a helper's report": dict(prompt=f'<agent-message from="a84cce07b243d331e">\n[Subagent hand-back] {TAGS}\n</agent-message>',
                              kind="peer", mode="prompt"),
}


def _write(path: Path, recs: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n", encoding="utf-8")
    return path


def _run_hook(root: Path, payload: dict) -> str:
    proc = subprocess.run([sys.executable, str(CC_HOOK), "--project", "alpha", "--data-root", str(root)],
                          input=json.dumps(payload), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(HOOKS))
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    finally:
        sys.path.remove(str(HOOKS))
    return mod


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    (tmp_path / "data").mkdir()
    return tmp_path / "data"


def _tables(st: ViewStore) -> dict[str, int]:
    return {t: st.query(f"SELECT count(*) AS n FROM {t}")[0]["n"]
            for t in ("keep_marks", "important_tags", "done_tags", "now_tags")}


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------

def test_a_queued_message_of_the_operator_is_a_prompt_of_the_operator() -> None:
    rec = hookshared.prompt_record(_queued(TAGS, time.time()))
    assert rec is not None and rec["message"]["content"] == TAGS
    assert not hookshared.tool_wrote(rec) and hookshared.operator_wrote(TAGS)


@pytest.mark.parametrize("case", sorted(TOOL_QUEUED))
def test_a_queued_message_of_the_tool_is_none_of_the_operators(case: str) -> None:
    c = TOOL_QUEUED[case]
    rec = hookshared.prompt_record(_queued(c["prompt"], time.time(), c["kind"], c["mode"]))
    assert rec is not None
    assert hookshared.tool_wrote(rec) or not hookshared.operator_wrote(c["prompt"])


def test_other_records_are_no_prompt() -> None:
    assert hookshared.prompt_record({"type": "attachment", "attachment": {"type": "edited_text_file"}}) is None
    assert hookshared.prompt_record({"type": "user", "message": {"content": [{"type": "tool_result"}]}}) is None
    assert hookshared.prompt_record(None) is None


# ---------------------------------------------------------------------------
# Live: the prompt hook and the Stop hook
# ---------------------------------------------------------------------------

def test_hook_records_the_queued_message_and_its_commands_act(root: Path, tmp_path: Path) -> None:
    """The message is only an attachment in the transcript (no "user"
    record has its words): it is the operator's turn, commands and all —
    a tag in a paste too."""
    at = time.time()
    said = f'and also this:\n<pasted_content id="53d3">\n{TAGS}\n</pasted_content>'
    t = _write(tmp_path / "t.jsonl", [
        _user("Fix the login timeout.", at, **HUMAN),
        _reply("Working on it.", at + 1),
        _queued("anything else", at + 2, **{}),
        _queued(TOOL_QUEUED["another session"]["prompt"], at + 3, "peer"),
        _queued(said, at + 4),
    ])
    out = _run_hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": "que00001", "prompt": said,
                           "transcript_path": str(t)})
    assert "#publish" in out
    chat = (root / "projects/alpha/chats/cc-que00001/chat.md").read_text(encoding="utf-8")
    assert "#vision offline first" in chat


@pytest.mark.parametrize("case", sorted(TOOL_QUEUED))
def test_hook_records_no_turn_for_a_queued_message_of_the_tool(root: Path, tmp_path: Path, case: str) -> None:
    c = TOOL_QUEUED[case]
    at = time.time()
    t = _write(tmp_path / "t.jsonl", [
        _user("Fix the login timeout.", at, **HUMAN),
        _reply("Working on it.", at + 1),
        _queued(c["prompt"], at + 2, c["kind"], c["mode"]),
    ])
    out = _run_hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": "que00002", "prompt": c["prompt"],
                           "transcript_path": str(t)})
    assert "#publish" not in out and "#vision" not in out
    assert not (root / "projects/alpha/chats/cc-que00002").exists()


def test_a_message_from_another_session_with_no_record_yet_is_still_no_turn(root: Path, tmp_path: Path) -> None:
    """Its prefix tells it before the transcript does (NOT_OPERATOR)."""
    prompt = TOOL_QUEUED["another session"]["prompt"]
    _run_hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": "que00003", "prompt": prompt,
                     "transcript_path": str(tmp_path / "missing.jsonl")})
    assert not (root / "projects/alpha/chats/cc-que00003").exists()


def _now_later() -> float:
    """A record's time after the hook that ran last (its turn's start is
    kept to the second)."""
    time.sleep(1.1)
    return time.time()


def test_two_messages_typed_while_the_agent_works_are_turns_in_order_with_their_answers(
        root: Path, tmp_path: Path) -> None:
    """The hook fires as each message is typed, while the turn before is
    still open: that turn keeps what the agent had written of its answer
    (it used to keep nothing), a turn with nothing written yet a marker, and
    the final answer goes to the last message."""
    recs = [_user("Fix the login timeout.", time.time(), **HUMAN)]
    t = _write(tmp_path / "t.jsonl", recs)
    base = {"session_id": "que00004", "transcript_path": str(t)}
    _run_hook(root, {**base, "hook_event_name": "UserPromptSubmit", "prompt": "Fix the login timeout."})
    recs.append(_reply("Looking at the session code.", _now_later()))
    _write(t, recs)
    _run_hook(root, {**base, "hook_event_name": "UserPromptSubmit", "prompt": "also check the logout #pin"})
    _now_later()
    _run_hook(root, {**base, "hook_event_name": "UserPromptSubmit", "prompt": "and the remember-me box"})
    at = _now_later()
    recs += [_queued("also check the logout #pin", at - 3), _queued("and the remember-me box", at - 2),
             _reply("All three are fixed.", at)]
    _write(t, recs)
    _run_hook(root, {**base, "hook_event_name": "Stop", "last_assistant_message": "All three are fixed."})
    chat = (root / "projects/alpha/chats/cc-que00004/chat.md").read_text(encoding="utf-8")
    lines = [ln for ln in chat.splitlines() if ln.startswith(("**User**:", "**Agent**:"))]
    assert lines == ["**User**: Fix the login timeout.", "**Agent**: Looking at the session code.",
                     "**User**: also check the logout #pin", "**Agent**: (no reply yet when the next message was typed)",
                     "**User**: and the remember-me box", "**Agent**: All three are fixed."]
    st = ViewStore(root)
    st.rebuild()
    assert st.query("SELECT turn FROM important_tags")[0]["turn"] == 2


def test_a_message_typed_as_the_turn_ends_gets_its_answer(root: Path, tmp_path: Path) -> None:
    """Typed while the agent worked, sent only after the turn ended (a
    "user" record with promptSource "queued", no prompt event then): its
    answer goes on its turn instead of being dropped."""
    recs = [_user("Fix the login timeout.", time.time(), **HUMAN)]
    t = _write(tmp_path / "t.jsonl", recs)
    base = {"session_id": "que00007", "transcript_path": str(t)}
    _run_hook(root, {**base, "hook_event_name": "UserPromptSubmit", "prompt": "Fix the login timeout."})
    _run_hook(root, {**base, "hook_event_name": "UserPromptSubmit", "prompt": "and the logout"})
    recs.append(_reply("The timeout is fixed.", _now_later()))
    _write(t, recs)
    _run_hook(root, {**base, "hook_event_name": "Stop", "last_assistant_message": "The timeout is fixed."})
    recs += [_user("and the logout", time.time(), turnOrigin="human", origin={"kind": "human"}, promptSource="queued"),
             _reply("The logout is fixed too.", time.time())]
    _write(t, recs)
    _run_hook(root, {**base, "hook_event_name": "Stop", "last_assistant_message": "The logout is fixed too."})
    chat = (root / "projects/alpha/chats/cc-que00007/chat.md").read_text(encoding="utf-8")
    assert chat.count("## Turn") == 2 and "The timeout is fixed." in chat and "The logout is fixed too." in chat
    assert chat.index("**User**: and the logout") < chat.index("The logout is fixed too.")


def test_the_same_message_sent_again_as_typed_is_one_turn(root: Path, tmp_path: Path) -> None:
    """Esc on a running turn sends the queued message again as a typed
    prompt (seen in a transcript: the attachment, then a "user" record with
    the same words 15 s later); the hook keeps one turn."""
    at = time.time()
    recs = [_queued("what does fair mean here", at)]
    t = _write(tmp_path / "t.jsonl", recs)
    base = {"session_id": "que00005", "transcript_path": str(t), "hook_event_name": "UserPromptSubmit",
            "prompt": "what does fair mean here"}
    _run_hook(root, base)
    _write(t, recs + [_user("[Request interrupted by user]", at + 1), _user("what does fair mean here", at + 2, **HUMAN)])
    _run_hook(root, base)
    chat = (root / "projects/alpha/chats/cc-que00005/chat.md").read_text(encoding="utf-8")
    assert chat.count("**User**: what does fair mean here") == 1


def test_a_reply_after_a_queued_notification_continues_the_last_turn(root: Path, tmp_path: Path) -> None:
    """The agent idle, a background task ends: its notice is a
    queued_command, no prompt event opens a turn, and the reply it wakes
    goes on the operator's last turn instead of being dropped."""
    at = time.time()
    recs = [_user("Run the long test.", at, **HUMAN)]
    t = _write(tmp_path / "t.jsonl", recs)
    base = {"session_id": "que00006", "transcript_path": str(t)}
    _run_hook(root, {**base, "hook_event_name": "UserPromptSubmit", "prompt": "Run the long test."})
    recs.append(_reply("Started it in the background.", at + 1))
    _write(t, recs)
    _run_hook(root, {**base, "hook_event_name": "Stop", "last_assistant_message": "Started it in the background."})
    c = TOOL_QUEUED["task notification"]
    recs += [_queued(c["prompt"], at + 60, c["kind"], c["mode"]), _reply("The long test passed: 41 passed.", at + 61)]
    _write(t, recs)
    _run_hook(root, {**base, "hook_event_name": "UserPromptSubmit", "prompt": c["prompt"]})
    _run_hook(root, {**base, "hook_event_name": "Stop", "last_assistant_message": "The long test passed: 41 passed."})
    chat = (root / "projects/alpha/chats/cc-que00006/chat.md").read_text(encoding="utf-8")
    assert "The long test passed" in chat and chat.count("## Turn") == 1
    assert "<task-notification" not in chat


# ---------------------------------------------------------------------------
# Afterwards: the importer and the capture check
# ---------------------------------------------------------------------------

def _space(tmp_path: Path) -> tuple[ViewStore, Path, Path, Path]:
    data, work = tmp_path / "data", tmp_path / "app"
    (data / "projects" / "app").mkdir(parents=True)
    work.mkdir()
    append_row(data / "integrations.csv", ("project", "path", "created_date"),
               {"project": "app", "path": str(work), "created_date": ""})
    return ViewStore(data), work, tmp_path / "claude", tmp_path / "codex"


def _session(at: float) -> list[dict]:
    """A session with every case: typed, queued while working (with tags,
    in a paste), the tool's queued messages, a queued message sent again
    as typed, and the history a fork copied in (forkedFrom)."""
    fork = {"sessionId": "11111111-0000-4000-8000-000000000000", "messageUuid": "e38967d0-0000-4000-8000-000000000000"}
    recs = [
        {**_user("Inherited from the parent chat #done tk_12345678", at - 500, **HUMAN), "forkedFrom": fork},
        {**_queued("Inherited queued message", at - 400), "forkedFrom": fork},
        {**_reply("Inherited reply.", at - 300), "forkedFrom": fork},
        _user("Fix the login timeout.", at, **HUMAN),
        _reply("Looking.", at + 1),
        _queued(f'save this <pasted_content id="a1">{TAGS}</pasted_content>', at + 2),
    ]
    for i, case in enumerate(sorted(TOOL_QUEUED)):
        c = TOOL_QUEUED[case]
        recs.append(_queued(c["prompt"], at + 3 + i, c["kind"], c["mode"]))
    recs += [
        _reply("Saved, and the timeout is fixed.", at + 10),
        _queued("what does fair mean here", at + 11),
        _user("[Request interrupted by user]", at + 12),
        _user("what does fair mean here", at + 13, **HUMAN),
        _reply("Fair means the same inputs.", at + 14),
        _user("what does fair mean here", at + 15, **HUMAN),  # asked again after the answer: a turn
        _reply("Same inputs, as said.", at + 16),
    ]
    return recs


def test_import_reads_queued_messages_as_the_operators_turns(tmp_path: Path) -> None:
    st, work, claude, codex = _space(tmp_path)
    d = claude / capturewatch.folder_slug(str(work))
    d.mkdir(parents=True)
    at = time.time() - 7200
    f = _write(d / "eeee5555-0000-4000-8000-000000000005.jsonl", _session(at))
    turns = sessionimport.claude_turns(f)
    assert [t["user"][:16] for t in turns] == ["Fix the login ti", "save this <paste", "what does fair m",
                                                "what does fair m"]
    assert [t["agent"] for t in turns] == ["Looking.", "Saved, and the timeout is fixed.",
                                           "Fair means the same inputs.", "Same inputs, as said."]
    prompts, texts, _assign = sessionimport.claude_usage_parts(f, "eeee5555")
    assert texts == [t["user"] for t in turns] and len(prompts) == 4
    assert sessionimport.run(st, "app", "claude", claude_root=claude, codex_root=codex)["imported"]
    st.rebuild()
    assert _tables(st) == {"keep_marks": 0, "important_tags": 0, "done_tags": 0, "now_tags": 0}


def test_capture_check_sees_a_queued_message_as_the_operators_last(tmp_path: Path) -> None:
    at = time.time()
    c = TOOL_QUEUED["another session"]
    f = _write(tmp_path / "t.jsonl", [
        _user("Fix the login timeout.", at - 100, **HUMAN),
        _queued("and the logout", at - 50),
        _queued(c["prompt"], at - 10, c["kind"], c["mode"]),
    ])
    assert capturewatch.last_prompt(f) == pytest.approx(at - 50, abs=1)


# ---------------------------------------------------------------------------
# A resumed imported chat: live turns act, imported ones do not
# ---------------------------------------------------------------------------

def test_a_resumed_imported_chat_acts_from_its_first_live_turn(root: Path, tmp_path: Path) -> None:
    folder = root / "projects/alpha/chats/cc-res00001"
    folder.mkdir(parents=True)
    (folder / "chat.md").write_text(
        "# Chat log — cc-res00001\n*Started 2026-11-10T10:00:00. Imported.*\n\n---\n"
        "\n## Turn 1 · 2026-11-10T10:00:00\n**User**: old #done tk_11111111 #vision old one\n**Agent**: ok\n"
        "\n## Turn 2 · 2026-11-10T10:05:00\n**User**: old #pin\n**Agent**: ok\n", encoding="utf-8")
    (folder / "meta.json").write_text(json.dumps({
        "agent_id": "cc-res00001", "agent_name": "cc-res00001", "project": "alpha", "created_date": "2611-10",
        "message_count": 2, "schema_version": 2, "capture": "import", "tool": "claude-code",
        "session_ref": "res00001-0000-4000-8000-000000000000"}), encoding="utf-8")
    st = ViewStore(root)
    st.rebuild()
    assert _tables(st) == {"keep_marks": 0, "important_tags": 0, "done_tags": 0, "now_tags": 0}
    t = _write(tmp_path / "t.jsonl", [_user("new #done tk_22222222 #vision new one", time.time(), **HUMAN)])
    _run_hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": "res00001-0000-4000-8000-000000000000",
                     "prompt": "new #done tk_22222222 #vision new one", "transcript_path": str(t)})
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["capture"] == "import" and meta["live_from"] == 3
    st.rebuild()
    done = st.query("SELECT turn, tasks FROM done_tags")
    assert [(r["turn"], "tk_22222222" in r["tasks"]) for r in done] == [(3, True)]
    assert [r["turn"] for r in st.query("SELECT turn FROM keep_marks")] == [3]
    assert st.query("SELECT count(*) AS n FROM important_tags")[0]["n"] == 0


# ---------------------------------------------------------------------------
# Cursor: a cursor-agent -p run is a helper chat
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("argv,want", [
    (["/home/u/.local/share/cursor-agent/versions/2025.11.06/node", "/home/u/.local/share/cursor-agent/versions/2025.11.06/index.js",
      "-p", "review the diff"], True),
    (["cursor-agent", "--print", "--output-format", "text", "review"], True),
    (["cursor-agent", "--print=true", "x"], True),
    (["cursor-agent"], False),                       # the interactive CLI
    (["cursor-agent", "resume"], False),
    (["/usr/share/cursor/cursor", "--type=renderer"], False),  # the editor
    (["bash", "-p"], False),                          # a -p of another program
])
def test_cursor_print_mode_is_told_by_the_command_line(argv: list[str], want: bool) -> None:
    assert hookshared.cursor_print_run(argv) is want


def test_cursor_helper_kind_reads_the_ancestors() -> None:
    lines = {10: ["/bin/sh", "-c", "hook"], 11: ["node", "/x/cursor-agent/index.js", "-p", "go"], 12: ["bash"]}
    assert hookshared.cursor_helper_kind([10, 11, 12], lines.get) == "cursor-print"
    assert hookshared.cursor_helper_kind([10, 12], lines.get) == ""
    assert "cursor-print" in hookshared.HELPER_KINDS


def test_a_cursor_print_run_is_a_helper_chat_and_reads_no_command(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load("sp_cursor_q", HOOKS / "cursor-capture.py")
    monkeypatch.setattr(mod.shared, "cursor_helper_kind", lambda *a, **k: "cursor-print")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "abcd1234-0000-4000-8000-000000000000")
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    payload = {"hook_event_name": "beforeSubmitPrompt", "conversation_id": "cur00001-0000", "prompt": TAGS,
               "workspace_roots": [str(root)]}
    assert mod.handle(payload, root, "alpha") == mod.ALLOW
    mod.handle({**payload, "hook_event_name": "afterAgentResponse", "text": "ok"}, root, "alpha")
    meta = json.loads((root / "projects/alpha/chats/cursor-cur00001/meta.json").read_text(encoding="utf-8"))
    assert meta["helper"] is True and meta["helper_kind"] == "cursor-print"
    assert meta["helper_of"] == "cc-abcd1234" and meta["helper_of_by"] == "env"
    st = ViewStore(root)
    st.rebuild()
    assert _tables(st) == {"keep_marks": 0, "important_tags": 0, "done_tags": 0, "now_tags": 0}


def test_a_cursor_chat_the_operator_types_in_still_acts(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load("sp_cursor_q2", HOOKS / "cursor-capture.py")
    monkeypatch.setattr(mod.shared, "cursor_helper_kind", lambda *a, **k: "")
    payload = {"hook_event_name": "beforeSubmitPrompt", "conversation_id": "cur00002-0000", "prompt": TAGS,
               "workspace_roots": [str(root)]}
    mod.handle(payload, root, "alpha")
    mod.handle({**payload, "hook_event_name": "afterAgentResponse", "text": "ok"}, root, "alpha")
    meta = json.loads((root / "projects/alpha/chats/cursor-cur00002/meta.json").read_text(encoding="utf-8"))
    assert not meta.get("helper")
    st = ViewStore(root)
    st.rebuild()
    assert st.query("SELECT count(*) AS n FROM done_tags")[0]["n"] == 1


# ---------------------------------------------------------------------------
# Probe: the newest transcript's queued messages carry the known markers
# ---------------------------------------------------------------------------

def test_probe_claude_codes_queued_messages_carry_the_known_markers() -> None:
    """Fails when Claude Code's newest transcripts hold a queued_command
    with an origin or a commandMode the rule does not know (read
    queued_prompt and tool_wrote again), or an operator's queued message
    stops saying origin human."""
    base = Path.home() / ".claude" / "projects"
    files = sorted((p for p in base.glob("*/*.jsonl") if p.is_file()), key=lambda p: p.stat().st_mtime)[-20:] \
        if base.is_dir() else []
    if not files:
        pytest.skip("no Claude Code transcript on this machine")
    known_origin = hookshared.OPERATOR_ORIGINS | hookshared.TOOL_ORIGINS | hookshared.SUBAGENT_ORIGINS | {""}
    unknown: set[str] = set()
    seen = 0
    for f in files:
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if "queued_command" not in line:
                    continue
                try:
                    raw = json.loads(line)
                except ValueError:
                    continue
                rec = hookshared.queued_prompt(raw)
                if rec is None:
                    continue
                seen += 1
                origin = rec.get("origin")
                kind = str(origin.get("kind") or "") if isinstance(origin, dict) else ""
                mode = str(rec.get("commandMode") or "")
                if kind not in known_origin:
                    unknown.add(f"origin.kind={kind}")
                if mode not in hookshared.QUEUED_MODES:
                    unknown.add(f"commandMode={mode}")
                text = str(rec["message"]["content"])
                if kind == "" and mode == "prompt" and not text.lstrip().startswith(hookshared.NOT_OPERATOR):
                    unknown.add("a prompt with no origin")
                if kind == "peer" and not (hookshared.tool_wrote(rec) or not hookshared.operator_wrote(text)):
                    unknown.add("a peer message the rule reads as the operator's")
    if not seen:
        pytest.skip("no queued message in the newest transcripts")
    assert not unknown, f"queued_command markers the rule does not know: {sorted(unknown)}"
