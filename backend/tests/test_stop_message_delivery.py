"""A waiting message at Claude Code's Stop (tk_40450bfa).

Claude Code labels every blocked Stop as a problem ("Stop hook reported a
problem"). In Slightly Parallel's own terminal the Stop hook no longer
blocks for a message: the server types it as the next prompt once the input
line is empty. Where the block stays, its reason opens with a line saying it
is a message, not an error. The inbox delivers each message body once.
Races are run many times, in a sandbox tmux (SHELL=/bin/sh)
with a stand-in for the agent's input box. No real agent runs."""

from __future__ import annotations

import functools
from contextlib import nullcontext
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
from datetime import datetime, timedelta
from http.client import IncompleteRead
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi.testclient import TestClient

from backend import msgdeliver, msgledger, pingstate, termlib
from backend.server import create_app

_HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"
_HOOK = _HOOKS / "claude-code-capture.py"
FAKE = Path(__file__).resolve().parent / "fixtures" / "fake_agent_prompt.py"
needs_tmux = pytest.mark.skipif(termlib.tmux_path() is None or os.name == "nt", reason="tmux is not installed")

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


def _verdict(client: TestClient, root: Path, sid: str, *, agent: str = WORKER, owner: str = WORKER):
    key = root / "projects" / "alpha" / "chats" / owner / msgledger.STOP_TOKEN_FILE
    if not key.exists():
        key.write_text(json.dumps({"token": "f" * 64}), encoding="utf-8")
    token = json.loads(key.read_text(encoding="utf-8"))["token"]
    return client.get("/api/messages/terminal", params={"agent_id": agent, "terminal": sid},
                      headers={msgledger.STOP_PROOF_HEADER: msgledger.stop_proof(root, token)})


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


@pytest.mark.parametrize(("copy_mode", "screen"), [
    ("1", ""),
    ("0", "─────\n❯ half typed\n─────"),
])
def test_stop_does_not_defer_to_another_chats_pane(root, monkeypatch, copy_mode, screen):
    _chat(root, WORKER, terminal="t0000aaaa")
    monkeypatch.setattr(termlib, "tmux_path", lambda: "tmux")
    monkeypatch.setattr(termlib, "get", lambda *_: {"backend": "tmux"})
    monkeypatch.setattr(msgdeliver, "_pane", lambda *_: {
        "fg": "claude", "in_mode": copy_mode, "dead": "0", "pid": "42",
        "id": "%0", "session": "$0", "attached": "0", "clients": "", "linked": "0", "sync": "0", "input_off": "0",
        "active": "1", "window_active": "1", "cursor_x": "0", "cursor_y": "1", "width": "80",
    })
    monkeypatch.setattr(termlib, "tmux_read", lambda *_: subprocess.CompletedProcess([], 0, screen))
    monkeypatch.setattr(msgdeliver, "occupant_why", lambda *_: "another chat holds this pane")
    assert msgdeliver.stop_leaves(root, WORKER)[1] == "another chat holds this pane"


@pytest.mark.parametrize(("status", "screen", "may_defer"), [
    (1, "", False),
    (0, "❯ 1. Yes", False),
    (0, "─────\n❯ half typed\n  second line\n─────", True),
])
def test_stop_defers_only_when_it_can_identify_the_input_box(root, monkeypatch, status, screen, may_defer):
    _chat(root, WORKER, terminal="t0000aaaa")
    monkeypatch.setattr(termlib, "tmux_path", lambda: "tmux")
    monkeypatch.setattr(termlib, "get", lambda *_: {"backend": "tmux"})
    monkeypatch.setattr(msgdeliver, "_pane", lambda *_: {
        "fg": "claude", "in_mode": "0", "dead": "0", "pid": "42",
        "id": "%0", "session": "$0", "attached": "0", "clients": "", "linked": "0", "sync": "0", "input_off": "0",
        "active": "1", "window_active": "1", "cursor_x": "0", "cursor_y": "1", "width": "80",
    })
    monkeypatch.setattr(termlib, "tmux_read", lambda *_: subprocess.CompletedProcess([], status, screen))
    monkeypatch.setattr(msgdeliver, "occupant_why", lambda *_: "")
    assert (msgdeliver.stop_leaves(root, WORKER)[1] == "") is may_defer


