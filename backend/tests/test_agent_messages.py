"""Messages between agents (tk_c1caab80): the ledger, the routes, the MCP
tools, and the decision to type into a terminal (a real one, in a sandbox
tmux). The hook that reads the marker: test_agent_message_hook.py."""

from __future__ import annotations

import csv
import json
import shlex
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend import mcp, msgdeliver, msgledger, termlib
from backend import server as _server
from backend.server import MCP_NEEDS_AGENT, create_app

FAKE = Path(__file__).resolve().parent / "fixtures" / "fake_agent_prompt.py"
TMUX = termlib.tmux_path() is not None
needs_tmux = pytest.mark.skipif(not TMUX, reason="tmux is not installed")

COORD = "cc-c00rd001"
WORKER = "cc-w0rker01"
CODEX = "codex-0c0dex01"


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


@pytest.fixture()
def client(root: Path):
    with TestClient(create_app(data_root=root, watch=False, run_monitor=False)) as c:
        yield c


def _send(c: TestClient, sender: str | None, to: str, text: str, **more: Any):
    body: dict[str, Any] = {"to": to, "text": text, **more}
    headers = {}
    if sender:
        body["agent_id"] = sender
        headers = {mcp.VIA_HEADER: mcp.VIA_VALUE}
    return c.post("/api/messages", json=body, headers=headers)


# ---------------------------------------------------------------------------
# The ledger
# ---------------------------------------------------------------------------


def test_a_message_is_kept_and_the_inbox_marks_it_read(root: Path) -> None:
    a = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="look at the hook")
    b = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="and the tests")
    assert msgledger.ID_RE.match(a["id"]) and a["id"] != b["id"]
    assert [r["delivered_via"] for r in msgledger.read_rows(root)] == ["", ""]
    got = msgledger.inbox(root, WORKER)
    assert [m["text"] for m in got["unread"]] == ["look at the hook", "and the tests"]
    assert got["recent"] == []
    again = msgledger.inbox(root, WORKER)
    assert again["unread"] == []
    assert {m["id"] for m in again["recent"]} == {a["id"], b["id"]}
    rows = msgledger.read_rows(root)
    assert all(r["delivered_via"] == "inbox" and r["read_at"] for r in rows)
    # Another chat's inbox holds none of them.
    assert msgledger.inbox(root, COORD) == {"unread": [], "recent": []}


def test_text_with_commas_quotes_and_lines_survives_the_ledger(root: Path) -> None:
    text = 'one, "two"\nthree\n#task not a command'
    msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text=text)
    assert msgledger.read_rows(root)[0]["text"] == text


def test_a_ledger_that_cannot_be_read_is_not_written_over(root: Path) -> None:
    # A field past the csv module's limit: the reader raises csv.Error.
    path = msgledger.ledger_path(root)
    damaged = "id,text\nmsg_00000001," + "x" * 200_000 + "\n"
    path.write_text(damaged, encoding="utf-8")
    with pytest.raises(csv.Error):
        msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="x")
    assert path.read_text(encoding="utf-8") == damaged


def test_control_characters_never_reach_a_terminal(client: TestClient, root: Path) -> None:
    r = _send(client, COORD, WORKER, "a\x1b[201~\rrm -rf ~\r\nb\tc\x07")
    assert r.status_code == 201
    assert msgledger.read_rows(root)[0]["text"] == "a[201~\nrm -rf ~\nb\tc"


# ---------------------------------------------------------------------------
# The routes and the MCP tools
# ---------------------------------------------------------------------------


def test_an_agent_sends_and_the_ledger_names_it(client: TestClient, root: Path) -> None:
    r = _send(client, COORD, WORKER, "check the marker")
    assert r.status_code == 201, r.text
    m = r.json()["message"]
    assert (m["from_agent"], m["to_agent"], m["project"], m["text"]) == (COORD, WORKER, "alpha", "check the marker")
    # No terminal here: it waits for the hook or the inbox.
    assert r.json()["delivered_via"] == "" and "next prompt" in r.json()["waiting"]
    listed = client.get(f"/api/messages?agent_id={WORKER}").json()
    assert listed["total"] == 1 and listed["messages"][0]["id"] == m["id"]


def test_the_operator_sends_from_the_page(client: TestClient) -> None:
    r = _send(client, None, WORKER, "from the page")
    assert r.status_code == 201, r.text
    assert r.json()["message"]["from_agent"] == msgledger.OPERATOR


