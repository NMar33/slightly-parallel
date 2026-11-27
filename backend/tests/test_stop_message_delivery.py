"""A waiting message at Claude Code's Stop (tk_40450bfa).

Claude Code labels every blocked Stop as a problem ("Stop hook reported a
problem"). In Slightly Parallel's own terminal the Stop hook no longer
blocks for a message: the server types it as the next prompt once the input
line is empty. Where the block stays, its reason opens with a line saying it
is a message, not an error. Each message reaches the chat once, whichever
way takes it; races are run many times, in a sandbox tmux (SHELL=/bin/sh)
with a stand-in for the agent's input box. No real agent runs."""

from __future__ import annotations

import functools
import importlib.util
import io
import json
import os
import shlex
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi.testclient import TestClient

from backend import msgdeliver, msgledger, termlib
from backend.server import create_app

_HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"
_HOOK = _HOOKS / "claude-code-capture.py"
FAKE = Path(__file__).resolve().parent / "fixtures" / "fake_agent_prompt.py"
needs_tmux = pytest.mark.skipif(termlib.tmux_path() is None or os.name == "nt", reason="needs tmux")

COORD = "cc-c00rd001"
WORKER = "cc-w0rker01"
SESSION = "w0rker01-0000-0000-0000-000000000000"
RACE_RUNS = 50


def _chat(root: Path, agent: str, **meta: Any) -> None:
    d = root / "projects" / "alpha" / "chats" / agent
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps({
        "agent_id": agent, "project": "alpha", "tool": "claude-code",
        "last_active": "2026-11-19T10:00:00", **meta}), encoding="utf-8")


def _env(**more: str) -> dict[str, str]:
    """The hook's environment: none of the SP terminal this test may itself run in."""
    env = {k: v for k, v in os.environ.items() if k not in ("SP_TERMINAL", "SP_PORT", "TMUX", "TMUX_PANE")}
    env.update(more)
    return env


def _hook(root: Path, event: dict, env: dict[str, str]) -> subprocess.CompletedProcess:
    proc = subprocess.run([sys.executable, str(_HOOK), "--project", "alpha", "--data-root", str(root)],
                          input=json.dumps(event), capture_output=True, encoding="utf-8", timeout=60, env=env)
    assert proc.returncode == 0, proc.stderr
    return proc


def _stop(root: Path, env: dict[str, str]) -> dict:
    proc = _hook(root, {"hook_event_name": "Stop", "session_id": SESSION, "last_assistant_message": "finished"}, env)
    return json.loads(proc.stdout or "{}")


def _closed_port() -> str:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return str(s.getsockname()[1])


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    r = tmp_path / "data"
    (r / "projects" / "alpha").mkdir(parents=True)
    for a in (COORD, WORKER):
        _chat(r, a)
    return r


# ---------------------------------------------------------------------------
# Outside Slightly Parallel's terminal: the block stays, and says what it is
# ---------------------------------------------------------------------------


def test_outside_an_sp_terminal_the_block_opens_with_not_an_error(root: Path) -> None:
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="#done the build")
    got = _stop(root, _env())
    assert got["decision"] == "block"
    first, rest = got["reason"].split("\n", 1)
    assert first == f"Not an error: this is a message from another agent ({COORD}), sent through Slightly Parallel."
    assert rest == msgledger.wake_text(row) and "#done" not in got["reason"]
    assert msgledger.find(root, row["id"])["delivered_via"] == "stop"  # type: ignore[index]


def test_the_operators_message_names_the_page(root: Path) -> None:
    msgledger.add(root, project="alpha", from_agent=msgledger.OPERATOR, to_agent=WORKER, text="from the page")
    first = _stop(root, _env())["reason"].split("\n", 1)[0]
    assert first == "Not an error: this is a message from the operator, sent from Slightly Parallel's page."


@pytest.mark.parametrize("how", ["no-server", "meta-names-another-terminal"])
def test_an_sp_terminal_no_server_can_type_into_keeps_the_block(root: Path, how: str) -> None:
    # The hook runs in an SP terminal, but no server of this data root
    # answers (or the chat's meta names another terminal): nobody would type
    # the message, so the Stop blocks as before.
    _chat(root, WORKER, terminal="t0000aaaa" if how == "no-server" else "t0000bbbb")
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="x")
    got = _stop(root, _env(SP_TERMINAL="t0000aaaa", SP_PORT=_closed_port()))
    assert got["decision"] == "block" and row["id"] in got["reason"]