@pytest.mark.parametrize("why_not", ["old", "strayed"])
def test_stop_keeps_the_wake_for_a_message_the_retry_loop_will_not_take(root, monkeypatch, why_not):
    monkeypatch.setattr(msgdeliver, "check", lambda *_: ("t0000aaaa", ""))
    fresh = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="still retryable")
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="use Stop")
    with msgledger.editing(root) as rows:
        if why_not == "strayed":
            rows[-1]["strayed"] = "cc-other"
        else:
            rows[-1]["sent_at"] = (datetime.now() - timedelta(days=2)).isoformat()
    assert msgledger.stop_waiting(root, WORKER)
    assert msgledger.waiting(root) == [fresh]
    assert msgdeliver.stop_leaves(root, WORKER)[1]
    assert msgledger.wake_text(fresh) in msgledger.stop_notice(root, WORKER)
    assert msgledger.find(root, row["id"])["delivered_via"] == "stop"


@pytest.mark.parametrize(("interrupted", "recover_via"), [
    ("load-buffer", "terminal"),
    ("if-shell", "hook"),
    ("if-shell", "inbox"),
])
def test_after_a_crash_the_message_arrives_once_by_terminal_next_prompt_or_inbox(
    root, monkeypatch, interrupted, recover_via,
):
    sid = "t0000aaaa"
    _chat(root, WORKER, terminal=sid)
    pane = {"id": "%0", "session": "$0", "pid": "42", "fg": "claude", "attached": "0", "clients": "",
            "cursor_y": "0", "cursor_x": "0", "width": "80"}
    monkeypatch.setattr(msgdeliver, "_check", lambda *_, **__: (sid, pane, ""))
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="recover me")
    calls = []

    def tmux(_root, command, *_args, **_kw):
        calls.append(command)
        if command == interrupted and calls.count(command) == 1:
            raise SystemExit("sender exited")
        return subprocess.CompletedProcess([], 0, "sent")

    monkeypatch.setattr(termlib, "tmux", tmux)
    with pytest.raises(SystemExit):
        msgdeliver.try_terminal(root, row["id"])
    assert not msgledger.find(root, row["id"])["delivered_via"]
    if recover_via == "terminal":
        assert msgdeliver.retry_waiting(root) == 1
        assert msgledger.find(root, row["id"])["delivered_via"] == "terminal"
    else:
        assert msgdeliver.retry_waiting(root) == 0
        def prompt(text: str):
            return _hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": SESSION,
                                "prompt": text}, _env()).stdout

        notice = msgledger.wake_text(row)
        if recover_via == "hook":
            assert prompt("the operator's next prompt").count(notice) == 1
        else:
            assert [r["id"] for r in msgledger.inbox(root, WORKER)["unread"]] == [row["id"]]
        late = prompt(notice)
        assert "Read it first with MCP tool messages" not in late
        assert "Answer it when it asks" not in late
        assert "already delivered" in late
        saved = msgledger.find(root, row["id"])
        assert saved is not None and saved["delivered_via"] == recover_via and saved["landed_at"]
        chat = root / "projects" / "alpha" / "chats" / WORKER / "chat.md"
        assert f'<sp-message from="{COORD}" id="{row["id"]}">' in chat.read_text(encoding="utf-8")
        if recover_via == "hook":
            assert [r["id"] for r in msgledger.inbox(root, WORKER)["unread"]] == [row["id"]]
        assert not msgledger.inbox(root, WORKER)["unread"]
    assert calls.count("if-shell") == 1
    assert msgdeliver.retry_waiting(root) == 0


@pytest.mark.parametrize("delivered_via", ["hook", "inbox"])
def test_a_late_stray_does_not_reopen_a_delivered_message(root, delivered_via):
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="already delivered")
    mid = row["id"]
    assert msgledger.claim_terminal(root, mid, "t0000aaaa") is not None
    assert msgledger.begin_terminal(root, mid)
    msgledger.finish_terminal(root, mid)
    if delivered_via == "hook":
        assert [r["id"] for r in msgledger.claim_for_hook(root, WORKER)] == [mid]
    else:
        assert [r["id"] for r in msgledger.inbox(root, WORKER)["unread"]] == [mid]

    assert msgledger.take_stray(root, "cc-other", msgledger.wake_text(row)) is not None
    saved = msgledger.find(root, mid)
    assert saved is not None and saved["delivered_via"] == delivered_via and saved["strayed"]
    assert not msgledger.stop_waiting(root, WORKER)
    assert msgledger.stop_notice(root, WORKER) == ""
    assert msgledger.claim_for_hook(root, WORKER) == []
    assert [r["id"] for r in msgledger.inbox(root, WORKER)["unread"]] == ([mid] if delivered_via == "hook" else [])


