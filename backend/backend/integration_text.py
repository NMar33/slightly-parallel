"""Setup's text edits: our block in AGENTS.md, the bridge line in CLAUDE.md,
our hook entries in each tool's hooks JSON, our MCP server in a JSON or TOML
config. Each takes the file's text and answers (new text, action); reading
and writing the files stays with the router (routers/setup.py)."""

from __future__ import annotations

import json
import re

from fastapi import HTTPException

BEGIN_MARK = "<!-- slightly-parallel:begin -->"
END_MARK = "<!-- slightly-parallel:end -->"
BRIDGE_LINE = "@AGENTS.md"
MCP_SERVER = "slightly-parallel"


def _marks_in(text: str) -> tuple[str, str] | None:
    """The pair of markers when this text holds both; None otherwise."""
    return (BEGIN_MARK, END_MARK) if BEGIN_MARK in text and END_MARK in text else None



#: The Cursor events Setup hooks (https://cursor.com/docs/agent/hooks): the
#: prompt, the reply, and the end of the loop (closes a turn whose reply
#: never came).
CURSOR_EVENTS = ("beforeSubmitPrompt", "afterAgentResponse", "stop")


def _hook_commands(entry) -> list[str]:
    """The command lines of one hook entry: Cursor's holds its command
    itself, Claude Code's and Codex's hold a list under ``hooks``."""
    if not isinstance(entry, dict):
        return []
    out = [str(entry["command"])] if "command" in entry else []
    for h in entry.get("hooks") or []:
        if isinstance(h, dict):
            out.append(str(h.get("command", "")))
    return out


def _hook_entry(command: str) -> dict:
    return {"hooks": [{"type": "command", "command": command}]}


def _ours(text: str) -> bool:
    """A file Setup wrote."""
    return "Slightly Parallel" in text


def _is_sp_hook(entry: dict) -> bool:
    hooks = entry.get("hooks")
    return isinstance(hooks, list) and any(
        "claude-code-capture.py" in str(h.get("command", ""))
        for h in hooks
        if isinstance(h, dict)
    )


def _upsert_hooks(
    existing_text: str, command: str, label: str = ".claude/settings.local.json",
) -> tuple[str, str]:
    """Merge our two hook entries into settings JSON, preserving the rest.

    The same shape serves Claude Code (``.claude/settings.local.json``) and
    Codex (``.codex/hooks.json``): ``hooks.<Event>[].hooks[].command``.
    """
    try:
        settings = json.loads(existing_text) if existing_text.strip() else {}
        if not isinstance(settings, dict):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(
            status_code=422,
            detail=f"{label} exists but is not valid JSON",
        )
    # Valid JSON of another shape is refused in words, not with a 500:
    # `"hooks": null` and `"hooks": []` are both seen in the wild.
    if settings.get("hooks") is None:
        settings["hooks"] = {}
    hooks = settings["hooks"]
    if not isinstance(hooks, dict):
        raise HTTPException(status_code=422, detail=f"{label}: `hooks` is not an object")
    changed = False
    for event in ("UserPromptSubmit", "Stop"):
        if hooks.get(event) is None:
            hooks[event] = []
        entries = hooks[event]
        if not isinstance(entries, list):
            raise HTTPException(status_code=422, detail=f"{label}: `hooks.{event}` is not a list")
        ours = [e for e in entries if isinstance(e, dict) and _is_sp_hook(e)]
        if ours:
            for e in ours:
                for h in e["hooks"]:
                    if isinstance(h, dict) and "claude-code-capture.py" in str(h.get("command", "")):
                        if h.get("command") != command:
                            h["command"] = command
                            changed = True
        else:
            entries.append(_hook_entry(command))
            changed = True
    new_text = json.dumps(settings, indent=2, ensure_ascii=False) + "\n"
    if not existing_text.strip():
        return new_text, "created"
    return new_text, ("updated" if changed else "unchanged")


