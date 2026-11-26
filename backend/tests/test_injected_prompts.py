"""Text the operator did not type is never the operator's message.

Every tool hands the agent prompts nobody typed: a scheduled task's, "the
usage limit has reset, continue", a background task's notification, another
session's message, a parent agent's brief to its subagent, a command's
template. Recorded live (the hooks) or read from the tool's log afterwards
(sessionimport.py), none of them is a turn of the operator and no #command
in them acts. The operator's own words, pasted text included, still do.

The records below have the shapes the tools write (Claude Code 2.1.288-
2.1.325, Codex 0.163-0.167, OpenCode 1.19.3); the words are made up. The
probes at the end read the newest transcripts on this machine, when there
are any, and fail when a tool writes a marker these rules do not know.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
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

#: A message with a command of every kind the server keeps or acts on.
TAGS = "Card fixes are due. #publish #vision offline first #done tk_12345678 #now #pin #important"


def _load_capture():
    spec = importlib.util.spec_from_file_location("sp_capture_inj", HOOKS / "capture.py")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(HOOKS))
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    finally:
        sys.path.remove(str(HOOKS))
    return mod


def _utc(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _user(text, **marks) -> dict:
    return {"type": "user", "message": {"role": "user", "content": text}, **marks}


# What Claude Code writes for each kind of prompt (field names and values
# as in the local transcripts; the text is the case's own).
HUMAN = {"turnOrigin": "human", "origin": {"kind": "human"}, "promptSource": "typed"}
CC_INJECTED = {
    "scheduled": {"turnOrigin": "scheduled", "promptSource": "system", "isMeta": True,
                  "wakeupSource": "schedule_wakeup", "scheduledTaskId": "c66fc97c"},
    "cron, older build": {"turnOrigin": "scheduled", "promptSource": "system", "isMeta": True,
                          "scheduledTaskId": "c66fc97c"},
    "usage limit reset": {"turnOrigin": "auto_continuation", "origin": {"kind": "auto-continuation"},
                          "promptSource": "system", "isMeta": True},
    "another session": {"turnOrigin": "peer", "origin": {"kind": "peer", "from": "uds:/run/user/1000/x"},
                        "promptSource": "system", "isMeta": True},
    "task notification": {"turnOrigin": "task_notification", "origin": {"kind": "task-notification"},
                          "promptSource": "system"},
    "task notification, origin only": {"origin": {"kind": "task-notification"}, "promptSource": "system"},
    "coordinator brief, meta": {"origin": {"kind": "coordinator"}, "isMeta": True},
}


def _run_hook(root: Path, payload: dict) -> str:
    proc = subprocess.run([sys.executable, str(CC_HOOK), "--project", "alpha", "--data-root", str(root)],
                          input=json.dumps(payload), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    (tmp_path / "data").mkdir()
    return tmp_path / "data"


# ---------------------------------------------------------------------------
# The one rule
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case", sorted(CC_INJECTED))
def test_the_rule_names_every_prompt_the_tool_wrote(case: str) -> None:
    assert hookshared.tool_wrote(_user(TAGS, **CC_INJECTED[case]))


@pytest.mark.parametrize("marks", [
    HUMAN,
    {**HUMAN, "promptSource": "suggestion_accepted"},
    {**HUMAN, "promptSource": "queued"},
    {"turnOrigin": "sdk", "promptSource": "sdk", "entrypoint": "sdk-cli"},  # claude -p: a helper chat, its rules
    {},  # an older build with no origin at all
    {"turnOrigin": "remote_typed", "promptSource": "typed"},  # an origin not known yet: never dropped on a guess
])
def test_the_rule_leaves_the_operators_prompts(marks: dict) -> None:
    assert not hookshared.tool_wrote(_user(TAGS, **marks))


def test_one_rule_for_the_hook_the_importer_and_the_capture_check() -> None:
    cc = _load_capture()
    spec = importlib.util.spec_from_file_location("sp_cc_inj", CC_HOOK)
    hook = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(HOOKS))
    try:
        spec.loader.exec_module(hook)  # type: ignore[union-attr]
    finally:
        sys.path.remove(str(HOOKS))
    assert hook.is_injected.__name__ == "tool_wrote" and cc.shared.tool_wrote.__name__ == "tool_wrote"
    assert sessionimport.tool_wrote is hookshared.tool_wrote
    assert capturewatch.tool_wrote is hookshared.tool_wrote


# ---------------------------------------------------------------------------
# Claude Code, live: the prompt hook
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case", sorted(CC_INJECTED))
def test_claude_code_a_prompt_the_tool_wrote_is_no_turn(root: Path, tmp_path: Path, case: str) -> None:
    """The prompt's transcript record is written before the hook runs, and
    notes may follow it (a reminder, an attachment: isMeta)."""
    t = tmp_path / "t.jsonl"
    t.write_text("\n".join(json.dumps(r) for r in [
        _user("an earlier message", **HUMAN),
        _user(TAGS, **CC_INJECTED[case]),
        _user("<system-reminder>a note the tool adds</system-reminder>", isMeta=True),
    ]) + "\n", encoding="utf-8")
    out = _run_hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": "inj00001", "prompt": TAGS,
                           "transcript_path": str(t)})
    assert "#publish" not in out and "#vision" not in out
    assert not (root / "projects/alpha/chats/cc-inj00001").exists()


def test_claude_code_the_operators_own_prompt_still_acts(root: Path, tmp_path: Path) -> None:
    """The control: typed, pasted, after a note, and the same words the tool
    once wrote earlier — the latest record with the words is the one read."""
    paste = f'Look at this:\n<pasted_content id="53d3">\n{TAGS}\n</pasted_content>'
    t = tmp_path / "t.jsonl"
    t.write_text("\n".join(json.dumps(r) for r in [
        _user(paste, **CC_INJECTED["scheduled"]),   # the same words, scheduled earlier
        _user("ok", **HUMAN),
        _user(paste, **HUMAN),
        _user("<system-reminder>a note</system-reminder>", isMeta=True),
    ]) + "\n", encoding="utf-8")
    out = _run_hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": "own00001", "prompt": paste,
                           "transcript_path": str(t)})
    assert "#publish" in out
    chat = (root / "projects/alpha/chats/cc-own00001/chat.md").read_text(encoding="utf-8")
    assert "#vision offline first" in chat


def test_claude_code_a_prompt_with_no_record_yet_is_the_operators(root: Path, tmp_path: Path) -> None:
    """No record found (a transcript not written yet, unreadable): kept."""
    t = tmp_path / "t.jsonl"
    t.write_text(json.dumps(_user("something else", **CC_INJECTED["scheduled"])) + "\n", encoding="utf-8")
    _run_hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": "nor00001", "prompt": TAGS,
                     "transcript_path": str(t)})
    _run_hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": "nor00002", "prompt": TAGS,
                     "transcript_path": str(tmp_path / "missing.jsonl")})
    assert (root / "projects/alpha/chats/cc-nor00001/chat.md").exists()
    assert (root / "projects/alpha/chats/cc-nor00002/chat.md").exists()


# ---------------------------------------------------------------------------
# Every adapter: a text under the tool's own prefix reads no command
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    f"<task-notification>\n<summary>done</summary>\n{TAGS}\n</task-notification>",
    f'Another Claude session sent a message: <agent-message from="a1b2">{TAGS}</agent-message>',
    f"<system-reminder>{TAGS}</system-reminder>",
])
def test_every_adapter_reads_no_command_from_the_tools_own_text(root: Path, text: str) -> None:
    """Codex notify, Cursor and OpenCode call open_turn directly, with no
    prefix check of their own; the server ignores such turns too."""
    cap = _load_capture().TurnCapture(root, "alpha", "oc-prefix01")
    signals = cap.open_turn(text)
    assert signals["commands"] == [] and signals["kept"] == []
    # Nor does a task id in it become the task the next #evidence means.
    assert "last_task" not in json.loads(cap.meta_path.read_text(encoding="utf-8"))
    cap.complete_turn("ok")
    st = ViewStore(root)
    st.rebuild()
    for table in ("keep_marks", "important_tags", "done_tags", "now_tags"):
        assert st.query(f"SELECT count(*) AS n FROM {table}")[0]["n"] == 0, table


def test_every_adapter_still_reads_the_operators_commands(root: Path) -> None:
    cap = _load_capture().TurnCapture(root, "alpha", "oc-own00001")
    signals = cap.open_turn(TAGS)
    assert {"done", "now", "pin"} <= set(signals["commands"])
    assert {k["kind"] for k in signals["kept"]} >= {"publish", "vision"}


# ---------------------------------------------------------------------------
# The importer reads the same turns the hook records
# ---------------------------------------------------------------------------

def _space(tmp_path: Path) -> tuple[ViewStore, Path, Path, Path]:
    data, work = tmp_path / "data", tmp_path / "app"
    (data / "projects" / "app").mkdir(parents=True)
    work.mkdir()
    append_row(data / "integrations.csv", ("project", "path", "created_date"),
               {"project": "app", "path": str(work), "created_date": ""})
    return ViewStore(data), work, tmp_path / "claude", tmp_path / "codex"


def test_import_of_a_claude_transcript_keeps_only_the_operators_turns(tmp_path: Path) -> None:
    st, work, claude, codex = _space(tmp_path)
    d = claude / capturewatch.folder_slug(str(work))
    d.mkdir(parents=True)
    at = time.time() - 7200
    recs = [_user("Fix the login timeout.", **HUMAN)]
    for case in sorted(CC_INJECTED):
        recs.append(_user(f"{case}: {TAGS}", **CC_INJECTED[case]))
    recs += [
        _user("[Request interrupted by user]"),
        _user("<bash-input>git status #done</bash-input>"),
        _user("<bash-stdout>clean</bash-stdout><bash-stderr></bash-stderr>", **HUMAN),
        _user("Base directory for this skill: /x\n#task write a task", isMeta=True),
        _user(f'Pasted: <pasted_content id="1">{TAGS}</pasted_content>', **HUMAN),
    ]
    for i, r in enumerate(recs):
        r["timestamp"] = _utc(at + i)
    recs.append({"type": "assistant", "timestamp": _utc(at + 99), "message": {"content": [{"type": "text", "text": "Done."}]}})
    f = d / "cccc3333-0000-4000-8000-000000000003.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    turns = sessionimport.claude_turns(f)
    assert [t["user"][:12] for t in turns] == ["Fix the logi", "Pasted: <pas"]
    assert sessionimport.run(st, "app", "claude", claude_root=claude, codex_root=codex)["imported"]
    st.rebuild()
    # An imported chat's tags are read, never acted on — the pasted one too.
    for table in ("keep_marks", "important_tags", "done_tags", "now_tags", "prompt_marks"):
        assert st.query(f"SELECT count(*) AS n FROM {table}")[0]["n"] == 0, table


def test_import_marks_a_claude_print_and_a_codex_exec_as_helpers(tmp_path: Path) -> None:
    """The hook marks them helpers live; a run read from the log afterwards
    is marked the same, and its prompt (an agent's) is no operator turn of
    the operator's own chats."""
    st, work, claude, codex = _space(tmp_path)
    d = claude / capturewatch.folder_slug(str(work))
    d.mkdir(parents=True)
    at = time.time() - 7200
    (d / "dddd4444-0000-4000-8000-000000000004.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {**_user("Reply with ok #done tk_12345678", turnOrigin="sdk", promptSource="sdk"),
         "entrypoint": "sdk-cli", "timestamp": _utc(at)},
        {"type": "assistant", "timestamp": _utc(at + 3), "message": {"content": [{"type": "text", "text": "ok"}]}},
    ]) + "\n", encoding="utf-8")
    sessionimport.run(st, "app", "claude", claude_root=claude, codex_root=codex)
    meta = json.loads((st.data_root / "projects/app/chats/cc-dddd4444/meta.json").read_text(encoding="utf-8"))
    assert meta["helper"] is True and meta["helper_kind"] == "claude-print"

    x = codex / "2026" / "11" / "06"
    x.mkdir(parents=True)
    sid = "01a1ae57-0000-7000-8000-00000000e0e0"
    (x / f"rollout-2026-11-06T11-52-24-{sid}.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"timestamp": _utc(at - 5), "type": "session_meta",
         "payload": {"id": sid, "cwd": str(work), "source": "exec", "originator": "codex_exec", "thread_source": "user"}},
        {"timestamp": _utc(at), "type": "response_item", "payload": {"type": "message", "role": "user",
         "content": [{"type": "input_text", "text": "Review the plan. #publish"}]}},
        {"timestamp": _utc(at + 3), "type": "response_item", "payload": {"type": "message", "role": "assistant",
         "content": [{"type": "output_text", "text": "Reviewed."}]}},
    ]) + "\n", encoding="utf-8")
    sessionimport.run(st, "app", "codex", claude_root=claude, codex_root=codex)
    meta = json.loads((st.data_root / "projects/app/chats/codex-0000e0e0/meta.json").read_text(encoding="utf-8"))
    assert meta["helper"] is True and meta["helper_kind"] == "codex-exec"


