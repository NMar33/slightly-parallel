"""The keep-alive scheduler uses the same verified pane and paste as messages."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

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


def _terminal(monkeypatch, root: Path, agent: str, *, screen: str, change: str = "", wrong_cursor: bool = False,
              during_check=None, after_submit=None, check_reservation: bool = True) -> list[str]:
    output: list[str] = []
    checked = False
    buffers: dict[str, str] = {}
    pane = {
        "fg": "codex" if agent == CODEX else "claude", "dead": "0", "pid": "123", "in_mode": "0",
        "id": "%1", "session": "$1", "active": "1", "window_active": "1", "linked": "0", "attached": "0",
        "clients": "", "cursor_x": "2", "sync": "0", "input_off": "0",
    }
    pane["cursor_y"] = str(next((n for n, line in enumerate(screen.split("\n")) if line.lstrip().startswith("›")), 0))
    pane["width"] = "80"
    if wrong_cursor:
        pane["cursor_y"] = str(int(pane["cursor_y"]) + 1)
    monkeypatch.setattr(termlib, "tmux_path", lambda: "tmux")
    monkeypatch.setattr(termlib, "get", lambda *_: {"backend": "tmux"})
    monkeypatch.setattr(msgdeliver, "_pane", lambda *_: pane)
    monkeypatch.setattr(msgdeliver, "occupant_why", lambda *_: "")

    def tmux(_root, *args, input=None):
        command = args[0]
        output.append(command)
        if command == "load-buffer":
            buffers[args[2]] = input
        elif command == "if-shell":
            buf = args[-2].split()[4]
            payload = buffers.pop(buf)
            if check_reservation:
                state = next(
                    state for path in (root / pingstate.DIRECTORY).glob("*.json")
                    if (state := pingstate.read(path)).get("nonce") == buf.removeprefix("sp-")
                )
                assert state["terminal"] == PANE and state["nonce"] in payload
            assert args[3] == "%1" and f"-b {buf} -t %1 ; send-keys -t %1 Enter" in args[-2]
            if after_submit is not None:
                after_submit()
            return subprocess.CompletedProcess(args, 0, "sent\n")
        return subprocess.CompletedProcess(args, 0, "")

    def tmux_read(_root, *args):
        nonlocal checked
        if during_check is not None and not checked and "load-buffer" in output:
            checked = True
            during_check()
        added = change if "load-buffer" in output else ""
        text = screen.replace("❯ ", "❯ " + added).replace("› ", "› " + added)
        if "-S" in args:
            y = int(args[args.index("-S") + 1])
            text = "\n".join(text.split("\n")[y:])
        return subprocess.CompletedProcess(args, 0, text)

    monkeypatch.setattr(termlib, "tmux", tmux)
    monkeypatch.setattr(termlib, "tmux_read", tmux_read)
    return output


@pytest.mark.parametrize(("agent", "screen"), [(AGENT, CLAUDE), (CODEX, CODEX_SCREEN)])
def test_due_ping_is_recorded_before_the_verified_paste(tmp_path, monkeypatch, agent, screen):
    _prepare(tmp_path, agent=agent)
    calls = _terminal(monkeypatch, tmp_path, agent, screen=screen)
    assert msgdeliver.ping_due(tmp_path, now=NOW) == 1
    assert calls == ["load-buffer", "if-shell"]
    state = pingstate.read(pingstate.state_path(tmp_path, agent))
    assert state["sent_at"] <= NOW.timestamp() < state["expires_at"]
    assert msgdeliver.ping_due(tmp_path, now=NOW + timedelta(minutes=1)) == 0
    assert calls.count("if-shell") == 1


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
    assert "if-shell" not in calls


def test_a_slow_sweep_samples_a_new_time_for_each_ping_reservation(tmp_path, monkeypatch):
    other = "cc-p1ng0002"
    _prepare(tmp_path)
    _prepare(tmp_path, agent=other)
    later = NOW + timedelta(seconds=pingstate.WINDOW_SECONDS + 1)
    clock = SimpleNamespace(current=NOW)
    monkeypatch.setattr(msgdeliver, "datetime", SimpleNamespace(now=lambda: clock.current))
    _terminal(monkeypatch, tmp_path, AGENT, screen=CLAUDE, after_submit=lambda: setattr(clock, "current", later))

    assert msgdeliver.ping_due(tmp_path) == 2
    first, second = (pingstate.read(pingstate.state_path(tmp_path, agent)) for agent in (AGENT, other))
    assert first["sent_at"] == NOW.timestamp()
    assert second["sent_at"] == later.timestamp()
    assert second["expires_at"] == later.timestamp() + pingstate.WINDOW_SECONDS


@pytest.mark.parametrize("change", ["expired", "quiet-boundary", "quiet-setting", "nonce", "disabled"])
def test_ping_rechecks_the_live_reservation_and_quiet_hours_after_final_pane_check(tmp_path, monkeypatch, change):
    _prepare(tmp_path)
    clock = SimpleNamespace(current=NOW)
    monkeypatch.setattr(msgdeliver, "datetime", SimpleNamespace(now=lambda: clock.current))
    state_path = pingstate.state_path(tmp_path, AGENT)
    settings = tmp_path / "settings.json"
    if change == "quiet-boundary":
        settings.write_text('{"ping":{"quiet_hours":"23:01-08:00"}}', encoding="utf-8")

    def change_before_submit():
        if change == "expired":
            clock.current += timedelta(seconds=pingstate.WINDOW_SECONDS)
        elif change == "quiet-boundary":
            clock.current += timedelta(minutes=1)
        elif change == "quiet-setting":
            settings.write_text('{"ping":{"quiet_hours":"22:00-08:00"}}', encoding="utf-8")
        elif change == "nonce":
            with pingstate.edit(state_path) as state:
                state["nonce"] = "different-reservation"
        else:
            pingstate.enroll(tmp_path, AGENT, enabled=False)

    calls = _terminal(monkeypatch, tmp_path, AGENT, screen=CLAUDE, during_check=change_before_submit,
                      check_reservation=False)
    assert msgdeliver.ping_due(tmp_path) == 0
    assert calls == ["load-buffer", "delete-buffer"]