def test_refusals_write_nothing(client: TestClient, root: Path) -> None:
    assert _send(client, COORD, "cc-nobody00", "x").status_code == 404
    assert _send(client, COORD, COORD, "to myself").status_code == 422
    assert _send(client, COORD, WORKER, "   ").status_code == 422
    assert _send(client, COORD, WORKER, "x" * (msgledger.TEXT_MAX + 1)).status_code == 422
    assert _send(client, COORD, WORKER, "x", reply_to="msg_00000000").status_code == 404
    assert _send(client, COORD, "", "x").status_code == 422
    assert not msgledger.ledger_path(root).exists()


def test_a_reply_names_the_message_it_answers(client: TestClient) -> None:
    first = _send(client, COORD, WORKER, "what broke?").json()["message"]
    r = _send(client, WORKER, COORD, "the lock", reply_to=first["id"])
    assert r.status_code == 201 and r.json()["message"]["reply_to"] == first["id"]


class _Api(mcp.Api):
    def __init__(self, c: TestClient) -> None:
        super().__init__("http://testserver")
        self.c = c

    def _call(self, method: str, path: str, body: dict | None = None) -> Any:
        r = self.c.request(method, path, json=body, headers={mcp.VIA_HEADER: mcp.VIA_VALUE})
        if r.status_code >= 400:
            raise mcp.ApiError(f"{r.status_code}: {r.json().get('detail', '')}")
        return r.json()


def test_the_mcp_tools_stamp_the_agent_and_cannot_send_as_the_operator(root: Path, monkeypatch) -> None:
    monkeypatch.setattr(_server.AgentsViaMcp, "_enforced", lambda self: True)
    with TestClient(create_app(data_root=root, watch=False, run_monitor=False)) as c:
        def as_agent(agent: str) -> mcp.Translator:
            tr = mcp.Translator(_Api(c), cwd=str(root))
            monkeypatch.setattr(tr, "identity", lambda: {"project": "alpha", "agent_id": agent})
            return tr

        # What the model sends as its own name is written over.
        sent = as_agent(COORD).call("message", {"to": WORKER, "text": "hello", "agent_id": "operator",
                                                "from": "operator"})
        assert sent["message"]["from_agent"] == COORD
        got = as_agent(WORKER).call("messages", {})
        assert [m["text"] for m in got["unread"]] == ["hello"] and "reply_to" in got["how_to_reply"]
        assert as_agent(WORKER).call("messages", {})["unread"] == []
        reply = as_agent(WORKER).call("message", {"to": COORD, "text": "hi back", "reply_to": sent["message"]["id"]})
        assert reply["message"]["reply_to"] == sent["message"]["id"]
        # The mark with no agent — a hand-made request as the operator — is refused.
        r = c.post("/api/messages", json={"to": WORKER, "text": "as the operator"},
                   headers={mcp.VIA_HEADER: mcp.VIA_VALUE})
        assert r.status_code == 403 and r.json()["detail"] == MCP_NEEDS_AGENT
        # An agent over plain HTTP, past the translator, is refused too.
        c.cookies.clear()
        r = c.post("/api/messages", json={"to": WORKER, "text": "raw", "agent_id": COORD})
        assert r.status_code == 422
        assert [m["text"] for m in msgledger.read_rows(root)] == ["hello", "hi back"]


def test_the_operator_has_no_inbox(client: TestClient) -> None:
    assert client.post("/api/messages/inbox", json={}).status_code == 422


# ---------------------------------------------------------------------------
# Is the input line empty?
# ---------------------------------------------------------------------------

RULE = "\x1b[38;5;244m" + "─" * 60 + "\x1b[39m"


def _cc(row: str, under: str = RULE, top: str = RULE) -> str:
    return f"history\n{top}\n\x1b[39m❯ {row}\n{under}\n  ⏵⏵ auto mode on\n\n"


@pytest.mark.parametrize("screen, tool, empty", [
    (_cc(""), "claude-code", True),
    (_cc("", top="\x1b[38;5;244m" + "─" * 40 + " chat-name ─\x1b[39m"), "claude-code", True),
    (_cc("half typed"), "claude-code", False),
    (_cc("", under="  second line of input"), "claude-code", False),
    (_cc("\x1b[2mTry \"fix the tests\"\x1b[0m"), "claude-code", True),
    ("Do you want to proceed?\n❯ 1. Yes\n  2. No\n", "claude-code", False),
    ("Do you want to proceed?\n" + RULE + "\n❯ 1. Yes\n" + RULE + "\n", "claude-code", False),
    ("$ ls\n$ \n", "claude-code", False),
    ("\x1b[1;2m› \x1b[0mearlier message\n\n\x1b[1m›\x1b[0m \x1b[2mAsk Codex to do anything\x1b[0m\n\n  model · ~/x\n",
     "codex", True),
    ("\x1b[1m›\x1b[0m #now half typed\n\n  model · ~/x\n", "codex", False),
    ("\x1b[1m›\x1b[0m \n  a second line\n", "codex", False),
    (_cc(""), "opencode", False),
])
def test_input_line(screen: str, tool: str, empty: bool) -> None:
    assert msgdeliver.input_empty(screen, tool) is empty


