"""The Cursor adapter (scripts/hooks/cursor-capture.py) and the hooks Setup
writes for it (.cursor/hooks.json).

The event samples under fixtures/cursor/ follow https://cursor.com/docs/agent/hooks:
the base fields of every hook, ``prompt`` on beforeSubmitPrompt, ``text`` on
afterAgentResponse and ``status`` + ``loop_count`` on stop.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.routers import setup as setup_router
from backend.server import create_app

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "hooks" / "cursor-capture.py"
_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "cursor"
_CONV = "7f3c2a1e-5b6d-4e8f-9a0b-1c2d3e4f5a6b"
_AGENT = "cursor-7f3c2a1e"


def _event(name: str, project_dir: Path, **changes) -> dict:
    text = (_FIXTURES / f"{name}.json").read_text(encoding="utf-8")
    # The paths go in as JSON text: a Windows path holds backslashes.
    text = text.replace("__PROJECT__", json.dumps(str(project_dir))[1:-1]).replace("__HOME__", json.dumps(str(project_dir.parent))[1:-1])
    event = json.loads(text)
    event.update(changes)
    return event


def _run(data_root: Path, stdin: str, *args: str, cwd: Path | None = None) -> tuple[dict, str]:
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--data-root", str(data_root), *args],
        input=stdin, capture_output=True, text=True, cwd=str(cwd) if cwd else None,
    )
    assert proc.returncode == 0, proc.stderr
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert len(lines) == 1, proc.stdout  # one JSON answer, nothing else on stdout
    return json.loads(lines[0]), proc.stderr


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    (tmp_path / "data").mkdir()
    return tmp_path / "data"


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    d = tmp_path / "my-app"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# The adapter
# ---------------------------------------------------------------------------


def test_prompt_and_reply_are_recorded_verbatim_and_answered(root: Path, project_dir: Path) -> None:
    out, _ = _run(root, json.dumps(_event("beforeSubmitPrompt", project_dir)), "--project", "my-app")
    assert out == {"continue": True}
    out, _ = _run(root, json.dumps(_event("afterAgentResponse", project_dir)), "--project", "my-app")
    assert out == {}
    out, _ = _run(root, json.dumps(_event("stop", project_dir)), "--project", "my-app")
    assert out == {}

    folder = root / "projects" / "my-app" / "chats" / _AGENT
    chat = (folder / "chat.md").read_text(encoding="utf-8")
    assert (
        "**User**: let's use postgres for this\nand keep the sqlite file for tests\n"
        "**Agent**: Done: `DATABASE_URL` now selects the engine.\n\nTests still run on the sqlite file."
    ) in chat
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["tool"] == "cursor" and meta["session_ref"] == _CONV
    assert meta["cwd"] == str(project_dir)                      # the first workspace root
    assert meta["message_count"] == 1 and "pending_turn" not in meta
    assert meta["last_stop"]["found_text"] is True               # the reply came before stop
    assert meta["last_stop"]["keys"] == sorted(_event("stop", project_dir))
    # The breadcrumb the MCP server reads names this chat.
    crumbs = [json.loads(p.read_text(encoding="utf-8")) for p in (root / ".sessions").glob("*.json")]
    assert crumbs and crumbs[0]["agent_id"] == _AGENT and crumbs[0]["project"] == "my-app"


def test_two_turns_of_one_conversation_are_one_chat(root: Path, project_dir: Path) -> None:
    for gen, (q, a) in enumerate([("first?", "first."), ("second?", "second.")], 1):
        _run(root, json.dumps(_event("beforeSubmitPrompt", project_dir, prompt=q, generation_id=f"g{gen}")),
             "--project", "my-app")
        _run(root, json.dumps(_event("afterAgentResponse", project_dir, text=a, generation_id=f"g{gen}")),
             "--project", "my-app")
        _run(root, json.dumps(_event("stop", project_dir, generation_id=f"g{gen}")), "--project", "my-app")
    chats = sorted(p.name for p in (root / "projects" / "my-app" / "chats").iterdir())
    assert chats == [_AGENT]  # keyed by conversation_id, not generation_id
    chat = (root / "projects" / "my-app" / "chats" / _AGENT / "chat.md").read_text(encoding="utf-8")
    assert "**User**: first?\n**Agent**: first." in chat
    assert "**User**: second?\n**Agent**: second." in chat


def test_stop_closes_a_turn_whose_reply_never_came_as_a_gap(root: Path, project_dir: Path) -> None:
    _run(root, json.dumps(_event("beforeSubmitPrompt", project_dir)), "--project", "my-app")
    _run(root, json.dumps(_event("stop", project_dir, status="aborted")), "--project", "my-app")
    folder = root / "projects" / "my-app" / "chats" / _AGENT
    chat = (folder / "chat.md").read_text(encoding="utf-8")
    assert "**Agent**: (reply not in transcript)" in chat
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    assert "pending_turn" not in meta and meta["last_stop"]["found_text"] is False
    # A build that hands the reply to stop instead is still recorded.
    _run(root, json.dumps(_event("beforeSubmitPrompt", project_dir, prompt="again?")), "--project", "my-app")
    _run(root, json.dumps(_event("stop", project_dir, text="Here.")), "--project", "my-app")
    chat = (folder / "chat.md").read_text(encoding="utf-8")
    assert "**User**: again?\n**Agent**: Here." in chat


def test_a_reply_with_no_turn_behind_it_is_dropped(root: Path, project_dir: Path) -> None:
    out, _ = _run(root, json.dumps(_event("afterAgentResponse", project_dir)), "--project", "my-app")
    assert out == {}
    assert not (root / "projects" / "my-app" / "chats" / _AGENT / "chat.md").exists()


def test_project_is_resolved_from_the_workspace_roots_without_a_project_flag(root: Path, tmp_path: Path) -> None:
    outer = tmp_path / "code"
    inner = outer / "my-app"
    inner.mkdir(parents=True)
    (root / "integrations.csv").write_text(
        f"project,path,created_date\nouter,{outer},2610-14\nmy-app,{inner},2610-14\n", encoding="utf-8")
    # A user-level hooks.json: the folder open in Cursor decides (longest match).
    _run(root, json.dumps(_event("beforeSubmitPrompt", inner / "src")))
    _run(root, json.dumps(_event("afterAgentResponse", inner / "src")))
    assert (root / "projects" / "my-app" / "chats" / _AGENT / "chat.md").exists()
    assert not (root / "projects" / "outer").exists()
    # No roots in the event: the directory the hook runs in (Cursor starts
    # a project hook from the project root).
    ev = _event("beforeSubmitPrompt", inner, conversation_id="other-conv", prompt="from cwd")
    del ev["workspace_roots"]
    _run(root, json.dumps(ev), cwd=outer)
    chat = (root / "projects" / "outer" / "chats" / "cursor-other-co" / "chat.md").read_text(encoding="utf-8")
    assert "**User**: from cwd" in chat
    # An unregistered folder records nothing and still lets the prompt through.
    out, _ = _run(root, json.dumps(_event("beforeSubmitPrompt", tmp_path / "elsewhere", conversation_id="x")))
    assert out == {"continue": True}
    assert not (root / "projects" / "my-app" / "chats" / "cursor-x").exists()


def test_a_malformed_or_strange_event_is_answered_and_never_blocks(root: Path, project_dir: Path) -> None:
    out, _ = _run(root, "this is not json", "--project", "my-app")
    assert out == {"continue": True}
    out, _ = _run(root, "", "--project", "my-app")
    assert out == {"continue": True}
    out, _ = _run(root, "[1, 2]", "--project", "my-app")
    assert out == {"continue": True}
    out, _ = _run(root, json.dumps({"hook_event_name": "afterFileEdit", "file_path": "x"}), "--project", "my-app")
    assert out == {}
    out, _ = _run(root, json.dumps(_event("beforeSubmitPrompt", project_dir, prompt=None)), "--project", "my-app")
    assert out == {"continue": True}
    assert not (root / "projects").exists()


def test_a_missing_data_root_is_named_and_never_built(tmp_path: Path, project_dir: Path) -> None:
    gone = tmp_path / "unmounted" / "data"
    out, err = _run(gone, json.dumps(_event("beforeSubmitPrompt", project_dir)), "--project", "my-app")
    assert out == {"continue": True}
    assert "[slightly-parallel] capture failed" in err and str(gone) in err
    assert not gone.exists()


def test_a_capture_failure_is_kept_for_the_dashboard(root: Path, project_dir: Path) -> None:
    # The chat folder is a file: the capture core cannot write there.
    (root / "projects" / "my-app" / "chats").mkdir(parents=True)
    (root / "projects" / "my-app" / "chats" / _AGENT).write_text("in the way", encoding="utf-8")
    out, err = _run(root, json.dumps(_event("beforeSubmitPrompt", project_dir)), "--project", "my-app")
    assert out == {"continue": True}
    assert "capture failed" in err
    errors = (root / ".capture" / "errors.jsonl").read_text(encoding="utf-8").splitlines()
    rec = json.loads(errors[-1])
    assert rec["tool"] == "cursor" and rec["agent_id"] == _AGENT and rec["error"].startswith("beforeSubmitPrompt:")


# ---------------------------------------------------------------------------
# Setup: .cursor/hooks.json
# ---------------------------------------------------------------------------


@pytest.fixture()
def env(tmp_path: Path):
    data_root = tmp_path / "data"
    data_root.mkdir()
    project_dir = tmp_path / "my-app"
    project_dir.mkdir()
    app = create_app(data_root=data_root, watch=False)
    with TestClient(app) as client:
        yield client, data_root, project_dir


def _integrate(client: TestClient, project_dir: Path, **overrides) -> dict:
    r = client.post("/api/setup/integrate", json={
        "project_code": "my-app", "project_dir": str(project_dir), **overrides,
    })
    assert r.status_code == 200, r.text
    return r.json()


def _actions(out: dict) -> dict[str, str]:
    return {"/".join(Path(r["file"]).parts[-2:]): r["action"] for r in out["results"]}


def test_integrate_writes_cursor_hooks_once(env) -> None:
    client, _root, project_dir = env
    out = _integrate(client, project_dir, write_cursor_hooks=True)
    assert _actions(out)[".cursor/hooks.json"] == "created"
    data = json.loads((project_dir / ".cursor" / "hooks.json").read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert sorted(data["hooks"]) == sorted(setup_router.CURSOR_EVENTS)
    for event in setup_router.CURSOR_EVENTS:
        cmds = [e["command"] for e in data["hooks"][event]]
        assert len(cmds) == 1
        assert "cursor-capture.py" in cmds[0] and "--project my-app" in cmds[0] and cmds[0].endswith(" || exit 0")
        assert "claude-code-capture.py" not in cmds[0]
    assert _actions(_integrate(client, project_dir, write_cursor_hooks=True))[".cursor/hooks.json"] == "unchanged"
    # Off by default, like the Codex hooks.
    assert ".cursor/hooks.json" not in _actions(_integrate(client, project_dir))


def test_cursor_hooks_merge_into_an_existing_file_and_leave_with_only_their_own(env) -> None:
    client, _root, project_dir = env
    (project_dir / ".cursor").mkdir()
    before = {
        "version": 1,
        "hooks": {
            "beforeSubmitPrompt": [{"command": "./hooks/lint-prompt.sh", "timeout": 5}],
            "afterFileEdit": [{"command": "./hooks/format.sh"}],
        },
    }
    (project_dir / ".cursor" / "hooks.json").write_text(json.dumps(before), encoding="utf-8")
    out = _integrate(client, project_dir, write_cursor_hooks=True)
    assert _actions(out)[".cursor/hooks.json"] == "updated"
    data = json.loads((project_dir / ".cursor" / "hooks.json").read_text(encoding="utf-8"))
    assert data["hooks"]["afterFileEdit"] == [{"command": "./hooks/format.sh"}]
    assert data["hooks"]["beforeSubmitPrompt"][0] == {"command": "./hooks/lint-prompt.sh", "timeout": 5}
    assert len(data["hooks"]["beforeSubmitPrompt"]) == 2
    assert all(len(data["hooks"][ev]) == 1 for ev in ("afterAgentResponse", "stop"))

    r = client.post("/api/setup/forget", json={"project_code": "my-app", "path": str(project_dir)})
    assert r.status_code == 200, r.text
    assert r.json()["hooks"] == "updated"
    after = json.loads((project_dir / ".cursor" / "hooks.json").read_text(encoding="utf-8"))
    assert after == before


def test_disconnect_removes_a_cursor_file_that_was_all_ours(env) -> None:
    client, _root, project_dir = env
    _integrate(client, project_dir, write_cursor_hooks=True)
    assert (project_dir / ".cursor" / "hooks.json").exists()
    r = client.post("/api/setup/forget", json={"project_code": "my-app", "path": str(project_dir)})
    assert r.status_code == 200, r.text
    assert not (project_dir / ".cursor").exists()


def test_cursor_hooks_bring_the_mcp_server_into_cursors_own_file(env) -> None:
    client, _root, project_dir = env
    (project_dir / ".cursor").mkdir()
    other = {"mcpServers": {"other": {"command": "other-server", "args": []}}}
    (project_dir / ".cursor" / "mcp.json").write_text(json.dumps(other), encoding="utf-8")
    out = _integrate(client, project_dir, write_cursor_hooks=True)
    assert _actions(out)[".cursor/mcp.json"] == "updated"
    servers = json.loads((project_dir / ".cursor" / "mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    assert servers["other"] == other["mcpServers"]["other"]
    # The same definition Claude Code gets in .mcp.json (Cursor's shape is the same).
    claude = json.loads((project_dir / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["slightly-parallel"]
    assert servers["slightly-parallel"] == claude
    assert servers["slightly-parallel"]["args"] == ["-m", "backend.mcp"] and "SP_API" in servers["slightly-parallel"]["env"]
    assert _actions(_integrate(client, project_dir, write_cursor_hooks=True))[".cursor/mcp.json"] == "unchanged"
    # Without the Cursor hooks, Cursor's file is left alone.
    (project_dir / ".cursor" / "mcp.json").write_text(json.dumps(other), encoding="utf-8")
    assert ".cursor/mcp.json" not in _actions(_integrate(client, project_dir))
    assert json.loads((project_dir / ".cursor" / "mcp.json").read_text(encoding="utf-8")) == other

    _integrate(client, project_dir, write_cursor_hooks=True)
    r = client.post("/api/setup/forget", json={"project_code": "my-app", "path": str(project_dir)})
    assert r.status_code == 200, r.text
    assert r.json()["mcp"] == "updated"
    assert json.loads((project_dir / ".cursor" / "mcp.json").read_text(encoding="utf-8")) == other
    assert not (project_dir / ".cursor" / "hooks.json").exists()


def test_disconnect_removes_a_cursor_mcp_file_that_was_all_ours(env) -> None:
    client, _root, project_dir = env
    _integrate(client, project_dir, write_cursor_hooks=True)
    assert (project_dir / ".cursor" / "mcp.json").exists()
    client.post("/api/setup/forget", json={"project_code": "my-app", "path": str(project_dir)})
    assert not (project_dir / ".cursor").exists()


def test_a_cursor_file_of_another_shape_is_refused_in_words(env) -> None:
    client, _root, project_dir = env
    (project_dir / ".cursor").mkdir()
    (project_dir / ".cursor" / "hooks.json").write_text("{not json", encoding="utf-8")
    r = client.post("/api/setup/integrate", json={
        "project_code": "my-app", "project_dir": str(project_dir), "write_cursor_hooks": True,
    })
    assert r.status_code == 422 and ".cursor/hooks.json" in r.json()["detail"]
    (project_dir / ".cursor" / "hooks.json").write_text(json.dumps({"version": 1, "hooks": []}), encoding="utf-8")
    r = client.post("/api/setup/integrate", json={
        "project_code": "my-app", "project_dir": str(project_dir), "write_cursor_hooks": True,
    })
    assert r.status_code == 422 and "`hooks` is not an object" in r.json()["detail"]


def test_setup_info_reports_the_cursor_adapter_like_the_others(env, tmp_path: Path) -> None:
    client, data_root, project_dir = env
    flags = client.get("/api/setup/info").json()["adapters"]
    assert flags["cursor_verified"] is False
    folder = data_root / "projects" / "alpha" / "chats" / "cursor-abc123"
    folder.mkdir(parents=True)
    (folder / "meta.json").write_text(json.dumps({"agent_id": "cursor-abc123", "project": "alpha"}), encoding="utf-8")
    (folder / "chat.md").write_text("## Turn 1 · 2026-10-14T10:00:00\n", encoding="utf-8")
    client.app.state.store.rebuild()
    assert client.get("/api/setup/info").json()["adapters"]["cursor_verified"] is True

    # A hook whose script moved away is flagged, for Cursor as for the others.
    _integrate(client, project_dir, write_cursor_hooks=True)
    assert client.get("/api/setup/info").json()["integrations"][0]["hooks_missing_script"] == []
    hooks = project_dir / ".cursor" / "hooks.json"
    # Paths as the hook line writes them (forward slashes on Windows).
    moved = setup_router._arg(tmp_path / "old-place" / "cursor-capture.py")
    # The file is JSON: the path stands in it escaped.
    hooks.write_text(hooks.read_text(encoding="utf-8").replace(json.dumps(setup_router._arg(setup_router._CURSOR_SCRIPT))[1:-1], json.dumps(moved)[1:-1]), encoding="utf-8")
    assert client.get("/api/setup/info").json()["integrations"][0]["hooks_missing_script"] == [moved]


def test_the_written_hook_command_runs_and_answers_even_when_its_script_is_gone(tmp_path: Path) -> None:
    command = setup_router._cursor_hook_command("my-app", tmp_path)
    gone = command.replace(str(setup_router._CURSOR_SCRIPT), str(tmp_path / "moved" / "cursor-capture.py"))
    proc = subprocess.run(gone, shell=True, input="{}", capture_output=True, text=True)
    assert proc.returncode == 0  # never 2: Cursor would block the prompt
    (tmp_path / "data").mkdir()
    proc = subprocess.run(setup_router._cursor_hook_command("my-app", tmp_path / "data"), shell=True,
                          input=json.dumps({"hook_event_name": "beforeSubmitPrompt", "prompt": "x",
                                            "conversation_id": "c"}), capture_output=True, text=True)
    assert proc.returncode == 0 and json.loads(proc.stdout) == {"continue": True}