def test_two_terminal_sends_cannot_overlap_in_one_pane(root, monkeypatch):
    sid = "t0000aaaa"
    _chat(root, WORKER, terminal=sid)
    pane = {"id": "%0", "session": "$0", "pid": "42", "fg": "claude", "attached": "0", "clients": "",
            "cursor_y": "0", "cursor_x": "0", "width": "80"}
    monkeypatch.setattr(msgdeliver, "_check", lambda *_, **__: (sid, pane, ""))
    first, second = [msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text=text)
                     for text in ("first", "second")]
    pasting = threading.Event()
    finish = threading.Event()
    results = []

    def tmux(_root, command, *_args, **_kw):
        if command == "if-shell" and not pasting.is_set():
            pasting.set()
            assert finish.wait(timeout=5)
        return subprocess.CompletedProcess([], 0, "sent")

    monkeypatch.setattr(termlib, "tmux", tmux)
    thread = threading.Thread(target=lambda: results.append(msgdeliver.try_terminal(root, first["id"])))
    thread.start()
    try:
        assert pasting.wait(timeout=5)
        assert not msgdeliver.try_terminal(root, second["id"])[0]
        assert not msgledger.find(root, second["id"])["delivered_via"]
    finally:
        finish.set()
        thread.join(timeout=5)
    assert results == [(True, "")]
    assert msgdeliver.retry_waiting(root) == 1


@pytest.mark.parametrize("config_text", [None, "# the previous config\n"], ids=["absent", "stale"])
def test_terminal_verdict_leaves_tmux_config_untouched(root, monkeypatch, config_text):
    sid = "t0000aaaa"
    _chat(root, WORKER, terminal=sid)
    termlib.put(root, {"id": sid, "backend": "tmux"})
    config = termlib.folder(root) / "tmux.conf"
    if config_text is not None:
        config.write_text(config_text, encoding="utf-8")
    commands = []

    def tmux(argv, **_kwargs):
        commands.append(argv)
        return subprocess.CompletedProcess(argv, 1, "")

    monkeypatch.setattr(termlib, "tmux_path", lambda: "tmux")
    monkeypatch.setattr(termlib.subprocess, "run", tmux)
    with TestClient(create_app(data_root=root, watch=False, run_monitor=False)) as client:
        response = _verdict(client, root, sid)
    assert response.status_code == 200 and response.json()["types"] is False
    assert (config.read_text(encoding="utf-8") if config.exists() else None) == config_text
    assert len(commands) == 1 and "display-message" in commands[0]


def test_terminal_verdict_rejects_an_unscoped_lookup(root, monkeypatch):
    def unexpected(*_args):
        pytest.fail("an unauthenticated lookup inspected a terminal")

    monkeypatch.setattr(msgdeliver, "stop_leaves", unexpected)
    with TestClient(create_app(data_root=root, watch=False, run_monitor=False)) as client:
        response = client.get("/api/messages/terminal", params={"agent_id": WORKER})
        other_chat = _verdict(client, root, "t0000aaaa", agent=COORD)
    assert response.status_code == 403
    assert other_chat.status_code == 403
    assert str(root) not in response.text and WORKER not in response.text


