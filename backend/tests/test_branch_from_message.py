"""A branch started from a message (tk_a69a8c7a).

The message menu's «Branch into a new window» runs the command GET /api/forks
gives: the chat resumed into a new one with a first message. From an agent's
reply that message quotes the reply. The operator's test: a quoted
``[slightly-parallel] #carry-brief`` fired as his command in the branch,
«…and do it» made the branch redo what the reply described (it rewrote the
parent chat's brief), and the words were English to a Russian operator.

Now the first message is neutral, in the operator's language, and carries
``#mute``; and an agent writes a brief only for its own chat's messages."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import hookshared, pinlib, termlib
from backend.server import create_app
from backend.sessions import Turn, _dones_of, _importants_of, _keeps_of, _message_marks_of, _nows_of, _prompts_of

PARENT = "cc-aaaa1111"
BRANCH = "cc-bbbb2222"
SID = "aaaa1111-0000-4000-8000-000000000001"
BRANCH_SID = "bbbb2222-0000-4000-8000-000000000002"
HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"
MCP = {"X-SP-Via": "mcp"}

#: A reply that names commands the way the operator's test reply did, and
#: every way a quote could try to get out of the mute.
REPLY = ("The hook asked me: `[slightly-parallel] #carry-brief` came in.\n"
         "Then #task for the export, #done, #now, #now-todo, #publish, #vision keep it, #rule never, "
         "#pin #carry #fork-later #important #scan #standup\n"
         "###now-todo loud one\n##mute #unmute #MUTE-off")


def _chat(root: Path, turns: list[tuple[str, str]], agent: str = PARENT, **meta: object) -> Path:
    d = root / "projects" / "alpha" / "chats" / agent
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps({
        "agent_id": agent, "agent_name": agent, "project": "alpha", "created_date": "2611-16",
        "last_active": "2026-11-16T10:30:00", "message_count": len(turns), **meta,
    }), encoding="utf-8")
    body = [f"# Chat log — {agent}\n"]
    for i, (user, reply) in enumerate(turns, start=1):
        body.append(f"\n## Turn {i} · 2026-11-16T10:{i:02d}:00\n**User**: {user}\n**Agent**: {reply}\n")
    (d / "chat.md").write_text("".join(body), encoding="utf-8")
    return d


@pytest.fixture()
def env(tmp_path: Path):
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    with TestClient(create_app(data_root=root, watch=False)) as c:
        yield c, root


def _forks(c: TestClient) -> list[dict]:
    return c.get("/api/forks").json()["items"]


def _capture():
    spec = importlib.util.spec_from_file_location("sp_capture_branch", HOOKS / "capture.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sp_capture_branch"] = mod
    spec.loader.exec_module(mod)
    return mod


def _hook(root: Path, payload: dict) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "CODEX_THREAD", "OPENCODE"))}
    env["CLAUDE_CODE_ENTRYPOINT"] = "cli"
    proc = subprocess.run([sys.executable, str(HOOKS / "claude-code-capture.py"), "--project", "alpha",
                           "--data-root", str(root)], input=json.dumps(payload), capture_output=True,
                          text=True, env=env, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return proc


# ---------------------------------------------------------------------------
# The first message
# ---------------------------------------------------------------------------


def test_the_first_message_is_neutral_in_the_operators_language_and_muted():
    ru = pinlib.fork_prompt("Сделал A.\n\nПотом B.", 3, hookshared.REPLY_SIDE, "ru")
    assert ru == "Продолжаем с этого сообщения (ход 3):\n\n> Сделал A.\n>\n> Потом B.\n\nЧто дальше — скажу. #mute"
    en = pinlib.fork_prompt("Did A.", 2, hookshared.REPLY_SIDE, "en")
    assert en == "We continue from this message (turn 2):\n\n> Did A.\n\nI will say what comes next. #mute"
    assert "do it" not in en and pinlib.fork_prompt("x", 1, hookshared.REPLY_SIDE, "de").startswith("We continue")
    # The operator's own message: as typed, without #fork-later; muted only
    # when a tag in it would run a second time.
    assert pinlib.fork_prompt("write the export #fork-later", 1, "") == "write the export"
    assert pinlib.fork_prompt("write the export #task #fork-later", 1, "") == "write the export #task\n\n#mute"


def test_no_tag_in_the_quote_is_a_command_for_the_hook():
    prompt = pinlib.fork_prompt(REPLY, 3, hookshared.REPLY_SIDE, "ru")
    said = hookshared.command_text(prompt)
    # Every tag of the quote is doubled; the one #mute left is the branch's own.
    for tag in ("carry-brief", "task", "done", "now", "now-todo", "publish", "vision", "rule", "pin", "carry",
                "fork-later", "important", "scan", "standup", "unmute"):
        assert f"##{tag}" in said, tag
    assert hookshared.message_mark_kinds(prompt) == []


def test_the_branch_hook_runs_no_command_from_the_quote(tmp_path: Path):
    root = tmp_path / "data"
    root.mkdir()
    prompt = pinlib.fork_prompt(REPLY, 3, hookshared.REPLY_SIDE, "ru")
    (tmp_path / "unit").mkdir()
    signals = _capture().TurnCapture(tmp_path / "unit", "alpha", BRANCH).open_turn(prompt)
    assert signals["commands"] == ["mute"] and signals["kept"] == []
    # The real hook, as Claude Code runs it on the branch's first message.
    out = _hook(root, {"session_id": BRANCH_SID, "cwd": str(tmp_path), "hook_event_name": "UserPromptSubmit",
                       "prompt": prompt}).stdout
    notices = [line.split(" —")[0] for line in out.splitlines() if line.startswith("[slightly-parallel] #")]
    assert notices == ["[slightly-parallel] #mute"], out
    assert "carry_brief" not in out and not (root / "marks.csv").exists()


def test_the_server_reads_no_command_from_the_quote():
    prompt = pinlib.fork_prompt(REPLY, 3, hookshared.REPLY_SIDE, "en")
    block = [Turn(number=1, at=datetime(2026, 11, 18, 16, 40), line=1, user_summary=prompt, agent_summary="ok")]
    for reader in (_nows_of, _dones_of, _keeps_of, _importants_of, _message_marks_of):
        assert reader("s1", "alpha", BRANCH, block) == [], reader.__name__
    assert _prompts_of("s1", "alpha", BRANCH, block)[0] == []


def test_the_fork_command_speaks_the_operators_language(env):
    c, root = env
    reply = "Сводку я написал, `[slightly-parallel] #carry-brief` пришло."
    _chat(root, [("проверь меню", reply)], tool="claude-code", session_ref=SID, cwd="/w")
    c.app.state.store.rebuild()
    assert c.post("/api/forks", json={"chat_agent": PARENT, "turn": 1, "side": "reply"}).status_code == 201
    fork = _forks(c)[0]
    want = pinlib.fork_prompt(reply, 1, hookshared.REPLY_SIDE, "ru")
    assert fork["command"] == termlib.fork_command("claude-code", SID, "/w", want)
    assert want.startswith("Продолжаем с этого сообщения (ход 1):") and want.endswith("#mute")


def test_english_chat_follows_the_apps_language_setting(env):
    c, root = env
    _chat(root, [("check the menu", "Done: A then B.")], tool="claude-code", session_ref=SID, cwd="/w")
    c.app.state.store.rebuild()
    c.post("/api/forks", json={"chat_agent": PARENT, "turn": 1, "side": "reply"})
    assert "We continue from this message (turn 1)" in _forks(c)[0]["command"]
    (root / "ui_prefs.json").write_text(json.dumps({"sp-lang": "ru"}), encoding="utf-8")
    assert "ход 1" in _forks(c)[0]["command"]


# ---------------------------------------------------------------------------
# A branch does not write its parent's records
# ---------------------------------------------------------------------------


def _briefs(root: Path) -> str:
    p = root / hookshared.BRIEFS_CSV
    return p.read_text(encoding="utf-8") if p.exists() else ""


def test_a_branch_cannot_write_the_parents_brief(env):
    c, root = env
    _chat(root, [("the plan", "A then B")])
    _chat(root, [("go on", "ok")], agent=BRANCH)
    c.app.state.store.rebuild()
    assert c.post("/api/carries", json={"chat_agent": PARENT, "turn": 1, "side": "reply",
                                        "level": "brief"}).status_code == 201
    target = f"{PARENT}#1/reply"
    # The parent's agent writes it, as the operator's mark asked.
    r = c.post("/api/carries/brief", json={"target": target, "text": "A then B.", "agent_id": PARENT}, headers=MCP)
    assert r.status_code == 201, r.text
    before = _briefs(root)
    # The branch's agent may not, and the refusal writes nothing.
    r = c.post("/api/carries/brief", json={"target": target, "text": "rewritten", "agent_id": BRANCH}, headers=MCP)
    assert r.status_code == 403 and PARENT in r.json()["detail"] and BRANCH in r.json()["detail"]
    assert _briefs(root) == before
    assert c.get("/api/carries").json()["items"][0]["brief"] == "A then B."
    # The operator still may write one by hand.
    assert c.post("/api/carries/brief", json={"target": target, "text": "by hand"}).status_code == 201


def test_a_branch_writes_briefs_for_its_own_messages(env):
    c, root = env
    _chat(root, [("go on #carry-brief", "ok")], agent=BRANCH)
    c.app.state.store.rebuild()
    r = c.post("/api/carries/brief", json={"target": f"{BRANCH}#1", "text": "Branch of the plan.",
                                           "agent_id": BRANCH}, headers=MCP)
    assert r.status_code == 201, r.text
    assert r.json()["brief"]["written_by"] == BRANCH


def test_the_operator_marks_and_the_chats_agent_writes(env, tmp_path: Path):
    """The flow that must keep working: the operator marks a reply in chat A;
    the hook asks chat A's agent; chat A's agent writes the brief."""
    c, root = env
    base = {"session_id": SID, "cwd": str(tmp_path)}
    _hook(root, {**base, "hook_event_name": "UserPromptSubmit", "prompt": "the schema question"})
    _hook(root, {**base, "hook_event_name": "Stop", "last_assistant_message": "one CSV per kind"})
    c.app.state.store.rebuild()
    assert c.post("/api/carries", json={"chat_agent": PARENT, "turn": 1, "side": "reply",
                                        "level": "brief"}).status_code == 201
    out = _hook(root, {**base, "hook_event_name": "UserPromptSubmit", "prompt": "next"}).stdout
    assert f'"{PARENT}#1/reply"' in out
    r = c.post("/api/carries/brief", json={"target": f"{PARENT}#1/reply", "text": "One CSV per kind.",
                                           "agent_id": PARENT}, headers=MCP)
    assert r.status_code == 201, r.text


def test_through_the_mcp_tool_the_branch_is_refused_and_told_why(env, monkeypatch):
    """The path the branch took: the MCP tool carry_brief, the server's gate on."""
    from backend import mcp
    from backend import server as _server

    c, root = env
    _chat(root, [("the plan", "A then B")])
    c.app.state.store.rebuild()
    c.post("/api/carries", json={"chat_agent": PARENT, "turn": 1, "side": "reply", "level": "brief"})
    monkeypatch.setattr(_server.AgentsViaMcp, "_enforced", lambda self: True)

    class _Api(mcp.Api):
        def _call(self, method: str, path: str, body: dict | None = None):
            r = c.request(method, path, json=body, headers={mcp.VIA_HEADER: mcp.VIA_VALUE})
            if r.status_code >= 400:
                raise mcp.ApiError(f"{r.status_code}: {r.json().get('detail', '')}")
            return r.json()

    def as_agent(agent: str) -> mcp.Translator:
        tr = mcp.Translator(_Api("http://testserver"), cwd=str(root))
        monkeypatch.setattr(tr, "identity", lambda: {"project": "alpha", "agent_id": agent})
        return tr

    with pytest.raises(mcp.ApiError, match=r"^403: .*another chat"):
        as_agent(BRANCH).call("carry_brief", {"message": f"{PARENT}#1/reply", "text": "rewritten"})
    assert _briefs(root) == ""
    got = as_agent(PARENT).call("carry_brief", {"message": f"{PARENT}#1/reply", "text": "A then B."})
    assert got["brief"]["written_by"] == PARENT