def test_import_of_a_codex_rollout_reads_no_subagent_report_as_a_turn(tmp_path: Path) -> None:
    """A Codex subagent's report reaches its parent as an agent_message, not
    a user message: neither path makes a turn of it."""
    st, work, claude, codex = _space(tmp_path)
    x = codex / "2026" / "11" / "06"
    x.mkdir(parents=True)
    sid = "01a1ae2c-0000-7000-8000-00000000f0f0"
    at = time.time() - 7200
    f = x / f"rollout-2026-11-06T11-50-00-{sid}.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in [
        {"timestamp": _utc(at - 5), "type": "session_meta",
         "payload": {"id": sid, "cwd": str(work), "source": "vscode", "originator": "codex-tui", "thread_source": "user"}},
        {"timestamp": _utc(at), "type": "response_item", "payload": {"type": "message", "role": "user",
         "content": [{"type": "input_text", "text": "Start three reviewers."}]}},
        {"timestamp": _utc(at + 1), "type": "inter_agent_communication_metadata", "payload": {"trigger_turn": False}},
        {"timestamp": _utc(at + 2), "type": "response_item", "payload": {
            "type": "agent_message", "author": "/root/review_math", "recipient": "/root",
            "content": [{"type": "input_text", "text": f"Message Type: FINAL_ANSWER\nSender: /root/review_math\n{TAGS}"}]}},
        {"timestamp": _utc(at + 3), "type": "response_item", "payload": {"type": "message", "role": "assistant",
         "content": [{"type": "output_text", "text": "All three reported."}]}},
    ]) + "\n", encoding="utf-8")
    assert [t["user"] for t in sessionimport.codex_turns(f)] == ["Start three reviewers."]


