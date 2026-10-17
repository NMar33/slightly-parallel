"""Setup endpoints: writing the integration block into target projects."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.routers.setup import BEGIN_MARK, BRIDGE_LINE, END_MARK
from backend.server import create_app


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
    body = {
        "project_code": "my-app",
        "project_dir": str(project_dir),
        **overrides,
    }
    r = client.post("/api/setup/integrate", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_integrate_creates_agents_and_bridge(env) -> None:
    client, data_root, project_dir = env
    out = _integrate(client, project_dir)

    agents = (project_dir / "AGENTS.md").read_text(encoding="utf-8")
    assert BEGIN_MARK in agents and END_MARK in agents
    assert "Project code: `my-app`" in agents
    assert "SLIGHTLY-PARALLEL.md" in agents

    claude = (project_dir / "CLAUDE.md").read_text(encoding="utf-8")
    assert BRIDGE_LINE in claude

    actions = {Path(r["file"]).name: r["action"] for r in out["results"]}
    assert actions == {
        "AGENTS.md": "created",
        "CLAUDE.md": "created",
        "settings.local.json": "created",
        ".mcp.json": "created",
    }

    # The capture hooks were installed alongside the block.
    hooks = json.loads(
        (project_dir / ".claude" / "settings.local.json").read_text(
            encoding="utf-8"
        )
    )["hooks"]
    for event in ("UserPromptSubmit", "Stop"):
        commands = [
            h["command"] for e in hooks[event] for h in e["hooks"]
        ]
        assert any("claude-code-capture.py" in c for c in commands)
        assert any("--project my-app" in c for c in commands)

    # Project folder materialized; integration recorded.
    assert (data_root / "projects" / "my-app").is_dir()
    info = client.get("/api/setup/info").json()
    assert info["integrations"][0]["project"] == "my-app"
    assert info["integrations"][0]["status"] == "fresh"


def test_integrate_appends_without_touching_existing_content(env) -> None:
    client, _root, project_dir = env
    (project_dir / "AGENTS.md").write_text(
        "# My project\n\nOwn instructions here.\n", encoding="utf-8"
    )
    (project_dir / "CLAUDE.md").write_text("My claude notes\n", encoding="utf-8")

    _integrate(client, project_dir)

    agents = (project_dir / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.startswith("# My project")
    assert "Own instructions here." in agents
    assert BEGIN_MARK in agents

    claude = (project_dir / "CLAUDE.md").read_text(encoding="utf-8")
    assert claude.startswith("My claude notes")
    assert claude.rstrip().endswith(BRIDGE_LINE)


def test_reintegrate_updates_block_in_place(env) -> None:
    client, _root, project_dir = env
    _integrate(client, project_dir)
    first = (project_dir / "AGENTS.md").read_text(encoding="utf-8")

    out = _integrate(client, project_dir, notes="checkpoint before every commit")
    second = (project_dir / "AGENTS.md").read_text(encoding="utf-8")

    assert second.count(BEGIN_MARK) == 1  # replaced, not duplicated
    assert "checkpoint before every commit" in second
    assert first != second
    agents_action = next(
        r["action"] for r in out["results"] if r["file"].endswith("AGENTS.md")
    )
    assert agents_action == "updated"


def test_reintegrate_identical_is_unchanged(env) -> None:
    client, _root, project_dir = env
    _integrate(client, project_dir)
    out = _integrate(client, project_dir)
    assert all(r["action"] == "unchanged" for r in out["results"])


def test_dry_run_touches_nothing(env) -> None:
    client, data_root, project_dir = env
    out = _integrate(client, project_dir, dry_run=True)
    assert out["dry_run"] is True
    assert not (project_dir / "AGENTS.md").exists()
    assert not (project_dir / "CLAUDE.md").exists()
    assert not (data_root / "integrations.csv").exists()
    # Preview content is still returned.
    assert any(BEGIN_MARK in r["content"] for r in out["results"])


def test_validation_rejects_bad_inputs(env) -> None:
    client, _root, project_dir = env
    bad_code = client.post(
        "/api/setup/integrate",
        json={"project_code": "Bad Code!", "project_dir": str(project_dir)},
    )
    assert bad_code.status_code == 422

    missing_dir = client.post(
        "/api/setup/integrate",
        json={"project_code": "ok", "project_dir": str(project_dir / "nope")},
    )
    assert missing_dir.status_code == 422

    relative = client.post(
        "/api/setup/integrate",
        json={"project_code": "ok", "project_dir": "some/relative/path"},
    )
    assert relative.status_code == 422


def test_forget_removes_registry_entry_and_leaves_user_files(env) -> None:
    client, _root, project_dir = env
    (project_dir / "README.md").write_text("mine\n", encoding="utf-8")
    _integrate(client, project_dir)
    r = client.post(
        "/api/setup/forget",
        json={"project_code": "my-app", "path": str(project_dir)},
    )
    assert r.status_code == 200
    assert client.get("/api/setup/info").json()["integrations"] == []
    # Only what Setup wrote is undone; the user's files are untouched.
    assert (project_dir / "README.md").read_text(encoding="utf-8") == "mine\n"


def test_integrate_writes_opencode_plugin(env) -> None:
    client, _data_root, project_dir = env
    out = _integrate(client, project_dir, write_opencode_plugin=True)
    plugin = project_dir / ".opencode" / "plugin" / "slightly-parallel.js"
    assert plugin.exists()
    text = plugin.read_text(encoding="utf-8")
    assert 'project: "my-app"' in text
    assert "capture-cli.py" in text
    actions = {Path(r["file"]).name: r["action"] for r in out["results"]}
    assert actions["slightly-parallel.js"] == "created"

    # Re-integrating is idempotent.
    out2 = _integrate(client, project_dir, write_opencode_plugin=True)
    actions2 = {Path(r["file"]).name: r["action"] for r in out2["results"]}
    assert actions2["slightly-parallel.js"] == "unchanged"


def test_codex_install_remove_and_foreign_guard(
    env, tmp_path: Path, monkeypatch
) -> None:
    from backend.routers import setup as setup_router

    client, _data_root, _project_dir = env
    cfg = tmp_path / "codex-config.toml"
    monkeypatch.setattr(setup_router, "CODEX_CONFIG_PATH", cfg)

    # Fresh install creates the file with our notify line.
    r = client.post("/api/setup/codex", json={"action": "install"})
    assert r.status_code == 200
    assert r.json()["status"]["state"] == "installed"
    assert "codex-capture.py" in cfg.read_text(encoding="utf-8")

    # Reinstall is a no-op; other content is preserved on remove.
    cfg.write_text(
        'model = "o4"\n' + setup_router._codex_notify_line(Path("/x")) + "\n",
        encoding="utf-8",
    )
    r = client.post("/api/setup/codex", json={"action": "remove"})
    assert r.status_code == 200
    text = cfg.read_text(encoding="utf-8")
    assert "codex-capture.py" not in text
    assert 'model = "o4"' in text

    # A foreign notify entry is never overwritten.
    cfg.write_text('notify = ["osascript", "notify.scpt"]\n', encoding="utf-8")
    r = client.post("/api/setup/codex", json={"action": "install"})
    assert r.status_code == 409
    assert "osascript" in cfg.read_text(encoding="utf-8")


def test_adapter_verification_flags(env) -> None:
    client, data_root, _project_dir = env
    flags = client.get("/api/setup/info").json()["adapters"]
    assert flags == {
        "claude_verified": False,
        "opencode_verified": False,
        "codex_verified": False,
        "cursor_verified": False,
    }

    # First captured OpenCode agent flips its flag.
    folder = data_root / "projects" / "alpha" / "chats" / "oc-abc123"
    folder.mkdir(parents=True)
    (folder / "meta.json").write_text(
        json.dumps({"agent_id": "oc-abc123", "project": "alpha"}),
        encoding="utf-8",
    )
    (folder / "chat.md").write_text("## Turn 1 · 2026-08-14T10:00:00\n", encoding="utf-8")
    client.post("/api/setup/data-root", json={"path": str(data_root)})  # force rebuild? not needed
    flags = client.get("/api/setup/info").json()["adapters"]
    assert flags["opencode_verified"] is True
    assert flags["codex_verified"] is False


# ---------------------------------------------------------------------------
# Removing a project: disconnect (undo Setup's writes) vs delete data (trash)
# ---------------------------------------------------------------------------


def test_disconnect_undoes_every_file_setup_wrote(env) -> None:
    client, data_root, project_dir = env
    (project_dir / "AGENTS.md").write_text("# Mine\n\nkeep this\n", encoding="utf-8")
    (project_dir / "CLAUDE.md").write_text("# Notes\n", encoding="utf-8")
    _integrate(client, project_dir)
    assert BEGIN_MARK in (project_dir / "AGENTS.md").read_text(encoding="utf-8")
    assert "claude-code-capture.py" in (project_dir / ".claude" / "settings.local.json").read_text(encoding="utf-8")

    r = client.post("/api/setup/forget", json={"project_code": "my-app", "path": str(project_dir)})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["agents_md"] == "removed" and out["claude_md"] == "removed"

    agents = (project_dir / "AGENTS.md").read_text(encoding="utf-8")
    assert BEGIN_MARK not in agents and "keep this" in agents      # user text survives
    claude = (project_dir / "CLAUDE.md").read_text(encoding="utf-8")
    assert BRIDGE_LINE not in claude and "# Notes" in claude
    # What Setup made and nothing else used is gone: the hooks file, its folder, the MCP wiring.
    assert not (project_dir / ".claude").exists()
    assert not (project_dir / ".mcp.json").exists()
    info = client.get("/api/setup/info").json()
    assert all(i["project"] != "my-app" for i in info["integrations"])


def test_disconnect_takes_out_the_sets_slightly_parallel_wrote(env) -> None:
    client, data_root, project_dir = env
    (project_dir / "AGENTS.md").write_text("# Mine\n\nkeep this\n", encoding="utf-8")
    _integrate(client, project_dir)
    with open(project_dir / "AGENTS.md", "a", encoding="utf-8") as fh:
        fh.write("\n<!-- sp:set all-rules -->\n## Rules for all agents\n\n1. Ask first.\n<!-- sp:set-end all-rules -->\n"
                 "\n<!-- sp:set ks_1a2b3c4d -->\n## Design\n\ntext\n<!-- sp:set-end ks_1a2b3c4d -->\n")
    (data_root / "set_integrations.json").write_text(json.dumps({"integrations": [
        {"set_id": "all-rules", "project": "my-app", "path": str(project_dir), "written_at": "2026-09-16T10:00:00"},
        {"set_id": "ks_1a2b3c4d", "project": "other", "path": "/elsewhere", "written_at": "2026-09-16T10:00:00"},
    ]}), encoding="utf-8")

    out = client.post("/api/setup/forget", json={"project_code": "my-app", "path": str(project_dir)}).json()
    assert out["sets"] == "removed"
    agents = (project_dir / "AGENTS.md").read_text(encoding="utf-8")
    assert "sp:set" not in agents and "keep this" in agents
    ledger = json.loads((data_root / "set_integrations.json").read_text(encoding="utf-8"))["integrations"]
    assert [e["project"] for e in ledger] == ["other"]


def test_disconnect_deletes_files_setup_created_from_nothing(env) -> None:
    client, _root, project_dir = env
    _integrate(client, project_dir)                # AGENTS.md / CLAUDE.md did not exist
    client.post("/api/setup/forget", json={"project_code": "my-app", "path": str(project_dir)})
    assert not (project_dir / "AGENTS.md").exists()
    assert not (project_dir / "CLAUDE.md").exists()


def _seed_project(client: TestClient, code: str, root: Path) -> None:
    chats = root / "projects" / code / "chats" / f"cc-{code}"
    chats.mkdir(parents=True)
    chats.joinpath("chat.md").write_text(
        f"# Chat log\n\n---\n\n## Turn 1 · 2026-08-19T09:00:00\n**User**: hi {code}\n**Agent**: ok\n",
        encoding="utf-8",
    )
    chats.joinpath("meta.json").write_text(json.dumps({"agent_id": f"cc-{code}"}), encoding="utf-8")
    client.app.state.store.rebuild()
    assert client.post("/api/scans", json={
        "created_date": "2608-19", "created_time": "09:10", "project": code,
        "agent_id": f"cc-{code}", "l1": f"{code} scan", "l2": "why",
    }).status_code == 201
    assert client.post("/api/decisions", json={
        "created_date": "2608-19", "created_time": "09:11", "project": code,
        "agent_id": f"cc-{code}", "decision_text": f"{code} decided",
        "l2": "revisit if x", "l3": ["a — rejected: b"],
    }).status_code == 201
    t = client.post("/api/tasks", json={
        "created_date": "2608-19", "created_time": "09:12", "project": code,
        "agent_id": f"cc-{code}", "title": f"{code} task", "tags": "ag_followup",
    })
    assert t.status_code == 201, t.text
    tid = t.json()["metadata"]["id"]
    assert client.post(f"/api/tasks/{tid}/update", json={"status": "doing"}).status_code == 200


def test_delete_data_archives_only_that_project(env) -> None:
    client, data_root, _dir = env
    _seed_project(client, "alpha", data_root)
    _seed_project(client, "beta", data_root)
    # A sprint spanning both projects keeps living, minus the membership.
    assert client.post("/api/sprints", json={
        "created_date": "2608-19", "started_date": "2608-19", "name": "S1",
        "projects": "alpha,beta", "status": "active", "agent_id": "operator", "project": "alpha",
    }).status_code == 201

    bad = client.post("/api/setup/delete-data", json={"project_code": "alpha", "confirm": "nope"})
    assert bad.status_code == 422

    r = client.post("/api/setup/delete-data", json={"project_code": "alpha", "confirm": "alpha"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["moved"]["scans"] == 1 and out["moved"]["decisions"] == 1
    assert out["moved"]["tasks"] == 1 and out["moved"]["task_events"] >= 1
    assert out["moved"]["projects_folder"] == 1 and out["moved"]["detail_docs"] >= 2
    assert out["moved"]["sprints_membership_stripped"] == 1

    # Live data: alpha gone, beta intact, sprint still there for beta only.
    assert client.get("/api/scans?project=alpha").json()["total"] == 0
    assert client.get("/api/scans?project=beta").json()["total"] == 1
    assert client.get("/api/decisions?project=beta").json()["total"] == 1
    assert client.get("/api/sessions?project=alpha").json()["total"] == 0
    assert client.get("/api/sessions?project=beta").json()["total"] == 1
    sp = client.get("/api/sprints").json()["sprints"][0]
    assert sp["projects"] == "beta"

    # Everything is in the trash, restorable by moving it back.
    trash = Path(out["trash"])
    assert (trash / "projects" / "alpha" / "chats" / "cc-alpha" / "chat.md").exists()
    assert (trash / "scans.csv").exists() and (trash / "decisions.csv").exists()
    assert any(trash.glob("snapshots/*.md")) and any(trash.glob("decision_details/*.md"))
    assert all(p["code"] != "alpha" for p in client.get("/api/setup/info").json()["data_projects"])


def test_integrate_writes_codex_hooks(env) -> None:
    client, _data_root, project_dir = env
    out = _integrate(client, project_dir, write_codex_hooks=True)
    hooks = project_dir / ".codex" / "hooks.json"
    assert hooks.exists()
    data = json.loads(hooks.read_text(encoding="utf-8"))
    for event in ("UserPromptSubmit", "Stop"):
        cmds = [h["command"] for e in data["hooks"][event] for h in e["hooks"]]
        assert len(cmds) == 1 and "claude-code-capture.py" in cmds[0] and "--tool codex" in cmds[0]
    actions = {Path(r["file"]).name: r["action"] for r in out["results"]}
    assert actions["hooks.json"] == "created"
    out2 = _integrate(client, project_dir, write_codex_hooks=True)
    actions2 = {Path(r["file"]).name: r["action"] for r in out2["results"]}
    assert actions2["hooks.json"] == "unchanged"


def test_disconnect_keeps_what_was_yours_in_the_files_it_shares(env) -> None:
    client, data_root, project_dir = env
    (project_dir / ".claude").mkdir()
    (project_dir / ".claude" / "settings.local.json").write_text(
        json.dumps({"permissions": {"allow": ["Bash(ls:*)"]}}), encoding="utf-8")
    (project_dir / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"other": {"command": "other-server"}}}), encoding="utf-8")
    _integrate(client, project_dir)
    assert "slightly-parallel" in json.loads((project_dir / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]

    r = client.post("/api/setup/forget", json={"project_code": "my-app", "path": str(project_dir)})
    assert r.status_code == 200, r.text
    assert r.json()["mcp"] == "updated"
    settings = json.loads((project_dir / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
    assert settings == {"permissions": {"allow": ["Bash(ls:*)"]}}
    servers = json.loads((project_dir / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    assert servers == {"other": {"command": "other-server"}}


def test_a_data_folder_slightly_parallel_cannot_write_to_is_refused_in_words(env, tmp_path) -> None:
    import os
    if os.name == "nt" or os.geteuid() == 0:
        pytest.skip("permissions do not stop this user")
    client, data_root, project_dir = env
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o555)
    try:
        r = client.post("/api/setup/data-root", json={"path": str(locked)})
        assert r.status_code == 422, r.text
        assert "cannot write" in r.json()["detail"]
        # The server still reads the folder it had.
        assert client.get("/api/setup/info").json()["data_root"] == str(data_root)
    finally:
        locked.chmod(0o755)


def test_hook_command_never_exits_2_when_its_script_is_gone(env, tmp_path: Path) -> None:
    """Exit 2 from a Claude Code hook blocks the prompt (UserPromptSubmit)
    or forces the agent on (Stop). A hook whose script was moved away must
    exit 0 instead."""
    import subprocess

    from backend.routers import setup

    command = setup._hook_command("my-app", tmp_path)
    assert command.endswith(" || exit 0")
    gone = command.replace(setup._arg(setup._CAPTURE_SCRIPT), setup._arg(tmp_path / "moved" / "claude-code-capture.py"))
    bare = gone[: -len(" || exit 0")]
    assert subprocess.run(bare, shell=True, input="{}", capture_output=True, text=True).returncode == 2
    assert subprocess.run(gone, shell=True, input="{}", capture_output=True, text=True).returncode == 0


def test_setup_info_flags_a_hook_whose_script_no_longer_exists(env, tmp_path: Path) -> None:
    client, _root, project_dir = env
    _integrate(client, project_dir, write_codex_hooks=True)
    row = client.get("/api/setup/info").json()["integrations"][0]
    assert row["hooks"] is True and row["hooks_missing_script"] == []

    # The repository moves: the hook still names the old path.
    settings = project_dir / ".claude" / "settings.local.json"
    from backend.routers import setup
    # Paths as the hook line writes them (forward slashes on Windows).
    old = setup._arg(setup._CAPTURE_SCRIPT)
    moved = setup._arg(tmp_path / "old-place" / "claude-code-capture.py")
    # The file is JSON: the path stands in it escaped.
    settings.write_text(settings.read_text(encoding="utf-8").replace(json.dumps(old)[1:-1], json.dumps(moved)[1:-1]), encoding="utf-8")
    row = client.get("/api/setup/info").json()["integrations"][0]
    assert row["hooks"] is True
    assert row["hooks_missing_script"] == [moved]


def test_info_says_which_tools_record_each_project(env) -> None:
    """A tool the project is not wired to loses its chats without a word:
    the page needs to know, per project, which tools record there."""
    client, _data_root, project_dir = env
    _integrate(client, project_dir)
    row = client.get("/api/setup/info").json()["integrations"][0]
    assert row["tools"] == {"claude": True, "codex": False, "opencode": False, "cursor": False}
    _integrate(client, project_dir, write_codex_hooks=True, write_opencode_plugin=True, write_cursor_hooks=True)
    row = client.get("/api/setup/info").json()["integrations"][0]
    assert row["tools"] == {"claude": True, "codex": True, "opencode": True, "cursor": True}


def test_installed_tools_are_found_by_command_or_by_their_settings_folder(tmp_path: Path, monkeypatch) -> None:
    from backend.routers import setup
    home = tmp_path / "home"
    (home / ".codex" / "sessions").mkdir(parents=True)         # the tool has been used
    (home / ".cursor").mkdir()
    monkeypatch.setattr(setup.shutil, "which", lambda c: "/usr/bin/opencode" if c == "opencode" else None)
    assert setup.tools_installed(home) == {"claude": False, "codex": True, "opencode": True, "cursor": True}
    # ~/.codex with only the MCP block Setup writes is not Codex being there.
    other = tmp_path / "other"; (other / ".codex").mkdir(parents=True); (other / ".codex" / "config.toml").write_text("x")
    monkeypatch.setattr(setup.shutil, "which", lambda c: None)
    assert setup.tools_installed(other)["codex"] is False


def test_the_codex_box_also_gives_codex_the_mcp_server(env) -> None:
    """Codex reads MCP servers from ~/.codex/config.toml only: without the
    block a Codex agent can record nothing it is asked to."""
    from backend.routers import setup as setup_router
    client, _data_root, project_dir = env
    out = _integrate(client, project_dir, write_codex_hooks=True)
    cfg = setup_router.CODEX_CONFIG_PATH
    assert "[mcp_servers.slightly-parallel]" in cfg.read_text(encoding="utf-8")
    assert {r["file"]: r["action"] for r in out["results"]}[str(cfg)] == "created"
    again = _integrate(client, project_dir, write_codex_hooks=True)
    assert {r["file"]: r["action"] for r in again["results"]}[str(cfg)] == "unchanged"
    assert cfg.read_text(encoding="utf-8").count("[mcp_servers.slightly-parallel]") == 1


def test_the_codex_mcp_block_never_makes_a_second_table(env) -> None:
    """A config that names our server another way, or that Codex cannot read,
    is left alone; the block carries PYTHONUTF8 like the other tools' entries."""
    from backend.routers import setup as setup_router
    client, _data_root, project_dir = env
    cfg = setup_router.CODEX_CONFIG_PATH
    cfg.parent.mkdir(parents=True, exist_ok=True)
    quoted = '[mcp_servers."slightly-parallel"]\ncommand = "x"\n'
    cfg.write_text(quoted, encoding="utf-8")
    _integrate(client, project_dir, write_codex_hooks=True)
    assert cfg.read_text(encoding="utf-8") == quoted
    cfg.write_text("this is = = not toml", encoding="utf-8")
    _integrate(client, project_dir, write_codex_hooks=True)
    assert cfg.read_text(encoding="utf-8") == "this is = = not toml"
    cfg.unlink()
    _integrate(client, project_dir, write_codex_hooks=True)
    assert "PYTHONUTF8" in cfg.read_text(encoding="utf-8")


