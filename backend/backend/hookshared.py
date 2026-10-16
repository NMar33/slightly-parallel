"""What the capture hooks and the server both need — one copy of each.

The hooks (scripts/hooks/*.py) run with whatever Python the operator's tool
finds and cannot import the backend package, so they load this file by
path, the way they load ``turntimes.py``. That is the whole contract of
this module: standard library only, no relative imports, nothing that
costs time at import.

What still lives in two places (a regex the hook and sessions.py both
compile, the setting defaults) is held equal by tests/test_hook_parity.py.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Who is speaking
# ---------------------------------------------------------------------------

#: What a tool hands in as the person's message that the person never typed:
#: a task notification, the harness's own notes, the echo of a command, a
#: helper agent's report. The hook does not capture these; the server reads
#: no command out of them.
NOT_OPERATOR: tuple[str, ...] = (
    "<task-notification",
    "<system-",
    "<local-command",
    "<command-",
    "Another Claude session sent a message",
    "<agent-message",
)

#: The tool's own bookkeeping inside a Claude Code transcript — "user"
#: records that are no prompt. Only for reading transcripts: a person may
#: well open a message with "Caveat:", so the hook does not skip on it.
TRANSCRIPT_NOISE: tuple[str, ...] = ("<command-", "<local-command", "Caveat:")


def is_human_prompt(rec: dict[str, Any]) -> bool:
    """A transcript ``user`` record that is the person typing — not a tool result."""
    if rec.get("type") != "user":
        return False
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        return not any(isinstance(p, dict) and p.get("type") == "tool_result" for p in content)
    return False


# ---------------------------------------------------------------------------
# Skills in a transcript
# ---------------------------------------------------------------------------

#: Commands built into Claude Code, not skills: a typed /branch is not a skill use.
BUILTIN_COMMANDS = frozenset({
    "add-dir", "agents", "artifacts", "branch", "bug", "clear", "compact", "config",
    "context", "cost", "doctor", "exit", "export", "fast", "feedback", "help", "hooks",
    "ide", "init", "login", "logout", "mcp", "memory", "model", "output-style",
    "permissions", "plugin", "privacy-settings", "release-notes", "reload-plugins",
    "rename", "resume", "rewind", "status", "statusline", "tasks", "terminal-setup",
    "theme", "todos", "upgrade", "usage", "vim",
})

COMMAND_NAME_RE = re.compile(r"<command-name>/([A-Za-z0-9:_-]+)</command-name>")


def skill_uses(rec: dict[str, Any]) -> list[tuple[str, str]]:
    """(skill, auto | typed) in one Claude Code transcript record."""
    content = (rec.get("message") or {}).get("content")
    out: list[tuple[str, str]] = []
    if rec.get("type") == "assistant" and isinstance(content, list):
        for p in content:
            if isinstance(p, dict) and p.get("type") == "tool_use" and p.get("name") == "Skill":
                name = str((p.get("input") or {}).get("skill") or "").strip()
                if name:
                    out.append((name, "auto"))
    elif rec.get("type") == "user" and not rec.get("isCompactSummary"):
        text = content if isinstance(content, str) else " ".join(
            str(p.get("text") or "") for p in content or [] if isinstance(p, dict) and p.get("type") == "text")
        # A typed command is the whole prompt; the tag quoted inside a message is not one.
        m = COMMAND_NAME_RE.search(text or "")
        if m and (text or "").lstrip().startswith(("<command-message>", "<command-name>")):
            if m.group(1) not in BUILTIN_COMMANDS:
                out.append((m.group(1), "typed"))
    return out


# The tools that change a file, and the input field that names it.
TOUCHING_TOOLS = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}


def touched_files(rec: dict[str, Any]) -> list[str]:
    """The files one Claude Code transcript record's tool calls changed:
    Edit, Write, MultiEdit, NotebookEdit — by the path they name. What a
    turn did to the folder, with or without git."""
    content = (rec.get("message") or {}).get("content")
    out: list[str] = []
    if rec.get("type") == "assistant" and isinstance(content, list):
        for p in content:
            if isinstance(p, dict) and p.get("type") == "tool_use" and p.get("name") in TOUCHING_TOOLS:
                path = str((p.get("input") or {}).get(TOUCHING_TOOLS[str(p.get("name"))]) or "").strip()
                if path:
                    out.append(path)
    return out


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------


def yymm_dd(d: datetime) -> str:
    """Slightly Parallel's date: 2610-04."""
    return f"{d.year % 100:02d}{d.month:02d}-{d.day:02d}"


def local_iso(ts: Any) -> str:
    """A transcript's timestamp as local, naive ``YYYY-MM-DDTHH:MM:SS`` ("" if it is none)."""
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return ""
    if d.tzinfo is not None:
        d = d.astimezone().replace(tzinfo=None)
    return d.strftime("%Y-%m-%dT%H:%M:%S")


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


