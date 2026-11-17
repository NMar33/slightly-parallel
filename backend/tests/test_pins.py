"""Marks on one message: #pin, #carry, #carry-brief, #fork-later.

The tags are adopted into marks.csv like #important; the buttons mark by
hand; an unmark wins over the old tag. After a context compaction the
capture hook gives the chat's carried messages back once, whole ones first,
then briefs, within the budget, and records it."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import hookshared, limits, marklib, sessions, termlib
from backend.integration_text import CLAUDE_EVENTS, _upsert_hooks
from backend.server import create_app

AGENT = "cc-aaaa1111"
SID = "aaaa1111-0000-4000-8000-000000000001"
HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"


def _chat(root: Path, turns: list[tuple[str, str]], agent: str = AGENT, **meta: object) -> Path:
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


def _items(c: TestClient, which: str, **q: str) -> list[dict]:
    path = {"pin": "pins", "carry": "carries", "fork": "forks"}[which]
    return c.get(f"/api/{path}", params=q).json()["items"]


# ---------------------------------------------------------------------------
# The tags
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text,kinds", [
    ("come back to this #pin", ["pin"]), ("#carry this", ["carry"]), ("#carry-brief", ["carry-brief"]),
    ("later #fork-later", ["fork"]), ("#PIN and #carry", ["pin", "carry"]),
    ("#pin #pin", ["pin"]), ("###pin with #carry quoted", ["pin"]),
    ("#mute #pin", []), ("#pinned ##pin x#pin #carry-on #carrying #fork-later-x #fork", []),
])
def test_the_tags(text, kinds):
    assert hookshared.message_mark_kinds(text) == kinds


def test_a_tag_the_tool_wrote_is_no_command():
    assert hookshared.message_mark_kinds("<task-notification> #pin") == []


def test_no_tag_collides_with_another_command():
    """#important-…, the kept tags and the other commands read none of these."""
    for text in ("#pin", "#carry", "#carry-brief", "#fork-later"):
        assert not sessions.IMPORTANT_TAG_RE.search(text) and not sessions.KEEP_TAG_RE.search(text)
        assert not sessions.TASK_CMD_RE.search(text) and not sessions.DONE_TAG_RE.search(text)
    capture = _capture()
    found = [m.group(1) for m in capture._COMMAND_RE.finditer("#carry-brief #carry #pin #fork-later")]
    assert found == ["carry-brief", "carry", "pin", "fork-later"]


def test_the_hook_names_a_mark_by_the_servers_id():
    target = marklib.message_target(AGENT, 3)
    assert hookshared.tag_mark_id("pin", target, AGENT, 3) == marklib._id("pin", target, AGENT, 3)
    assert hookshared.parse_target(f"{AGENT}#3/reply") == (AGENT, 3, "reply")
    assert hookshared.parse_target("nothing") is None


def test_the_hook_reads_a_chat_as_the_server_does(tmp_path: Path):
    d = _chat(tmp_path, [("one\n\\## Turn 9 · 2026-11-16T10:00:00 quoted", "two\nlines"), ("three", "")])
    server = [(t.number, t.user_summary, t.agent_summary) for t in sessions.parse_turns(d / "chat.md")]
    assert [(n, u, a) for n, _at, u, a in hookshared.chat_turns(d / "chat.md")] == server


# ---------------------------------------------------------------------------
# Adopted from the chat, listed, unmarked
# ---------------------------------------------------------------------------


def test_each_tag_marks_its_message(env):
    c, root = env
    _chat(root, [("look here #pin", "ok"), ("keep it #carry", "the plan"), ("and #carry-brief", "a"),
                 ("someone else #fork-later", "b"), ("#important", "c")])
    c.app.state.store.rebuild()
    assert [(i["target"], i["excerpt"]) for i in _items(c, "pin")] == [(f"{AGENT}#1", "look here")]
    carried = _items(c, "carry")
    assert {(i["kind"], i["target"]) for i in carried} == {("carry", f"{AGENT}#2"), ("carry-brief", f"{AGENT}#3")}
    assert next(i for i in carried if i["kind"] == "carry")["reply"] == "the plan"
    assert [i["target"] for i in _items(c, "fork")] == [f"{AGENT}#4"]
    # The Important page reads none of them.
    assert {m["kind"] for m in c.get("/api/marks").json()["marks"]} == {"message", "agent"}


def test_a_helper_chat_marks_nothing(env):
    c, root = env
    _chat(root, [("#pin #carry #fork-later", "ok")], helper=True, helper_kind="claude-print")
    c.app.state.store.rebuild()
    assert _items(c, "pin") == [] and _items(c, "carry") == [] and _items(c, "fork") == []


def test_removed_is_not_adopted_again(env):
    c, root = env
    _chat(root, [("look here #pin", "ok")])
    c.app.state.store.rebuild()
    target = f"{AGENT}#1"
    assert c.post("/api/pins/remove", json={"target": target}).json()["removed"] == 1
    assert _items(c, "pin") == []
    c.app.state.store.rebuild()
    assert _items(c, "pin") == []


