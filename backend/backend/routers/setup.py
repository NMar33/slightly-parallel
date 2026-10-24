"""Project integration — the Setup page's backend.

Writes the Slightly Parallel section into a target project's ``AGENTS.md`` (and the
``@AGENTS.md`` bridge line into ``CLAUDE.md``), so integrating a project is
a form submit instead of hand-editing files.

Safety model: this endpoint writes OUTSIDE the data root by design — that is
its purpose — but only ever to files named exactly ``AGENTS.md`` or
``CLAUDE.md`` inside an operator-supplied existing directory, and only with
server-composed content. The managed block is fenced by marker comments so
re-integration replaces it in place; operator content around it is never
touched. Integrations are recorded in ``integrations.csv`` at the data root
so the page can show status and refresh stale blocks after a contract move.
"""

from __future__ import annotations

import json
import shutil
import os
import re
from typing import Any
import string
import subprocess
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from .. import example
from ..config import Settings
from ..csvio import append_if_absent, read_rows, rewrite_rows
from ..project_admin import (
    delete_project_data, known_projects, remove_block, remove_bridge, strip_file,
)
from ..date_utils import today_yymm_dd
from ..db import ViewStore
from ..file_safety import write_in_place
from ..hookshared import codex_home
from ..integration_text import (
    BEGIN_MARK, BRIDGE_LINE, END_MARK, MCP_SERVER, _CODEX_MCP_RE, _TOML_TABLE_RE, _drop_json_key,
    _insert_top_level, _marks_in, _ours, _remove_cursor_hooks,
    _remove_hooks, _upsert_block, _upsert_bridge, _upsert_codex_mcp, _upsert_cursor_hooks,
    _upsert_hooks, _upsert_json_key,
)
from .deps import get_store
# What Setup left in a project folder, read by this page and by #sp alike
# (folderstate.py: a library, so the checkup imports no router).
from ..folderstate import (  # noqa: E402,F401
    HOOK_FILES as _HOOK_FILES, OPENCODE_PLUGIN as _OPENCODE_PLUGIN, TOOLS, contract_path,
    hooks_file_has as _hooks_file_has,
    hooks_installed as _hooks_installed, integration_status as _integration_status,
    missing_hook_scripts as _missing_hook_scripts, tools_wired as _tools_wired,
)

router = APIRouter()

_REPO_ROOT = Path(__file__).resolve().parents[3]


_PROJECT_CODE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
#: The project's note is one line in AGENTS.md.
NOTES_MAX = 300

_INTEGRATIONS_COLUMNS = ("project", "path", "created_date")


_AGENTS_BLOCK_TEMPLATE = _REPO_ROOT / "templates" / "agents-block.md"


def _compose_block(
    project_code: str, api_url: str, notes: str, data_root: Path,
    project_dir: Path | str = "<the registered project path>",
) -> str:
    """The block between the markers, from the editable template
    (Settings → Agent prompts) with this project's values filled in."""
    template = string.Template(_AGENTS_BLOCK_TEMPLATE.read_text(encoding="utf-8"))
    body = template.safe_substitute(
        project_code=project_code,
        contract=str(contract_path()),
        api_url=api_url,
        data_root=str(data_root),
        project_dir=str(project_dir),
        notes_line=(f"\n- Project notes: {notes.strip()}" if notes.strip() else ""),
    ).strip("\n")
    return "\n".join([BEGIN_MARK, body, END_MARK])


# ---------------------------------------------------------------------------
# OpenCode plugin — automatic verbatim capture
# ---------------------------------------------------------------------------

_OPENCODE_TEMPLATE = _REPO_ROOT / "scripts" / "hooks" / "slightly-parallel-opencode.js"
_CAPTURE_CLI = _REPO_ROOT / "scripts" / "hooks" / "capture-cli.py"


def _compose_opencode_plugin(project_code: str, data_root: Path) -> str:
    """The shipped plugin template with this project's values baked in."""
    template = _OPENCODE_TEMPLATE.read_text(encoding="utf-8")
    config = (
        "const SP = {\n"
        "  // Written by the Slightly Parallel Setup page — re-integrate to refresh.\n"
        # JSON strings are JavaScript strings: a quote in a path stays text.
        f"  python: {json.dumps(_plugin_python())},\n"
        f"  captureCli: {json.dumps(str(_CAPTURE_CLI))},\n"
        f"  project: {json.dumps(project_code)},\n"
        f"  dataRoot: {json.dumps(str(data_root))},\n"
        "}"
    )
    start = template.index("const SP = {")
    end = template.index("}", template.index("dataRoot")) + 1
    return template[:start] + config + template[end:]


# ---------------------------------------------------------------------------
# Claude Code hooks — automatic verbatim capture
# ---------------------------------------------------------------------------

_CAPTURE_SCRIPT = _REPO_ROOT / "scripts" / "hooks" / "claude-code-capture.py"


def _windows() -> bool:
    return os.name == "nt"


def _venv_python() -> Path:
    """The backend's own interpreter, where each system puts it."""
    v = _REPO_ROOT / "backend" / ".venv"
    return v / "Scripts" / "python.exe" if _windows() else v / "bin" / "python"


