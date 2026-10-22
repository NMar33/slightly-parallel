"""#sp — is Slightly Parallel working, for this chat and this folder?

One set of checks, answered the same way to every caller: the MCP tool
``checkup`` (an agent after the operator's #sp), ``GET /api/checkup`` and
``python sp.py check``. Each finding has a status — ``ok``, ``note``,
``concern`` or ``unknown`` — the evidence it rests on, and the next step.
What could not be checked is ``unknown``, never ``ok``: "all fine" is said
only when everything was checked. Installed and working are kept apart: a
skill in its folder is not proof that an agent loaded it, and only a real
MCP call proves MCP.

Reads only. Nothing here changes a file, a setting or a process.
"""

from __future__ import annotations

import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .db import ViewStore

OK, NOTE, CONCERN, UNKNOWN = "ok", "note", "concern", "unknown"
ORDER = {CONCERN: 0, UNKNOWN: 1, NOTE: 2, OK: 3}

#: A message the hook recorded this recently counts as this one: the hook
#: writes it before the agent starts.
CAPTURE_GRACE_S = 15 * 60
DISK_CONCERN_BYTES = 2 * 1024**3
DISK_NOTE_FRACTION = 0.10
MEMORY_CONCERN_MB = 1024


def finding(id: str, area: str, status: str, title: str, evidence: str = "", next: str = "") -> dict[str, Any]:
    """``id`` is the check, with its reason after a colon when it is not fine:
    ``chat:capture_stale`` → id ``chat``, reason ``chat.capture_stale`` — the
    key of its recipe in checkup_fixes.md."""
    check, _, why = id.partition(":")
    return {"id": check, "reason": f"{check}.{why}" if why else "", "area": area, "status": status,
            "title": title, "evidence": evidence, "next": next}


FIXES = Path(__file__).with_name("checkup_fixes.md")


def recipes() -> dict[str, str]:
    """reason → its recipe (checkup_fixes.md, one ``## reason`` section each),
    with the rules every recipe carries in ``_rules``."""
    try:
        text = FIXES.read_text(encoding="utf-8")
    except OSError:
        return {}
    head, *parts = text.split("\n## ")
    out = {"_rules": head.split("Rules for every recipe:", 1)[-1].strip()}
    for part in parts:
        name, _, body = part.partition("\n")
        out[name.strip()] = body.strip()
    return out


def _folders(store: ViewStore) -> dict[str, str]:
    from . import capturewatch
    from .csvio import read_rows
    out: dict[str, str] = {}
    for row in read_rows(store.data_root / "integrations.csv"):
        code, path = str(row.get("project") or ""), str(row.get("path") or "")
        if code and path:
            out[code] = capturewatch._norm(path)
    return out


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------


def folder(store: ViewStore, cwd: str) -> tuple[dict[str, Any], str, str]:
    """Which project this folder belongs to. Returns the finding, the code, the folder."""
    from . import capturewatch
    if not cwd:
        return finding("folder:none_given", "setup", UNKNOWN, "No folder given", "the caller sent no working folder",
                       "call it from the project's folder"), "", ""
    folders = _folders(store)
    code = capturewatch._owner(cwd, folders)
    if not code:
        return finding("folder:not_integrated", "setup", CONCERN, "This folder is not connected to Slightly Parallel",
                       f"{len(folders)} folders are, this one is not",
                       "open Setup and integrate it: the chats here are not recorded"), "", ""
    return finding("folder", "setup", OK, f"Folder belongs to project {code}"), code, folders[code]


#: How a chat was found that counts as knowing it: by its own tool process,
#: or named by the caller. A shared terminal or the folder's newest chat is a guess.
SURE = ("process", "given")


