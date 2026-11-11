"""Helper chats recorded before the hooks marked them — once, at start.

The hooks mark a helper chat (a codex exec, a Codex subagent, a claude -p)
in its meta.json since 2026-11-11 (hookshared.HELPER_KINDS). A chat
recorded before is marked here from the tool's own log: Codex's session
file's first line (``source``, ``originator``), the ``entrypoint`` of Claude
Code's transcript. OpenCode keeps no log this reads: its chats are left.

The parent: Codex's subagents name their parent thread. Any other old
helper has no environment to read any more; its parent is the Claude Code
or Codex chat of the same project (the same registered folder tree) that
was in a turn — from its prompt to its answer's end — when the helper's
first message came, and only when exactly one chat was (``helper_of_by:
"time"``). Two or none: no parent, never a guess.

Each chat once: meta.json ``helper_backfill`` says what was found
(``{"at", "result": "helper" | "not a helper" | "no log", "version"}``),
written with the helper fields under the lock the hook takes for meta.json,
only when meta.json is still the one read. A chat the hook marked already
is left. Nothing raises into the server; nothing is archived or deleted:
what the helpers' commands made before stays for the operator to decide.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .file_safety import acquire_flock, atomic_write_json
from .hookshared import (
    claude_entrypoint, claude_helper_kind, codex_helper_kind, codex_home, codex_session_meta, session_key,
)
from .sessions import parse_chat
from .usagebackfill import _tool_of, find_transcript

log = logging.getLogger("sp.helperbackfill")

MARKER = "helper_backfill"
VERSION = 1
#: An answer with no recorded end is taken to run until the next prompt, or
#: this long after its own (the last turn of a chat).
OPEN_TURN = timedelta(minutes=30)


def _read_meta(folder: Path) -> Any:
    return json.loads((folder / "meta.json").read_text(encoding="utf-8"))


def _windows(folder: Path) -> list[tuple[datetime, datetime]]:
    """When a chat was in a turn: each prompt to its answer's end (the hook's
    stamp), else to the next prompt, at most OPEN_TURN."""
    from . import turntimes
    turns, _n = parse_chat(folder / "chat.md")
    known = turntimes.times(folder)
    out = []
    for i, t in enumerate(turns):
        nxt = turns[i + 1].at if i + 1 < len(turns) else None
        got = known.get(t.number)
        end = got.end if got is not None and got.end is not None else min(nxt or t.at + OPEN_TURN, t.at + OPEN_TURN)
        out.append((t.at, max(end, t.at)))
    return out


def _first_at(folder: Path) -> datetime | None:
    turns, _n = parse_chat(folder / "chat.md")
    return turns[0].at if turns else None


def signal(meta: dict[str, Any], agent_id: str, claude_root: Path, codex_dir: Path,
           project_path: str = "") -> tuple[str, str, str]:
    """(result, helper kind, the parent thread a Codex subagent names) from
    the chat's own log."""
    tool = _tool_of(meta, agent_id)
    if tool not in ("claude-code", "codex"):
        return "no log", "", ""
    log_path = find_transcript(meta, tool, claude_root, codex_dir, project_path)
    if log_path is None:
        return "no log", "", ""
    if tool == "codex":
        kind, parent = codex_helper_kind(codex_session_meta(log_path))
    else:
        kind, parent = claude_helper_kind(claude_entrypoint(log_path)), ""
    return ("helper" if kind else "not a helper"), kind, parent


def _parent_by_time(helper: Path, others: dict[Path, list[tuple[datetime, datetime]]]) -> str:
    at = _first_at(helper)
    if at is None:
        return ""
    hits = [f.name for f, wins in others.items() if f != helper and any(a <= at <= b for a, b in wins)]
    return hits[0] if len(hits) == 1 else ""


