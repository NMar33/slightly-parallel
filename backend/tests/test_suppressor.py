"""The ### suppressor: a command written with three hashes is the message's
only command; every other tag in it — in a pasted reply, a log — is silenced.
The hook and the server read it the same way (hookshared.command_text)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path

from backend.hookshared import command_text, plain_text
from backend.sessions import Turn, _dones_of, _importants_of, _keeps_of, _nows_of, _prompts_of

_HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"


def _capture():
    spec = importlib.util.spec_from_file_location("sp_capture_suppressor", _HOOKS / "capture.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sp_capture_suppressor"] = mod
    spec.loader.exec_module(mod)
    return mod


PASTE = "###now-todo look at this reply: <pasted_content>the #now card, then #done and #vision</pasted_content>"


def test_three_hashes_make_the_only_command():
    assert command_text("#now build it") == "#now build it"          # no ###: untouched
    said = command_text(PASTE)
    assert said.startswith("#now-todo ") and "##now card" in said and "##done" in said and "##vision" in said
    # What a command keeps: its own tag taken out like any, the rest as typed.
    assert plain_text(PASTE).startswith("#now-todo ") and "the #now card, then #done" in plain_text(PASTE)
    # A heading, four hashes, or a hash inside a word is no ### command.
    for text in ("### Heading #now", "####now x", "a###now #done"):
        assert command_text(text) == text


def _turn(n: int, said: str, reply: str = "ok") -> Turn:
    return Turn(number=n, at=datetime(2026, 10, 24, 12, n), line=n, user_summary=said, agent_summary=reply)


def test_the_server_reads_only_the_loud_command():
    block = [_turn(1, PASTE)]
    nows = _nows_of("s1", "alpha", "cc-a", block)
    assert [(r["column_"], r["body"]) for r in nows] == [("todo", PASTE)]   # the message as written
    assert _dones_of("s1", "alpha", "cc-a", block) == []
    assert _keeps_of("s1", "alpha", "cc-a", block) == []
    # Without ### every tag is a command, as before.
    plain = [_turn(1, "the #now card, then #done")]
    assert _dones_of("s1", "alpha", "cc-a", plain) and _nows_of("s1", "alpha", "cc-a", plain)
    # The prompt and the important readers too.
    quiet = [_turn(1, "###now-todo see: <pasted_content>#prompt keep this, #important and #important-task</pasted_content>")]
    assert _prompts_of("s1", "alpha", "cc-a", quiet)[0] == []
    assert _importants_of("s1", "alpha", "cc-a", quiet) == []
    loud = [_turn(1, "#prompt keep this #important")]
    assert _prompts_of("s1", "alpha", "cc-a", loud)[0] and _importants_of("s1", "alpha", "cc-a", loud)


def test_the_hook_tells_the_agent_only_the_loud_command(tmp_path: Path):
    capture = _capture()
    root = tmp_path / "data"
    root.mkdir()
    cap = capture.TurnCapture(root, "alpha", "cc-abc12345")
    signals = cap.open_turn(PASTE)
    assert signals["commands"] == ["now-todo"]
    assert signals["kept"] == []
    # The chat keeps the message as it was typed.
    assert "###now-todo look at this reply" in (cap.folder / "chat.md").read_text(encoding="utf-8")