def this_chat(store: ViewStore, agent_id: str, now: float, identity: str = "given") -> dict[str, Any]:
    """This chat is being recorded (the hook writes each message first)."""
    from .sessions import chat_path, parse_turns
    if not agent_id:
        return finding("chat:identity_unknown", "capture", UNKNOWN, "This chat's identity is not known",
                       "no chat was found for the caller", "run #sp in the chat itself, through the MCP tool")
    if identity not in SURE:
        how = "a terminal it shares with other chats" if identity == "shared-parent" else "the newest chat in this folder"
        return finding("chat:identity_guessed", "capture", UNKNOWN, "Could not tell which chat this is",
                       f"the guess is {agent_id}, from {how}",
                       "run #sp in the chat itself: its MCP server is found by its own tool")
    path = chat_path(store, agent_id)
    if path is None:
        return finding("chat:not_recorded", "capture", CONCERN, "This chat is not recorded",
                       f"no chat folder for {agent_id}",
                       "check the hook in this folder (Setup › Re-integrate), then send a message")
    try:
        turns = parse_turns(path)
    except OSError as exc:
        return finding("chat:unreadable", "capture", CONCERN, "This chat's record cannot be read", str(exc))
    if not turns:
        return finding("chat:empty", "capture", CONCERN, "This chat has no recorded messages", str(path.name))
    last = turns[-1].at.timestamp()
    age = now - last
    if age > CAPTURE_GRACE_S:
        return finding("chat:capture_stale", "capture", CONCERN, f"No message recorded in this chat for {age / 60:.0f} min",
                       f"the last one at {turns[-1].at:%Y-%m-%d %H:%M}; the hook writes each message as it is sent",
                       "the hook may have stopped: python sp.py report, section Capture hook errors")
    return finding("chat", "capture", OK, "This chat is recorded",
                   f"{len(turns)} messages; the last {age:.0f} s ago")


def capture(store: ViewStore) -> dict[str, Any]:
    from . import capturewatch
    try:
        c = capturewatch.check(store)
    except Exception as exc:  # noqa: BLE001 — a check that fails is unknown, not fine
        return finding("capture:check_failed", "capture", UNKNOWN, "Capture could not be checked", str(exc))
    errors, missed = int(c.get("errors_n") or 0), len(c.get("missed") or [])
    lost = sum(int(g.get("sessions") or 0) for g in c.get("lost") or [] if not g.get("ignored"))
    if errors or missed or lost:
        parts = [f"{errors} hook errors in a day"] * bool(errors) + [f"{missed} chats with messages not recorded"] * bool(missed) \
            + [f"{lost} sessions of the last week never recorded"] * bool(lost)
        return finding("capture:missed", "capture", CONCERN, "Some messages are not being recorded", "; ".join(parts),
                       "Monitor › Capture lists them; lost sessions can be imported there")
    watched = int(c.get("watched") or 0)
    return finding("capture", "capture", OK, "No messages missed, no hook errors in a day",
                   f"{watched} active Claude Code sessions compared with their logs" if watched else "")


#: The tool a chat runs in, from its id's prefix (the capture hooks name them).
TOOL_OF = {"cc": "claude", "codex": "codex", "oc": "opencode", "cursor": "cursor"}


def integration(project: str, path: str, agent_id: str = "") -> list[dict[str, Any]]:
    """The folder's own files: the contract block, the hooks, the tools wired."""
    if not path:
        return []
    from .routers import setup
    out = []
    status = setup._integration_status(path)
    if status == "fresh":
        out.append(finding("contract", "setup", OK, "The contract block in AGENTS.md is current"))
    else:
        out.append(finding("contract:not_current", "setup", CONCERN, f"The contract block in AGENTS.md is {status}",
                           f"{project}: AGENTS.md", "Setup › Re-integrate this folder"))
    missing = setup._missing_hook_scripts(path)
    if missing:
        out.append(finding("hooks:script_missing", "setup", CONCERN, "A hook points to a script that is gone",
                           f"{len(missing)} missing, e.g. {Path(missing[0]).name}",
                           "the app folder moved: Setup › Re-integrate"))
    elif any((tools := setup._tools_wired(path)).values()):
        wired = [t for t, on in tools.items() if on]
        mine = TOOL_OF.get(agent_id.split("-", 1)[0]) if agent_id else None
        if mine and not tools.get(mine):
            out.append(finding("hooks:not_installed", "setup", CONCERN, f"No capture hook for {mine}, the tool of this chat",
                               "hooks for " + ", ".join(wired), f"Setup › Re-integrate this folder with {mine} ticked"))
        else:
            out.append(finding("hooks", "setup", OK, "Hooks are installed", "for " + ", ".join(wired)))
    else:
        out.append(finding("hooks:not_installed", "setup", CONCERN, "No capture hook in this folder", path,
                           "Setup › Re-integrate, with the tools you use"))
    return out