# ---------------------------------------------------------------------------
# OpenCode: the plugin, driven by node with a stand-in for OpenCode
# ---------------------------------------------------------------------------

_DRIVER = r"""
import { pathToFileURL } from 'node:url'
const [plugin, sessionsJson] = process.argv.slice(2)
const sessions = JSON.parse(sessionsJson)
const calls = []
const $ = (strings, ...values) => ({
  quiet: async () => {
    // The flag written before each value: --phase ${phase}, --agent ${agent}.
    const flags = {}
    values.forEach((v, i) => { flags[strings[i].trim().split(/\s+/).pop()] = v })
    const stdin = values[values.length - 1]
    calls.push({ phase: flags['--phase'], agent: flags['--agent'], input: JSON.parse(await stdin.text()) })
    return { text: () => '' }
  },
})
const client = { session: {
  get: async ({ path }) => ({ data: sessions[path.id] || { id: path.id } }),
  messages: async () => ({ data: [] }),
  children: async () => ({ data: [] }),
} }
const mod = await import(pathToFileURL(plugin).href)
const hooks = await mod.SlightlyParallelCapture({ client, directory: '/tmp/x', $ })
const part = (text) => ({ id: 'prt_1', type: 'text', text })
// The operator types in the main session.
await hooks['chat.message']({ sessionID: 'ses_main0000OPERATOR1' }, { message: { id: 'msg_1' }, parts: [part('#vision offline first')] })
// The task tool briefs a subagent in a child session.
await hooks['chat.message']({ sessionID: 'ses_child000SUBAGENT1' }, { message: { id: 'msg_2' }, parts: [part('Review it. #publish #done tk_12345678')] })
// A custom command: OpenCode fills in its template as the message's text.
await hooks['command.execute.before']({ command: 'review', sessionID: 'ses_main0000OPERATOR1', arguments: 'the login page' }, { parts: [] })
await hooks['chat.message']({ sessionID: 'ses_main0000OPERATOR1' }, { message: { id: 'msg_3' }, parts: [part('Template body. #publish #pin\nthe login page')] })
// The next message is the operator's own again.
await hooks['chat.message']({ sessionID: 'ses_main0000OPERATOR1' }, { message: { id: 'msg_4' }, parts: [part('thanks #pin')] })
console.log(JSON.stringify(calls))
"""


