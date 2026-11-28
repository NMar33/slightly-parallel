"""The keep-alive scheduler uses the same verified pane and paste as messages."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from backend import msgdeliver, pingstate, termlib

AGENT = "cc-p1ng0001"
CODEX = "codex-aabbcc01"
PANE = "t0000aaaa"
NOW = datetime(2030, 4, 12, 23, 0, 0)
CLAUDE = "─────\n❯ \n─────"
CODEX_SCREEN = "› \n  \x1b[2mstatus\x1b[0m"


def _prepare(root: Path, *, agent: str = AGENT, **overrides: object) -> Path:
    folder = root / "projects" / "alpha" / "chats" / agent
    folder.mkdir(parents=True)
    meta = folder / "meta.json"
    tool = "codex" if agent == CODEX else "claude-code"
    data = {"agent_id": agent, "tool": tool, "message_count": 1,
            "terminal": PANE, "last_answer_at": (NOW - timedelta(minutes=55)).isoformat(),
            "prompt_hook": True, **overrides}
    meta.write_text(json.dumps(data), encoding="utf-8")
    pingstate.enroll(root, agent, enabled=True)
    return meta


def _terminal(monkeypatch, root: Path, agent: str, *, screen: str, change: str = "", wrong_cursor: bool = False) -> list[str]:
    output: list[str] = []
    buffers: dict[str, str] = {}
    pane = {"fg": "codex" if agent == CODEX else "claude", "dead": "0", "pid": "123", "in_mode": "0"}
    pane["cursor_y"] = str(next((n for n, line in enumerate(screen.split("\n")) if line.lstrip().startswith("›")), 0))
    pane["width"] = "80"
    if wrong_cursor:
        pane["cursor_y"] = str(int(pane["cursor_y"]) + 1)
    monkeypatch.setattr(termlib, "tmux_path", lambda: "tmux")
    monkeypatch.setattr(termlib, "get", lambda *_: {"backend": "tmux"})
    monkeypatch.setattr(msgdeliver, "_pane", lambda *_: pane)
    monkeypatch.setattr(msgdeliver, "occupant_why", lambda *_: "")
    monkeypatch.setattr(msgdeliver, "ENTER_AFTER_S", 0)

    def tmux(_root, *args, input=None):
        command = args[0]
        output.append(command)
        if command == "load-buffer":
            buffers[args[2]] = input
        elif command == "paste-buffer":
            state = pingstate.read(pingstate.state_path(root, agent))
            assert state["terminal"] == PANE and state["nonce"] in buffers[args[4]]
            assert state["sent_at"] <= NOW.timestamp() < state["expires_at"]
            buffers["input"] = buffers.pop(args[4]) + change
        return subprocess.CompletedProcess(args, 0, "")

    def tmux_read(_root, *args):
        text = screen.replace("❯ ", "❯ " + buffers.get("input", "")).replace("› ", "› " + buffers.get("input", ""))
        return subprocess.CompletedProcess(args, 0, text)

    monkeypatch.setattr(termlib, "tmux", tmux)
    monkeypatch.setattr(termlib, "tmux_read", tmux_read)
    return output


@pytest.mark.parametrize(("agent", "screen"), [(AGENT, CLAUDE), (CODEX, CODEX_SCREEN)])
def test_due_ping_is_recorded_before_the_verified_paste(tmp_path, monkeypatch, agent, screen):
    _prepare(tmp_path, agent=agent)
    calls = _terminal(monkeypatch, tmp_path, agent, screen=screen)
    assert msgdeliver.ping_due(tmp_path, now=NOW) == 1
    assert calls == ["load-buffer", "paste-buffer", "send-keys"]
    assert msgdeliver.ping_due(tmp_path, now=NOW + timedelta(minutes=1)) == 0
    assert calls.count("send-keys") == 1


@pytest.mark.parametrize("case", [
    "busy", "just-answered", "quiet", "foreign", "unreadable", "codex-legacy",
    "codex-running", "wrong-cursor", "changed-draft", "disabled", "draft",
])
def test_ping_waits_if_the_terminal_or_time_is_not_ready(tmp_path, monkeypatch, case):
    agent = CODEX if case in ("unreadable", "codex-legacy", "codex-running", "wrong-cursor") else AGENT
    meta = _prepare(tmp_path, agent=agent)
    screen = CODEX_SCREEN if agent == CODEX else CLAUDE
    data = json.loads(meta.read_text(encoding="utf-8"))
    if case == "busy":
        data["pending_turn"] = 2
    elif case == "just-answered":
        data["last_answer_at"] = (NOW - timedelta(minutes=54)).isoformat()
    elif case == "quiet":
        (tmp_path / "settings.json").write_text('{"ping":{"quiet_hours":"22:00-08:00"}}', encoding="utf-8")
    elif case == "foreign":
        data.pop("terminal")
    elif case == "unreadable":
        screen = "Codex has no composer on the screen"
    elif case == "codex-legacy":
        data.pop("prompt_hook")
    elif case == "codex-running":
        screen = "Working (1s · esc to interrupt)\n" + screen
    elif case == "disabled":
        pingstate.enroll(tmp_path, agent, enabled=False)
    elif case == "draft":
        screen = "─────\n❯ please wait\n─────"
    meta.write_text(json.dumps(data), encoding="utf-8")
    calls = _terminal(monkeypatch, tmp_path, agent, screen=screen,
                      change=" another instruction" if case == "changed-draft" else "",
                      wrong_cursor=case == "wrong-cursor")
    assert msgdeliver.ping_due(tmp_path, now=NOW) == 0
    assert "send-keys" not in calls
    if case != "changed-draft":
        assert "paste-buffer" not in calls