def test_the_buttons_mark_both_sides_and_one_carry_level(env):
    c, root = env
    _chat(root, [("question", "a long answer")])
    c.app.state.store.rebuild()
    r = c.post("/api/pins", json={"chat_agent": AGENT, "turn": 1, "side": "reply", "project": "alpha"})
    assert r.status_code == 201 and r.json()["mark"]["target"] == f"{AGENT}#1/reply"
    assert _items(c, "pin")[0]["text"] == "a long answer"
    c.post("/api/carries", json={"chat_agent": AGENT, "turn": 1, "level": "carry"})
    c.post("/api/carries", json={"chat_agent": AGENT, "turn": 1, "level": "brief"})
    assert [i["kind"] for i in _items(c, "carry")] == ["carry-brief"]
    assert c.post("/api/carries", json={"chat_agent": AGENT, "turn": 0}).status_code == 422
    # Marking is the operator's.
    assert c.post("/api/pins", json={"chat_agent": AGENT, "turn": 1, "agent_id": "cc-other"}).status_code == 422


def test_search_and_filters(env):
    c, root = env
    _chat(root, [("the login timeout #pin", "ok"), ("the colours #pin", "ok")])
    _chat(root, [("other chat #pin", "ok")], agent="cc-bbbb2222")
    c.app.state.store.rebuild()
    assert [i["turn"] for i in _items(c, "pin", q="LOGIN")] == [1]
    assert {i["agent_id"] for i in _items(c, "pin", agent_id="cc-bbbb2222")} == {"cc-bbbb2222"}
    assert len(_items(c, "pin", project="alpha")) == 3 and _items(c, "pin", project="beta") == []


def test_a_fork_has_its_command_and_a_state(env):
    c, root = env
    _chat(root, [("write the export, it's #fork-later work", "ok")], tool="claude-code", session_ref=SID,
          cwd="/home/op/my project")
    c.app.state.store.rebuild()
    fork = _items(c, "fork")[0]
    assert fork["command"] == ("cd '/home/op/my project' && claude -r " + SID
                               + " --fork-session $'write the export, it\\'s  work'")
    assert c.post("/api/forks/state", json={"target": fork["target"], "state": "started"}).json()["changed"] == 1
    assert _items(c, "fork")[0]["state"] == "started"
    assert c.post("/api/forks/state", json={"target": fork["target"], "state": "maybe"}).status_code == 422
    assert c.post("/api/forks/state", json={"target": f"{AGENT}#9", "state": "dropped"}).status_code == 404


def test_fork_command_per_tool():
    assert termlib.fork_command("codex", "01a1-x", "/w", "go").startswith("cd /w && codex fork 01a1-x $'go'")
    assert termlib.fork_command("opencode", "x", "/w", "go") == ""
    assert termlib.fork_command("claude-code", "-rm", "/w", "go") == ""
    assert termlib.fork_command("claude-code", "x", "", "go") == ""


def test_a_brief_is_written_for_a_carry_brief_message_only(env):
    c, root = env
    _chat(root, [("decide the schema #carry-brief", "ok"), ("plain", "ok")])
    c.app.state.store.rebuild()
    r = c.post("/api/carries/brief", json={"target": f"{AGENT}#1", "text": "We chose one CSV per kind.",
                                           "agent_id": AGENT}, headers={"X-SP-Via": "mcp"})
    assert r.status_code == 201, r.text
    item = _items(c, "carry")[0]
    assert item["brief"] == "We chose one CSV per kind." and item["brief_by"] == AGENT
    assert c.post("/api/carries/brief", json={"target": f"{AGENT}#2", "text": "x", "agent_id": AGENT},
                  headers={"X-SP-Via": "mcp"}).status_code == 404
    assert c.post("/api/carries/brief", json={"target": f"{AGENT}#1", "text": "x" * (limits.MAX_CARRY_BRIEF + 1),
                                              "agent_id": AGENT}, headers={"X-SP-Via": "mcp"}).status_code == 422


# ---------------------------------------------------------------------------
# Given back after a compaction
# ---------------------------------------------------------------------------


def test_whole_ones_first_then_briefs_newest_first_within_the_budget(tmp_path: Path):
    root = tmp_path
    long = "x" * 900
    _chat(root, [("old #carry", "r1"), ("brief me #carry-brief", "r2"), (f"new #carry {long}", "r3" * 3000),
                 ("unmarked", "r4")])
    items = hookshared.carried_items(root, AGENT, root / "projects/alpha/chats" / AGENT / "chat.md", reply_cap=100)
    assert [(i["turn"], i["kind"]) for i in items] == [(3, "carry"), (1, "carry"), (2, "carry-brief")]
    assert items[0]["reply"].startswith("r3r3") and "more characters" in items[0]["reply"]
    assert "write the brief now" in hookshared.compose_carried(items, 100_000)[0]  # no brief written yet
    text, given, left = hookshared.compose_carried(items, 1200)
    assert given == [f"{AGENT}#1", f"{AGENT}#2"] and left == [f"{AGENT}#3"]
    assert "old #carry" in text and f"{AGENT}#3 (turn 3, #carry)" in text and "pins" in text
    assert hookshared.compose_carried([], 1000) == ("", [], [])


