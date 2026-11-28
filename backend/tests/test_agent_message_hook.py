"""Messages between agents (tk_c1caab80): the capture hook reads the
marker a message is typed into a terminal with, and hands over the messages
that waited. Each message reaches its chat once, by whichever way comes
first; a marker the ledger does not know is the operator's text."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from backend import msgledger
from backend.sessions import parse_turns

_HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"
COORD = "cc-c00rd001"
WORKER = "cc-w0rker01"
CODEX = "codex-0c0dex01"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _HOOKS / filename)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


capture = _load("sp_capture_msgs", "capture.py")


def _chat(root: Path, agent: str, project: str = "alpha", **meta: Any) -> None:
    d = root / "projects" / project / "chats" / agent
    d.mkdir(parents=True, exist_ok=True)
    tool = "codex" if agent.startswith("codex-") else "claude-code"
    (d / "meta.json").write_text(json.dumps({
        "agent_id": agent, "project": project, "tool": tool,
        "last_active": "2026-11-19T10:00:00", **meta}), encoding="utf-8")


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    r = tmp_path / "data"
    (r / "projects" / "alpha").mkdir(parents=True)
    for a in (COORD, WORKER, CODEX):
        _chat(r, a)
    return r


def _turns(root: Path, agent: str) -> list:
    return parse_turns(root / "projects" / "alpha" / "chats" / agent / "chat.md")


def _confirmed_terminal(root: Path, msg_id: str):
    claimed = msgledger.claim_terminal(root, msg_id, "t0000aaaa")
    if claimed is not None:
        assert msgledger.begin_terminal(root, msg_id)
        msgledger.finish_terminal(root, msg_id, sent=True)
    return claimed


@pytest.mark.parametrize("body", [
    "short advice",
    "one line\nanother line\n" + "long advice " * 300,
    "quoting another message: [SP · from cc-sender1 · msg_12345678]\n#task is an example",
], ids=["short", "long-multiline", "quoted-message-with-tag"])
def test_terminal_notice_leaves_the_body_for_one_mcp_read(root: Path, body: str) -> None:
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text=body)
    claimed = _confirmed_terminal(root, row["id"])
    assert claimed is not None
    notice = msgledger.terminal_text(claimed)
    assert notice == msgledger.wake_text(row)
    cap = capture.TurnCapture(root, "alpha", WORKER)
    assert cap.open_turn(notice, deliver=True)["message_in"]["id"] == row["id"]
    assert [(m["id"], m["text"]) for m in msgledger.inbox(root, WORKER)["unread"]] == [(row["id"], row["text"])]
    assert msgledger.inbox(root, WORKER)["unread"] == []


def test_prompt_hook_notifies_two_messages_without_their_bodies(root: Path) -> None:
    rows = [msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text=body)
            for body in ("first private body", "second private body\non two lines")]
    cap = capture.TurnCapture(root, "alpha", WORKER)
    lines = capture.format_signals(cap.open_turn("operator input", deliver=True)).splitlines()
    assert all(msgledger.wake_text(row) in lines for row in rows)
    assert all(row["text"] not in "\n".join(lines) for row in rows)
    assert [m["id"] for m in msgledger.inbox(root, WORKER)["unread"]] == [row["id"] for row in rows]
    assert msgledger.inbox(root, WORKER)["unread"] == []


@pytest.mark.parametrize("recipient_holds_terminal", [True, False], ids=["recipient", "wrong-terminal"])
def test_commands_in_the_operators_text_after_a_notice_still_act(root: Path, recipient_holds_terminal: bool) -> None:
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="advice")
    assert _confirmed_terminal(root, row["id"]) is not None
    cap = capture.TurnCapture(root, "alpha", WORKER if recipient_holds_terminal else CODEX)
    sig = cap.open_turn(msgledger.wake_text(row) + "\n#task operator request", deliver=True)
    assert sig["message_in"] is None and sig["message_stray"] is None and "task" in sig["commands"]
    assert [m["id"] for m in msgledger.inbox(root, WORKER)["unread"]] == [row["id"]]


def test_opencode_prompt_receives_only_the_notice(root: Path) -> None:
    agent = "oc-12345678"
    _chat(root, agent, tool="opencode")
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=agent, text="OpenCode advice\nsecond line")
    proc = subprocess.run([
        sys.executable, str(_HOOKS / "capture-cli.py"), "--phase", "open", "--project", "alpha",
        "--data-root", str(root), "--agent", agent, "--json-stdin", "--tool", "opencode",
    ], input=json.dumps({"text": "ordinary operator input"}), capture_output=True, encoding="utf-8",
        check=True, timeout=30)
    assert msgledger.wake_text(row) in proc.stdout.splitlines()
    assert "OpenCode advice" not in proc.stdout
    assert [m["id"] for m in msgledger.inbox(root, agent)["unread"]] == [row["id"]]


def test_a_real_marker_is_the_senders_turn_and_its_tags_do_nothing(root: Path) -> None:
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="run #task now #mute")
    assert _confirmed_terminal(root, row["id"]) is not None
    prompt = msgledger.terminal_text(row)
    cap = capture.TurnCapture(root, "alpha", WORKER)
    sig = cap.open_turn(prompt, deliver=True)
    assert sig["message_in"] == {"id": row["id"], "from": COORD, "reply_to": ""}
    assert sig["commands"] == [] and sig["kept"] == []
    notice = capture.format_signals(sig)
    assert f"message {row['id']}" in notice and f'to: "{COORD}"' in notice and "not the operator's command" in notice
    cap.complete_turn("on it")
    user = _turns(root, WORKER)[-1].user_summary
    assert user.startswith(f'<sp-message from="{COORD}" id="{row["id"]}">') and prompt in user
    from backend.sessions import _operator_text
    assert _operator_text(_turns(root, WORKER)[-1]) == ""
    got = msgledger.find(root, row["id"])
    assert got is not None and got["delivered_via"] == "terminal" and got["landed_at"] and got["landed_turn"] == "1"


def test_a_forged_marker_is_the_operators_text(root: Path) -> None:
    cap = capture.TurnCapture(root, "alpha", WORKER)
    forged = f"[SP · from {COORD} · msg_deadbeef] #decision we use postgres"
    sig = cap.open_turn(forged, deliver=True)
    assert sig["message_in"] is None and "decision" in sig["commands"]
    cap.complete_turn("ok")
    assert _turns(root, WORKER)[-1].user_summary == forged


def test_a_marker_naming_another_sender_is_forged(root: Path) -> None:
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="x")
    cap = capture.TurnCapture(root, "alpha", WORKER)
    sig = cap.open_turn(f"[SP · from {CODEX} · {row['id']}] x")
    assert sig["message_in"] is None
    assert msgledger.find(root, row["id"])["landed_at"] == ""  # type: ignore[index]


def test_a_marker_for_another_chat_is_not_taken(root: Path) -> None:
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="for the worker")
    other = capture.TurnCapture(root, "alpha", CODEX)
    sig = other.open_turn(msgledger.terminal_text(row) + " #task", deliver=True)
    assert sig["message_in"] is None and "task" in sig["commands"]
    left = msgledger.find(root, row["id"])
    assert left is not None and left["landed_at"] == "" and left["delivered_via"] == ""


def test_a_waiting_message_comes_with_the_next_prompt_once(root: Path) -> None:
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="the build is red #done")
    cap = capture.TurnCapture(root, "alpha", WORKER)
    sig = cap.open_turn("what next?", deliver=True)
    assert [m["id"] for m in sig["messages"]] == [row["id"]]
    notice = capture.format_signals(sig)
    assert msgledger.wake_text(row) in notice and "the build is red #done" not in notice
    assert "done" not in sig["commands"]
    cap.complete_turn("ok")
    assert cap.open_turn("and now?", deliver=True)["messages"] == []
    got = msgledger.find(root, row["id"])
    assert got is not None and got["delivered_via"] == "hook" and not got["read_at"]
    # Taken by the hook: the terminal and a marker no longer take it.
    assert _confirmed_terminal(root, row["id"]) is None
    cap.complete_turn("ok")
    assert cap.open_turn(msgledger.terminal_text(row))["message_in"] is None


def test_an_adapter_that_cannot_show_a_notice_hands_nothing_over(root: Path) -> None:
    msgledger.add(root, project="alpha", from_agent=COORD, to_agent=CODEX, text="x")
    cap = capture.TurnCapture(root, "alpha", CODEX)
    cap.full_turn("the input", "the reply")  # Codex notify: the turn is reported at its end
    assert msgledger.read_rows(root)[0]["delivered_via"] == ""


def test_typed_into_the_terminal_the_marker_lands_once(root: Path) -> None:
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="x")
    assert _confirmed_terminal(root, row["id"]) is not None
    assert msgledger.claim_for_hook(root, WORKER) == []
    cap = capture.TurnCapture(root, "alpha", WORKER)
    prompt = msgledger.terminal_text(row)
    assert cap.open_turn(prompt)["message_in"] is not None
    # The same prompt event again (a retried hook) is the same turn.
    assert cap.open_turn(prompt)["turn_number"] == 1
    cap.complete_turn("ok")
    # Sent again by hand later: the marker is spent, the text is the operator's.
    assert cap.open_turn(prompt)["message_in"] is None
    assert len(_turns(root, WORKER)) == 2


def test_two_combined_terminal_notices_leave_both_bodies_available_once(root: Path) -> None:
    rows = [msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text=body)
            for body in ("first advice", "second advice")]
    for row in rows:
        assert _confirmed_terminal(root, row["id"]) is not None
    prompt = "\n".join(msgledger.wake_text(row) for row in rows)
    capture.TurnCapture(root, "alpha", WORKER).open_turn(prompt, deliver=True)
    assert [m["id"] for m in msgledger.inbox(root, WORKER)["unread"]] == [row["id"] for row in rows]
    assert msgledger.inbox(root, WORKER)["unread"] == []


def _run_hook(root: Path, tool: str, session: str, prompt: str) -> str:
    args = [sys.executable, str(_HOOKS / "claude-code-capture.py"), "--project", "alpha", "--data-root", str(root)]
    if tool == "codex":
        args += ["--tool", "codex"]
    proc = subprocess.run(args, input=json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": session,
                                                  "prompt": prompt}),
                          capture_output=True, encoding="utf-8", timeout=60)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_claude_submit_after_an_indented_quote_records_the_real_notice(root: Path) -> None:
    mid, notice = _recovered_notice(root)
    session = "w0rker01-0000-0000-0000-000000000000"

    first = _run_hook(root, "claude-code", session, f"    {notice}")
    assert "already delivered" not in first
    saved = msgledger.find(root, mid)
    assert saved is not None and saved["terminal_state"] == "uncertain" and not saved["landed_at"]

    # The actual terminal wake follows before the earlier prompt has a Stop.
    second = _run_hook(root, "claude-code", session, notice)
    assert f"message {mid} was already delivered" in second
    saved = msgledger.find(root, mid)
    assert saved is not None and saved["delivered_via"] == "hook" and saved["landed_turn"] == "2"
    assert len(_turns(root, WORKER)) == 2


@pytest.mark.parametrize("tool, session, agent", [
    ("claude-code", "w0rker01-0000-0000-0000-000000000000", WORKER),
    ("codex", "00000000-0000-7000-8000-00000c0dex01", CODEX),
])
def test_the_prompt_hooks_of_claude_code_and_codex(root: Path, tool: str, session: str, agent: str) -> None:
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=agent, text="typed in #task")
    _confirmed_terminal(root, row["id"])
    waiting = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=agent, text="the second one")
    out = _run_hook(root, tool, session, msgledger.terminal_text(row))
    if tool == "codex":
        out = json.loads(out.strip().splitlines()[-1])["hookSpecificOutput"]["additionalContext"]
    assert f"message {row['id']}" in out and msgledger.wake_text(waiting) in out
    assert "the second one" not in out
    got = {r["id"]: r for r in msgledger.read_rows(root)}
    assert got[row["id"]]["landed_at"] and got[waiting["id"]]["delivered_via"] == "hook"
    user = _turns(root, agent)[-1].user_summary
    assert user.startswith("<sp-message")




def test_a_marker_typed_into_another_chats_terminal_is_a_stray_and_goes_back(root: Path) -> None:
    """19 Nov: two messages for codex-ca00f219 were typed into the pane
    codex-12e64f61 held; its hook kept them as the operator's text, tags
    live, and the real addressee then read them in its inbox too. Now the
    wrong chat records a stray (tags muted), the ledger notes it, and the
    message reaches its own chat once."""
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="for the worker #task #decision x")
    assert _confirmed_terminal(root, row["id"]) is not None
    other = capture.TurnCapture(root, "alpha", CODEX)
    sig = other.open_turn(msgledger.terminal_text(row), deliver=True)
    assert sig["message_in"] is None
    assert sig["message_stray"] == {"id": row["id"], "from": COORD, "to": WORKER}
    assert sig["commands"] == [] and sig["kept"] == []
    notice = capture.format_signals(sig)
    assert f"for the chat {WORKER}" in notice and "not for you" in notice
    other.complete_turn("noted")
    user = _turns(root, CODEX)[-1].user_summary
    assert user.startswith(f'<sp-message from="{COORD}" id="{row["id"]}" for="{WORKER}" stray="1">')
    from backend.sessions import _operator_text
    assert _operator_text(_turns(root, CODEX)[-1]) == ""
    left = msgledger.find(root, row["id"])
    assert left is not None and left["delivered_via"] == "" and left["landed_at"] == ""
    assert left["strayed"].startswith(f"{CODEX} ") and left["strayed"].endswith("turn 1")
    # The terminal is not tried for it again; its own chat's hook takes it, once.
    assert msgledger.waiting(root) == []
    from backend import msgdeliver
    assert "another chat held" in msgdeliver.try_terminal(root, row["id"])[1]
    cap = capture.TurnCapture(root, "alpha", WORKER)
    assert [m["id"] for m in cap.open_turn("next", deliver=True)["messages"]] == [row["id"]]
    assert [m["id"] for m in msgledger.inbox(root, WORKER)["unread"]] == [row["id"]]
    assert msgledger.inbox(root, WORKER)["unread"] == []


@pytest.mark.parametrize("typing_failed", [True, False], ids=["paste-failed", "wrong-terminal"])
def test_read_during_pending_terminal_notice_never_requeues_the_body(root: Path, typing_failed: bool) -> None:
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="typed")
    assert msgledger.claim_terminal(root, row["id"], "t0000aaaa") is not None
    assert msgledger.begin_terminal(root, row["id"])
    got = msgledger.inbox(root, WORKER)
    assert [m["id"] for m in got["unread"]] == [row["id"]] and got["in_flight"] == []
    if typing_failed:
        msgledger.finish_terminal(root, row["id"])
    else:
        msgledger.take_stray(root, CODEX, msgledger.terminal_text(row), 3)
    assert msgledger.find(root, row["id"])["delivered_via"] == "inbox"  # type: ignore[index]
    assert msgledger.inbox(root, WORKER)["unread"] == []
    assert msgledger.claim_for_hook(root, WORKER) == []
    assert msgledger.waiting(root) == []


def test_a_pasted_marker_of_a_message_never_typed_stays_the_operators_text(root: Path) -> None:
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="for the worker")
    msgledger.claim_for_hook(root, WORKER)  # handed over by the hook, then pasted elsewhere
    sig = capture.TurnCapture(root, "alpha", CODEX).open_turn(msgledger.terminal_text(row) + " #task", deliver=True)
    assert sig["message_stray"] is None and "task" in sig["commands"]
    assert msgledger.find(root, row["id"])["strayed"] == ""  # type: ignore[index]


def test_an_edited_notice_in_the_wrong_chat_preserves_the_operator_command(root: Path) -> None:
    from backend.sessions import _operator_text

    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="recover")
    mid = row["id"]
    assert msgledger.claim_terminal(root, mid, "t0000aaaa") is not None
    assert msgledger.begin_terminal(root, mid)
    msgledger.finish_terminal(root, mid)
    assert [r["id"] for r in msgledger.claim_for_hook(root, WORKER)] == [mid]

    edited = msgledger.wake_text(row).removesuffix(".") + "! #task operator request"
    cap = capture.TurnCapture(root, "alpha", CODEX)
    signals = cap.open_turn(edited, deliver=True)
    cap.complete_turn("noted")

    assert signals["message_stray"] is None
    assert "task" in signals["commands"]
    assert _operator_text(_turns(root, CODEX)[-1]) == edited
    saved = msgledger.find(root, mid)
    assert saved is not None and saved["delivered_via"] == "hook" and not saved["strayed"]


@pytest.mark.parametrize(("agent", "muted"), [
    (WORKER, False),
    (WORKER, True),
    (CODEX, True),
    (CODEX, False),
])
def test_a_mixed_late_notice_keeps_only_the_operator_text_and_tag_behavior(root, agent, muted):
    from backend.sessions import _operator_text

    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="recover")
    mid = row["id"]
    assert msgledger.claim_terminal(root, mid, "t0000aaaa") is not None
    assert msgledger.begin_terminal(root, mid)
    msgledger.finish_terminal(root, mid)
    assert [r["id"] for r in msgledger.claim_for_hook(root, WORKER)] == [mid]

    said = '<pasted_content id="x">#task operator request</pasted_content>'
    if muted:
        said += "\n#mute"
    notice = msgledger.wake_text(row)
    cap = capture.TurnCapture(root, "alpha", agent)
    signals = cap.open_turn(f"{notice}\n{said}", deliver=True)
    cap.complete_turn("noted")

    assert signals["message_in"] is None and signals["message_stray"] is None
    assert ("task" in signals["commands"]) is not muted
    assert _operator_text(_turns(root, agent)[-1]) == said
    response = capture.format_signals(signals)
    assert f"message {mid} was already delivered" in response
    assert notice not in response
    saved = msgledger.find(root, mid)
    assert saved is not None and saved["delivered_via"] == "hook" and not saved["strayed"]


def test_a_quoted_notice_without_a_terminal_attempt_stays_in_the_operators_text(root: Path) -> None:
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="not yet sent")
    assert msgledger.claim_for_hook(root, WORKER)
    said = f"Here is the notification text\n{msgledger.wake_text(row)}\n#task operator request"
    cap = capture.TurnCapture(root, "alpha", WORKER)
    signals = cap.open_turn(said)
    cap.complete_turn("noted")
    assert not signals["message_late"] and "task" in signals["commands"]
    assert _turns(root, WORKER)[-1].user_summary == said


@pytest.mark.parametrize(("quote", "via", "agent"), [
    ('Translate "{notice}" into French.', "hook", WORKER),
    ("```text\n{notice}\n```", "inbox", WORKER),
    ("Here is a message:\n> {notice}", "hook", CODEX),
    ("#task Investigate this log\n{notice}", "inbox", WORKER),
    ("    {notice}\n    end of the quoted log", "hook", WORKER),
])
def test_a_quoted_late_notice_stays_in_history_and_does_not_spend_the_real_marker(root, quote, via, agent):
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="recover")
    mid = row["id"]
    assert msgledger.claim_terminal(root, mid, "t0000aaaa") is not None
    assert msgledger.begin_terminal(root, mid)
    msgledger.finish_terminal(root, mid)
    if via == "hook":
        assert [r["id"] for r in msgledger.claim_for_hook(root, WORKER)] == [mid]
    else:
        assert [r["id"] for r in msgledger.inbox(root, WORKER)["unread"]] == [mid]

    notice = msgledger.wake_text(row)
    quoted = quote.format(notice=notice)
    cap = capture.TurnCapture(root, "alpha", agent)
    signals = cap.open_turn(quoted, deliver=True)
    cap.complete_turn("noted")
    assert _turns(root, agent)[-1].user_summary == quoted.strip()
    assert "already delivered" not in capture.format_signals(signals)
    saved = msgledger.find(root, mid)
    assert saved is not None and saved["terminal_state"] == "uncertain" and not saved["landed_at"]

    recipient = capture.TurnCapture(root, "alpha", WORKER)
    late = recipient.open_turn(notice, deliver=True)
    assert f"message {mid} was already delivered" in capture.format_signals(late)
    saved = msgledger.find(root, mid)
    assert saved is not None and saved["delivered_via"] == via and saved["landed_at"]


def _recovered_notice(root: Path) -> tuple[str, str]:
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="recover")
    mid = row["id"]
    assert msgledger.claim_terminal(root, mid, "t0000aaaa") is not None
    assert msgledger.begin_terminal(root, mid)
    msgledger.finish_terminal(root, mid)
    assert [r["id"] for r in msgledger.claim_for_hook(root, WORKER)] == [mid]
    return mid, msgledger.wake_text(row)


@pytest.mark.parametrize("adapter", ["codex-notify", "opencode"])
def test_adapter_capture_preserves_an_indented_notice_quote(root, tmp_path, monkeypatch, adapter):
    mid, notice = _recovered_notice(root)
    quoted = f"    {notice}\n    end of the quoted log"
    if adapter == "codex-notify":
        session = "00000000-0000-0000-0000-0000cafef00d"
        agent = "codex-cafef00d"
        (root / "integrations.csv").write_text(f"project,path\nalpha,{tmp_path.resolve()}\n", encoding="utf-8")
        payload = {"type": "agent-turn-complete", "thread-id": session, "cwd": str(tmp_path),
                   "input-messages": [quoted], "last-assistant-message": "Noted."}
        args = [sys.executable, str(_HOOKS / "codex-capture.py"), "--data-root", str(root), json.dumps(payload)]
    else:
        from backend.routers import setup as setup_router
        from tests.conftest import need

        node = shutil.which("node")
        if not node:
            need("node")
        agent = "oc-cafef00d"
        monkeypatch.setattr(setup_router, "_plugin_python", lambda: [sys.executable])
        plugin = tmp_path / "capture.mjs"
        plugin.write_text(setup_router._compose_opencode_plugin("alpha", root), encoding="utf-8")
        # The real plugin invokes the real capture CLI. Stand in for the
        # host's shell template and unused session metadata API.
        harness = r"""
