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

from backend import msgdeliver, msgledger, termlib
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
    ("send-keys", "hook"),
    ("send-keys", "inbox"),
])
def test_after_a_crash_the_message_arrives_once_by_terminal_next_prompt_or_inbox(
    root, monkeypatch, interrupted, recover_via,
):
    sid = "t0000aaaa"
    _chat(root, WORKER, terminal=sid)
    monkeypatch.setattr(msgdeliver, "check", lambda *_: (sid, ""))
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="recover me")
    calls = []

    def tmux(_root, command, *_args, **_kw):
        calls.append(command)
        if command == interrupted and calls.count(command) == 1:
            raise SystemExit("sender exited")
        return subprocess.CompletedProcess([], 0)

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
    assert calls.count("send-keys") == 1
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
    monkeypatch.setattr(msgdeliver, "check", lambda *_: (sid, ""))
    first, second = [msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text=text)
                     for text in ("first", "second")]
    pasting = threading.Event()
    finish = threading.Event()
    results = []

    def tmux(_root, command, *_args, **_kw):
        if command == "paste-buffer" and not pasting.is_set():
            pasting.set()
            assert finish.wait(timeout=5)
        return subprocess.CompletedProcess([], 0)

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
