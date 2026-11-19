"""A task made from a message (the terminal's message menu): the server gives
a provisional title, the title waits for the chat's agent, the hook tells it
once on the chat's next turn, and the agent sets the title once."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import hookshared, titlelib
from backend.server import create_app

AGENT = "cc-aaaa1111"
OTHER = "cc-bbbb2222"
#: A chat the hook records itself: its agent id is the session's start (cc-dddd4444).
SID = "dddd4444-0000-4000-8000-000000000001"
HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"

REPLY = ("Понял: в этом чате я тестирую фичи терминала. Контракт прочитан.\n\n"
         "## Окно терминала теряет фокус\n- **после** переключения вкладки")


# ---------------------------------------------------------------------------
# The provisional title
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("message,title", [
    # A service opener is skipped; the heading's marks and emphasis go.
    (REPLY, "Окно терминала теряет фокус"),
    ("Готово.\n\n1. Fix the **login** timeout in the [terminal](http://x) `window`",
     "Fix the login timeout in the terminal window"),
    ("Got it — reading the code.\n\nThe board loses its scroll on reload", "The board loses its scroll on reload"),
    ("Ok\n\n```\nnpm run build\n```\n\n> the build is slow on macOS", "the build is slow on macOS"),
    # One line: kept whole, opener and all.
    ("Да, нужно переделать окно задач", "Да, нужно переделать окно задач"),
    ("Сделал", "Сделал"),
    ("the menu #now forgets the lane", "the menu forgets the lane"),
    ("", ""),
])
def test_provisional_title(message, title):
    assert titlelib.provisional_title(message) == title


def test_a_long_line_is_cut_at_a_word():
    line = ("Окно терминала теряет фокус после того как оператор переключает вкладку в браузере "
            "и возвращается назад")
    got = titlelib.provisional_title(line)
    assert len(got) <= 80 and got.endswith("…")
    assert line.startswith(got[:-1]) and line[len(got) - 1] == " "          # cut between words


# ---------------------------------------------------------------------------
# The server
# ---------------------------------------------------------------------------


def _chat(root: Path, turns: list[tuple[str, str]], agent: str = AGENT) -> None:
    d = root / "projects" / "alpha" / "chats" / agent
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps({
        "agent_id": agent, "agent_name": agent, "project": "alpha", "created_date": "2611-16",
        "last_active": "2026-11-16T10:30:00", "message_count": len(turns),
    }), encoding="utf-8")
    body = [f"# Chat log — {agent}\n"]
    for i, (user, reply) in enumerate(turns, start=1):
        body.append(f"\n## Turn {i} · 2026-11-16T10:{i:02d}:00\n**User**: {user}\n**Agent**: {reply}\n")
    (d / "chat.md").write_text("".join(body), encoding="utf-8")


@pytest.fixture()
def env(tmp_path: Path):
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    _chat(root, [("what breaks in the terminal?", REPLY)])
    with TestClient(create_app(data_root=root, watch=False)) as c:
        yield c, root


def _make(c: TestClient, source: str = f"{AGENT}#1/reply", **more: object) -> dict:
    """What the message menu sends."""
    body = {"project": "alpha", "projects": "alpha", "agent_id": "operator", "actor": "operator",
            "title": "Понял: в этом чате я тестирую фичи терминала.", "status": "todo", "priority": "med",
            "description": f"{REPLY}\n\nИз чата: {AGENT}#1", "title_from": "message", "title_source": source, **more}
    r = c.post("/api/tasks", json=body)
    assert r.status_code == 201, r.text
    return r.json()["metadata"]


def _title(c: TestClient, tid: str) -> str:
    return c.get(f"/api/tasks/{tid}").json()["metadata"]["title"]


def test_the_menu_task_gets_the_provisional_title_and_the_flag(env):
    c, root = env
    meta = _make(c)
    assert meta["title"] == "Окно терминала теряет фокус"
    row = titlelib.state_of(root, meta["id"])
    assert row and row["state"] == "waiting" and row["agent_id"] == AGENT and row["turn"] == "1"
    assert row["side"] == "reply"
    assert [w["task_id"] for w in hookshared.title_waits(root, AGENT)] == [meta["id"]]
    assert hookshared.title_waits(root, OTHER) == []


def test_without_the_field_nothing_changes(env):
    c, root = env
    r = c.post("/api/tasks", json={"project": "alpha", "actor": "operator", "title": "Понял: plain",
                                   "status": "todo", "description": "x"})
    assert r.json()["metadata"]["title"] == "Понял: plain"
    assert titlelib.state_of(root, r.json()["metadata"]["id"]) is None


def test_a_message_not_in_the_record_is_titled_from_the_description(env):
    c, _root = env
    meta = _make(c, source=f"{AGENT}#9")
    assert meta["title"] == "Окно терминала теряет фокус"


def test_a_bad_source_is_refused(env):
    c, _root = env
    r = c.post("/api/tasks", json={"project": "alpha", "actor": "operator", "title": "t", "status": "todo",
                                   "title_from": "message", "title_source": "not a message"})
    assert r.status_code == 422 and "title_source" in r.json()["detail"]


def test_the_source_agent_sets_the_title_once(env):
    c, root = env
    tid = _make(c)["id"]
    r = c.post(f"/api/tasks/{tid}/update", json={"actor": AGENT, "title": "Терминал теряет фокус при смене вкладки"})
    assert r.status_code == 200, r.text
    assert _title(c, tid) == "Терминал теряет фокус при смене вкладки"
    assert titlelib.state_of(root, tid)["state"] == "agent"
    again = c.post(f"/api/tasks/{tid}/update", json={"actor": AGENT, "title": "another"})
    assert again.status_code == 422 and "given once already" in again.json()["detail"]
    assert _title(c, tid) == "Терминал теряет фокус при смене вкладки"


def test_the_agent_title_is_held_to_80_characters(env):
    c, root = env
    tid = _make(c)["id"]
    r = c.post(f"/api/tasks/{tid}/update", json={"actor": AGENT, "title": "x" * 81})
    assert r.status_code == 422
    assert titlelib.state_of(root, tid)["state"] == "waiting"


def test_another_agent_is_refused(env):
    c, root = env
    tid = _make(c)["id"]
    r = c.post(f"/api/tasks/{tid}/update", json={"actor": OTHER, "title": "mine"})
    assert r.status_code == 422 and f"{AGENT}#1/reply" in r.json()["detail"]
    assert titlelib.state_of(root, tid)["state"] == "waiting"


def test_the_operator_renames_first(env):
    c, root = env
    tid = _make(c)["id"]
    # The window sends the title it shows with a save: no change, the flag stays.
    assert c.post(f"/api/tasks/{tid}/update", json={"actor": "operator", "title": _title(c, tid)}).status_code == 200
    assert titlelib.state_of(root, tid)["state"] == "waiting"
    assert c.post(f"/api/tasks/{tid}/update", json={"actor": "operator", "title": "Мой заголовок"}).status_code == 200
    assert titlelib.state_of(root, tid)["state"] == "operator"
    assert hookshared.title_waits(root, AGENT) == []
    r = c.post(f"/api/tasks/{tid}/update", json={"actor": AGENT, "title": "the agent's"})
    assert r.status_code == 422 and "the operator renamed" in r.json()["detail"]
    assert _title(c, tid) == "Мой заголовок"


def test_other_operator_tasks_are_not_the_agents_to_retitle(env):
    """Was: any agent may retitle a task not made from a message. Since the
    operator's "only your own" (tk_1f8e63dc), an agent retitles only a card
    it created (test_task_own_cards.py)."""
    c, _root = env
    r = c.post("/api/tasks", json={"project": "alpha", "actor": "operator", "title": "the operator's",
                                   "status": "todo"})
    tid = r.json()["metadata"]["id"]
    refused = c.post(f"/api/tasks/{tid}/update", json={"actor": OTHER, "title": "retitled"})
    assert refused.status_code == 422 and "created by the operator" in refused.json()["detail"]
    assert _title(c, tid) == "the operator's"


def test_the_source_agent_gives_the_title_only(env):
    """The exception is the title, once: the text stays the operator's."""
    c, root = env
    tid = _make(c)["id"]
    r = c.post(f"/api/tasks/{tid}/update", json={"actor": AGENT, "title": "Терминал теряет фокус",
                                                  "description": "my words"})
    assert r.status_code == 422 and "description" in r.json()["detail"]
    assert titlelib.state_of(root, tid)["state"] == "waiting"
    assert c.post(f"/api/tasks/{tid}/update", json={"actor": AGENT, "title": "Терминал теряет фокус"}).status_code == 200


