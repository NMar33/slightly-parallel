"""A Codex chat is tied to a terminal only when it is proven to run there
(tk_49aa81aa).

Codex 0.170 runs the hooks of every chat in one app-server daemon, started
from one Slightly Parallel terminal: the daemon kept that terminal's
SP_TERMINAL, so every Codex chat recorded it, and the window gave the
terminal to whichever Codex chat was active last (tab title, rhythm, message
menu, chat card). Now the hook records no terminal under the daemon, and
the page links a Codex chat only when the processes above its hook include
the pane's shell — the proof messages are typed by (msgdeliver).
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import pytest

from backend import hookshared, termlib

_HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"

# The daemon's command line as Codex 0.170 starts it (path shortened), and a
# Codex started directly in a pane.
DAEMON_ARGS = ["/home/u/.codex/packages/app-server-daemon/releases/0.170.0-x86_64-unknown-linux-musl/bin/codex",
               "app-server", "--listen", "unix://", "--analytics-default-enabled", "--managed-daemon"]
UPDATER_ARGS = [DAEMON_ARGS[0], "app-server", "daemon", "pid-update-loop"]
TUI_ARGS = ["/home/u/.nvm/versions/node/v24/lib/node_modules/@openai/codex/vendor/bin/codex", "resume"]


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _HOOKS / filename)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _chat(root: Path, agent: str, tool: str, terminal: str, last_active: str) -> None:
    d = root / "projects" / "alpha" / "chats" / agent
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps({
        "agent_id": agent, "project": "alpha", "tool": tool, "terminal": terminal,
        "last_active": last_active}), encoding="utf-8")


def _crumb(root: Path, agent: str, pids: list[int]) -> None:
    d = root / ".sessions" / "f00dfeedf00d"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{agent}.json").write_text(json.dumps({
        "agent_id": agent, "project": "alpha", "session_id": agent, "at": time.time(), "pids": pids}),
        encoding="utf-8")


@pytest.fixture()
def root(tmp_path: Path, monkeypatch) -> Path:
    r = tmp_path / "data"
    (r / "projects" / "alpha").mkdir(parents=True)
    monkeypatch.setattr(termlib, "_link_cache", (None, 0.0, {}))
    return r


def test_codex_chats_under_the_daemon_are_not_given_its_terminal(root: Path, monkeypatch) -> None:
    # The pane of terminal t1: this test's parent is its shell. The daemon is
    # elsewhere: a process that is no ancestor of the pane's.
    pane, codex_in_pane = os.getppid(), os.getpid()
    daemon = 1 if os.name != "nt" else 4
    monkeypatch.setattr(termlib, "tmux_panes", lambda _root: {
        "t1": {"fg": "codex", "activity": 0.0, "dead": False, "pid": str(pane)}})
    # Two Codex chats whose hooks ran in the daemon, both naming t1 (the real
    # records: every Codex chat said t868b1baa).
    _chat(root, "codex-aaaa0001", "codex", "t1", "2026-11-19T22:00:00")
    _chat(root, "codex-bbbb0002", "codex", "t1", "2026-11-19T23:00:00")
    _crumb(root, "codex-aaaa0001", [daemon])
    _crumb(root, "codex-bbbb0002", [daemon])
    assert "t1" not in termlib.agent_links(root)

    # A Codex started in the pane: its hook's processes include the pane's
    # shell. It holds t1, though another Codex chat was active later.
    monkeypatch.setattr(termlib, "_link_cache", (None, 0.0, {}))
    _chat(root, "codex-cccc0003", "codex", "t1", "2026-11-19T21:00:00")
    _crumb(root, "codex-cccc0003", [codex_in_pane, pane])
    assert termlib.agent_links(root)["t1"]["agent_id"] == "codex-cccc0003"


def test_a_codex_chat_with_no_pane_has_no_link_and_claude_code_is_unchanged(root: Path, monkeypatch) -> None:
    monkeypatch.setattr(termlib, "tmux_panes", lambda _root: {})
    _chat(root, "codex-aaaa0001", "codex", "t2", "2026-11-19T22:00:00")
    _crumb(root, "codex-aaaa0001", [os.getpid(), os.getppid()])
    # A Claude Code chat's hook runs under its own tool in the pane: its
    # SP_TERMINAL is its terminal, as before, with no proof asked.
    _chat(root, "cc-dddd0004", "claude-code", "t3", "2026-11-19T22:00:00")
    links = termlib.agent_links(root)
    assert "t2" not in links
    assert links["t3"]["agent_id"] == "cc-dddd0004"


def test_the_daemon_is_found_above_the_hook() -> None:
    args = {10: ["/bin/sh", "-c", "python3 hook.py"], 11: DAEMON_ARGS, 12: UPDATER_ARGS,
            20: ["python3", "hook.py"], 21: TUI_ARGS, 22: ["/bin/bash", "-l"]}
    assert hookshared.codex_daemon_above([10, 11, 12], args_of=lambda p: args.get(p, []))
    # Codex in a pane, without the daemon: its SP_TERMINAL is the pane's.
    assert not hookshared.codex_daemon_above([20, 21, 22], args_of=lambda p: args.get(p, []))
    assert not hookshared.codex_daemon_above([12], args_of=lambda p: args.get(p, []))


def test_the_hook_records_no_terminal_under_the_daemon(tmp_path: Path, monkeypatch) -> None:
    capture = _load("sp_capture_link", "capture.py")
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("SP_TERMINAL", "t868b1baa")
    monkeypatch.setattr(capture.shared, "codex_daemon_above", lambda *a, **k: True)
    capture.TurnCapture(root, "alpha", "codex-aaaa0001").note_origin("codex", "thread-a", "")
    capture.TurnCapture(root, "alpha", "cc-dddd0004").note_origin("claude-code", "sess-d", "")
    meta = lambda a: json.loads((root / "projects/alpha/chats" / a / "meta.json").read_text(encoding="utf-8"))  # noqa: E731
    assert "terminal" not in meta("codex-aaaa0001")
    assert meta("cc-dddd0004")["terminal"] == "t868b1baa"
    # Codex started in the pane itself keeps its terminal.
    monkeypatch.setattr(capture.shared, "codex_daemon_above", lambda *a, **k: False)
    capture.TurnCapture(root, "alpha", "codex-cccc0003").note_origin("codex", "thread-c", "")
    assert meta("codex-cccc0003")["terminal"] == "t868b1baa"
