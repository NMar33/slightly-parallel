"""Helper chats: a run another program started (codex exec, claude -p,
opencode run, a Codex subagent). The hooks mark it in meta.json from what
the tool writes (recorded first lines of real session files, account ids
scrubbed, in fixtures/helpers/), with the chat that started it when the
environment names it. Its messages are recorded; no command in them acts.
The operator's own chats are unchanged: a tag anywhere in the message acts,
pasted text included."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from backend import hookshared, keeplib
from backend.db import ViewStore
from tests.conftest import make_chat

HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"
FIX = Path(__file__).resolve().parent / "fixtures" / "helpers"
PARENT_CLAUDE = "ca77654e-a6ba-48c9-8221-caaa2475a406"


def _first(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8").splitlines()[0])


# ---------------------------------------------------------------------------
# The signals, from recorded lines
# ---------------------------------------------------------------------------


def test_codex_first_lines_name_exec_subagent_and_interactive_runs() -> None:
    assert hookshared.codex_helper_kind(_first("codex-exec.jsonl")) == ("codex-exec", "")
    kind, parent = hookshared.codex_helper_kind(_first("codex-subagent.jsonl"))
    assert kind == "codex-subagent" and parent == "01a1ae2c-b888-7193-987d-757c1266687f"
    # Codex's guardian reviewer: no thread_spawn, the parent beside it.
    kind, parent = hookshared.codex_helper_kind(_first("codex-guardian.jsonl"))
    assert kind == "codex-subagent" and parent == "01a18ee9-c2a8-7512-afda-d4773bc512ce"
    assert hookshared.codex_helper_kind(_first("codex-interactive.jsonl")) == ("", "")
    # The payload alone, and lines that are no session_meta.
    assert hookshared.codex_helper_kind(_first("codex-exec.jsonl")["payload"])[0] == "codex-exec"
    for junk in (None, [], "exec", {"type": "turn_context", "payload": {"source": "exec"}}, {"source": {"subagent": 5}}):
        assert hookshared.codex_helper_kind(junk)[0] in ("", "codex-subagent")
    assert hookshared.codex_helper_kind({"source": {"subagent": 5}}) == ("codex-subagent", "")


def test_codex_session_meta_reads_the_first_line_only(tmp_path: Path) -> None:
    f = tmp_path / "rollout-2026-11-01T23-59-28-01a19731-8780-7dc2-bb2f-546a563aaee9.jsonl"
    f.write_text((FIX / "codex-exec.jsonl").read_text(encoding="utf-8") + '{"type":"turn_context"}\n', encoding="utf-8")
    assert hookshared.codex_session_meta(f)["payload"]["source"] == "exec"
    (tmp_path / "bad.jsonl").write_text("not json\n", encoding="utf-8")
    assert hookshared.codex_session_meta(tmp_path / "bad.jsonl") is None
    assert hookshared.codex_session_meta(tmp_path / "missing.jsonl") is None


def test_claude_print_is_named_by_its_entrypoint() -> None:
    assert hookshared.claude_entrypoint(FIX / "claude-print.jsonl") == "sdk-cli"
    assert hookshared.claude_helper_kind("sdk-cli") == "claude-print"
    assert hookshared.claude_helper_kind("sdk-ts") == "claude-print"
    for interactive in ("cli", "claude-vscode", "", None):
        assert hookshared.claude_helper_kind(interactive) == ""
    assert hookshared.claude_entrypoint(FIX / "missing.jsonl") == ""


def test_opencode_run_is_named_by_its_argv() -> None:
    fx = json.loads((FIX / "opencode-run.json").read_text(encoding="utf-8"))
    assert fx["argv"][2] == "run"
    src = (HOOKS / "slightly-parallel-opencode.js").read_text(encoding="utf-8")
    assert "process.argv[2] === 'run'" in src and "'opencode-run'" in src
    assert "opencode-run" in hookshared.HELPER_KINDS


# ---------------------------------------------------------------------------
# The parent, from the environment the helper inherited
# ---------------------------------------------------------------------------


def test_the_parent_comes_from_the_variables_its_tool_set() -> None:
    # codex exec started by a Claude Code chat (seen in the hook's own environment).
    env = {"CLAUDE_CODE_SESSION_ID": PARENT_CLAUDE, "CLAUDE_PID": "1", "CLAUDE_EFFORT": "medium"}
    assert hookshared.helper_parent("codex", "01a1c7d7-a31d-71d2-9d1e-3f9935e20b38", env) == "cc-ca77654e"
    # codex exec started by a Codex chat: Codex gives its shell commands CODEX_THREAD_ID.
    env = {"CODEX_THREAD_ID": "01a1c7d9-feb1-7a02-9e8e-748adb87e8e7"}
    assert hookshared.helper_parent("codex", "01a1c7d7-a31d-71d2-9d1e-3f9935e20b38", env) == "codex-db87e8e7"
    # A variable that names the helper itself is no parent.
    assert hookshared.helper_parent("codex", "01a1c7d9-feb1-7a02-9e8e-748adb87e8e7", env) == ""
    own = {"CLAUDE_CODE_SESSION_ID": "aa3e9edd-a2bd-4ecb-92c3-eebd003f59c6"}
    assert hookshared.helper_parent("claude-code", "aa3e9edd-a2bd-4ecb-92c3-eebd003f59c6", own) == ""
    assert hookshared.helper_parent("codex", "x", {}) == ""


def test_two_candidates_go_to_the_one_started_last_or_to_none() -> None:
    me = os.getpid()
    started = hookshared.process_started(me)
    if started is None:
        pytest.skip("this system does not say when a process started")
    # A Codex thread made before this process vs. the Claude Code process (this one):
    # the Claude Code chat started later, so it is the nearer.
    old_thread = "01000000-0000-7000-8000-00000000c0de"   # UUIDv7 time: 1970 + a bit
    env = {"CODEX_THREAD_ID": old_thread, "CLAUDE_CODE_SESSION_ID": PARENT_CLAUDE, "CLAUDE_PID": str(me)}
    assert hookshared.helper_parent("opencode", "ses_x", env) == "cc-ca77654e"
    # A thread made after it (its id's time is now + an hour): the Codex chat is nearer.
    later = format(int((time.time() + 3600) * 1000), "012x")
    new_thread = f"{later[:8]}-{later[8:12]}-7000-8000-00000000beef"
    env["CODEX_THREAD_ID"] = new_thread
    assert hookshared.helper_parent("opencode", "ses_x", env) == "codex-0000beef"
    # One time unknown (no CLAUDE_PID): never a guess.
    del env["CLAUDE_PID"]
    assert hookshared.helper_parent("opencode", "ses_x", env) == ""


def _crumb(root: Path, name: str, agent: str, pid: int, started: float | None) -> None:
    d = root / ".sessions" / "digest"
    d.mkdir(parents=True, exist_ok=True)
    body = {"agent_id": agent, "session_id": name, "at": time.time()}
    if started is not None:
        body.update(tool_pid=pid, tool_started=started)
    (d / f"{name}.json").write_text(json.dumps(body), encoding="utf-8")


def test_a_nested_claude_print_finds_its_parent_by_process(tmp_path: Path) -> None:
    """claude -p sets CLAUDE_CODE_SESSION_ID to its own session: the parent
    Claude Code is found among the hook's ancestors, by the process its own
    breadcrumb names, and only if that process started when the crumb says."""
    me = os.getpid()
    started = hookshared.process_started(me)
    if started is None:
        pytest.skip("this system does not say when a process started")
    root = tmp_path / "data"
    env = {"CLAUDE_CODE_SESSION_ID": "aa3e9edd-a2bd-4ecb-92c3-eebd003f59c6", "CLAUDE_PID": "999999"}
    _crumb(root, "parent", "cc-ca77654e", me, started)
    assert hookshared.helper_parent("claude-code", "aa3e9edd-a2bd", env, root, pids=[123, me, 1]) == "cc-ca77654e"
    # The nearest wins: another chat further up does not.
    parent = os.getppid()
    p_started = hookshared.process_started(parent)
    if p_started is not None:
        _crumb(root, "grand", "cc-11111111", parent, p_started)
        assert hookshared.helper_parent("claude-code", "aa3e9edd-a2bd", env, root, pids=[me, parent]) == "cc-ca77654e"
    # A number used again by another process: the start time differs, no match.
    _crumb(root, "parent", "cc-ca77654e", me, started - 3600)
    assert hookshared.helper_parent("claude-code", "aa3e9edd-a2bd", env, root, pids=[me]) == ""
    # Two chats claim the process (a resumed session): unknown.
    _crumb(root, "parent", "cc-ca77654e", me, started)
    _crumb(root, "twin", "cc-22222222", me, started)
    assert hookshared.helper_parent("claude-code", "aa3e9edd-a2bd", env, root, pids=[me]) == ""
    # Its own process is never its parent.
    env["CLAUDE_PID"] = str(me)
    assert hookshared.helper_parent("claude-code", "aa3e9edd-a2bd", env, root, pids=[me]) == ""


# ---------------------------------------------------------------------------
# The hooks: the chat is marked, its commands do not act
# ---------------------------------------------------------------------------

HELPER_PROMPT = (
    "You are a critic. Review the draft below.\n#entrypoint the install film\n"
    "#now fix it #done tk_12345678 #vision offline #usage-off"
)


def _env(**more: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("CLAUDE", "CODEX_THREAD", "CODEX_SESSION", "OPENCODE"))}
    env.update(more)
    return env


def _hook(script: str, args: list[str], payload: dict | None, env: dict[str, str]) -> subprocess.CompletedProcess:
    proc = subprocess.run([sys.executable, str(HOOKS / script), *args],
                          input=json.dumps(payload) if payload is not None else "",
                          capture_output=True, text=True, env=env, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return proc


def _meta(root: Path, project: str, agent: str) -> dict:
    return json.loads((root / "projects" / project / "chats" / agent / "meta.json").read_text(encoding="utf-8"))


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    (tmp_path / "data").mkdir()
    return tmp_path / "data"


def test_a_claude_print_chat_is_marked_and_its_commands_do_not_act(root: Path, tmp_path: Path) -> None:
    env = _env(CLAUDE_CODE_ENTRYPOINT="sdk-cli", CLAUDE_CODE_SESSION_ID="bbbb2222-0000-4000-8000-000000000002")
    args = ["--project", "alpha", "--data-root", str(root)]
    sid = "bbbb2222-0000-4000-8000-000000000002"
    out = _hook("claude-code-capture.py", args, {"hook_event_name": "UserPromptSubmit", "session_id": sid,
                                                  "cwd": str(tmp_path), "prompt": HELPER_PROMPT}, env)
    # No notice for a command, no kept id, no usage answer (a #usage alone would block the prompt).
    assert "#entrypoint" not in out.stdout and "#now" not in out.stdout and "ep_" not in out.stdout
    assert '"decision"' not in out.stdout
    _hook("claude-code-capture.py", args, {"hook_event_name": "Stop", "session_id": sid,
                                            "last_assistant_message": "Reviewed."}, env)
    meta = _meta(root, "alpha", "cc-bbbb2222")
    assert meta["helper"] is True and meta["helper_kind"] == "claude-print" and meta["helper_of"] == ""
    assert "usage_show" not in meta          # #usage-off did not act
    chat = (root / "projects/alpha/chats/cc-bbbb2222/chat.md").read_text(encoding="utf-8")
    assert "#entrypoint the install film" in chat and "Reviewed." in chat   # recorded whole
    # A #usage alone in a helper is recorded as a message, not answered by the hook.
    out = _hook("claude-code-capture.py", args, {"hook_event_name": "UserPromptSubmit", "session_id": sid,
                                                  "cwd": str(tmp_path), "prompt": "#usage"}, env)
    assert '"decision"' not in out.stdout
    # The server keeps nothing from it.
    store = ViewStore(data_root=root)
    store.rebuild()
    for table in ("keep_marks", "important_tags", "done_tags", "now_tags", "prompt_marks"):
        assert store.query(f"SELECT count(*) AS n FROM {table}")[0]["n"] == 0, table
    assert keeplib.adopt(store) == []
    assert store.query("SELECT count(*) AS n FROM sessions WHERE agent_id = 'cc-bbbb2222'")[0]["n"] == 1


def test_the_operators_pasted_text_still_acts(root: Path, tmp_path: Path) -> None:
    """The same text pasted by the operator into an interactive chat: every
    tag in it acts, as before (the operator's decision; ### silences)."""
    env = _env(CLAUDE_CODE_ENTRYPOINT="cli")
    sid = "cccc3333-0000-4000-8000-000000000003"
    pasted = f"look at this:\n<pasted_content id=\"a1\">\n{HELPER_PROMPT}\n</pasted_content>"
    out = _hook("claude-code-capture.py", ["--project", "alpha", "--data-root", str(root)],
                {"hook_event_name": "UserPromptSubmit", "session_id": sid, "cwd": str(tmp_path), "prompt": pasted}, env)
    assert "#now" in out.stdout and "ep_" in out.stdout
    assert "helper" not in _meta(root, "alpha", "cc-cccc3333")
    store = ViewStore(data_root=root)
    store.rebuild()
    assert store.query("SELECT count(*) AS n FROM keep_marks WHERE agent_id = 'cc-cccc3333'")[0]["n"] >= 2


def test_a_codex_exec_under_a_claude_chat_names_that_chat(root: Path, tmp_path: Path) -> None:
    rollout = tmp_path / "rollout-2026-11-01T23-59-28-01a19731-8780-7dc2-bb2f-546a563aaee9.jsonl"
    rollout.write_text((FIX / "codex-exec.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
    env = _env(CLAUDE_CODE_SESSION_ID=PARENT_CLAUDE, CLAUDE_PID="1", CLAUDE_EFFORT="medium",
               CLAUDE_CODE_ENTRYPOINT="cli")
    sid = "01a19731-8780-7dc2-bb2f-546a563aaee9"
    _hook("claude-code-capture.py", ["--project", "alpha", "--data-root", str(root), "--tool", "codex"],
          {"hook_event_name": "UserPromptSubmit", "session_id": sid, "cwd": str(tmp_path),
           "transcript_path": str(rollout), "turn_id": "t1", "prompt": HELPER_PROMPT}, env)
    meta = _meta(root, "alpha", f"codex-{hookshared.session_key('codex', sid)}")
    assert meta["helper"] is True and meta["helper_kind"] == "codex-exec"
    assert meta["helper_of"] == "cc-ca77654e" and meta["helper_of_by"] == "env"
    # Codex's breadcrumb never records the Claude Code process it runs under as its own.
    crumbs = [json.loads(p.read_text(encoding="utf-8")) for p in (root / ".sessions").glob("*/*.json")]
    assert crumbs and all("tool_pid" not in c for c in crumbs)


def test_a_codex_subagent_names_its_parent_thread(root: Path, tmp_path: Path) -> None:
    rollout = tmp_path / "rollout-2026-11-06T15-21-39-01a1af17-423a-77a1-b4c2-509b9e485414.jsonl"
    rollout.write_text((FIX / "codex-subagent.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
    sid = "01a1af17-423a-77a1-b4c2-509b9e485414"
    _hook("claude-code-capture.py", ["--project", "alpha", "--data-root", str(root), "--tool", "codex"],
          {"hook_event_name": "UserPromptSubmit", "session_id": sid, "cwd": str(tmp_path),
           "transcript_path": str(rollout), "prompt": "look at the storage"}, _env())
    meta = _meta(root, "alpha", f"codex-{hookshared.session_key('codex', sid)}")
    assert meta["helper_kind"] == "codex-subagent" and meta["helper_of"] == "codex-1266687f"
    assert meta["helper_of_by"] == "session"


def test_codex_notify_marks_an_exec_run_found_by_its_thread(root: Path, tmp_path: Path) -> None:
    home = tmp_path / "codexhome"
    day = home / "sessions" / "2026" / "11" / "01"
    day.mkdir(parents=True)
    sid = "01a19731-8780-7dc2-bb2f-546a563aaee9"
    (day / f"rollout-2026-11-01T23-59-28-{sid}.jsonl").write_text(
        (FIX / "codex-exec.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
    proj = tmp_path / "app"
    proj.mkdir()
    (root / "integrations.csv").write_text(f"project,path,created_date\napp,{proj},2611-01\n", encoding="utf-8")
    env = _env(CODEX_HOME=str(home), CODEX_THREAD_ID="01a1c7d9-feb1-7a02-9e8e-748adb87e8e7")
    event = {"type": "agent-turn-complete", "thread-id": sid, "turn-id": "t1", "cwd": str(proj),
             "input-messages": [HELPER_PROMPT], "last-assistant-message": "ok"}
    subprocess.run([sys.executable, str(HOOKS / "codex-capture.py"), "--data-root", str(root), json.dumps(event)],
                   check=True, env=env, capture_output=True)
    meta = _meta(root, "app", f"codex-{hookshared.session_key('codex', sid)}")
    assert meta["helper_kind"] == "codex-exec" and meta["helper_of"] == "codex-db87e8e7"


def test_an_opencode_run_is_marked_through_the_cli_adapter(root: Path, tmp_path: Path) -> None:
    env = _env(CLAUDE_CODE_SESSION_ID=PARENT_CLAUDE, OPENCODE="1")
    args = ["--phase", "open", "--project", "alpha", "--data-root", str(root), "--agent", "oc-qzuy1aol",
            "--json-stdin", "--tool", "opencode", "--session", "ses_e38248c5effeQzUy1aOldkFUcq", "--cwd", str(tmp_path)]
    proc = subprocess.run([sys.executable, str(HOOKS / "capture-cli.py"), *args],
                          input=json.dumps({"text": HELPER_PROMPT, "helper": "opencode-run"}),
                          capture_output=True, text=True, env=env, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    assert "ep_" not in proc.stdout and "#now" not in proc.stdout
    meta = _meta(root, "alpha", "oc-qzuy1aol")
    assert meta["helper_kind"] == "opencode-run" and meta["helper_of"] == "cc-ca77654e"
    # A helper kind the plugin does not send is not taken.
    proc = subprocess.run([sys.executable, str(HOOKS / "capture-cli.py"), *args[:7], "oc-other001", *args[8:]],
                          input=json.dumps({"text": "hi", "helper": "anything"}),
                          capture_output=True, text=True, env=env, encoding="utf-8")
    assert "helper" not in _meta(root, "alpha", "oc-other001")


def test_a_helper_stays_one_and_a_later_parent_fills_an_empty_one(root: Path) -> None:
    sys.path.insert(0, str(HOOKS))
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("capture_helpers_t", HOOKS / "capture.py")
        cap_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cap_mod)  # type: ignore[union-attr]
    finally:
        sys.path.remove(str(HOOKS))
    cap = cap_mod.TurnCapture(root, "alpha", "cc-dddd4444")
    cap.open_turn("hello")
    cap.note_origin("claude-code", "dddd4444", "/x", helper_kind="claude-print")
    assert _meta(root, "alpha", "cc-dddd4444")["helper_of"] == ""
    cap.note_origin(helper_kind="claude-print", helper_of="cc-ca77654e", helper_of_by="env")
    cap.note_origin(helper_kind="claude-print", helper_of="cc-99999999", helper_of_by="env")
    cap.note_origin()          # no signal on a later prompt: nothing cleared
    meta = _meta(root, "alpha", "cc-dddd4444")
    assert meta["helper"] is True and meta["helper_of"] == "cc-ca77654e"
    # A chat never names itself.
    cap2 = cap_mod.TurnCapture(root, "alpha", "cc-eeee5555")
    cap2.open_turn("x")
    cap2.note_origin(helper_kind="claude-print", helper_of="cc-eeee5555")
    assert _meta(root, "alpha", "cc-eeee5555")["helper_of"] == ""


def test_an_agent_in_a_helper_chat_gets_no_command_from_its_prompt(data_root: Path) -> None:
    """The task route reads the operator's last command from the chat (a #now
    makes the card 'doing'): in a helper chat its prompt is no operator's."""
    from backend import tasklib, undolib
    make_chat(data_root, "ALPHA", "codex-0000beef", [("2026-09-01T10:00:00", "#now-todo {ui} build it", "ok")])
    meta_path = data_root / "projects/ALPHA/chats/codex-0000beef/meta.json"
    store = ViewStore(data_root=data_root)
    store.rebuild()
    assert tasklib._operator_command(store, "codex-0000beef")[0] == "now"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.update(helper=True, helper_kind="codex-exec", helper_of="")
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    store.rebuild()
    assert tasklib._operator_command(store, "codex-0000beef") == ("", "", "", "")
    assert undolib._turns(store, "codex-0000beef") == []


# ---------------------------------------------------------------------------
# The backfill: chats recorded before the hooks marked helpers
# ---------------------------------------------------------------------------


def _chat(root: Path, project: str, agent: str, tool: str, ref: str, turns: list[tuple[str, str]],
          cwd: str = "/work/app", **meta: object) -> Path:
    make_chat(root, project, agent, [(at, user, "ok") for at, user in turns])
    folder = root / "projects" / project / "chats" / agent
    m = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    m.update(tool=tool, session_ref=ref, cwd=cwd, **meta)
    (folder / "meta.json").write_text(json.dumps(m), encoding="utf-8")
    return folder


def _rollout(codex: Path, sid: str, fixture: str) -> None:
    d = codex / "sessions" / "2026" / "11" / "01"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"rollout-2026-11-01T10-00-00-{sid}.jsonl").write_text(
        (FIX / fixture).read_text(encoding="utf-8"), encoding="utf-8")


def test_the_backfill_marks_old_helpers_from_the_tools_logs(tmp_path: Path) -> None:
    from backend import helperbackfill
    root, claude, codex = tmp_path / "data", tmp_path / "claude", tmp_path / "codex"
    # Two Claude Code chats: A works 10:00-10:20, B 11:00-11:10; C overlaps B at 11:05.
    a = _chat(root, "app", "cc-aaaa1111", "claude-code", "aaaa1111-0", [("2026-11-01T10:00:00", "plan")])
    _chat(root, "app", "cc-bbbb2222", "claude-code", "bbbb2222-0", [("2026-11-01T11:00:00", "write")])
    _chat(root, "app", "cc-cccc3333", "claude-code", "cccc3333-0", [("2026-11-01T11:04:00", "review")])
    # A codex exec inside A's turn: one chat was in a turn, it is the parent.
    e1 = "01a19731-8780-7dc2-bb2f-000000000001"
    _rollout(codex, e1, "codex-exec.jsonl")
    _chat(root, "app", f"codex-{hookshared.session_key('codex', e1)}", "codex", e1, [("2026-11-01T10:05:00", "#entrypoint critic")])
    # One inside both B's and C's turns: never a guess.
    e2 = "01a19731-8780-7dc2-bb2f-000000000002"
    _rollout(codex, e2, "codex-exec.jsonl")
    _chat(root, "app", f"codex-{hookshared.session_key('codex', e2)}", "codex", e2, [("2026-11-01T11:05:00", "critic")])
    # A subagent names its parent; an interactive Codex chat is no helper.
    sub = "01a1af17-423a-77a1-b4c2-509b9e485414"
    _rollout(codex, sub, "codex-subagent.jsonl")
    _chat(root, "app", f"codex-{hookshared.session_key('codex', sub)}", "codex", sub, [("2026-11-01T12:00:00", "x")])
    inter = "01a18ee9-c2a8-7512-afda-d4773bc512ce"
    _rollout(codex, inter, "codex-interactive.jsonl")
    _chat(root, "app", f"codex-{hookshared.session_key('codex', inter)}", "codex", inter, [("2026-11-01T13:00:00", "y")])
    # A claude -p whose transcript says sdk-cli, at 10:10 (A's turn); a chat with no log.
    slug = claude / "-work-app"
    slug.mkdir(parents=True)
    (slug / "dddd4444-0.jsonl").write_text((FIX / "claude-print.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
    _chat(root, "app", "cc-dddd4444", "claude-code", "dddd4444-0", [("2026-11-01T10:10:00", "draft")])
    _chat(root, "app", "oc-eeee5555", "opencode", "ses_e", [("2026-11-01T10:11:00", "z")])
    assert a.is_dir()

    got = helperbackfill.backfill(root, claude_root=claude, codex_dir=codex)
    assert got == {"helper": 4, "not a helper": 1, "no log": 4, "parent": 3}, got
    meta = lambda agent: _meta(root, "app", agent)  # noqa: E731
    m1 = meta(f"codex-{hookshared.session_key('codex', e1)}")
    assert (m1["helper_kind"], m1["helper_of"], m1["helper_of_by"]) == ("codex-exec", "cc-aaaa1111", "time")
    m2 = meta(f"codex-{hookshared.session_key('codex', e2)}")
    assert m2["helper"] is True and m2["helper_of"] == "" and "helper_of_by" not in m2
    ms = meta(f"codex-{hookshared.session_key('codex', sub)}")
    assert (ms["helper_kind"], ms["helper_of"], ms["helper_of_by"]) == ("codex-subagent", "codex-1266687f", "session")
    assert "helper" not in meta(f"codex-{hookshared.session_key('codex', inter)}")
    assert meta("cc-dddd4444")["helper_kind"] == "claude-print" and meta("cc-dddd4444")["helper_of"] == "cc-aaaa1111"
    assert meta("oc-eeee5555")["helper_backfill"]["result"] == "no log"
    # Once: a second run reads nothing again and changes nothing.
    before = {p: p.read_bytes() for p in root.glob("projects/*/chats/*/meta.json")}
    assert helperbackfill.backfill(root, claude_root=claude, codex_dir=codex) == {}
    assert before == {p: p.read_bytes() for p in root.glob("projects/*/chats/*/meta.json")}
    # The #entrypoint in the old helper's prompt is no longer kept.
    store = ViewStore(data_root=root)
    store.rebuild()
    assert store.query("SELECT count(*) AS n FROM keep_marks")[0]["n"] == 0


def test_the_backfill_never_writes_over_a_meta_that_moved(tmp_path: Path, monkeypatch) -> None:
    from backend import helperbackfill
    root, codex = tmp_path / "data", tmp_path / "codex"
    e1 = "01a19731-8780-7dc2-bb2f-000000000001"
    _rollout(codex, e1, "codex-exec.jsonl")
    folder = _chat(root, "app", f"codex-{hookshared.session_key('codex', e1)}", "codex", e1, [("2026-11-01T10:05:00", "x")])
    real = helperbackfill.signal

    def moved(*a, **k):
        got = real(*a, **k)
        m = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        m["message_count"] = 9          # the hook wrote while the backfill read
        (folder / "meta.json").write_text(json.dumps(m), encoding="utf-8")
        return got
    monkeypatch.setattr(helperbackfill, "signal", moved)
    assert helperbackfill.backfill(root, claude_root=tmp_path / "claude", codex_dir=codex) == {}
    m = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    assert "helper" not in m and "helper_backfill" not in m and m["message_count"] == 9


# ---------------------------------------------------------------------------
# The lists the operator reads
# ---------------------------------------------------------------------------


def _fleet(root: Path) -> None:
    """A parent with two helpers (one with its tokens), a helper with no
    parent, one whose parent was never recorded, and a helper of a helper."""
    _chat(root, "app", "cc-aaaa1111", "claude-code", "aaaa1111-0", [("2026-11-01T10:00:00", "plan the work")])
    _chat(root, "app", "codex-00000001", "codex", "t1", [("2026-11-01T10:05:00", "You are a critic.\nRead it.")],
          helper=True, helper_kind="codex-exec", helper_of="cc-aaaa1111", helper_of_by="env", message_count=1)
    _chat(root, "app", "cc-bbbb2222", "claude-code", "bbbb2222-0", [("2026-11-01T10:06:00", "draft the reply")],
          helper=True, helper_kind="claude-print", helper_of="cc-aaaa1111", helper_of_by="env")
    _chat(root, "app", "codex-00000002", "codex", "t2", [("2026-11-01T11:00:00", "by hand")],
          helper=True, helper_kind="codex-exec", helper_of="")
    _chat(root, "app", "codex-00000003", "codex", "t3", [("2026-11-01T11:10:00", "lost parent")],
          helper=True, helper_kind="codex-exec", helper_of="cc-gone0000")
    _chat(root, "app", "codex-00000004", "codex", "t4", [("2026-11-01T10:07:00", "nested")],
          helper=True, helper_kind="codex-exec", helper_of="codex-00000001")
    usage = root / "projects/app/chats/codex-00000001/usage.jsonl"
    usage.write_text(json.dumps({"turn": 1, "at": "2026-11-01T10:05:30", "id": "1", "tool": "codex",
                                 "model": "gpt-5.5", "new": 1000, "cache_write": 0, "cache": 500, "output": 200,
                                 "thinking": 0, "ttl": "", "helper": "", "effort": "high"}) + "\n", encoding="utf-8")


def test_the_board_lists_operator_chats_and_folds_helpers(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    from backend.server import create_app
    root = tmp_path / "data"
    _fleet(root)
    with TestClient(create_app(data_root=root, watch=False)) as client:
        got = client.get("/api/agents/profiles?project=app").json()
        assert [p["agent"]["agent_id"] for p in got["profiles"]] == ["cc-aaaa1111"]
        helpers = got["profiles"][0]["helpers"]
        assert [h["agent_id"] for h in helpers] == ["codex-00000001", "cc-bbbb2222"]
        first = helpers[0]
        assert first["first_line"] == "You are a critic." and first["message_count"] == 1
        assert first["tool"] == "codex" and first["helper_kind"] == "codex-exec" and first["tokens"] == 1200
        assert helpers[1]["tokens"] == 0 and helpers[1]["cost_usd"] is None
        # No parent, or a parent never recorded: the folded group. A helper of a helper is under it.
        assert sorted(h["agent_id"] for h in got["orphans"]) == ["codex-00000002", "codex-00000003"]
        # A helper's own page: its chat, and the helper it started.
        one = client.get("/api/agents/codex-00000001/profile").json()
        assert one["agent"]["helper"] is True and one["agent"]["helper_of"] == "cc-aaaa1111"
        assert [h["agent_id"] for h in one["helpers"]] == ["codex-00000004"]
        assert one["sessions"] and one["totals"]["turns"] == 1
        # The Chats page: the operator's chats; one chat by its id, a helper too; or all.
        ids = {s["agent_id"] for s in client.get("/api/sessions?project=app").json()["sessions"]}
        assert ids == {"cc-aaaa1111"}
        assert client.get("/api/sessions?agent_id=codex-00000001").json()["total"] == 1
        assert len({s["agent_id"] for s in client.get("/api/sessions?project=app&helpers=1").json()["sessions"]}) == 6
        # The overview and the project: counts of the operator's chats.
        snap = client.get("/api/snapshot").json()
        assert snap["kpi"]["agents"] == 1 and [a["agent_id"] for a in snap["agents"]] == ["cc-aaaa1111"]
        assert {r["agent_id"] for r in snap["recent_activity"]} == {"cc-aaaa1111"}
        proj = client.get("/api/project/app").json()
        assert proj["summary"]["active_agents"] == 1 and {a["agent_id"] for a in proj["agents"]} == {"cc-aaaa1111"}
        lanes = client.get("/api/timeline?project=app").json()["lanes"]
        assert [x["agent_id"] for x in lanes] == ["cc-aaaa1111"]
        # The standup's material: the day's operator chats only.
        mat = client.get("/api/standups/material?project=app&date=2611-01").json()
        assert {c["agent_id"] for c in mat["chats"]} == {"cc-aaaa1111"}
