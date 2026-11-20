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


def test_a_real_marker_is_the_senders_turn_and_its_tags_do_nothing(root: Path) -> None:
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="run #task now #mute")
    assert msgledger.claim_terminal(root, row["id"]) is not None
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
    assert "the build is red #done" in notice and f"from the agent {COORD}" in notice
    assert "done" not in sig["commands"]
    cap.complete_turn("ok")
    assert cap.open_turn("and now?", deliver=True)["messages"] == []
    got = msgledger.find(root, row["id"])
    assert got is not None and got["delivered_via"] == "hook" and got["read_at"]
    # Taken by the hook: the terminal and a marker no longer take it.
    assert msgledger.claim_terminal(root, row["id"]) is None
    cap.complete_turn("ok")
    assert cap.open_turn(msgledger.terminal_text(row))["message_in"] is None


def test_an_adapter_that_cannot_show_a_notice_hands_nothing_over(root: Path) -> None:
    msgledger.add(root, project="alpha", from_agent=COORD, to_agent=CODEX, text="x")
    cap = capture.TurnCapture(root, "alpha", CODEX)
    cap.full_turn("the input", "the reply")  # Codex notify: the turn is reported at its end
    assert msgledger.read_rows(root)[0]["delivered_via"] == ""


def test_typed_into_the_terminal_the_marker_lands_once(root: Path) -> None:
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="x")
    assert msgledger.claim_terminal(root, row["id"]) is not None
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


def _run_hook(root: Path, tool: str, session: str, prompt: str) -> str:
    args = [sys.executable, str(_HOOKS / "claude-code-capture.py"), "--project", "alpha", "--data-root", str(root)]
    if tool == "codex":
        args += ["--tool", "codex"]
    proc = subprocess.run(args, input=json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": session,
                                                  "prompt": prompt}),
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


@pytest.mark.parametrize("tool, session, agent", [
    ("claude-code", "w0rker01-0000-0000-0000-000000000000", WORKER),
    ("codex", "00000000-0000-7000-8000-00000c0dex01", CODEX),
])
def test_the_prompt_hooks_of_claude_code_and_codex(root: Path, tool: str, session: str, agent: str) -> None:
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=agent, text="typed in #task")
    msgledger.claim_terminal(root, row["id"])
    waiting = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=agent, text="the second one")
    out = _run_hook(root, tool, session, msgledger.terminal_text(row))
    if tool == "codex":
        out = json.loads(out.strip().splitlines()[-1])["hookSpecificOutput"]["additionalContext"]
    assert f"message {row['id']}" in out and "the second one" in out
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
    assert msgledger.claim_terminal(root, row["id"]) is not None
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
    assert msgledger.inbox(root, WORKER)["unread"] == []


def test_a_message_in_flight_in_the_terminal_is_not_handed_over_by_the_inbox(root: Path) -> None:
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="typed")
    assert msgledger.claim_terminal(root, row["id"]) is not None
    got = msgledger.inbox(root, WORKER)
    assert got["unread"] == [] and [m["id"] for m in got["in_flight"]] == [row["id"]]
    assert "text" not in got["in_flight"][0]
    # Typed into another chat's pane: back to its own chat, through the inbox once.
    msgledger.take_stray(root, CODEX, msgledger.terminal_text(row), 3)
    got = msgledger.inbox(root, WORKER)
    assert [m["id"] for m in got["unread"]] == [row["id"]] and got["in_flight"] == []
    assert msgledger.inbox(root, WORKER)["unread"] == []
    assert msgledger.claim_for_hook(root, WORKER) == []


def test_a_pasted_marker_of_a_message_never_typed_stays_the_operators_text(root: Path) -> None:
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="for the worker")
    msgledger.claim_for_hook(root, WORKER)  # handed over by the hook, then pasted elsewhere
    sig = capture.TurnCapture(root, "alpha", CODEX).open_turn(msgledger.terminal_text(row) + " #task", deliver=True)
    assert sig["message_stray"] is None and "task" in sig["commands"]
    assert msgledger.find(root, row["id"])["strayed"] == ""  # type: ignore[index]