def replace_file(src: Any, dst: Any) -> None:
    """``os.replace``, patient on Windows: there a file another process has
    open (a reader, an antivirus scan) refuses to be replaced for a moment,
    where POSIX would just swap it."""
    if os.name != "nt":
        os.replace(src, dst)
        return
    for attempt in range(40):  # pragma: no cover — Windows only
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == 39:
                raise
            time.sleep(0.025)


def tail_lines(path: Any, max_bytes: int = 256 * 1024) -> list[str]:
    """The last whole lines of a file, at most ``max_bytes`` of them — the
    files beside a chat (turns.jsonl, work.jsonl, skills.jsonl) only grow,
    and their readers want the end. A line longer than the window is read
    by widening it; a missing file is no lines."""
    try:
        with open(path, "rb") as fh:
            size = fh.seek(0, os.SEEK_END)
            want = max_bytes
            while True:
                start = max(0, size - want)
                fh.seek(start)
                data = fh.read()
                # Cut mid-line: the first piece is the end of a line, not a line.
                if start > 0:
                    cut = data.find(b"\n")
                    if cut < 0 or not data[cut + 1:].strip():
                        if want >= size:
                            break
                        want *= 4
                        continue
                    data = data[cut + 1:]
                break
    except OSError:
        return []
    return data.decode("utf-8", errors="replace").splitlines()


def last_json(path: Any, key: str) -> Any:
    """``key`` of the last line of a .jsonl file that has it (None if none)."""
    for raw in reversed(tail_lines(path)):
        try:
            value = json.loads(raw).get(key)
        except (ValueError, AttributeError):
            continue
        if value:
            return value
    return None


# ---------------------------------------------------------------------------
# Processes
# ---------------------------------------------------------------------------


def _proc_parent(pid: int) -> int:
    """The parent of ``pid`` from /proc (Linux); 0 when it cannot be read."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as f:
            # "pid (name) state ppid …" — the name may hold spaces and brackets.
            return int(f.read().rsplit(")", 1)[1].split()[1])
    except (OSError, ValueError, IndexError):
        return 0


def _ps_parents() -> dict[int, int]:
    """Every process's parent from one ``ps`` call (macOS and other systems
    without /proc); empty when ps cannot be run."""
    import subprocess
    try:
        got = subprocess.run(["ps", "-A", "-o", "pid=,ppid="], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=2)
    except (OSError, subprocess.SubprocessError):
        return {}
    table: dict[int, int] = {}
    for line in got.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            table[int(parts[0])] = int(parts[1])
    return table


def _win_parents() -> dict[int, int]:
    """Every process's parent on Windows, from the kernel's own snapshot
    (Toolhelp32): no ps there, and a shell command per prompt is slow."""
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_char * 260)]

    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    except (OSError, AttributeError):
        return {}
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k32.Process32First.argtypes = k32.Process32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if not snap or snap == ctypes.c_void_p(-1).value:
        return {}
    table: dict[int, int] = {}
    try:
        e = Entry()
        e.dwSize = ctypes.sizeof(Entry)
        ok = k32.Process32First(snap, ctypes.byref(e))
        while ok:
            table[int(e.th32ProcessID)] = int(e.th32ParentProcessID)
            ok = k32.Process32Next(snap, ctypes.byref(e))
    finally:
        k32.CloseHandle(snap)
    return table


def ancestors(limit: int = 12) -> list[int]:
    """This process's parents, nearest first. The tool that runs a chat is a
    parent of both its capture hook and its MCP server, so the two can
    recognise each other by it. Linux reads /proc; Windows the kernel's
    process snapshot; elsewhere one ``ps`` call lists every process. The
    walk happens in memory (this runs on every prompt and MCP write)."""
    if os.name == "nt":
        table = _win_parents()
        parent_of = lambda pid: table.get(pid, 0)  # noqa: E731
    elif os.path.isdir(f"/proc/{os.getpid()}"):
        parent_of = _proc_parent
    else:
        table = _ps_parents()
        parent_of = lambda pid: table.get(pid, 0)  # noqa: E731
    out: list[int] = []
    pid = os.getpid()
    for _ in range(limit):
        parent = parent_of(pid)
        if parent <= 1 or parent in out:
            break
        out.append(parent)
        pid = parent
    return out


def load_beside(name: str) -> Any:
    """Another standard-library-only module of this folder, by path (for a
    caller that was itself loaded by path and has no package to import from)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(f"sp_{name}", Path(__file__).resolve().parent / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def session_key(tool: str, session: str) -> str:
    """The 8 characters of a session id that name its agent. Codex's ids are
    UUIDv7: their first characters are the time, about a minute a step, so
    two sessions started in one minute shared them and became one agent;
    for Codex the last 8, the random part. Claude Code's and Cursor's ids are
    random throughout and keep their first 8, as before."""
    s = session or "unknown"
    return s.replace("-", "")[-8:] if tool == "codex" else s[:8]