def _plugin_python() -> list[str]:
    """The interpreter for the OpenCode plugin, as argv words (its shell
    template spreads an array). The same choice as the hooks: python3 where
    it exists; on Windows the backend's own interpreter, else the py launcher."""
    if not _windows():
        return ["python3"]
    venv = _venv_python()
    return [str(venv)] if venv.exists() else ["py", "-3"]


def _hook_python() -> str:
    """What a hook command starts with. Linux and macOS: python3, as always
    (a changed line would read as an outdated install). Windows has no
    python3: the backend's own interpreter by its full path, else the py
    launcher."""
    if not _windows():
        return "python3"
    venv = _venv_python()
    return f'"{_arg(venv)}"' if venv.exists() else "py -3"


def _arg(path: Path) -> str:
    """A path inside the quotes of a hook line, with forward slashes. Python
    takes them on Windows too, and a backslash before the closing quote
    (a data folder at a drive's root, D:\\) escaped it in the shell the
    tool runs, which then refused every prompt; a UNC path lost a slash."""
    return str(path).replace("\\", "/") if _windows() else str(path)


def _hook_command(project_code: str, data_root: Path, tool: str = "claude-code") -> str:
    """The hook line. It ends in ``|| exit 0`` (read the same by sh and
    cmd): when the script is gone — the repository moved, renamed or
    deleted — python exits 2, and Claude Code reads exit 2 on
    UserPromptSubmit as "block this prompt" and on Stop as "keep going".
    A hook must never do either."""
    suffix = "" if tool == "claude-code" else f" --tool {tool}"
    if tool == "codex" and _windows():
        # Codex runs a hook in PowerShell on Windows: a quoted path there is a
        # string, not a command, without the call operator, and Windows
        # PowerShell 5.1 has no ||. The hook failed on every prompt.
        return (
            f'& {_hook_python()} "{_arg(_CAPTURE_SCRIPT)}" '
            f'--project {project_code} --data-root "{_arg(data_root)}"{suffix}; exit 0'
        )
    return (
        f'{_hook_python()} "{_arg(_CAPTURE_SCRIPT)}" '
        f'--project {project_code} --data-root "{_arg(data_root)}"{suffix} || exit 0'
    )


_CURSOR_SCRIPT = _REPO_ROOT / "scripts" / "hooks" / "cursor-capture.py"


def _cursor_hook_command(project_code: str, data_root: Path) -> str:
    """The Cursor hook line: its own adapter, which answers the JSON Cursor
    reads on stdout. The same ``|| exit 0`` tail as the other hooks: Cursor
    reads exit 2 as "block", and a moved repository must never block a prompt."""
    return (
        f'{_hook_python()} "{_arg(_CURSOR_SCRIPT)}" '
        f'--data-root "{_arg(data_root)}" --project {project_code} || exit 0'
    )


def _write_or_remove(path: Path, text: str) -> None:
    """Write the file, or remove it when all that is left is an empty object."""
    try:
        empty = json.loads(text) == {}
    except json.JSONDecodeError:
        empty = False
    if empty:
        path.unlink()
    else:
        write_in_place(path, text)


def _rmdir_if_empty(*folders: Path) -> None:
    for folder in folders:
        try:
            folder.rmdir()   # fails, rightly, on a folder that holds anything
        except OSError:
            return


def _validated_dir(raw: str, label: str = "project_dir") -> Path:
    if not raw or not raw.strip():
        raise HTTPException(status_code=422, detail=f"{label} is required")
    p = Path(raw.strip()).expanduser()
    if not p.is_absolute():
        raise HTTPException(
            status_code=422, detail=f"{label} must be an absolute path"
        )
    try:
        p = p.resolve()
    except OSError as exc:
        raise HTTPException(status_code=422, detail=f"cannot resolve path: {exc}")
    if not p.is_dir():
        raise HTTPException(status_code=422, detail=f"not an existing directory: {p}")
    return p


def _api_url(request: Request) -> str:
    """The backend's canonical address for agents.

    Derived from settings, not request.base_url — in dev the request arrives
    through the Vite proxy and base_url would name the dev server's port.
    """
    settings: Settings = request.app.state.settings
    return f"http://{settings.host}:{settings.port}"


def tools_installed(home: Path | None = None) -> dict[str, bool]:
    """Which tools this computer has: the command on PATH, or the folder the
    tool keeps its settings in (an app started from a menu leaves that too)."""
    home = home or Path.home()
    marks = {
        "claude": (("claude",), (".claude",)),
        # Not ~/.codex itself: Setup writes the MCP server there for everyone.
        "codex": (("codex",), (".codex/sessions", ".codex/auth.json")),
        "opencode": (("opencode",), (".config/opencode", ".local/share/opencode")),
        "cursor": (("cursor", "cursor-agent"), (".cursor",)),
    }
    return {
        tool: any(shutil.which(c) for c in commands) or any((home / d).exists() for d in dirs)
        for tool, (commands, dirs) in marks.items()
    }