def test_an_agent_cannot_ask_for_it(env):
    c, root = env
    r = c.post("/api/tasks", json={"project": "alpha", "agent_id": OTHER, "title": "an agent's", "status": "agent",
                                   "tags": "ag_idea", "description": "x", "title_from": "message",
                                   "title_source": f"{AGENT}#1"})
    assert r.status_code == 201, r.text
    assert titlelib.state_of(root, r.json()["metadata"]["id"]) is None
    assert "title_from" in r.json().get("ignored", [])


# ---------------------------------------------------------------------------
# The hook's notice
# ---------------------------------------------------------------------------


def _capture():
    import importlib.util
    spec = importlib.util.spec_from_file_location("sp_capture_titles", HOOKS / "capture.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sp_capture_titles"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_the_notice_comes_once_on_the_source_chat_only(env):
    c, root = env
    _chat(root, [("hello", "hi")], agent=OTHER)
    tid = _make(c)["id"]
    cap = _capture()
    first = cap.format_signals(cap.TurnCapture(root, "alpha", AGENT).open_turn("go on"))
    assert first.count("#task-title") == 1
    assert (f"[slightly-parallel] #task-title — the operator made {tid} from your reply in turn 1" in first
            and f'task_update {{id: "{tid}", title}}' in first and "Окно терминала теряет фокус" in first)
    second = cap.format_signals(cap.TurnCapture(root, "alpha", AGENT).open_turn("and then"))
    assert "#task-title" not in second
    other = cap.format_signals(cap.TurnCapture(root, "alpha", OTHER).open_turn("go on"))
    assert "#task-title" not in other


def test_no_notice_once_the_title_is_given(env):
    c, root = env
    tid = _make(c)["id"]
    assert c.post(f"/api/tasks/{tid}/update", json={"actor": "operator", "title": "Мой"}).status_code == 200
    cap = _capture()
    assert "#task-title" not in cap.format_signals(cap.TurnCapture(root, "alpha", AGENT).open_turn("go on"))


def test_the_claude_code_hook_prints_it(env, tmp_path: Path):
    c, root = env
    base = {"session_id": SID, "cwd": str(tmp_path)}
    env_ = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "CODEX_THREAD", "OPENCODE"))}
    env_["CLAUDE_CODE_ENTRYPOINT"] = "cli"

    def hook(payload: dict) -> str:
        p = subprocess.run([sys.executable, str(HOOKS / "claude-code-capture.py"), "--project", "alpha",
                            "--data-root", str(root)], input=json.dumps(payload), capture_output=True,
                           text=True, env=env_, encoding="utf-8")
        assert p.returncode == 0, p.stderr
        return p.stdout

    hook({**base, "hook_event_name": "UserPromptSubmit", "prompt": "what is wrong?"})
    hook({**base, "hook_event_name": "Stop", "last_assistant_message": "Готово.\n\nThe scroll jumps on reload"})
    c.app.state.store.rebuild()
    agent = "cc-dddd4444"
    tid = _make(c, source=f"{agent}#1/reply")["id"]
    assert _title(c, tid) == "The scroll jumps on reload"
    out = hook({**base, "hook_event_name": "UserPromptSubmit", "prompt": "next"})
    assert f"#task-title — the operator made {tid}" in out
    assert "#task-title" not in hook({**base, "hook_event_name": "UserPromptSubmit", "prompt": "more"})