def _remove_hooks(existing_text: str) -> tuple[str, str]:
    try:
        settings = json.loads(existing_text) if existing_text.strip() else {}
        if not isinstance(settings, dict):
            return existing_text, "unchanged"
    except json.JSONDecodeError:
        return existing_text, "unchanged"
    hooks = settings.get("hooks", {})
    if not isinstance(hooks, dict):
        return existing_text, "unchanged"  # not a shape we wrote: nothing of ours to take out
    changed = False
    for event in ("UserPromptSubmit", "Stop"):
        entries = hooks.get(event, [])
        if not isinstance(entries, list):
            continue
        kept = [
            e for e in entries
            if not (isinstance(e, dict) and _is_sp_hook(e))
        ]
        if len(kept) != len(entries):
            changed = True
            if kept:
                hooks[event] = kept
            else:
                hooks.pop(event, None)
    if not hooks and "hooks" in settings:
        settings.pop("hooks")
    if not changed:
        return existing_text, "unchanged"
    return json.dumps(settings, indent=2, ensure_ascii=False) + "\n", "updated"


def _is_sp_cursor_hook(entry) -> bool:
    return isinstance(entry, dict) and "cursor-capture.py" in str(entry.get("command", ""))


def _upsert_cursor_hooks(existing_text: str, command: str) -> tuple[str, str]:
    """Merge our three hook entries into ``.cursor/hooks.json``, preserving
    the rest. Cursor's shape (schema version 1) is
    ``{"version": 1, "hooks": {"<event>": [{"command": "…"}]}}``: one
    level flatter than Claude Code's, so it has its own merge."""
    label = ".cursor/hooks.json"
    try:
        settings = json.loads(existing_text) if existing_text.strip() else {}
        if not isinstance(settings, dict):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=422, detail=f"{label} exists but is not valid JSON")
    changed = False
    if settings.get("version") is None:
        settings["version"] = 1
        changed = True
    if settings.get("hooks") is None:
        settings["hooks"] = {}
    hooks = settings["hooks"]
    if not isinstance(hooks, dict):
        raise HTTPException(status_code=422, detail=f"{label}: `hooks` is not an object")
    for event in CURSOR_EVENTS:
        if hooks.get(event) is None:
            hooks[event] = []
        entries = hooks[event]
        if not isinstance(entries, list):
            raise HTTPException(status_code=422, detail=f"{label}: `hooks.{event}` is not a list")
        ours = [e for e in entries if _is_sp_cursor_hook(e)]
        if ours:
            for e in ours:
                if e.get("command") != command:
                    e["command"] = command
                    changed = True
        else:
            entries.append({"command": command})
            changed = True
    new_text = json.dumps(settings, indent=2, ensure_ascii=False) + "\n"
    if not existing_text.strip():
        return new_text, "created"
    return new_text, ("updated" if changed else "unchanged")


def _remove_cursor_hooks(existing_text: str) -> tuple[str, str]:
    """Take our entries out of ``.cursor/hooks.json``; other hooks stay. A
    file left with only its version number is emptied, so the caller
    removes it."""
    try:
        settings = json.loads(existing_text) if existing_text.strip() else {}
        if not isinstance(settings, dict):
            return existing_text, "unchanged"
    except json.JSONDecodeError:
        return existing_text, "unchanged"
    hooks = settings.get("hooks", {})
    if not isinstance(hooks, dict):
        return existing_text, "unchanged"
    changed = False
    for event in CURSOR_EVENTS:
        entries = hooks.get(event, [])
        if not isinstance(entries, list):
            continue
        kept = [e for e in entries if not _is_sp_cursor_hook(e)]
        if len(kept) != len(entries):
            changed = True
            if kept:
                hooks[event] = kept
            else:
                hooks.pop(event, None)
    if not changed:
        return existing_text, "unchanged"
    if not hooks:
        settings.pop("hooks", None)
        if set(settings) <= {"version"}:
            settings = {}
    return json.dumps(settings, indent=2, ensure_ascii=False) + "\n", "updated"