def _is_git_repo(path_raw: str) -> bool:
    """Optional: a repo lets file entries fill line counts automatically."""
    p = Path(path_raw)
    if not p.is_dir():
        return False
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"], cwd=str(p),
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


@router.get("/api/setup/info")
def setup_info(
    request: Request,
    store: ViewStore = Depends(get_store),
) -> dict:
    """Everything the Setup page needs: detected paths + known integrations."""
    codex = codex_status()
    from .. import capturewatch
    skip = capturewatch.ignored(store.data_root)
    gone = capturewatch.check(store).get("lost", [])
    integrations = [
        {
            "project": r.get("project", ""),
            "path": r.get("path", ""),
            "created_date": r.get("created_date", ""),
            "status": _integration_status(r.get("path", "")),
            "hooks": _hooks_installed(r.get("path", "")),
            # Which tools record their chats here; a tool this computer has
            # and the project lacks loses its chats without a word.
            "tools": _tools_wired(r.get("path", ""), codex_global=codex["state"] == "installed"),
            # Sessions of the last week the tool ran here and nothing recorded.
            "lost": {g["tool"]: g["sessions"] for g in gone if g["project"] == r.get("project") and g["sessions"] and not g["ignored"]},
            # Sessions nothing recorded that can still be imported from the tool's own log.
            "importable": {g["tool"]: g["sessions"] + g["earlier"] for g in gone if g["project"] == r.get("project")},
            "ignored": sorted(k.split(":", 1)[1] for k in skip if k.split(":", 1)[0] == r.get("project")),
            # A hook whose script path no longer exists records nothing:
            # Setup has to be run again from where the app now lives.
            "hooks_missing_script": _missing_hook_scripts(r.get("path", "")),
            "git": _is_git_repo(r.get("path", "")),
        }
        for r in read_rows(store.data_root / "integrations.csv")
    ]
    # An adapter counts as verified once a real captured agent with its
    # id prefix exists anywhere in the data — self-updating proof.
    agent_ids = [str(a.get("agent_id") or "") for a in store.agents()]
    adapters = {
        "claude_verified": any(i.startswith("cc-") for i in agent_ids),
        "opencode_verified": any(i.startswith("oc-") for i in agent_ids),
        "codex_verified": any(i.startswith("codex-") for i in agent_ids),
        "cursor_verified": any(i.startswith("cursor-") for i in agent_ids),
    }
    return {
        "data_projects": known_projects(store),
        "app_root": str(_REPO_ROOT),
        "contract_path": str(contract_path()),
        "contract_exists": contract_path().exists(),
        "data_root": str(store.data_root),
        # The example project (example.py): on, there, being played.
        "example": example.describe(request.app),
        "api_url": _api_url(request),
        "integrations": integrations,
        "codex": codex,
        "adapters": adapters,
        "tools_installed": tools_installed(),
        "computer": _computer(),
    }


# ---------------------------------------------------------------------------
# This computer: start at login, and the shortcut (autostart.py)
# ---------------------------------------------------------------------------

# Where they are written: the user's home, and this folder's .sp/ for the
# record of what was written. Tests point both at a temporary folder
# (conftest), as they do CODEX_CONFIG_PATH.
AUTOSTART_HOME: Path | None = None
AUTOSTART_ROOT: Path = _REPO_ROOT
SANDBOX_REFUSAL = "a test server (SP_SANDBOX=1) does not change this computer's login or desktop"


def _computer() -> dict:
    from .. import autostart
    return {**autostart.status(AUTOSTART_ROOT), "system": autostart.platform_key(),
            "sandbox": os.environ.get("SP_SANDBOX") == "1" and AUTOSTART_HOME is None}


def _switch(kind: str, on: bool) -> list[str]:
    """Turn one on or off; the files written or removed. Refused on a test
    server, which must not reach the operator's login or desktop."""
    from .. import autostart
    if os.environ.get("SP_SANDBOX") == "1" and AUTOSTART_HOME is None:
        raise HTTPException(status_code=409, detail=SANDBOX_REFUSAL)
    try:
        if on:
            return autostart.enable(AUTOSTART_ROOT, kind, home=AUTOSTART_HOME)
        return autostart.disable(AUTOSTART_ROOT, kind)
    except OSError as exc:
        raise HTTPException(status_code=422, detail=f"{kind}: {exc}") from exc


@router.post("/api/setup/computer")
def setup_computer(body: dict = Body(...)) -> dict:
    """Settings › General: ``{autostart: bool}`` and/or ``{shortcut: bool}``."""
    changed: dict[str, list[str]] = {}
    for kind in ("autostart", "shortcut"):
        if kind in body:
            changed[kind] = _switch(kind, bool(body[kind]))
    return {"changed": changed, "computer": _computer()}