def test_a_removed_carry_is_not_given_back(env):
    c, root = env
    d = _chat(root, [("keep #carry", "r1"), ("this too #carry", "r2")])
    c.app.state.store.rebuild()
    _items(c, "carry")  # adopted
    c.post("/api/carries/remove", json={"target": f"{AGENT}#1"})
    items = hookshared.carried_items(root, AGENT, d / "chat.md", reply_cap=100)
    assert [i["turn"] for i in items] == [2]


def _capture():
    import importlib.util
    spec = importlib.util.spec_from_file_location("sp_capture_pins", HOOKS / "capture.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sp_capture_pins"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_once_per_compaction(tmp_path: Path):
    root = tmp_path
    _chat(root, [("keep #carry", "the answer")])
    cap = _capture().TurnCapture(root, "alpha", AGENT)
    assert cap.compactions_due() == []
    cap.note_compacts([1000.0])
    assert cap.compactions_due() == [1000.0]
    text = cap.give_back_carried("prompt", 1000.0)
    assert "keep #carry" in text and "the answer" in text
    assert cap.compactions_due() == []                 # answered
    cap.note_compacts([1000.0])                        # the same one read again
    assert cap.compactions_due() == []
    rec = hookshared.carried_deliveries(cap.folder)
    assert rec[-1]["given"] == [f"{AGENT}#1"] and rec[-1]["via"] == "prompt"
    import time
    later = time.time() + 120
    cap.note_compacts([later])
    assert cap.compactions_due() == [later]


def _env(**more: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "CODEX_THREAD", "OPENCODE"))}
    env.update(more, CLAUDE_CODE_ENTRYPOINT="cli")
    return env


def _hook(root: Path, payload: dict) -> subprocess.CompletedProcess:
    proc = subprocess.run([sys.executable, str(HOOKS / "claude-code-capture.py"), "--project", "alpha",
                           "--data-root", str(root)], input=json.dumps(payload), capture_output=True,
                          text=True, env=_env(), encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return proc


def test_the_hook_gives_them_back_at_session_start_after_a_compaction(tmp_path: Path):
    root = tmp_path / "data"
    root.mkdir()
    base = {"session_id": SID, "cwd": str(tmp_path)}
    out = _hook(root, {**base, "hook_event_name": "UserPromptSubmit", "prompt": "the plan is A then B #carry"})
    assert "[slightly-parallel] #carry — nothing to write" in out.stdout
    _hook(root, {**base, "hook_event_name": "Stop", "last_assistant_message": "Agreed: A, then B."})
    # A new chat or a resume gives nothing back; a compaction does.
    assert _hook(root, {**base, "hook_event_name": "SessionStart", "source": "startup"}).stdout == ""
    out = _hook(root, {**base, "hook_event_name": "SessionStart", "source": "compact"})
    assert out.stdout.startswith("[slightly-parallel] carried") and "the plan is A then B #carry" in out.stdout
    assert "Agreed: A, then B." in out.stdout
    # The next prompt does not give them again.
    out = _hook(root, {**base, "hook_event_name": "UserPromptSubmit", "prompt": "go on"})
    assert "carried" not in out.stdout


def test_a_brief_marked_by_hand_is_asked_for_at_the_next_prompt(env, tmp_path: Path):
    c, root = env
    base = {"session_id": SID, "cwd": str(tmp_path)}
    _hook(root, {**base, "hook_event_name": "UserPromptSubmit", "prompt": "the schema question"})
    _hook(root, {**base, "hook_event_name": "Stop", "last_assistant_message": "ok"})
    c.app.state.store.rebuild()
    assert c.post("/api/carries", json={"chat_agent": AGENT, "turn": 1, "level": "brief"}).status_code == 201
    out = _hook(root, {**base, "hook_event_name": "UserPromptSubmit", "prompt": "next"})
    assert f'#carry-brief — the operator marked 1 message' in out.stdout and f'"{AGENT}#1"' in out.stdout
    # The tag in the message itself: one notice, naming this turn.
    out = _hook(root, {**base, "hook_event_name": "UserPromptSubmit", "prompt": "and this #carry-brief"})
    assert out.stdout.count("#carry-brief —") == 1 and f'"{AGENT}#3"' in out.stdout


def test_setup_installs_the_compaction_hook():
    text, _ = _upsert_hooks("", "python3 /x/claude-code-capture.py --project alpha", events=CLAUDE_EVENTS)
    hooks = json.loads(text)["hooks"]
    assert hooks["SessionStart"][0]["matcher"] == "compact"
    assert "matcher" not in hooks["UserPromptSubmit"][0]


def test_a_pinned_message_says_so_in_search(env):
    c, root = env
    _chat(root, [("the zebra question #pin", "the zebra answer")])
    c.app.state.store.rebuild()
    _items(c, "pin")  # adopted on read, like every tag
    from backend import searchlib
    searchlib.forget()
    hits = {h.id: h.meta for h in searchlib.search(c.app.state.store, "zebra") if h.kind == "turn"}
    assert hits[f"{AGENT}#1.user"].get("pinned") is True and "pinned" not in hits[f"{AGENT}#1.agent"]