def _mark(folder: Path, value: dict[str, Any], helper: dict[str, Any], used: dict[str, Any]) -> bool:
    """Write the marker and the helper fields only when meta.json is still
    the one read (``used``); False, nothing written, when it changed."""
    meta_path = folder / "meta.json"
    with acquire_flock(meta_path.with_name("meta.json.lock"), timeout_s=5.0):
        meta = _read_meta(folder)
        if meta != used:
            return False
        meta.update(helper)
        meta[MARKER] = value
        atomic_write_json(meta_path, meta)
    return True


def backfill(data_root: Path, claude_root: Path | None = None, codex_dir: Path | None = None) -> dict[str, int]:
    """Mark every old helper chat of every project. Answers {result: chats}
    of this run, and ``parent`` (how many got a parent)."""
    from .csvio import read_rows
    data_root = Path(data_root)
    claude_root = claude_root or Path.home() / ".claude" / "projects"
    codex_dir = codex_dir or codex_home()
    paths = {str(r.get("project") or "").strip(): str(r.get("path") or "").strip()
             for r in read_rows(data_root / "integrations.csv")}
    counts: dict[str, int] = {}
    projects = data_root / "projects"
    try:
        codes = sorted(p.name for p in projects.iterdir() if p.is_dir() and not p.is_symlink()) if projects.is_dir() else []
    except OSError:
        codes = []
    for code in codes:
        chats = projects / code / "chats"
        try:
            folders = sorted(p for p in chats.iterdir() if p.is_dir() and not p.is_symlink()) if chats.is_dir() else []
        except OSError:
            continue
        found: list[tuple[Path, dict[str, Any], str, str, str]] = []
        kinds: dict[Path, bool] = {}
        for folder in folders:
            try:
                meta = _read_meta(folder)
            except (OSError, ValueError):
                continue
            if not isinstance(meta, dict):
                continue
            kinds[folder] = bool(meta.get("helper"))
            if meta.get("helper") or (isinstance(meta.get(MARKER), dict) and meta[MARKER].get("version") == VERSION):
                continue
            try:
                result, kind, parent_thread = signal(meta, folder.name, claude_root, codex_dir, paths.get(code, ""))
            except Exception:  # noqa: BLE001 — one chat never stops the rest
                log.exception("helper backfill: %s/%s not read", code, folder.name)
                continue
            kinds[folder] = bool(kind)
            found.append((folder, meta, result, kind, parent_thread))
        # The chats that can be a parent: every one of the project that is no helper.
        windows: dict[Path, list[tuple[datetime, datetime]]] = {}
        for folder, is_helper in kinds.items():
            if not is_helper:
                try:
                    windows[folder] = _windows(folder)
                except Exception:  # noqa: BLE001
                    continue
        for folder, meta, result, kind, parent_thread in found:
            helper: dict[str, Any] = {}
            if kind:
                if parent_thread:
                    parent, by = f"codex-{session_key('codex', parent_thread)}", "session"
                else:
                    parent = _parent_by_time(folder, windows)
                    by = "time" if parent else ""
                helper = {"helper": True, "helper_kind": kind, "helper_of": parent}
                if by:
                    helper["helper_of_by"] = by
            marker = {"at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), "result": result, "version": VERSION}
            try:
                if not _mark(folder, marker, helper, meta):
                    continue
            except Exception:  # noqa: BLE001
                log.exception("helper backfill: %s/%s not marked", code, folder.name)
                continue
            counts[result] = counts.get(result, 0) + 1
            if helper.get("helper_of"):
                counts["parent"] = counts.get("parent", 0) + 1
    return counts


def run_once(data_root: Path) -> None:
    """The server's start (the thread of the other backfills): never raises."""
    try:
        t = time.monotonic()
        got = backfill(Path(data_root))
        if got:
            log.info("helper backfill (%.1f s): %s", time.monotonic() - t,
                     ", ".join(f"{k} {v}" for k, v in sorted(got.items())))
    except Exception:  # noqa: BLE001 — an unmarked helper shows on the board as a chat
        log.exception("helpers not backfilled")


__all__ = ["backfill", "run_once", "signal", "MARKER", "VERSION"]