@router.post("/api/setup/integrate")
def integrate(
    request: Request,
    body: dict = Body(...),
    store: ViewStore = Depends(get_store),
) -> dict:
    """Write (or refresh) the integration block in a target project.

    ``dry_run: true`` returns the exact planned content without touching
    disk — the page shows this as the preview.
    """
    project_code = str(body.get("project_code") or "").strip()
    if not _PROJECT_CODE_RE.match(project_code):
        raise HTTPException(
            status_code=422,
            detail=(
                "project_code must be a lowercase slug "
                "(letters, digits, '-', '_'; max 64 chars)"
            ),
        )
    project_dir = _validated_dir(str(body.get("project_dir") or ""))
    write_agents = bool(body.get("write_agents", True))
    write_bridge = bool(body.get("write_claude_bridge", True))
    write_hooks = bool(body.get("write_claude_hooks", True))
    write_opencode = bool(body.get("write_opencode_plugin", False))
    write_codex = bool(body.get("write_codex_hooks", False))
    write_cursor = bool(body.get("write_cursor_hooks", False))
    write_mcp = bool(body.get("write_mcp", True))
    # One line of the file agents read: no line breaks (a break would start
    # a new instruction of its own), and no essay.
    notes = " ".join(str(body.get("notes") or "").split())[:NOTES_MAX]
    dry_run = bool(body.get("dry_run", False))

    block = _compose_block(
        project_code, _api_url(request), notes,
        request.app.state.settings.data_root, project_dir,
    )

    results: list[dict] = []

    if write_agents:
        agents_path = project_dir / "AGENTS.md"
        try:
            existing = agents_path.read_text(encoding="utf-8") if agents_path.exists() else ""
        except OSError as exc:
            raise HTTPException(status_code=422, detail=f"cannot read {agents_path}: {exc}")
        new_text, action = _upsert_block(existing, block)
        if not dry_run and action != "unchanged":
            write_in_place(agents_path, new_text)
        results.append(
            {"file": str(agents_path), "action": action, "content": block}
        )

    if write_bridge:
        claude_path = project_dir / "CLAUDE.md"
        try:
            existing = claude_path.read_text(encoding="utf-8") if claude_path.exists() else ""
        except OSError as exc:
            raise HTTPException(status_code=422, detail=f"cannot read {claude_path}: {exc}")
        new_text, action = _upsert_bridge(existing)
        if not dry_run and action != "unchanged":
            write_in_place(claude_path, new_text)
        results.append(
            {"file": str(claude_path), "action": action, "content": BRIDGE_LINE}
        )

    if write_hooks:
        hooks_path = project_dir / ".claude" / "settings.local.json"
        try:
            existing = (
                hooks_path.read_text(encoding="utf-8")
                if hooks_path.exists()
                else ""
            )
        except OSError as exc:
            raise HTTPException(
                status_code=422, detail=f"cannot read {hooks_path}: {exc}"
            )
        command = _hook_command(
            project_code, request.app.state.settings.data_root
        )
        new_text, action = _upsert_hooks(existing, command)
        if not dry_run and action != "unchanged":
            hooks_path.parent.mkdir(parents=True, exist_ok=True)
            write_in_place(hooks_path, new_text)
        results.append(
            {"file": str(hooks_path), "action": action, "content": new_text}
        )

    if write_codex:
        # Codex hooks: per project, the same two events in the same shape.
        codex_path = project_dir / ".codex" / "hooks.json"
        try:
            existing = (
                codex_path.read_text(encoding="utf-8") if codex_path.exists() else ""
            )
        except OSError as exc:
            raise HTTPException(status_code=422, detail=f"cannot read {codex_path}: {exc}")
        command = _hook_command(
            project_code, request.app.state.settings.data_root, tool="codex"
        )
        new_text, action = _upsert_hooks(existing, command, label=".codex/hooks.json")
        if not dry_run and action != "unchanged":
            codex_path.parent.mkdir(parents=True, exist_ok=True)
            write_in_place(codex_path, new_text)
        results.append(
            {"file": str(codex_path), "action": action, "content": new_text}
        )
        # Codex lists its MCP servers in ~/.codex/config.toml only, one block
        # for every project. Without it a Codex agent reads the contract and
        # can write nothing it asks for.
        try:
            config = CODEX_CONFIG_PATH.read_text(encoding="utf-8") if CODEX_CONFIG_PATH.exists() else ""
        except OSError as exc:
            raise HTTPException(status_code=422, detail=f"cannot read {CODEX_CONFIG_PATH}: {exc}")
        block = codex_mcp_block(_api_url(request))
        new_config, mcp_action = _upsert_codex_mcp(config, block)
        if not dry_run and mcp_action not in ("unchanged", "kept"):
            CODEX_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            write_in_place(CODEX_CONFIG_PATH, new_config)
        results.append({"file": str(CODEX_CONFIG_PATH), "action": mcp_action, "content": block})

    if write_cursor:
        # Cursor hooks: per project, three events in Cursor's own shape.
        cursor_path = project_dir / ".cursor" / "hooks.json"
        try:
            existing = (
                cursor_path.read_text(encoding="utf-8") if cursor_path.exists() else ""
            )
        except OSError as exc:
            raise HTTPException(status_code=422, detail=f"cannot read {cursor_path}: {exc}")
        new_text, action = _upsert_cursor_hooks(
            existing, _cursor_hook_command(project_code, request.app.state.settings.data_root)
        )
        if not dry_run and action != "unchanged":
            cursor_path.parent.mkdir(parents=True, exist_ok=True)
            write_in_place(cursor_path, new_text)
        results.append(
            {"file": str(cursor_path), "action": action, "content": new_text}
        )

    if write_opencode:
        plugin_path = project_dir / ".opencode" / "plugin" / _OPENCODE_PLUGIN
        content = _compose_opencode_plugin(
            project_code, request.app.state.settings.data_root
        )
        try:
            existing = (
                plugin_path.read_text(encoding="utf-8")
                if plugin_path.exists()
                else ""
            )
        except OSError as exc:
            raise HTTPException(
                status_code=422, detail=f"cannot read {plugin_path}: {exc}"
            )
        action = (
            "unchanged"
            if existing == content
            else ("updated" if existing else "created")
        )
        if not dry_run and action != "unchanged":
            plugin_path.parent.mkdir(parents=True, exist_ok=True)
            write_in_place(plugin_path, content)
        results.append(
            {"file": str(plugin_path), "action": action, "content": content}
        )

    if write_mcp:
        # How agents write: the MCP server, wired where each tool looks for
        # it. Claude Code reads .mcp.json in the project; Cursor reads
        # .cursor/mcp.json (the same shape, https://cursor.com/docs/context/mcp);
        # OpenCode reads opencode.json; Codex's config is global
        # (POST /api/setup/codex).
        entry = mcp_server_entry(_api_url(request))
        results.append(_write_mcp_file(project_dir / ".mcp.json", "mcpServers", entry, dry_run=dry_run))
        if write_cursor:
            results.append(_write_mcp_file(project_dir / ".cursor" / "mcp.json", "mcpServers", entry, dry_run=dry_run))
        if write_opencode:
            oc_entry = {"type": "local", "command": [entry["command"], *entry["args"]],
                        "environment": entry["env"], "enabled": True}
            results.append(_write_mcp_file(project_dir / "opencode.json", "mcp", oc_entry, dry_run=dry_run,
                                           also=_allow_opencode_folder))

    if not dry_run:
        # Make the project visible in the sidebar immediately.
        (store.data_root / "projects" / project_code).mkdir(
            parents=True, exist_ok=True
        )

        # Record (or refresh) the integration registry entry.
        # The look and the append are one locked step: two Setup posts at
        # once both found no row and wrote one each.
        append_if_absent(
            store.data_root / "integrations.csv",
            _INTEGRATIONS_COLUMNS,
            {
                "project": project_code,
                "path": str(project_dir),
                "created_date": today_yymm_dd(),
            },
            lambda r: r.get("project") == project_code and r.get("path") == str(project_dir),
        )
        store.rebuild()
        # A project set up now gets the rules for all agents like every other.
        from .integrate import sync_all_rules
        sync_all_rules(store)

    # This computer, when asked: on only. Integrating again with a box left
    # clear turns nothing off; Settings › General does that.
    for kind, label in (("autostart", "start at login"), ("shortcut", "shortcut")):
        if not body.get(kind):
            continue
        if dry_run:
            results.append({"file": label, "action": "would turn on", "content": ""})
            continue
        try:
            for path in _switch(kind, True):
                results.append({"file": path, "action": label, "content": ""})
        except HTTPException as exc:
            results.append({"file": label, "action": "not done", "content": str(exc.detail)})

    return {
        "dry_run": dry_run,
        "project_code": project_code,
        "project_dir": str(project_dir),
        "results": results,
    }