@pytest.mark.parametrize("payload", [
    None,
    {"types": True, "terminal": "t0000bbbb", "data_root": "another root"},
], ids=["truncated", "unbound-legacy-verdict"])
def test_stop_falls_back_if_the_terminal_verdict_is_unreliable(root, monkeypatch, payload):
    from urllib import request

    spec = importlib.util.spec_from_file_location("sp_cc_stop_msg", _HOOK)
    cc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cc)
    sid = "t0000aaaa"
    _chat(root, WORKER, terminal=sid)
    monkeypatch.setenv("SP_TERMINAL", sid)
    meta = root / "projects" / "alpha" / "chats" / WORKER / "meta.json"

    class Truncated(io.BytesIO):
        def read(self, *_args, **_kwargs):
            raise IncompleteRead(b'{"types":')

    class Opener:
        def open(self, *_args, **_kwargs):
            return Truncated() if payload is None else io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(request, "build_opener", lambda *_: Opener())
    assert cc.terminal_types(str(root), WORKER, meta) is False


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
    def terminal(mid):
        if msgledger.claim_terminal(root, mid, "t0000aaaa") is None:
            return False
        assert msgledger.begin_terminal(root, mid)
        msgledger.finish_terminal(root, mid, sent=True)
        return True

    for _ in range(RACE_RUNS):
        msg_id = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="race")["id"]
        won = _all_at_once({"stop": lambda: msgledger.stop_notice(root, WORKER, opening=True),
                            "terminal": functools.partial(terminal, msg_id),
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


def _agent(c: TestClient, root: Path, work: Path, typed: str = "", *,
           live_input: bool = False) -> tuple[str, Path]:
    """The stand-in for Claude Code in an SP terminal, its meta naming that
    terminal and its breadcrumb holding the pane's shell (what the hook
    writes on a prompt)."""
    log = work / "worker.log"
    crumb = root / ".sessions" / "f0f0f0f0f0f0" / f"{WORKER}.json"
    cmd = (f"SP_FAKE_CRUMB={shlex.quote(str(crumb))} SP_FAKE_AGENT={WORKER} "
           + ("SP_FAKE_LIVE_INPUT=1 " if live_input else "")
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
    assert _verdict(c, root, sid).json() == {"types": True}
    assert _verdict(c, root, "t0000bbbb").json() == {"types": False}
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
def test_automatic_delivery_can_wait_for_the_next_prompt_and_inbox_while_typing(term) -> None:
    c, root, work, port = term
    sid, log = _agent(c, root, work, typed="half typed")
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="x")
    env = _env(SP_TERMINAL=sid, SP_PORT=port)
    assert "decision" not in _stop(root, env)
    for _ in range(3):
        assert msgdeliver.retry_waiting(root) == 0
    out = _hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": SESSION,
                       "prompt": "the operator's own prompt"}, env).stdout
    assert msgledger.wake_text(row) in out
    assert msgledger.find(root, row["id"])["delivered_via"] == "hook"  # type: ignore[index]
    assert [(m["id"], m["text"]) for m in msgledger.inbox(root, WORKER)["unread"]] == [(row["id"], "x")]
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


@needs_tmux
def test_keep_alive_through_the_tty_and_capture_hook(term) -> None:
    client, root, work, port = term
    pane, log = _agent(client, root, work, live_input=True)
    _chat(root, WORKER, terminal=pane, message_count=1)
    pingstate.enroll(root, WORKER, enabled=True)
    assert msgdeliver.ping_due(root) == 1
    typed = _lines(log, 1)
    assert len(typed) == 1 and typed[0].endswith(" Reply with one word.")
    assert msgledger.inbox(root, WORKER)["unread"] == []
    env = _env(SP_TERMINAL=pane, SP_PORT=port)
    prompt = _hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": SESSION, "prompt": typed[0]}, env)
    assert not prompt.stdout and not prompt.stderr
    assert _stop(root, env) == {}
    folder = root / "projects" / "alpha" / "chats" / WORKER
    assert " · ping\n" in (folder / "chat.md").read_text(encoding="utf-8")
    assert json.loads((folder / "turns.jsonl").read_text(encoding="utf-8"))["ping"]
    assert not (folder / "work.jsonl").exists()
    assert msgdeliver.ping_due(root) == 0


@needs_tmux
@pytest.mark.parametrize("change", ["pane-selection", "foreign-client"])
def test_terminal_send_aborts_if_ownership_changes_after_screen_read(term, monkeypatch, change):
    client, root, work, _ = term
    sid, original_log = _agent(client, root, work)
    target = termlib.PREFIX + sid
    tmux_read = termlib.tmux_read
    other = ""
    foreign = None
    if change == "pane-selection":
        # A real second pane. The original is still the selected pane while
        # we prove the chat and read its composer.
        other_log = work / "other.log"
        command = " ".join(shlex.quote(x) for x in (sys.executable, str(FAKE), str(other_log), "claude-code"))
        second = termlib.tmux(root, "split-window", "-d", "-P", "-F", "#{pane_id}", "-t", target, command)
        assert second.returncode == 0
        other = second.stdout.strip()
    reads = 0

    def switch_after_observation(data, *args, **kwargs):
        nonlocal reads, foreign
        result = tmux_read(data, *args, **kwargs)
        if args and args[0] == "capture-pane":
            reads += 1
            if reads == 2:
                if change == "pane-selection":
                    assert termlib.tmux(root, "select-pane", "-t", other).returncode == 0
                else:
                    foreign = subprocess.Popen(
                        termlib.tmux_argv(root, "-C", "attach-session", "-t", target),
                        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                    deadline = time.monotonic() + 5
                    while not tmux_read(root, "list-clients", "-t", target).stdout.strip():
                        assert foreign.poll() is None and time.monotonic() < deadline
                        threading.Event().wait(0.01)
        return result

    monkeypatch.setattr(termlib, "tmux_read", switch_after_observation)
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="do not type")
    try:
        assert not msgdeliver.try_terminal(root, row["id"])[0]
        assert reads == 2
        assert not original_log.exists()
        if other:
            assert row["id"] not in tmux_read(root, "capture-pane", "-p", "-t", other).stdout
            assert not other_log.exists()
        saved = msgledger.find(root, row["id"])
        assert saved is not None and msgledger.retryable(saved)
    finally:
        if foreign is not None:
            foreign.terminate()
            foreign.wait(timeout=5)
            if foreign.stdin is not None:
                foreign.stdin.close()