def skills(store: ViewStore) -> dict[str, Any]:
    """Slightly Parallel's own skills, in the home folders every tool reads."""
    from . import skilllib
    try:
        rows = store.query(f"SELECT * FROM {skilllib._view()} WHERE source = ? AND status = 'active'",
                           (skilllib.BUILTIN_SOURCE,))
    except Exception as exc:  # noqa: BLE001
        return finding("skills:check_failed", "setup", UNKNOWN, "Skills could not be checked", str(exc))
    states: dict[str, list[str]] = {}
    for row in rows:
        for e in skilllib.installs_for(store, row):
            if e.get("project") == skilllib.ALL_PROJECTS:
                states.setdefault(str(e.get("status")), []).append(str(row.get("name") or row["id"]))
    n = len(rows)
    fresh = len(states.get("fresh", []))
    if states.get("missing"):
        return finding("skills:missing", "setup", CONCERN, "Some built-in skills are not installed",
                       ", ".join(states["missing"][:5]), "Skills page: install them into All projects")
    if states.get("stale") or states.get("changed"):
        detail = [f"{len(states.get('stale', []))} behind"] * bool(states.get("stale")) + \
                 [f"{len(states.get('changed', []))} edited on disk"] * bool(states.get("changed"))
        return finding("skills:outdated", "setup", NOTE, f"{fresh} of {n} built-in skills are current", ", ".join(detail),
                       "Skills page: update, or keep the edited copy")
    return finding("skills", "setup", OK, f"All {n} built-in skills are installed and current",
                   "installed is not proof an agent loaded them")


def data(store: ViewStore) -> dict[str, Any]:
    errors = list(getattr(store, "load_errors", []))
    root = store.data_root
    if not os.access(root, os.W_OK):
        return finding("data:not_writable", "data", CONCERN, "The data folder cannot be written", str(root),
                       "check its permissions: nothing new is saved")
    if errors:
        return finding("data:load_errors", "data", CONCERN, f"{len(errors)} data files could not be read",
                       f"e.g. {Path(str(errors[0].get('file', ''))).name}: {str(errors[0].get('error', ''))[:120]}",
                       "Internals › Data check")
    return finding("data", "data", OK, "Data is readable and writable")


def disk(store: ViewStore) -> dict[str, Any]:
    try:
        u = shutil.disk_usage(store.data_root)
    except OSError as exc:
        return finding("disk:unreadable", "data", UNKNOWN, "Free disk space could not be read", str(exc))
    free_gb = u.free / 1024**3
    text = f"{free_gb:.1f} GB free of {u.total / 1024**3:.0f} GB"
    if u.free < DISK_CONCERN_BYTES:
        return finding("disk:full", "data", CONCERN, "The disk is nearly full", text, "free space: writes will start failing")
    if u.free < u.total * DISK_NOTE_FRACTION:
        return finding("disk:low", "data", NOTE, "Disk space is low", text)
    return finding("disk", "data", OK, "Disk space is fine", text)


def backup(store: ViewStore, now: float) -> dict[str, Any]:
    from . import app_settings, backup as engine
    values = app_settings.load(store.data_root)
    if not values.get("backup.enabled", True):
        return finding("backup:off", "data", NOTE, "Backups are off", "", "Settings › Backups")
    every = int(values.get("backup.every_hours", 6))
    try:
        archives = engine.list_archives(engine.backup_root_for(store.data_root))
    except Exception as exc:  # noqa: BLE001
        return finding("backup:list_failed", "data", UNKNOWN, "Backups could not be listed", str(exc))
    if not archives:
        return finding("backup:none", "data", CONCERN, "There is no backup yet", "", "Backups page: make one now")
    latest = max(a.at for a in archives)
    hours = (now - latest.timestamp()) / 3600
    text = f"the last one {hours:.0f} h ago ({latest:%Y-%m-%d %H:%M}); every {every} h"
    if hours > 3 * every + 1:
        return finding("backup:old", "data", CONCERN, "The last backup is old", text,
                       "Backups page: make one, and check the server log for failures")
    return finding("backup", "data", OK, "Backups run", text)


def server(now: float) -> list[dict[str, Any]]:
    """The server's memory and its recent errors and slow requests."""
    from . import logbook
    m = logbook.process_memory()
    up_h = (now - logbook.STARTED_AT) / 3600
    mem = f"{m['rss_mb']:.0f} MB now, peak {m['peak_mb']:.0f} MB, up {up_h:.1f} h"
    high, went = m["rss_mb"] >= MEMORY_CONCERN_MB, m["peak_mb"] >= MEMORY_CONCERN_MB
    out = [finding("memory:high" if high else "memory:peak_high" if went else "memory", "server",
                   CONCERN if m["rss_mb"] >= MEMORY_CONCERN_MB else NOTE if m["peak_mb"] >= MEMORY_CONCERN_MB else OK,
                   "The server holds a lot of memory" if m["rss_mb"] >= MEMORY_CONCERN_MB
                   else "The server's memory went high once" if m["peak_mb"] >= MEMORY_CONCERN_MB
                   else "Server memory is normal", mem,
                   "python sp.py report, and docs/monitoring.md" if m["peak_mb"] >= MEMORY_CONCERN_MB else "")]
    s = logbook.stats()
    req = s.get("requests") or {}
    errs, slow, n = int(s.get("errors_n") or 0), int(req.get("slow_n") or 0), int(req.get("n") or 0)
    since = datetime.fromtimestamp(float(s.get("since") or logbook.STARTED_AT)).strftime("%Y-%m-%d %H:%M")
    if errs:
        out.append(finding("errors:in_log", "server", CONCERN, f"{errs} errors in the server log", f"since {since}",
                           "Monitor › Server shows them; copy for AI or download the report"))
    else:
        out.append(finding("errors", "server", OK, "No errors in the server log", f"{n} requests since {since}"))
    if n >= 20 and slow / n > 0.05:          # a handful of requests says nothing
        out.append(finding("slow:requests", "server", NOTE, f"{slow} of {n} requests were slow (≥ {logbook.SLOW_REQUEST_MS} ms)",
                           "", "Monitor › Server lists the slowest pages"))
    return out