def test_without_a_live_terminal_the_message_waits(root: Path) -> None:
    row = msgledger.add(root, project="alpha", from_agent=COORD, to_agent=WORKER, text="x")
    typed, why = msgdeliver.try_terminal(root, row["id"])
    assert not typed and why
    assert msgledger.find(root, row["id"])["delivered_via"] == ""  # type: ignore[index]


# ---------------------------------------------------------------------------
# Into a real terminal (a sandbox tmux of the test's own data root)
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
    with TestClient(create_app(data_root=root, watch=False, run_monitor=False)) as c:
        assert c.post("/api/settings", json={"values": {"terminal.enabled": True}}).status_code == 200
        yield c, root, work
    termlib.tmux(root, "kill-server")


def _fake_agent(c: TestClient, root: Path, work: Path, agent: str, typed: str = "") -> tuple[str, Path]:
    log = work / f"{agent}.log"
    cmd = " ".join(shlex.quote(x) for x in (sys.executable, str(FAKE), str(log), "claude-code", typed))
    got = c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha", "command": cmd, "label": agent})
    assert got.status_code == 201, got.text
    sid = got.json()["session"]["id"]
    _chat(root, agent, terminal=sid)
    termlib._link_cache = (None, 0.0, {})  # the hook just wrote the link
    deadline = time.time() + 10
    while time.time() < deadline:
        if "fake agent ready" in termlib.capture(root, sid)["text"]:
            return sid, log
        time.sleep(0.1)
    raise AssertionError(f"the fake agent did not start: {termlib.capture(root, sid)['text']!r}")


def _logged(log: Path, want: int, wait: float = 5.0) -> list[str]:
    deadline = time.time() + wait
    lines: list[str] = []
    while time.time() < deadline:
        lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        if len(lines) >= want:
            break
        time.sleep(0.1)
    return lines


@needs_tmux
def test_typed_into_the_live_terminal_once_with_its_marker(term) -> None:
    c, root, work = term
    _, log = _fake_agent(c, root, work, WORKER)
    r = _send(c, COORD, WORKER, "look at the lock")
    assert r.status_code == 201 and r.json()["typed"] and r.json()["delivered_via"] == "terminal", r.text
    m = r.json()["message"]
    lines = _logged(log, 1)
    assert lines == [f"[SP · from {COORD} · {m['id']}] look at the lock"]
    assert msgdeliver.retry_waiting(root) == 0
    time.sleep(0.5)
    assert _logged(log, 2, wait=0.5) == lines


@needs_tmux
def test_not_typed_over_the_operators_half_typed_line(term) -> None:
    c, root, work = term
    _, log = _fake_agent(c, root, work, WORKER, typed="half typed")
    r = _send(c, COORD, WORKER, "wait for the line")
    assert r.status_code == 201 and not r.json()["typed"] and r.json()["delivered_via"] == ""
    assert "input line" in r.json()["waiting"]
    assert msgdeliver.retry_waiting(root) == 0
    assert not log.exists()
    # The operator clears the line: the next round types it, once.
    Path(str(log) + ".clear").write_text("", encoding="utf-8")
    deadline = time.time() + 5
    typed = 0
    while time.time() < deadline and not typed:
        time.sleep(0.3)
        typed = msgdeliver.retry_waiting(root)
    assert typed == 1
    lines = _logged(log, 1)
    assert len(lines) == 1 and lines[0].endswith("wait for the line")
    assert msgdeliver.retry_waiting(root) == 0


@needs_tmux
def test_a_shell_in_front_gets_nothing(term) -> None:
    c, root, work = term
    got = c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha", "label": "sh"})
    sid = got.json()["session"]["id"]
    _chat(root, WORKER, terminal=sid)
    termlib._link_cache = (None, 0.0, {})
    time.sleep(0.5)
    r = _send(c, COORD, WORKER, "echo pwned")
    assert not r.json()["typed"] and "shell" in r.json()["waiting"]