def test_opencode_a_subagent_is_a_helper_and_a_command_is_what_was_typed(tmp_path: Path) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    plugin = tmp_path / "plugin.mjs"
    plugin.write_text((HOOKS / "slightly-parallel-opencode.js").read_text(encoding="utf-8"), encoding="utf-8")
    driver = tmp_path / "driver.mjs"
    driver.write_text(_DRIVER, encoding="utf-8")
    sessions = {"ses_child000SUBAGENT1": {"id": "ses_child000SUBAGENT1", "parentID": "ses_main0000OPERATOR1"}}
    proc = subprocess.run([node, str(driver), str(plugin), json.dumps(sessions)], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    calls = json.loads(proc.stdout.strip().splitlines()[-1])
    assert [(c["phase"], c["agent"]) for c in calls] == [("open", "oc-perator1")] * 1 + [("open", "oc-ubagent1")] + [("open", "oc-perator1")] * 2
    own, child, command, after = (c["input"] for c in calls)
    assert own == {"text": "#vision offline first"}
    assert child["helper"] == "opencode-subagent" and child["helper_of"] == "oc-perator1"
    assert command == {"text": "/review the login page"}
    assert after == {"text": "thanks #pin"}


@pytest.mark.parametrize("idle", ["session.idle", "session.status", "session.status,session.idle", "missing"])
def test_opencode_run_awaits_pending_reply_capture_on_dispose(tmp_path: Path, idle: str) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    plugin = tmp_path / "plugin.mjs"
    plugin.write_text((HOOKS / "slightly-parallel-opencode.js").read_text(encoding="utf-8"), encoding="utf-8")
    driver = tmp_path / "helper.mjs"
    driver.write_text(r"""
import { pathToFileURL } from 'node:url'
const [, , plugin, idle] = process.argv
process.argv[2] = 'run'
const calls = []
const sid = 'ses_example1234abcd'
const part = (text) => ({ id: 'prt_1', type: 'text', text })
const { SlightlyParallelCapture } = await import(pathToFileURL(plugin).href)
const hooks = await SlightlyParallelCapture({
  client: { session: {
    messages: async () => ({ data: [
      { info: { role: 'user', id: 'prompt' }, parts: [part('Read this')] },
      { info: { role: 'assistant', id: 'reply' }, parts: [part('The final reply')] },
    ] }),
    children: async () => ({ data: [] }),
  } },
  directory: '/tmp/sample',
  $: (strings, ...values) => ({ quiet: async () => {
    const input = JSON.parse(await values.at(-1).text())
    await new Promise(resolve => setTimeout(resolve, 25))
    calls.push({ phase: values[2], text: input.text, helper: input.helper })
    return { text: () => '' }
  } }),
})
await hooks['chat.message']({ sessionID: sid }, { message: { id: 'prompt' }, parts: [part('Read this')] })
// OpenCode's bus invokes this without awaiting capture. Shutdown can also
// start before the plugin receives the idle event.
for (const type of idle.split(',')) {
  if (type !== 'missing') void hooks.event({ event: { type, properties: { sessionID: sid, status: { type: 'idle' } } } })
}
await hooks.dispose?.()
console.log(JSON.stringify(calls))
process.exit(0)
""", encoding="utf-8")
    proc = subprocess.run([node, str(driver), str(plugin), idle], capture_output=True, text=True, timeout=20)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == [
        {"phase": "open", "text": "Read this", "helper": "opencode-run"},
        {"phase": "complete", "text": "The final reply", "helper": "opencode-run"},
    ]


def test_opencode_a_subagent_chat_is_marked_through_the_cli_adapter(root: Path, tmp_path: Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(HOOKS / "capture-cli.py"), "--phase", "open", "--project", "alpha", "--data-root", str(root),
         "--agent", "oc-ubagent1", "--json-stdin", "--tool", "opencode", "--session", "ses_child000SUBAGENT1",
         "--cwd", str(tmp_path)],
        input=json.dumps({"text": "Review it. #publish", "helper": "opencode-subagent", "helper_of": "oc-perator1"}),
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "#publish" not in proc.stdout
    meta = json.loads((root / "projects/alpha/chats/oc-ubagent1/meta.json").read_text(encoding="utf-8"))
    assert meta["helper"] is True and meta["helper_kind"] == "opencode-subagent"
    assert meta["helper_of"] == "oc-perator1" and meta["helper_of_by"] == "session"


# ---------------------------------------------------------------------------
# Probes: the newest transcripts on this machine still carry the markers
# ---------------------------------------------------------------------------

def _newest(paths: list[Path]) -> Path | None:
    live = [p for p in paths if p.is_file()]
    return max(live, key=lambda p: p.stat().st_mtime) if live else None


def test_probe_claude_codes_newest_transcript_carries_the_known_markers() -> None:
    """Fails when Claude Code writes a prompt origin or source the rule does
    not know — read tool_wrote again and add it to the right list — or when
    the operator's typed prompts stop saying "human": the hook would then
    read nothing and keep every prompt, scheduled ones included."""
    base = Path.home() / ".claude" / "projects"
    newest = _newest(list(base.glob("*/*.jsonl"))) if base.is_dir() else None
    if newest is None:
        pytest.skip("no Claude Code transcript on this machine")
    known_origin = hookshared.OPERATOR_ORIGINS | hookshared.TOOL_ORIGINS | hookshared.SUBAGENT_ORIGINS | {""}
    known_source = hookshared.OPERATOR_SOURCES | {"system", ""}
    unknown, typed_not_human, typed = set(), 0, 0
    with open(newest, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if '"user"' not in line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict) or not hookshared.is_human_prompt(rec) or rec.get("isSidechain"):
                continue
            origin = rec.get("origin")
            for field, value, known in (("turnOrigin", str(rec.get("turnOrigin") or ""), known_origin),
                                        ("origin.kind", str(origin.get("kind") or "") if isinstance(origin, dict) else "", known_origin),
                                        ("promptSource", str(rec.get("promptSource") or ""), known_source)):
                if value not in known:
                    unknown.add(f"{field}={value}")
            if rec.get("promptSource") == "typed":
                typed += 1
                typed_not_human += rec.get("turnOrigin") != "human"
    assert not unknown, f"{newest.name}: markers the rule does not know: {sorted(unknown)}"
    assert typed_not_human == 0, f"{newest.name}: {typed_not_human} of {typed} typed prompts do not say turnOrigin human"


def test_probe_codexs_newest_rollout_keeps_reports_out_of_user_messages() -> None:
    """The importer reads Codex's user messages (type message, role user);
    a subagent's report comes as an agent_message. Fails when a report
    shape starts arriving as a user message, or the first line stops
    naming an exec run or a subagent the way codex_helper_kind reads."""
    base = hookshared.codex_home() / "sessions"
    newest = _newest(list(base.glob("*/*/*/rollout-*.jsonl"))) if base.is_dir() else None
    if newest is None:
        pytest.skip("no Codex rollout on this machine")
    first = hookshared.codex_session_meta(newest)
    assert first is not None, f"{newest.name}: the first line is no session_meta"
    pl = first.get("payload") or {}
    if pl.get("source") == "exec" or isinstance(pl.get("source"), dict):
        assert hookshared.codex_helper_kind(first)[0], f"{newest.name}: a helper run the first line no longer names"
    leaked = 0
    with open(newest, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            p = rec.get("payload") if isinstance(rec, dict) else None
            if isinstance(p, dict) and p.get("type") == "message" and p.get("role") == "user":
                text = " ".join(str(c.get("text") or "") for c in p.get("content") or [] if isinstance(c, dict))
                leaked += text.lstrip().startswith("Message Type:")
    assert leaked == 0, f"{newest.name}: {leaked} subagent reports arrive as user messages"


def test_probe_opencode_still_keeps_a_subagents_parent() -> None:
    """The plugin tells a subagent's session by its parentID. Fails when
    OpenCode's store stops keeping one."""
    db = Path.home() / ".local" / "share" / "opencode" / "opencode.db"
    if not db.is_file():
        pytest.skip("no OpenCode store on this machine")
    import sqlite3
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2)
        cols = {r[1] for r in con.execute("PRAGMA table_info(session)")}
        con.close()
    except sqlite3.Error as exc:
        pytest.skip(f"OpenCode's store cannot be read: {exc}")
    assert "parent_id" in cols, "OpenCode's sessions no longer keep their parent"