@router.post("/api/setup/forget")
def forget(
    body: dict = Body(...),
    store: ViewStore = Depends(get_store),
) -> dict:
    """Disconnect: drop the registry row and undo every file Setup wrote in
    the project folder (the Claude Code, Codex and Cursor hooks, the OpenCode
    plugin, AGENTS.md block, CLAUDE.md bridge, the MCP server). Slightly Parallel's own data for the project is not touched."""
    project_code = str(body.get("project_code") or "").strip()
    path = str(body.get("path") or "").strip()
    csv_path = store.data_root / "integrations.csv"
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail="no integrations recorded")

    def mutate(rows: list[dict[str, str]]) -> bool:
        before = len(rows)
        rows[:] = [
            r
            for r in rows
            if not (r.get("project") == project_code and r.get("path") == path)
        ]
        if len(rows) == before:
            raise HTTPException(
                status_code=404,
                detail=f"integration not found: {project_code} @ {path}",
            )
        return True

    rewrite_rows(csv_path, _INTEGRATIONS_COLUMNS, mutate)

    # Uninstall the OpenCode plugin if we wrote it.
    plugin_path = Path(path) / ".opencode" / "plugin" / _OPENCODE_PLUGIN
    try:
        if plugin_path.exists() and _ours(plugin_path.read_text(encoding="utf-8")):
            plugin_path.unlink()
            _rmdir_if_empty(plugin_path.parent, plugin_path.parent.parent)
    except OSError:
        pass

    # Uninstall our capture hooks from the project's local settings too:
    # Claude Code's, Codex's and Cursor's. A file left with nothing in it
    # is removed, and so is its folder when Setup made it.
    hooks_action = "unchanged"
    for rel in _HOOK_FILES:
        hooks_path = Path(path) / rel
        remove = _remove_cursor_hooks if rel.parts[0] == ".cursor" else _remove_hooks
        try:
            if hooks_path.exists():
                new_text, action = remove(hooks_path.read_text(encoding="utf-8"))
                if action == "updated":
                    hooks_action = action
                    _write_or_remove(hooks_path, new_text)
                    _rmdir_if_empty(hooks_path.parent)
        except OSError:
            hooks_action = "unreadable"

    # And the MCP server Setup wired in: .mcp.json for Claude Code,
    # .cursor/mcp.json for Cursor, opencode.json for OpenCode. Other
    # servers in those files stay.
    mcp_action = "unchanged"
    for mcp_path, top in (
        (Path(path) / ".mcp.json", "mcpServers"),
        (Path(path) / ".cursor" / "mcp.json", "mcpServers"),
        (Path(path) / "opencode.json", "mcp"),
    ):
        try:
            if mcp_path.exists():
                new_text, action = _drop_json_key(mcp_path.read_text(encoding="utf-8"), top, MCP_SERVER)
                if top == "mcp":
                    new_text, more = _drop_opencode_folder(new_text)
                    action = "updated" if "updated" in (action, more) else action
                if action == "updated":
                    mcp_action = action
                    _write_or_remove(mcp_path, new_text)
                    _rmdir_if_empty(mcp_path.parent)
        except OSError:
            mcp_action = "unreadable"

    agents_action = strip_file(
        Path(path) / "AGENTS.md", lambda t: remove_block(t, *(_marks_in(t) or (BEGIN_MARK, END_MARK)))
    )
    # The sets Integrate wrote, "Rules for all agents" among them, leave with
    # the project; no later sync reaches a folder that is not set up.
    from .integrate import forget_project, remove_all_sets
    sets_action = strip_file(Path(path) / "AGENTS.md", remove_all_sets)
    forget_project(store, project_code)
    bridge_action = strip_file(
        Path(path) / "CLAUDE.md", lambda t: remove_bridge(t, BRIDGE_LINE)
    )

    return {
        "forgotten": project_code,
        "path": path,
        "hooks": hooks_action,
        "mcp": mcp_action,
        "agents_md": agents_action,
        "sets": sets_action,
        "claude_md": bridge_action,
    }