def test_a_windows_hook_line_never_ends_a_path_with_a_backslash(monkeypatch) -> None:
    """A data folder at a drive's root wrote --data-root "D:\\" : the backslash
    escaped the quote in the tool's shell, and every prompt was refused."""
    from backend.routers import setup as setup_router
    monkeypatch.setattr(setup_router, "_windows", lambda: True)
    line = setup_router._hook_command("app", Path("D:\\"))
    assert '\\"' not in line and '--data-root "D:/"' in line
    unc = setup_router._cursor_hook_command("app", Path("\\\\nas\\sp"))
    assert '--data-root "//nas/sp' in unc and '\\"' not in unc


def test_the_codex_hook_line_on_windows_is_powershell(monkeypatch) -> None:
    """Codex runs a hook in PowerShell on Windows: the line calls the program
    with & and ends in ; exit 0 (no ||, which Windows PowerShell 5.1 lacks)."""
    from backend.routers import setup as setup_router
    monkeypatch.setattr(setup_router, "_windows", lambda: True)
    line = setup_router._hook_command("app", Path("D:\\data"), tool="codex")
    assert line.startswith("& ") and line.endswith("; exit 0") and "||" not in line and "--tool codex" in line
    assert setup_router._hook_command("app", Path("D:\\data")).endswith(" || exit 0")      # Claude Code keeps its shape


def test_codex_home_follows_codex_home(monkeypatch, tmp_path) -> None:
    from backend.hookshared import codex_home
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "ch"))
    assert codex_home() == tmp_path / "ch"
    monkeypatch.delenv("CODEX_HOME")
    assert codex_home() == Path.home() / ".codex"
