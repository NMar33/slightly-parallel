"""What Setup left in a project folder: the contract block in AGENTS.md, the
capture hooks and the scripts they name, which tools record their chats.

Read by the Setup page (routers/setup.py) and by #sp (checkup.py). Out of the
router so the checkup, a library, imports none."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .contract_parts import CONTRACT_FILE
from .integration_text import BEGIN_MARK, _hook_commands, _is_sp_hook, _marks_in

REPO_ROOT = Path(__file__).resolve().parents[2]
#: The OpenCode plugin file Setup writes into a project.
OPENCODE_PLUGIN = "slightly-parallel.js"


HOOK_SCRIPT_RE = re.compile(r'"([^"]*(?:claude-code-capture|cursor-capture)\.py)"')
HOOK_FILES = (
    Path(".claude") / "settings.local.json", Path(".codex") / "hooks.json", Path(".cursor") / "hooks.json",
)


def missing_hook_scripts(path_raw: str) -> list[str]:
    """The capture scripts our installed hooks (Claude Code, Codex and
    Cursor) name that no longer exist: the repository was moved, renamed
    or deleted after Setup wrote the hook. Such a hook records nothing."""
    missing: list[str] = []
    for rel in HOOK_FILES:
        try:
            settings = json.loads((Path(path_raw) / rel).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        hooks = settings.get("hooks") if isinstance(settings, dict) else None
        if not isinstance(hooks, dict):
            continue
        for entries in hooks.values():
            for e in entries if isinstance(entries, list) else []:
                for command in _hook_commands(e):
                    m = HOOK_SCRIPT_RE.search(command)
                    if m and m.group(1) not in missing and not Path(m.group(1)).is_file():
                        missing.append(m.group(1))
    return missing


def hooks_installed(path_raw: str) -> bool:
    """Are our Claude Code capture hooks present in this folder's local settings?"""
    hooks_path = Path(path_raw) / ".claude" / "settings.local.json"
    try:
        settings = json.loads(hooks_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    hooks = settings.get("hooks") if isinstance(settings, dict) else None
    if not isinstance(hooks, dict):
        return False
    return all(
        any(_is_sp_hook(e) for e in hooks.get(ev, []) if isinstance(e, dict))
        for ev in ("UserPromptSubmit", "Stop")
    )


def hooks_file_has(path_raw: str, rel: str, script: str) -> bool:
    """Does this folder's hooks file (``rel``) hold an entry that runs ``script``?"""
    try:
        data = json.loads((Path(path_raw) / rel).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    hooks = data.get("hooks") if isinstance(data, dict) else None
    if not isinstance(hooks, dict):
        return False
    return any(script in c for entries in hooks.values() if isinstance(entries, list)
               for e in entries for c in _hook_commands(e))


#: The tools Setup can wire a project to, in the order the page lists them.
TOOLS = ("claude", "codex", "opencode", "cursor")


def tools_wired(path_raw: str, codex_global: bool = False) -> dict[str, bool]:
    """Which tools record their chats in this folder. Codex counts as wired
    by the global notify hook too, which serves every integrated project."""
    return {
        "claude": hooks_installed(path_raw),
        "codex": codex_global or hooks_file_has(path_raw, ".codex/hooks.json", "claude-code-capture.py"),
        "opencode": (Path(path_raw) / ".opencode" / "plugin" / OPENCODE_PLUGIN).is_file(),
        "cursor": hooks_file_has(path_raw, ".cursor/hooks.json", "cursor-capture.py"),
    }


def integration_status(path_raw: str) -> str:
    """fresh | stale | missing — is the recorded AGENTS.md block current?"""
    agents = Path(path_raw) / "AGENTS.md"
    try:
        text = agents.read_text(encoding="utf-8")
    except OSError:
        return "missing"
    if _marks_in(text) is None:
        return "missing"
    return "fresh" if BEGIN_MARK in text and str(contract_path()) in text else "stale"


def contract_path() -> Path:
    return REPO_ROOT / CONTRACT_FILE