@router.post("/api/setup/delete-data")
def delete_data(
    body: dict = Body(...),
    store: ViewStore = Depends(get_store),
) -> dict:
    """Archive everything Slightly Parallel holds for a project into ``.trash/``.

    ``confirm`` must repeat the project code — this moves chats and every
    ledger row of the project out of the live data root.
    """
    project_code = str(body.get("project_code") or "").strip()
    confirm = str(body.get("confirm") or "").strip()
    if not project_code:
        raise HTTPException(status_code=422, detail="project_code is required")
    if confirm != project_code:
        raise HTTPException(
            status_code=422, detail="confirm must repeat the project code"
        )
    if project_code not in {p["code"] for p in known_projects(store)}:
        raise HTTPException(status_code=404, detail=f"no data for project: {project_code}")
    return delete_project_data(store, project_code)


# ---------------------------------------------------------------------------
# Data root — the one piece of boot config that is web-editable.
# ---------------------------------------------------------------------------
#
# Rationale: host/port/CORS/terminal stay .env-only (changing them from a
# browser is a security lever), but the data root is a data-location choice
# a first-run user must be able to make without editing files. The path is
# validated server-side, the .env line is composed server-side, and the
# running app is hot-swapped so no restart is needed.

ENV_PATH = _REPO_ROOT / ".env"

# Characters that would break the quoted .env value as sp.py reads it back
# (sp.py read_env: a quote ends it, $ expands, a line break ends the line).
# A backslash is plain text there — no shell sources .env any more — and
# every Windows path has one.
_ENV_UNSAFE = re.compile(r'["$`\n\r]')


def _upsert_env_line(env_path: Path, key: str, value: str, *, replaces: str = "") -> None:
    """Set ``key="value"`` in .env, preserving every other line. ``replaces``
    names an older spelling of the same setting: its line is taken over, so a
    file written before a rename does not end up saying two things."""
    line = f'{key}="{value}"'
    try:
        text = env_path.read_text(encoding="utf-8")
    except OSError:
        text = ""
    lines = text.splitlines()
    prefixes = tuple(f"{k}=" for k in (key, replaces) if k)
    replaced = False
    kept: list[str] = []
    for existing in lines:
        if existing.strip().startswith(prefixes):
            if not replaced:
                kept.append(line)
                replaced = True
            continue                      # an older spelling of the same thing
        kept.append(existing)
    if not replaced:
        kept.append(line)
    lines = kept
    write_in_place(env_path, "\n".join(lines).rstrip("\n") + "\n")