@needs_tmux
@pytest.mark.parametrize("path", ["http", "websocket"])
def test_operator_input_queued_while_delivery_checks_takes_priority(term, monkeypatch, path):
    client, root, work, _ = term
    sid, log = _agent(client, root, work)
    target = termlib.PREFIX + sid
    tmux_read = termlib.tmux_read
    writer = None
    started = threading.Event()
    reads = 0
    token = client.get("/api/terminal/state").json()["token"]
    context = client.websocket_connect(f"/ws/terminal/{sid}?token={token}") if path == "websocket" else nullcontext(None)

    def inspect_then_type(data, *args, **kwargs):
        nonlocal writer, reads
        result = tmux_read(data, *args, **kwargs)
        if args and args[0] == "capture-pane":
            reads += 1
            if reads == 2:
                def type_draft():
                    started.set()
                    row = termlib.get(root, sid)
                    assert row is not None
                    if socket is None:
                        assert termlib.type_into(root, row, "operator draft", enter=False)
                    else:
                        socket.send_json({"type": "input", "data": "operator draft", "typed": True})

                writer = threading.Thread(target=type_draft)
                writer.start()
                assert started.wait(5)
                deadline = time.monotonic() + 5
                # The operator must reach the pane while this preflight is
                # still waiting, rather than when the delivery gives up.
                while "operator draft" not in tmux_read(root, "capture-pane", "-p", "-t", target).stdout:
                    assert time.monotonic() < deadline
                    threading.Event().wait(0.01)
        return result

    monkeypatch.setattr(termlib, "tmux_read", inspect_then_type)
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="stay in inbox")
    with context as socket:
        if socket is not None:
            _wait_for_registered_client(root, sid)
        try:
            assert not msgdeliver.try_terminal(root, row["id"])[0]
        finally:
            if writer is not None:
                writer.join(timeout=5)
        assert writer is not None and not writer.is_alive()
        deadline = time.monotonic() + 5
        while True:
            screen = tmux_read(root, "capture-pane", "-p", "-t", target).stdout
            if "operator draft" in screen:
                break
            assert time.monotonic() < deadline
            threading.Event().wait(0.01)
        assert row["id"] not in screen and not log.exists()


@pytest.mark.parametrize("continuation", ["another line of the draft", "› "])
def test_codex_draft_is_checked_beyond_its_first_continuation_row(continuation):
    screen = f"› \n\n   {continuation}\n\n  \x1b[2mfoo · ~/work\x1b[0m"
    assert not msgdeliver.input_empty(screen, "codex")


def _wait_for_registered_client(root: Path, sid: str) -> None:
    target = termlib.PREFIX + sid
    deadline = time.monotonic() + 5
    while not termlib.tmux_read(root, "list-clients", "-t", target).stdout.strip():
        assert time.monotonic() < deadline
        threading.Event().wait(0.01)


@needs_tmux
def test_delivery_still_uses_an_attached_sp_view(term):
    client, root, work, _ = term
    sid, log = _agent(client, root, work)
    token = client.get("/api/terminal/state").json()["token"]
    with client.websocket_connect(f"/ws/terminal/{sid}?token={token}"):
        _wait_for_registered_client(root, sid)
        row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="still automatic")
        ok, reason = msgdeliver.try_terminal(root, row["id"])
        assert ok, reason
        assert _lines(log, 1) == [msgledger.wake_text(row)]