def test_a_capture_failure_on_stop_is_not_a_message(root: Path, monkeypatch, capsys) -> None:
    """A real failure still goes to stderr as before, names itself, opens no
    block, and takes no waiting message."""
    spec = importlib.util.spec_from_file_location("sp_cc_stop_msg", _HOOK)
    cc = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(cc)  # type: ignore[union-attr]
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="x")

    def boom(*_a, **_kw):
        raise RuntimeError("disk gone")

    monkeypatch.setattr(cc.TurnCapture, "complete_turn", boom)
    monkeypatch.setattr(cc, "record_failure", lambda *a, **k: None)
    monkeypatch.delenv("SP_TERMINAL", raising=False)
    monkeypatch.setattr(sys, "argv", ["hook", "--project", "alpha", "--data-root", str(root)])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"hook_event_name": "Stop", "session_id": SESSION})))
    assert cc.main() == 0
    out = capsys.readouterr()
    assert out.out == ""
    assert out.err.startswith("[slightly-parallel] capture failed: RuntimeError: disk gone")
    assert "Not an error" not in out.err and "[SP · from" not in out.err
    assert msgledger.find(root, row["id"])["delivered_via"] == ""  # type: ignore[index]


def _all_at_once(ways: dict[str, Any]) -> dict[str, Any]:
    """Each way's result, all started together on one barrier."""
    go = threading.Barrier(len(ways))
    won: dict[str, Any] = {}
    errors: list[BaseException] = []

    def run(name: str, fn) -> None:
        go.wait()
        try:
            won[name] = fn()
        except BaseException as exc:  # noqa: BLE001 — reported by the test
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(n, f)) for n, f in ways.items()]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    return won


def test_the_ledger_hands_each_message_to_one_way_under_races(root: Path) -> None:
    # The Stop hook, the terminal and the next prompt all at once: one wins.
    for _ in range(RACE_RUNS):
        msg_id = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="race")["id"]
        won = _all_at_once({"stop": lambda: msgledger.stop_notice(root, WORKER, opening=True),
                            "terminal": functools.partial(msgledger.claim_terminal, root, msg_id),
                            "hook": lambda: msgledger.claim_for_hook(root, WORKER)})
        winners = [n for n, v in won.items() if v]
        assert len(winners) == 1, won
        assert msgledger.find(root, msg_id)["delivered_via"] == winners[0]  # type: ignore[index]


# ---------------------------------------------------------------------------
# In Slightly Parallel's terminal (a sandbox tmux and a real server on a port)
# ---------------------------------------------------------------------------