@router.post("/api/setup/data-root")
def setup_data_root(
    request: Request,
    body: dict = Body(...),
) -> dict:
    """Switch the data root: persist to .env and hot-swap the running app.

    The target must be an existing absolute directory. Existing data is NOT
    moved — it stays in the old root; the dashboard simply starts reading
    and writing the new one. Integration blocks that embed the old root
    will show as stale on this page until refreshed.
    """
    raw = str(body.get("path") or "").strip()
    if not raw:
        raise HTTPException(status_code=422, detail="path is required")
    if _ENV_UNSAFE.search(raw):
        raise HTTPException(
            status_code=422,
            detail="path contains characters not allowed in .env",
        )
    p = _validated_dir(raw, label="path")
    # Slightly Parallel writes here from the first minute: say so now, not with a
    # crash later and a server left pointing at a folder it cannot use.
    try:
        probe = p / ".sp-write-test"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Slightly Parallel cannot write to {p} ({exc.strerror or exc}). Choose a folder you own, or change its permissions.",
        )

    before = request.app.state.settings.data_root
    try:
        request.app.state.swap_data_root(p)
    except OSError as exc:
        # Half a move is worse than none: go back to the folder that worked.
        request.app.state.swap_data_root(before)
        raise HTTPException(status_code=422, detail=f"Slightly Parallel could not open {p} as its data folder ({exc.strerror or exc}).")
    _upsert_env_line(ENV_PATH, "SP_DATA_ROOT", str(p), replaces="SCAN_DATA_ROOT")

    return {
        "data_root": str(p),
        "env_file": str(ENV_PATH),
        "restart_required": False,
    }


# ---------------------------------------------------------------------------
# Codex adapter — global (one notify hook serves every registered project)
# ---------------------------------------------------------------------------

_CODEX_SCRIPT = _REPO_ROOT / "scripts" / "hooks" / "codex-capture.py"
CODEX_CONFIG_PATH = codex_home() / "config.toml"

# ---------------------------------------------------------------------------
# The MCP server — how agents write
# ---------------------------------------------------------------------------

_MCP_PYTHON = _venv_python()


def mcp_server_entry(api_url: str) -> dict:
    """The one launch line every tool gets: this repo's interpreter, the
    translator module, the server it forwards to."""
    python = str(_MCP_PYTHON if _MCP_PYTHON.exists() else ("python3" if not _windows() else "python"))
    return {
        "command": python,
        "args": ["-m", "backend.mcp"],
        # PYTHONUTF8: the pipes are UTF-8 on every system. On Windows they
        # were the locale's code page, and a Cyrillic title ended the server.
        "env": {"SP_API": api_url, "PYTHONPATH": str(_REPO_ROOT / "backend"), "PYTHONUTF8": "1"},
    }


def _write_mcp_file(path: Path, top: str, entry: dict, *, dry_run: bool, also=None) -> dict:
    try:
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError as exc:
        raise HTTPException(status_code=422, detail=f"cannot read {path}: {exc}")
    new_text, action = _upsert_json_key(existing, top, MCP_SERVER, entry)
    if also:
        new_text, more = also(new_text)
        if more != "unchanged" and action == "unchanged":
            action = "updated"
    if not dry_run and action != "unchanged":
        path.parent.mkdir(parents=True, exist_ok=True)
        write_in_place(path, new_text)
    return {"file": str(path), "action": action, "content": new_text}


def _opencode_folder_pattern() -> str:
    """Slightly Parallel's folder as an OpenCode permission pattern. The
    contract (SLIGHTLY-PARALLEL.md) lives there, outside the project: OpenCode
    asks before reading outside the project, and `opencode run` says no
    without asking, so the agent never read the contract."""
    return _arg(_REPO_ROOT) + "/*"


def _allow_opencode_folder(text: str) -> tuple[str, str]:
    """``permission.external_directory`` in opencode.json allows our folder,
    keeping the user's own setting for every other folder (a word such as
    "ask" becomes the ``*`` rule; OpenCode applies the last matching rule)."""
    try:
        data = json.loads(text) if text.strip() else {}
    except json.JSONDecodeError:
        return text, "unchanged"
    if not isinstance(data, dict):
        return text, "unchanged"
    perm: Any = data.get("permission")
    if isinstance(perm, str):
        perm = {"*": perm}
    elif not isinstance(perm, dict):
        perm = {}
    rule = perm.get("external_directory")
    if isinstance(rule, str):
        rule = {"*": rule}
    elif not isinstance(rule, dict):
        rule = {}
    pattern = _opencode_folder_pattern()
    if rule.get(pattern) == "allow" and list(rule)[-1] == pattern:
        return text, "unchanged"
    rule.pop(pattern, None)
    rule[pattern] = "allow"
    perm["external_directory"] = rule
    data["permission"] = perm
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n", "updated"


def _drop_opencode_folder(text: str) -> tuple[str, str]:
    """Take our folder's rule out of opencode.json again; the user's stay."""
    try:
        data = json.loads(text) if text.strip() else {}
    except json.JSONDecodeError:
        return text, "unchanged"
    perm = data.get("permission") if isinstance(data, dict) else None
    rule = perm.get("external_directory") if isinstance(perm, dict) else None
    if not isinstance(rule, dict) or _opencode_folder_pattern() not in rule:
        return text, "unchanged"
    del rule[_opencode_folder_pattern()]
    if not rule:
        del perm["external_directory"]
    if not perm:
        del data["permission"]
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n", "updated"