@needs_tmux
def test_open_healthy_websocket_keeps_accepted_frames_in_order_during_delivery_contention(term, monkeypatch):
    client, root, work, _ = term
    sid, log = _agent(client, root, work)
    token = client.get("/api/terminal/state").json()["token"]
    real_lock = termlib.acquire_flock

    def short_default(path, **kwargs):
        # Reproduce the previous default deadline without a five-second sleep.
        kwargs.setdefault("timeout_s", 0)
        return real_lock(path, **kwargs)

    monkeypatch.setattr(termlib, "acquire_flock", short_default)
    entered, finished = threading.Event(), threading.Event()
    original = termlib.write_operator

    def observe(*args):
        entered.set()
        try:
            return original(*args)
        finally:
            finished.set()

    monkeypatch.setattr(termlib, "write_operator", observe)
    with client.websocket_connect(f"/ws/terminal/{sid}?token={token}") as socket:
        _wait_for_registered_client(root, sid)
        with real_lock(termlib.input_lock(root, sid)):
            socket.send_json({"type": "input", "data": "queued keys\r", "typed": True})
            assert entered.wait(5)
            # Both frames are on the same live socket before the first PTY write.
            socket.send_json({"type": "input", "data": "next keys\r", "typed": True})
            assert not finished.wait(0.15)
        assert finished.wait(5)
        assert _lines(log, 2) == ["queued keys", "next keys"]


@needs_tmux
def test_websocket_reports_uncertain_input_and_reconnect_never_replays_enter(term, monkeypatch, caplog):
    from backend.routers import terminal

    client, root, work, _ = term
    sid, log = _agent(client, root, work)
    token = client.get("/api/terminal/state").json()["token"]
    url = f"/ws/terminal/{sid}?token={token}"
    write = terminal.PtySession.write
    attempts = []

    def uncertain(session, data):
        if data == b"possibly typed\r":
            attempts.append(data)
            return "uncertain"
        return write(session, data)

    monkeypatch.setattr(terminal.PtySession, "write", uncertain)
    with client.websocket_connect(url) as socket:
        socket.receive_bytes()
        socket.send_bytes(b"possibly typed\r")
        # A second frame serves as a witness if the failed frame was ignored.
        socket.send_bytes(b"unexpected next key\r")
        while True:
            message = socket.receive()
            if message["type"] == "websocket.close":
                break
            assert b"unexpected next key" not in message.get("bytes", b"")
    assert message["code"] == 1011
    assert "uncertain" in message["reason"]
    assert "terminal input uncertain" in caplog.text
    with client.websocket_connect(url) as socket:
        socket.receive_bytes()
        socket.send_bytes(b"after reconnect\r")
        assert _lines(log, 1) == ["after reconnect"]
    assert attempts == [b"possibly typed\r"]


@needs_tmux
def test_terminal_send_defers_recent_operator_input_even_while_screen_looks_empty(term):
    client, root, work, _ = term
    sid, log = _agent(client, root, work)
    terminal = termlib.get(root, sid)
    assert terminal is not None
    # Writing a space leaves a screen that still parses as empty. Real input
    # can also be waiting in the TUI's queue when the capture happens.
    assert termlib.type_into(root, terminal, " ", enter=False)
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="later")
    assert not msgdeliver.try_terminal(root, row["id"])[0]
    saved = msgledger.find(root, row["id"])
    assert saved is not None and msgledger.retryable(saved)
    assert not log.exists()


@needs_tmux
def test_whitespace_draft_defers_delivery_until_the_composer_is_ready(term):
    client, root, work, _ = term
    sid, log = _agent(client, root, work, typed="   ")
    assert not termlib.operator_editing(root, sid)
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="later")
    assert not msgdeliver.try_terminal(root, row["id"])[0]
    assert not log.exists()

    log.with_suffix(".log.clear").touch()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and msgdeliver.check(root, WORKER)[1]:
        time.sleep(0.05)
    sent, why = msgdeliver.try_terminal(root, row["id"])
    assert sent, why
    assert _lines(log, 1) == [msgledger.wake_text(row)]


