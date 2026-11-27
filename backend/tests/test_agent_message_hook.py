"""Messages between agents (tk_c1caab80): the capture hook reads the
marker a message is typed into a terminal with, and hands over the messages
that waited. Each message reaches its chat once, by whichever way comes
first; a marker the ledger does not know is the operator's text."""

from __future__ import annotations

import importlib.util
import json
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


@pytest.mark.parametrize(("agent", "notice_first", "muted"), [
    (WORKER, True, False),
    (WORKER, False, True),
    (CODEX, True, True),
    (CODEX, False, False),
])
def test_a_mixed_late_notice_keeps_only_the_operator_text_and_tag_behavior(root, agent, notice_first, muted):
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
    signals = cap.open_turn("\n".join((notice, said) if notice_first else (said, notice)), deliver=True)
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