def codex_mcp_block(api_url: str) -> str:
    e = mcp_server_entry(api_url)
    args = ", ".join(json.dumps(a) for a in e["args"])
    # Every variable the other tools get (PYTHONUTF8 among them: without it a
    # non-Latin title ends the server on Windows), with this server's address.
    env = {**e["env"], "SP_API": api_url}
    pairs = ", ".join(f"{k} = {json.dumps(v)}" for k, v in env.items())
    return (
        f"[mcp_servers.{MCP_SERVER}]\n"
        f"command = {json.dumps(e['command'])}\n"
        f"args = [{args}]\n"
        f"env = {{ {pairs} }}\n"
    )


_NOTIFY_RE = re.compile(r"^notify\s*=.*$", re.MULTILINE)


def _codex_notify_line(data_root: Path) -> str:
    # json.dumps quotes each part as TOML reads it: a Windows path's
    # backslashes would otherwise be escapes.
    program = "python3" if not _windows() else str(_venv_python()) if _venv_python().exists() else "python"
    return "notify = [" + ", ".join(json.dumps(x) for x in (program, str(_CODEX_SCRIPT), "--data-root", str(data_root))) + "]"


def codex_status() -> dict:
    """installed | foreign | absent — the state of notify in config.toml."""
    try:
        text = CODEX_CONFIG_PATH.read_text(encoding="utf-8")
    except OSError:
        return {"state": "absent", "config": str(CODEX_CONFIG_PATH)}
    m = _NOTIFY_RE.search(text)
    if not m:
        return {"state": "absent", "config": str(CODEX_CONFIG_PATH)}
    if "codex-capture.py" in m.group(0):
        return {"state": "installed", "config": str(CODEX_CONFIG_PATH)}
    return {"state": "foreign", "config": str(CODEX_CONFIG_PATH)}


@router.post("/api/setup/codex")
def setup_codex(
    request: Request,
    body: dict = Body(...),
) -> dict:
    """Install or remove the global Codex notify hook.

    Codex's ``notify`` lives in ``~/.codex/config.toml`` and is global by
    design — one entry serves every registered project (the adapter
    resolves the project from the event's working directory). A foreign
    notify value is never overwritten.
    """
    action = str(body.get("action") or "install")
    dry_run = bool(body.get("dry_run", False))
    line = _codex_notify_line(request.app.state.settings.data_root)

    try:
        text = (
            CODEX_CONFIG_PATH.read_text(encoding="utf-8")
            if CODEX_CONFIG_PATH.exists()
            else ""
        )
    except OSError as exc:
        raise HTTPException(
            status_code=422, detail=f"cannot read {CODEX_CONFIG_PATH}: {exc}"
        )

    m = _NOTIFY_RE.search(text)
    if action == "install":
        if m and "codex-capture.py" not in m.group(0):
            raise HTTPException(
                status_code=409,
                detail=(
                    "config.toml already has a notify entry that is not "
                    "Slightly Parallel's — refusing to overwrite it. Merge by hand: "
                    + line
                ),
            )
        if m:
            table = _TOML_TABLE_RE.search(text)
            if table is not None and table.start() < m.start():
                # Ours, but written under a table by an earlier install:
                # taken out of there and put where Codex reads it.
                stripped = re.sub(r"\n{3,}", "\n\n", text[:m.start()] + text[m.end():])
                new_text = _insert_top_level(stripped, line)
            else:
                new_text = _NOTIFY_RE.sub(lambda _m: line, text, count=1)
            file_action = "unchanged" if new_text == text else "updated"
        else:
            new_text = _insert_top_level(text, line)
            file_action = "created" if not text.strip() else "updated"
        # The MCP server rides in the same file: Codex lists its servers
        # globally, so one block serves every project.
        new_text, mcp_action = _upsert_codex_mcp(new_text, codex_mcp_block(_api_url(request)))
        if mcp_action != "unchanged" and file_action == "unchanged":
            file_action = mcp_action
    elif action == "remove":
        if not m or "codex-capture.py" not in m.group(0):
            new_text, file_action = text, "unchanged"
        else:
            new_text = _NOTIFY_RE.sub("", text, count=1)
            # The MCP server install wrote goes with the hook.
            new_text = _CODEX_MCP_RE.sub("", new_text, count=1)
            new_text = re.sub(r"\n{3,}", "\n\n", new_text).lstrip("\n")
            file_action = "updated"
    else:
        raise HTTPException(status_code=422, detail="action must be install or remove")

    if not dry_run and file_action != "unchanged":
        CODEX_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        write_in_place(CODEX_CONFIG_PATH, new_text)

    return {
        "action": action,
        "file": str(CODEX_CONFIG_PATH),
        "file_action": file_action,
        "line": line,
        "status": codex_status() if not dry_run else {"state": "preview"},
    }