@needs_tmux
@pytest.mark.parametrize("changed_late", [False, True], ids=["initial", "before-submit"])
def test_automatic_enter_never_reaches_a_synchronized_sibling(term, monkeypatch, changed_late):
    client, root, work, _ = term
    sid, log = _agent(client, root, work)
    target = termlib.PREFIX + sid
    other_log = work / "sibling.log"
    command = " ".join(shlex.quote(x) for x in (sys.executable, str(FAKE), str(other_log), "claude-code"))
    other = termlib.tmux(root, "split-window", "-d", "-P", "-F", "#{pane_id}", "-t", target, command)
    assert other.returncode == 0
    sibling = other.stdout.strip()
    read = termlib.tmux_read
    deadline = time.monotonic() + 5
    while "fake agent ready" not in read(root, "capture-pane", "-p", "-t", sibling).stdout:
        assert time.monotonic() < deadline
        threading.Event().wait(0.01)
    assert termlib.tmux(root, "send-keys", "-l", "-t", sibling, "sibling draft").returncode == 0

    def enable() -> None:
        assert termlib.tmux(root, "set-window-option", "-t", target, "synchronize-panes", "on").returncode == 0

    captures = 0

    def change_after_screen(data, *args, **kwargs):
        nonlocal captures
        result = read(data, *args, **kwargs)
        if args[0] == "capture-pane":
            captures += 1
            if captures == 2:
                enable()
        return result

    if changed_late:
        monkeypatch.setattr(termlib, "tmux_read", change_after_screen)
    else:
        enable()
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="only in its own pane")
    assert not msgdeliver.try_terminal(root, row["id"])[0]
    assert captures == (2 if changed_late else 0)
    assert not log.exists() and not other_log.exists()
    assert "sibling draft" in read(root, "capture-pane", "-p", "-t", sibling).stdout
    saved = msgledger.find(root, row["id"])
    assert saved is not None and msgledger.retryable(saved)


@needs_tmux
@pytest.mark.parametrize("changed_late", [False, True], ids=["initial", "before-submit"])
def test_input_disabled_pane_cannot_confirm_delivery(term, monkeypatch, changed_late):
    client, root, work, _ = term
    sid, log = _agent(client, root, work)
    target = termlib.PREFIX + sid
    read = termlib.tmux_read
    pane = read(root, "display-message", "-p", "-t", target, "#{pane_id}").stdout.strip()

    def disable() -> None:
        assert termlib.tmux(root, "select-pane", "-d", "-t", pane).returncode == 0

    captures = 0

    def change_after_screen(data, *args, **kwargs):
        nonlocal captures
        result = read(data, *args, **kwargs)
        if args[0] == "capture-pane":
            captures += 1
            if captures == 2:
                disable()
        return result

    if changed_late:
        monkeypatch.setattr(termlib, "tmux_read", change_after_screen)
    else:
        disable()
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="will be retried")
    assert not msgdeliver.try_terminal(root, row["id"])[0]
    assert not log.exists()
    saved = msgledger.find(root, row["id"])
    assert saved is not None and not saved["delivered_via"] and msgledger.retryable(saved)
    assert termlib.tmux(root, "select-pane", "-e", "-t", pane).returncode == 0
    assert msgdeliver.try_terminal(root, row["id"])[0]
    assert _lines(log, 1) == [msgledger.wake_text(row)]


@pytest.mark.parametrize(("field", "value"), [
    ("cursor_x", ""), ("cursor_y", "unavailable"), ("width", ""), ("width", "0"),
    ("active", ""), ("window_active", ""),
])
def test_terminal_check_requires_positive_pane_features(root, monkeypatch, field, value):
    sid = "t0000aaaa"
    _chat(root, WORKER, terminal=sid)
    pane = {"id": "%0", "session": "$0", "pid": "42", "fg": "claude", "attached": "0", "clients": "",
            "dead": "0", "linked": "0", "in_mode": "0", "sync": "0", "input_off": "0",
            "cursor_y": "0", "cursor_x": "0", "width": "80", "active": "1", "window_active": "1"}
    pane[field] = value
    monkeypatch.setattr(termlib, "tmux_path", lambda: "tmux")
    monkeypatch.setattr(termlib, "get", lambda *_: {"backend": "tmux"})
    monkeypatch.setattr(msgdeliver, "_pane", lambda *_: pane)
    monkeypatch.setattr(msgdeliver, "occupant_why", lambda *_: "")
    monkeypatch.setattr(termlib, "tmux_read", lambda *_: subprocess.CompletedProcess([], 0, "─────\n❯ \n─────"))
    assert msgdeliver.check(root, WORKER)[1]