def mcp(via_mcp: bool, identity: str = "given") -> dict[str, Any]:
    if via_mcp and identity == "process":
        return finding("mcp", "agent", OK, "MCP answers from this chat", "this check came through it")
    if via_mcp:
        return finding("mcp", "agent", OK, "MCP answers this caller", "which chat it serves could not be told")
    return finding("mcp:untested", "agent", UNKNOWN, "MCP from this chat was not tested",
                   "asked over HTTP or the command line", "an agent proves it by calling the MCP tool checkup")


# ---------------------------------------------------------------------------
# All of them
# ---------------------------------------------------------------------------


def run(store: ViewStore, *, cwd: str = "", agent_id: str = "", identity: str = "given", via_mcp: bool = False,
        now: float | None = None) -> dict[str, Any]:
    now = now or time.time()
    found: list[dict[str, Any]] = []

    def safe(fn: Callable[[], Any]) -> None:
        try:
            got = fn()
        except Exception as exc:  # noqa: BLE001 — a check that breaks is unknown, never fine
            got = finding("check:failed", "other", UNKNOWN, "A check failed to run", str(exc))
        found.extend(got if isinstance(got, list) else [got])

    try:
        where, project, path = folder(store, cwd)
    except Exception as exc:  # noqa: BLE001 — the rest still runs
        where, project, path = finding("check:failed", "setup", UNKNOWN, "Which project this folder is in could not be read", str(exc)), "", ""
    found.append(where)
    safe(lambda: this_chat(store, agent_id, now, identity))
    safe(lambda: mcp(via_mcp, identity))
    safe(lambda: capture(store))
    safe(lambda: integration(project, path, agent_id))
    safe(lambda: skills(store))
    safe(lambda: data(store))
    safe(lambda: disk(store))
    safe(lambda: backup(store, now))
    safe(lambda: server(now))
    found.sort(key=lambda f: ORDER.get(f["status"], 9))
    # Each finding that is not fine carries its recipe: how to confirm, who
    # acts, the steps, how to verify (checkup_fixes.md).
    book = recipes()
    for f in found:
        if f["status"] != OK and f["reason"]:
            f["recipe"] = book.get(f["reason"], "")
    counts = {s: sum(1 for f in found if f["status"] == s) for s in (CONCERN, UNKNOWN, NOTE, OK)}
    if counts[CONCERN]:
        verdict = f"{counts[CONCERN]} concern{'s' * (counts[CONCERN] > 1)} in {len(found)} checks" + \
            (f"; {counts[UNKNOWN]} could not be checked" if counts[UNKNOWN] else "")
    elif counts[UNKNOWN]:
        verdict = f"No concerns in {len(found)} checks; {counts[UNKNOWN]} could not be checked"
    else:
        verdict = f"All fine: {len(found)} checks"
    return {"verdict": verdict, "counts": counts, "project": project, "findings": found,
            "rules": book.get("_rules", "") if any(f.get("recipe") for f in found) else "",
            "checked_at": datetime.fromtimestamp(now).isoformat(timespec="seconds")}


def as_text(result: dict[str, Any]) -> str:
    """The checkup as plain lines, for the command line."""
    marks = {OK: "ok  ", NOTE: "note", CONCERN: "!!  ", UNKNOWN: "??  "}
    lines = [result["verdict"]]
    for f in result["findings"]:
        lines.append(f"  {marks.get(f['status'], '    ')} {f['title']}" + (f" — {f['evidence']}" if f["evidence"] else ""))
        if f["next"] and f["status"] != OK:
            lines.append(f"       → {f['next']}")
    return "\n".join(lines)