import { execFileSync } from 'node:child_process'
import { pathToFileURL } from 'node:url'
const [plugin, directory, text] = process.argv.slice(1)
const { SlightlyParallelCapture } = await import(pathToFileURL(plugin))
const shell = (strings, ...values) => ({
  quiet: async () => {
    const words = []
    for (let i = 0; i < values.length - 1; i++) {
      words.push(...strings[i].trim().split(/\s+/).filter(Boolean), ...[values[i]].flat())
    }
    const [exe, ...args] = words
    const out = execFileSync(exe, args, { input: await values.at(-1).text(), encoding: 'utf8' })
    return { text: () => out }
  }
})
const hooks = await SlightlyParallelCapture({ client: { session: {} }, directory, $: shell })
await hooks['chat.message']({ sessionID: 'ses_cafef00d' }, { parts: [{ type: 'text', text }] })
process.exit(0)
"""
        args = [node, "--input-type=module", "-e", harness, str(plugin), str(tmp_path), quoted]

    proc = subprocess.run(args, capture_output=True, encoding="utf-8", timeout=45)
    assert proc.returncode == 0, proc.stderr
    chat = root / "projects" / "alpha" / "chats" / agent / "chat.md"
    assert f"**User**: {quoted}\n" in chat.read_text(encoding="utf-8")
    saved = msgledger.find(root, mid)
    assert saved is not None and not saved["strayed"] and saved["terminal_state"] == "uncertain"


@pytest.mark.parametrize("tool,session,agent", [
    ("claude-code", "w0rker01-0000-0000-0000-000000000000", WORKER),
    ("codex", "00000000-0000-7000-8000-00000c0dex01", CODEX),
])
def test_stop_wakes_once_without_running_tags(root, tool, session, agent, monkeypatch):
    # The hook's JSON uses UTF-8 even when the parent defaults to a Windows code page.
    monkeypatch.setattr(subprocess, "_text_encoding", lambda: "cp1252")
    _run_hook(root, tool, session, "ordinary operator input")
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=agent, text="#done")
    def stop(active):
        payload = dict(hook_event_name="Stop", session_id=session, stop_hook_active=active,
                       last_assistant_message="finished")
        proc = subprocess.run([sys.executable, str(_HOOKS / "claude-code-capture.py"), "--project", "alpha",
                               "--data-root", str(root), "--tool", tool], input=json.dumps(payload),
                              capture_output=True, encoding="utf-8", check=True, timeout=30)
        return json.loads(proc.stdout or "{}")
    result = stop(False)
    assert result["decision"] == "block" and row["id"] in result["reason"]
    assert "#done" not in result["reason"]
    # Claude Code shows the reason as a Stop hook problem: it opens with the
    # line saying it is a message (tk_40450bfa). Codex's comes back as the
    # prompt itself, so it is the notice exactly.
    notice = result["reason"]
    if tool == "claude-code":
        opening, notice = notice.split("\n", 1)
        assert opening == msgledger.stop_opening(row)
    assert ascii(notice) == ascii(msgledger.wake_text(row))
    _run_hook(root, tool, session, notice)
    errors = root / ".capture" / "errors.jsonl"
    assert _turns(root, agent)[-1].user_summary.startswith("<sp-message"), (
        f"reason {result['reason']!r}; ledger row {msgledger.find(root, row['id'])}; "
        f"hook errors {errors.read_text(encoding='utf-8') if errors.is_file() else 'none'}")
    later = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=agent, text="later")
    assert "decision" not in stop(True)
    assert [r["id"] for r in msgledger.inbox(root, agent)["unread"]] == [row["id"], later["id"]]


def test_ping_enrolls_only_the_named_agent_and_can_turn_off(root: Path) -> None:
    cap = capture.TurnCapture(root, "alpha", COORD)
    signals = cap.open_turn(f'<pasted_content id="1">please #ping {WORKER}</pasted_content>')
    assert signals["ping_commands"] == [f"keep-alive enabled for {WORKER}"]
    assert (root / ".ping" / f"{WORKER}.json").is_file()
    assert not (root / ".ping" / f"{COORD}.json").exists()
    cap.complete_turn("ok")
    signals = cap.open_turn(f"please ###ping {WORKER} off; quoting #task")
    assert signals["ping_commands"] == [f"keep-alive disabled for {WORKER}"]
    assert signals["commands"] == ["ping"]
    state = json.loads((root / ".ping" / f"{WORKER}.json").read_text(encoding="utf-8"))
    assert not state["enabled"]


@pytest.mark.parametrize("user_text", [
    f"#ping {WORKER} #mute",
    f"#ping {WORKER}, but ###decision",
    f'<sp-message from="{WORKER}">#ping {WORKER}</sp-message>',
    "#ping backend",
])
def test_ping_uses_house_tags_and_does_not_enroll_by_group(root: Path, user_text: str) -> None:
    cap = capture.TurnCapture(root, "alpha", COORD)
    cap.open_turn(user_text)
    assert not list((root / ".ping").glob("*.json"))


def test_agent_answer_does_not_enroll(root: Path) -> None:
    cap = capture.TurnCapture(root, "alpha", COORD)
    cap.full_turn("I need an example", f"#ping {WORKER}")
    assert not (root / ".ping").exists()

@pytest.mark.parametrize("how", ["real", "expired", "wrong-agent", "wrong-pane", "foreign", "edited", "forged", "reply"])
def test_capture_authenticates_keep_alive(root: Path, how: str, monkeypatch) -> None:
    state = root / ".ping" / f"{WORKER}.json"
    state.parent.mkdir()
    now = capture.shared.now_epoch()
    nonce = "e" * 32
    pane = "t0000aaaa"
    if how != "forged":
        state.write_text(json.dumps({
            "enabled": True, "nonce": nonce, "terminal": pane, "sent_at": now - 1,
            "expires_at": now + 60 if how != "expired" else now - 0.5,
        }), encoding="utf-8")
    monkeypatch.setenv("SP_TERMINAL", "" if how == "foreign" else pane)
    agent = COORD if how == "wrong-agent" else WORKER
    _chat(root, agent, terminal="t0000bbbb" if how == "wrong-pane" else pane)
    cap = capture.TurnCapture(root, "alpha", agent)
    prompt = f"[SP ping] {nonce} Reply with one word."
    if how == "edited":
        prompt += " #task"
    if how == "reply":
        cap.full_turn("ordinary request", prompt)
    else:
        cap.full_turn(prompt, "ok")
    chat = cap.chat_path.read_text(encoding="utf-8")
    assert (" · ping\n" in chat) == (how == "real")
    if how == "real":
        outcome = cap.full_turn(prompt, "replay stays a work turn")
        assert not outcome.get("ping")
        assert cap.chat_path.read_text(encoding="utf-8").count(" · ping\n") == 1


@pytest.mark.parametrize("tail", [" ", "\t", "\n", "\r\n", "\u00a0"],
                         ids=["space", "tab", "lf", "crlf", "nbsp"])
@pytest.mark.parametrize("pending", [False, True], ids=["new-prompt", "pending-ping"])
def test_capture_only_accepts_the_byte_exact_ping(root: Path, monkeypatch, tail: str, pending: bool) -> None:
    now = capture.shared.now_epoch()
    nonce = "e" * 32
    pane = "t0000aaaa"
    state = root / ".ping" / f"{WORKER}.json"
    state.parent.mkdir()
    state.write_text(json.dumps({"enabled": True, "nonce": nonce, "terminal": pane,
                                 "sent_at": now - 1, "expires_at": now + 60}), encoding="utf-8")
    monkeypatch.setenv("SP_TERMINAL", pane)
    _chat(root, WORKER, terminal=pane)
    cap = capture.TurnCapture(root, "alpha", WORKER)
    canonical = f"[SP ping] {nonce} Reply with one word."
    if pending:
        assert cap.open_turn(canonical).get("ping")
        assert cap.open_turn(canonical).get("ping")  # an exact hook retry
    outcome = cap.open_turn(canonical + tail)
    assert not outcome.get("ping")
    if not pending:
        assert json.loads(state.read_text(encoding="utf-8"))["nonce"] == nonce


def test_ping_does_not_spend_work_notices_or_create_work_stamps(root: Path, monkeypatch) -> None:
    now = capture.shared.now_epoch()
    nonce = "c" * 32
    pane = "t0000aaaa"
    monkeypatch.setenv("SP_TERMINAL", pane)
    _chat(root, WORKER, terminal=pane, unsigned_commits=[{"sha": "abcdef0", "subject": "change"}])
    state = root / ".ping" / f"{WORKER}.json"
    state.parent.mkdir()
    state.write_text(json.dumps({"enabled": True, "nonce": nonce, "terminal": pane,
                                 "sent_at": now - 1, "expires_at": now + 60}), encoding="utf-8")
    mail = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="work later")
    cap = capture.TurnCapture(root, "alpha", WORKER)
    ping = cap.open_turn(f"[SP ping] {nonce} Reply with one word.", deliver=True)
    assert ping.get("ping") and not ping.get("messages") and not ping.get("identity")
    assert cap.open_turn(f"[SP ping] {nonce} Reply with one word.", deliver=True).get("ping")
    cap.complete_turn("ok")
    assert not (cap.folder / "work.jsonl").exists()
    assert json.loads((cap.folder / "turns.jsonl").read_text(encoding="utf-8"))["ping"]
    ordinary = cap.open_turn("Ready to work", deliver=True)
    assert ordinary["messages"][0]["id"] == mail["id"] and ordinary["identity"]
    assert ordinary["unsigned_commits"]["commits"][0]["sha"] == "abcdef0"

def _mixed_chat(root: Path) -> tuple[Path, str]:
    from datetime import datetime, timedelta

    cap = capture.TurnCapture(root, "alpha", WORKER)
    yesterday = (datetime.now() - timedelta(days=1)).date().isoformat()
    turns = [
        (1, "10:00:00", "", "work on tk_11111111", "first answer"),
        (2, "10:55:00", " · ping", "[SP ping] received", "ok tk_99999999"),
        (3, "11:20:00", "", "[SP ping]", "ordinary request quoting ping"),
    ]
    raw = "".join(f"## Turn {n} · {yesterday}T{at}{suffix}\n**User**: {user}\n**Agent**: {answer}\n\n"
                  for n, at, suffix, user, answer in turns)
    cap.chat_path.write_text(raw, encoding="utf-8")
    stamps = [{
        "turn": n, "start": f"{yesterday}T{at}", "end": f"{yesterday}T{at[:-2]}30",
        "ping": bool(suffix), "active_sec": 120 if suffix else 30, "source": "hook",
    } for n, at, suffix, _, _ in turns]
    (cap.folder / "turns.jsonl").write_text("".join(json.dumps(row) + "\n" for row in stamps), encoding="utf-8")
    return cap.chat_path, yesterday


def test_ping_is_excluded_from_work_sessions_task_mentions_and_standup_nudge(root: Path) -> None:
    from backend import sessions, turntimes

    path, _ = _mixed_chat(root)
    assert [turn.number for turn in sessions.parse_turns(path)] == [1, 3]
    sessions_for_chat = sessions.derive_sessions([("alpha", WORKER, path)], 120)
    assert len(sessions_for_chat) == 1 and sessions_for_chat[0].turns_n == 2
    assert {hit["task_id"] for hit in sessions_for_chat[0].mentions} == {"tk_11111111"}
    timing = turntimes.times(path.parent)
    assert set(timing) == {1, 3}
    raw_lines = path.read_text(encoding="utf-8").splitlines()
    excerpt = "\n".join(sessions.work_chat_lines(line + "\r" for line in raw_lines))
    assert "tk_99999999" not in excerpt and "ordinary request quoting ping" in excerpt
    standup = capture._standup_owed(root, "alpha")
    assert standup and standup["messages_n"] == 2


@pytest.mark.parametrize("stamp", ["ping", "missing", "without-kind"])
def test_ping_usage_keeps_its_turn_number_but_does_not_count_in_work_rhythm(root: Path, monkeypatch, stamp: str) -> None:
    from backend import rhythm, usagebackfill, usagelib

    path, day = _mixed_chat(root)
    stamps = path.parent / "turns.jsonl"
    records = [json.loads(line) for line in stamps.read_text(encoding="utf-8").splitlines()]
    if stamp == "missing":
        del records[1]
        work = {"turn": 2, "at": f"{day}T10:55:30"}
        (path.parent / "work.jsonl").write_text(json.dumps(work) + "\n", encoding="utf-8")
    elif stamp == "without-kind":
        del records[1]["ping"]
    stamps.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    assert [n for n, *_ in usagebackfill.chat_turns(path.parent, {})] == [1, 2, 3]
    monkeypatch.setattr(usagelib, "chat_usage", lambda _path: {"turns": {
        1: {"at": f"{day}T10:00:00", "main": {"new": 10}},
        2: {"at": f"{day}T10:55:00", "main": {"new": 20}},
        3: {"at": f"{day}T11:20:00", "main": {"new": 30}},
    }})
    points = rhythm._folder_points(path.parent)
    assert [amount for kind, _, amount in points if kind == "tok"] == [10, 30]
    assert sum(kind == "msg" for kind, _, _ in points) == 4


def test_rhythm_refreshes_when_the_chat_turn_kind_changes_without_a_new_stamp(root: Path, monkeypatch) -> None:
    from backend import rhythm, usagelib

    path, day = _mixed_chat(root)
    ping_chat = path.read_text(encoding="utf-8")
    path.write_text(ping_chat.replace(" · ping\n", "\n"), encoding="utf-8")
    (path.parent / "turns.jsonl").unlink()
    monkeypatch.setattr(usagelib, "chat_usage", lambda _path: {"turns": {
        2: {"at": f"{day}T10:55:00", "main": {"new": 20}},
    }})

    assert [amount for kind, _, amount in rhythm._folder_points(path.parent) if kind == "tok"] == [20]
    path.write_text(ping_chat, encoding="utf-8")
    assert rhythm._folder_points(path.parent) == []