def _drop_json_key(existing_text: str, top: str, name: str) -> tuple[str, str]:
    """Take ``<top>.<name>`` out of a JSON file's text, keeping everything else."""
    try:
        data = json.loads(existing_text) if existing_text.strip() else {}
    except json.JSONDecodeError:
        return existing_text, "unchanged"
    if not isinstance(data, dict) or not isinstance(data.get(top), dict) or name not in data[top]:
        return existing_text, "unchanged"
    del data[top][name]
    if not data[top]:
        del data[top]
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n", "updated"


def _upsert_block(existing: str, block: str) -> tuple[str, str]:
    """Insert or replace the fenced block. Returns (new_text, action)."""
    marks = _marks_in(existing)
    if marks:
        start = existing.index(marks[0])
        end = existing.index(marks[1]) + len(marks[1])
        new_text = existing[:start] + block + existing[end:]
        action = "unchanged" if new_text == existing else "updated"
        return new_text, action
    if not existing.strip():
        return block + "\n", "created"
    sep = "\n\n" if not existing.endswith("\n\n") else ""
    if not existing.endswith("\n"):
        sep = "\n\n"
    return existing + sep + block + "\n", "appended"


def _upsert_bridge(existing: str) -> tuple[str, str]:
    """Ensure the @AGENTS.md line exists in CLAUDE.md content."""
    if any(line.strip() == BRIDGE_LINE for line in existing.splitlines()):
        return existing, "unchanged"
    if not existing.strip():
        return BRIDGE_LINE + "\n", "created"
    sep = "" if existing.endswith("\n") else "\n"
    return existing + sep + BRIDGE_LINE + "\n", "appended"


def _upsert_json_key(existing_text: str, top: str, name: str, entry: dict) -> tuple[str, str]:
    """Set ``<top>.<name>`` in a JSON file's text, keeping everything else."""
    try:
        data = json.loads(existing_text) if existing_text.strip() else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"not valid JSON: {exc}")
    if not isinstance(data, dict):
        raise HTTPException(status_code=422, detail="the file is not a JSON object")
    servers = data.get(top)
    if not isinstance(servers, dict):
        servers = {}
        data[top] = servers
    if servers.get(name) == entry:
        return existing_text, "unchanged"
    action = "updated" if name in servers or existing_text.strip() else "created"
    servers[name] = entry
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n", action


_CODEX_MCP_RE = re.compile(r"^\[mcp_servers\.slightly-parallel\]\n(?:(?!\[).*\n?)*", re.MULTILINE)


def _upsert_codex_mcp(text: str, block: str) -> tuple[str, str]:
    """Our block into Codex's config, in place. A file Codex could not read,
    or one that holds our server in a shape this does not edit (a quoted
    name, a sub-table), is left as it is: "kept" — never a second table."""
    import tomllib
    try:
        parsed = tomllib.loads(text) if text.strip() else {}
    except tomllib.TOMLDecodeError:
        return text, "kept"
    m = _CODEX_MCP_RE.search(text)
    ours = isinstance(parsed.get("mcp_servers"), dict) and MCP_SERVER in parsed["mcp_servers"]
    if ours and (not m or "[mcp_servers." + MCP_SERVER + "." in text):
        return text, "kept"
    if m:
        if m.group(0).rstrip("\n") == block.rstrip("\n"):
            return text, "unchanged"
        return text[:m.start()] + block + text[m.end():], "updated"
    joined = (text.rstrip("\n") + "\n\n" if text.strip() else "") + block
    return joined, "created" if not text.strip() else "updated"


_TOML_TABLE_RE = re.compile(r"^\s*\[", re.MULTILINE)


def _insert_top_level(text: str, line: str) -> str:
    """Put a top-level key into TOML text: before the first ``[table]``.

    A key written after a table header belongs to that table, so a line
    appended to the end of a config with any table in it was never read.
    """
    m = _TOML_TABLE_RE.search(text)
    if m is None:
        return (text.rstrip("\n") + "\n\n" if text.strip() else "") + line + "\n"
    head, rest = text[:m.start()], text[m.start():]
    return (head.rstrip("\n") + "\n\n" if head.strip() else "") + line + "\n\n" + rest