@pytest.fixture()
def term(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SHELL", "/bin/sh")
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    work = tmp_path / "work"
    work.mkdir()
    (root / "integrations.csv").write_text(f"project,path\nalpha,{work}\n", encoding="utf-8")
    for a in (COORD, WORKER):
        _chat(root, a)
    port = int(_closed_port())
    server = uvicorn.Server(uvicorn.Config(create_app(data_root=root, watch=False, run_monitor=False),
                                           host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    with TestClient(create_app(data_root=root, watch=False, run_monitor=False)) as c:
        assert c.post("/api/settings", json={"values": {"terminal.enabled": True}}).status_code == 200
        deadline = time.time() + 10
        while not server.started and time.time() < deadline:
            time.sleep(0.05)
        assert server.started
        yield c, root, work, str(port)
    server.should_exit = True
    thread.join(timeout=5)
    termlib.tmux(root, "kill-server")


def _agent(c: TestClient, root: Path, work: Path, typed: str = "") -> tuple[str, Path]:
    """The stand-in for Claude Code in an SP terminal, its meta naming that
    terminal and its breadcrumb holding the pane's shell (what the hook
    writes on a prompt)."""
    log = work / "worker.log"
    crumb = root / ".sessions" / "f0f0f0f0f0f0" / f"{WORKER}.json"
    cmd = (f"SP_FAKE_CRUMB={shlex.quote(str(crumb))} SP_FAKE_AGENT={WORKER} "
           + " ".join(shlex.quote(x) for x in (sys.executable, str(FAKE), str(log), "claude-code", typed)))
    got = c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha", "command": cmd, "label": WORKER})
    assert got.status_code == 201, got.text
    sid = got.json()["session"]["id"]
    _chat(root, WORKER, terminal=sid)
    termlib._link_cache = (None, 0.0, {})
    deadline = time.time() + 10
    while time.time() < deadline:
        if "fake agent ready" in termlib.capture(root, sid)["text"] and crumb.exists():
            return sid, log
        time.sleep(0.1)
    raise AssertionError(f"the fake agent did not start: {termlib.capture(root, sid)['text']!r}")


def _lines(log: Path, want: int, wait: float = 5.0) -> list[str]:
    deadline = time.time() + wait
    lines: list[str] = []
    while time.time() < deadline:
        lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        if len(lines) >= want:
            break
        time.sleep(0.05)
    return lines


def _type_when_idle(root: Path, wait: float = 5.0) -> int:
    deadline = time.time() + wait
    typed = 0
    while time.time() < deadline and not typed:
        typed = msgdeliver.retry_waiting(root)
        if not typed:
            time.sleep(0.2)
    return typed


@needs_tmux
def test_stop_in_an_sp_terminal_leaves_the_message_to_one_typed_prompt(term) -> None:
    c, root, work, port = term
    # The operator is typing, so the server types nothing when it is sent.
    sid, log = _agent(c, root, work, typed="half typed")
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="look at the lock #task")
    typed, why = msgdeliver.try_terminal(root, row["id"])
    assert not typed and "input line" in why
    env = _env(SP_TERMINAL=sid, SP_PORT=port)
    assert "decision" not in _stop(root, env)
    assert msgledger.find(root, row["id"])["delivered_via"] == ""  # type: ignore[index]
    verdict = c.get(f"/api/messages/terminal?agent_id={WORKER}").json()
    assert verdict["types"] is True and verdict["terminal"] == sid and verdict["why"] == ""
    # The line is cleared: the next round types the notice, once.
    Path(str(log) + ".clear").write_text("", encoding="utf-8")
    assert _type_when_idle(root) == 1
    assert _lines(log, 1) == [msgledger.wake_text(row)]
    assert msgdeliver.retry_waiting(root) == 0 and "decision" not in _stop(root, env)
    time.sleep(0.5)
    assert _lines(log, 2, wait=0.3) == [msgledger.wake_text(row)]
    got = msgledger.find(root, row["id"])
    assert got is not None and got["delivered_via"] == "terminal" and not got["landed_at"]
    # The typed notice comes in as the prompt: landed, as today; then the inbox reads it.
    _hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": SESSION, "prompt": msgledger.wake_text(row)}, env)
    got = msgledger.find(root, row["id"])
    assert got is not None and got["landed_at"] and got["delivered_via"] == "terminal" and not got["read_at"]
    assert [m["id"] for m in msgledger.inbox(root, WORKER)["unread"]] == [row["id"]]
    assert msgledger.find(root, row["id"])["read_at"]  # type: ignore[index]


@needs_tmux
def test_a_line_left_half_typed_hands_the_message_to_the_next_prompt(term) -> None:
    c, root, work, port = term
    sid, log = _agent(c, root, work, typed="half typed")
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="x")
    env = _env(SP_TERMINAL=sid, SP_PORT=port)
    assert "decision" not in _stop(root, env)
    assert msgdeliver.retry_waiting(root) == 0  # still typing: it waits
    out = _hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": SESSION,
                       "prompt": "the operator's own prompt"}, env).stdout
    assert msgledger.wake_text(row) in out
    assert msgledger.find(root, row["id"])["delivered_via"] == "hook"  # type: ignore[index]
    Path(str(log) + ".clear").write_text("", encoding="utf-8")
    time.sleep(0.5)
    assert msgdeliver.retry_waiting(root) == 0 and not log.exists()


@needs_tmux
@pytest.mark.parametrize("in_sp_terminal", [True, False], ids=["sp-terminal", "foreign-stop"])
def test_stop_and_the_typer_at_once_deliver_each_message_once(term, in_sp_terminal: bool) -> None:
    """50 messages, each with the Stop hook and the terminal's typer started
    together. In the SP terminal the hook never blocks and each is typed
    once; with a Stop that blocks (the hook not in that terminal) either the
    block or the typed prompt takes it, never both."""
    c, root, work, port = term
    sid, log = _agent(c, root, work)
    env = _env(SP_TERMINAL=sid, SP_PORT=port) if in_sp_terminal else _env(SP_PORT=port)
    typed_total = 0
    for i in range(RACE_RUNS):
        row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text=f"race {i}")
        result = _all_at_once({"stop": functools.partial(_stop, root, env),
                               "typed": functools.partial(msgdeliver.try_terminal, root, row["id"])})
        typed = result["typed"][0]
        blocked = result["stop"].get("decision") == "block"
        if in_sp_terminal:
            assert not blocked, result
            if not typed:  # the screen was mid-redraw: the next round types it
                typed = _type_when_idle(root) == 1
            assert typed
        else:
            assert typed != blocked, (typed, result)
            if blocked:
                assert row["id"] in result["stop"]["reason"]
        typed_total += typed
        got = msgledger.find(root, row["id"])
        assert got is not None and got["delivered_via"] == ("stop" if blocked else "terminal")
        lines = _lines(log, typed_total)
        assert len(lines) == typed_total, (i, lines)
        assert lines.count(msgledger.wake_text(row)) == (1 if typed else 0)
    time.sleep(0.5)
    assert len(_lines(log, typed_total + 1, wait=0.3)) == typed_total
    assert msgdeliver.retry_waiting(root) == 0
