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

import bisect
import errno
import hashlib
import json
import math
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

try:  # pragma: no cover — non-Unix platforms
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]
try:  # pragma: no cover — Windows: the same lock, spelled msvcrt.locking
    import msvcrt
except ImportError:  # pragma: no cover
    msvcrt = None  # type: ignore[assignment]

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


# ---------------------------------------------------------------------------
# The ### suppressor
# ---------------------------------------------------------------------------

#: A command written with three hashes (``###now-todo``, ``###done``) is the
#: message's only command: every other tag in it is silenced — the ones in a
#: pasted reply, a log, a document. Every tag reader goes through
#: command_text, the hook's and the server's alike.
_LOUD_RE = re.compile(r"(?<![\w#])###(?=[A-Za-z])")
#: A tag's ``#``: the regexes of every command read ``(?<![\w#])#word``, so a
#: second ``#`` in front makes it read by none.
_TAG_HASH_RE = re.compile(r"(?<![\w#])#(?=[A-Za-z])")


#: ``#mute`` anywhere in a message: no command in it runs, ``###`` ones too.
_MUTE_RE = re.compile(r"(?<![\w#])#mute(?![\w-])", re.IGNORECASE)
_MUTED_RE = re.compile(r"(?<![\w#])##mute(?![\w-])", re.IGNORECASE)


def command_text(text: str) -> str:
    """The message as the commands read it. With ``#mute`` in it, every tag is
    silenced (its ``#`` doubled) but ``#mute`` itself, so the notice can say
    so. Else, with a ``###`` command in it, that command reads as an ordinary
    one and every other tag is silenced; without one, the message as it is."""
    if not text:
        return text
    if _MUTE_RE.search(text):
        return _MUTED_RE.sub("#mute", _TAG_HASH_RE.sub("##", _LOUD_RE.sub("#", text)))
    if not _LOUD_RE.search(text):
        return text
    return _LOUD_RE.sub("#", _TAG_HASH_RE.sub("##", text))


def plain_text(text: str) -> str:
    """The message for what a command keeps of it (a prompt's body, a
    vision's text): the ``###`` command written as an ordinary one, so it is
    taken out like one; every other tag stays as it was typed."""
    if not text or not _LOUD_RE.search(text):
        return text
    return _LOUD_RE.sub("#", text)


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


# A shell command that makes a commit: ``git commit``, ``git -C x commit``.
_GIT_COMMIT_RE = re.compile(r"\bgit\b[^;&|\n]*?\scommit\b")


def ran_commit(rec: dict[str, Any]) -> bool:
    """Whether one Claude Code transcript record's tool calls ran a git
    commit through the shell: the turn's own commits are then this chat's,
    and the hook checks that they say which task they are for."""
    content = (rec.get("message") or {}).get("content")
    if rec.get("type") != "assistant" or not isinstance(content, list):
        return False
    for p in content:
        if isinstance(p, dict) and p.get("type") == "tool_use" and p.get("name") == "Bash":
            if _GIT_COMMIT_RE.search(str((p.get("input") or {}).get("command") or "")):
                return True
    return False


# A shell command that may make a commit: commit, merge, cherry-pick, revert,
# rebase, am, pull (a merge). The time of such a call tells which chat made a
# commit that several chats saw appear (gitwork.owns_commit).
_GIT_MAKES_RE = re.compile(r"\bgit\b[^;&|\n]*?\s(?:commit|merge|cherry-pick|revert|rebase|am|pull)\b")


def makes_commit(command: Any) -> bool:
    """Whether a shell command's text may create a commit."""
    return bool(_GIT_MAKES_RE.search(str(command or "")))


class CommitCalls:
    """The shell calls of a turn that may make a commit, as [start, end] in
    local time: fed tool calls and their results in order, by call id. A call
    with no result yet (the turn ended first) keeps its start as its end."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self._open: dict[str, int] = {}

    def started(self, call_id: str, command: Any, at: str) -> None:
        if at and makes_commit(command):
            self._open[str(call_id)] = len(self.calls)
            self.calls.append([at, at])

    def ended(self, call_id: str, at: str) -> None:
        i = self._open.pop(str(call_id), None)
        if i is not None and at:
            self.calls[i][1] = at

    def finish(self, at: str) -> list[list[str]]:
        """The calls, with the ones still open (no result came: the turn
        ended, or the shell went on in the background) closed at ``at``."""
        if at:
            for i in self._open.values():
                self.calls[i][1] = max(self.calls[i][1], at)
        self._open.clear()
        return self.calls

    def take(self, rec: dict[str, Any]) -> None:
        """One transcript record of Claude Code (a Bash call or its result)
        or of Codex (a shell or exec tool call, or its output, by call id)."""
        at = local_iso(rec.get("timestamp") or "")
        pl = rec.get("payload")
        if rec.get("type") == "response_item" and isinstance(pl, dict):
            kind = str(pl.get("type") or "")
            call_id = str(pl.get("call_id") or "")
            if kind in ("function_call", "custom_tool_call", "local_shell_call"):
                self.started(call_id, " ".join(str(pl.get(k) or "") for k in ("arguments", "input", "action")), at)
            elif kind.endswith("_output"):
                self.ended(call_id, at)
            return
        content = (rec.get("message") or {}).get("content")
        if not isinstance(content, list):
            return
        for p in content:
            if not isinstance(p, dict):
                continue
            if p.get("type") == "tool_use" and p.get("name") == "Bash":
                self.started(str(p.get("id") or ""), (p.get("input") or {}).get("command"), at)
            elif p.get("type") == "tool_result":
                self.ended(str(p.get("tool_use_id") or ""), at)


def codex_rollout(thread_id: str, home: str | None = None) -> Path | None:
    """The Codex session file of ``thread_id`` (rollout-…-<id>.jsonl under
    $CODEX_HOME/sessions, ~/.codex by default), the newest if several."""
    if not re.fullmatch(r"[0-9A-Za-z-]{8,80}", thread_id or ""):
        return None
    base = Path(home or os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "sessions"
    try:
        hits = list(base.glob(f"*/*/*/rollout-*{thread_id}.jsonl"))
    except OSError:
        return None
    return max(hits, key=lambda p: p.stat().st_mtime) if hits else None


def codex_last_turn(rollout: Path, turn_id: str = "") -> tuple[str, list[list[str]]]:
    """(when a turn began, its commit calls) from a Codex session file: the
    turn ``turn_id`` names, else the last one — from its ``task_started`` to
    the next. A call with no output is closed at the turn's last record.
    ("", []) when the file cannot be read or the turn is not in it."""
    turns: list[dict[str, Any]] = []      # each: id, started, calls, last
    try:
        with open(rollout, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec, dict):
                    continue
                pl = rec.get("payload")
                at = local_iso(rec.get("timestamp") or "")
                if rec.get("type") == "event_msg" and isinstance(pl, dict) and pl.get("type") == "task_started":
                    turns.append({"id": str(pl.get("turn_id") or ""), "started": at, "calls": CommitCalls(), "last": at})
                    continue
                if turns:
                    turns[-1]["calls"].take(rec)
                    if at:
                        turns[-1]["last"] = at
    except OSError:
        return "", []
    pick = next((t for t in reversed(turns) if t["id"] == turn_id), None) if turn_id else (turns[-1] if turns else None)
    if pick is None:
        return "", []
    return pick["started"], pick["calls"].finish(pick["last"])


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


def try_lock(fh: Any) -> bool:
    """One non-blocking try at an exclusive lock on an open file; True when
    held. ``flock`` on Linux and macOS, the first byte on Windows (a lock may
    lie past the end of an empty file)."""
    if fcntl is not None:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False
        except OSError as exc:
            if exc.errno == errno.EWOULDBLOCK:
                return False
            raise
    if msvcrt is None:  # pragma: no cover
        return False
    fh.seek(0)  # pragma: no cover
    try:  # pragma: no cover
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)  # pyright: ignore[reportAttributeAccessIssue] — Windows only
        return True
    except OSError:  # pragma: no cover
        return False


def unlock(fh: Any) -> None:
    try:
        if fcntl is not None:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        elif msvcrt is not None:  # pragma: no cover
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)  # pyright: ignore[reportAttributeAccessIssue] — Windows only
    except OSError:
        pass


@contextmanager
def locked(path: Any, timeout_s: float = 2.0):
    """Hold the lock beside ``path`` (``<name>.lock``, file_safety.lock_path's
    spelling) for a read-then-write. A hook must never hang the session it
    observes: after ``timeout_s`` the block runs without the lock."""
    p = Path(path)
    with open(p.with_name(p.name + ".lock"), "a", encoding="utf-8") as lock:
        deadline = time.monotonic() + timeout_s
        held = try_lock(lock)
        while not held and time.monotonic() < deadline:
            time.sleep(0.01)
            held = try_lock(lock)
        try:
            yield
        finally:
            if held:
                unlock(lock)


def _append_bytes(p: Path, text: str) -> None:
    """The append itself; the caller holds the lock."""
    with open(p, "ab") as fh:
        # A write cut off mid-line (a killed process) leaves no
        # newline; appended straight after it, this line would be
        # glued to the broken one and lost with it.
        if fh.tell() and not _ends_with_newline(p):
            fh.write(b"\n")
        fh.write(text.encode("utf-8"))


def append_locked(path: Any, text: str, timeout_s: float = 2.0) -> None:
    """Append ``text`` to ``path`` under the lock beside it, so a server
    rewriting the file meanwhile does not drop the line (see ``locked``)."""
    p = Path(path)
    with locked(p, timeout_s):
        _append_bytes(p, text)


def _ends_with_newline(p: Path) -> bool:
    with open(p, "rb") as fh:
        fh.seek(-1, os.SEEK_END)
        return fh.read(1) == b"\n"


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
    # Split at the newline only: str.splitlines also splits at U+2028, U+0085
    # and \x1c-\x1e, which json.dumps(ensure_ascii=False) leaves in a line's
    # text, so a line holding one came back as two pieces that are not JSON.
    lines = data.decode("utf-8", errors="replace").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return [ln.removesuffix("\r") for ln in lines]


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


def process_started(pid: int) -> float | None:
    """When ``pid`` started, as a Unix time; None when it cannot be read.

    Process numbers come back: Windows hands out a dead process's number
    again within minutes. A breadcrumb that names a number names the
    process that had it then; a process with that number that started
    after the breadcrumb was written is another one."""
    try:
        if os.name == "nt":
            return _win_started(pid)
        if os.path.isdir(f"/proc/{pid}"):
            with open(f"/proc/{pid}/stat", encoding="utf-8") as f:
                ticks = int(f.read().rsplit(")", 1)[1].split()[19])
            with open("/proc/stat", encoding="utf-8") as f:
                boot = next(int(line.split()[1]) for line in f if line.startswith("btime "))
            return boot + ticks / os.sysconf("SC_CLK_TCK")
        import subprocess
        got = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=2, env={**os.environ, "LC_ALL": "C"})
        text = " ".join(got.stdout.split())
        return datetime.strptime(text, "%a %b %d %H:%M:%S %Y").timestamp() if text else None
    except (OSError, ValueError, IndexError, StopIteration, Exception):  # noqa: BLE001 — unknown is an answer
        return None


def _win_started(pid: int) -> float | None:
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    # Without these, ctypes passes the handle as a C int: on 64-bit Windows a
    # handle past 2**31 is cut, GetProcessTimes fails and the handle leaks.
    k32.GetProcessTimes.restype = wintypes.BOOL
    k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    k32.CloseHandle.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        times = [wintypes.FILETIME() for _ in range(4)]
        if not k32.GetProcessTimes(handle, *[ctypes.byref(x) for x in times]):
            return None
        ft = times[0]
        # 100-ns steps since 1601-01-01.
        return ((ft.dwHighDateTime << 32) | ft.dwLowDateTime) / 1e7 - 11644473600
    finally:
        k32.CloseHandle(handle)


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
    for Codex the last 8, the random part. OpenCode's (ses_<time><random>)
    the same; its plugin names the agent the same way. Claude Code's and
    Cursor's ids are random throughout and keep their first 8, as before."""
    s = session or "unknown"
    if tool == "opencode":
        return s[-8:].lower()  # letters of both cases; a folder name ignores case on macOS and Windows
    return s.replace("-", "")[-8:] if tool == "codex" else s[:8]


def codex_home() -> Path:
    """Where Codex keeps its config and sessions: $CODEX_HOME, else ~/.codex.
    (On Windows Codex finds the home folder through the system, not
    USERPROFILE: CODEX_HOME is the one setting both sides read.)"""
    import os
    return Path(os.environ["CODEX_HOME"]) if os.environ.get("CODEX_HOME") else Path.home() / ".codex"


# ---------------------------------------------------------------------------
# chat.md's own format: what a message may not start a line with
# ---------------------------------------------------------------------------

# Lines in captured content that would collide with chat.md's own structure
# (a user pasting a session page quotes real turn headers) are escaped with
# a leading backslash; the sessions parser strips it when reading.
_STRUCTURAL_RE = re.compile(r"^(## Turn \d+ · |\*\*User\*\*: ?|\*\*Agent\*\*: ?)")


_LINE_BREAK_RE = re.compile(r"\r\n|\r|\x0c| | ")


def escape_content(text: str) -> str:
    """A message as chat.md holds it, written by the hook and by an import
    (sessionimport.py) alike; the reader (sessions.py) strips the escape."""
    # Every line separator becomes "\n" first: the reader splits on all of
    # them, so a header hidden behind a "\r" would otherwise read as a turn.
    text = _LINE_BREAK_RE.sub("\n", text or "")
    # A lone surrogate (half of an emoji pasted from a terminal) cannot be
    # written as UTF-8; the whole turn was lost over it. It becomes "?".
    text = text.encode("utf-8", "replace").decode("utf-8")
    return "\n".join(
        ("\\" + line) if _STRUCTURAL_RE.match(line) else line
        for line in text.split("\n")
    )


# ---------------------------------------------------------------------------
# git's file names, as the files are named
# ---------------------------------------------------------------------------

#: Paths as they are: by default git prints a name outside ASCII as an
#: octal-escaped quoted string ("\320\267…" for заметки.md), which matched
#: no file and no stamp.
GIT_PLAIN_PATHS = ("-c", "core.quotePath=false")

_RENAME_BRACES = re.compile(r"\{([^{}]*) => ([^{}]*)\}")


def numstat_path(raw: str) -> str:
    """The file a ``--numstat`` line is about. A rename is written
    ``old => new`` or ``dir/{old => new}/rest``: the file is the new name.
    A name git still quotes (one holding a quote, a backslash or a control
    character) is unquoted."""
    path = raw
    if " => " in path:
        if _RENAME_BRACES.search(path):
            path = _RENAME_BRACES.sub(lambda m: m.group(2), path).replace("//", "/")
        else:
            path = path.split(" => ", 1)[1]
    if len(path) >= 2 and path[0] == path[-1] == '"':
        try:
            path = path[1:-1].encode("latin-1", "backslashreplace").decode("unicode_escape").encode("latin-1").decode("utf-8")
        except (UnicodeError, ValueError):
            path = path[1:-1]
    return path


def tracked_cores(data_root: Any, project: str) -> list[dict[str, str]]:
    """The cores of ``project`` with tracking on and not expired (cores.csv at
    the data root; corelib.py writes it). The capture hook tells the agent
    on its first turn; the server reads the same way."""
    import csv
    import datetime as _dt
    today = _dt.date.today().isoformat()
    out: list[dict[str, str]] = []
    try:
        with open(Path(data_root) / "cores.csv", encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
    except (OSError, csv.Error):
        return out
    for r in rows:
        if r.get("project") != project or r.get("status") != "view" or r.get("tracking_on") != "1":
            continue
        until = str(r.get("tracking_until") or "")
        if until and until < today:
            continue
        out.append({"id": str(r.get("id") or ""), "name": str(r.get("name") or ""), "until": until})
    return out



# ---------------------------------------------------------------------------
# Helper chats: a run another program started (codex exec, claude -p, …)
# ---------------------------------------------------------------------------
#
# A helper is recorded like any chat, but its messages are no operator's:
# no command in them acts, and the board lists it under the chat that
# started it. What says a chat is one, as each tool writes it (checked with
# Codex 0.163, Claude Code 2.1.322, OpenCode 1.19.3):
#
# - Codex: the session file's first line (``session_meta``): ``source:
#   "exec"`` / ``originator: "codex_exec"`` for ``codex exec``; ``source:
#   {"subagent": …}`` for Codex's own subagents, the parent thread in
#   ``thread_spawn.parent_thread_id`` (or ``parent_thread_id`` beside it).
# - Claude Code: ``entrypoint`` ``sdk-cli`` for ``claude -p`` (``sdk-ts`` /
#   ``sdk-py`` for a program on the Agent SDK) — in every transcript line,
#   and in the hook's environment as CLAUDE_CODE_ENTRYPOINT.
# - OpenCode: the plugin's process runs ``opencode run`` (argv).
#
# Who started it: the environment the helper inherits. Claude Code gives the
# programs it starts CLAUDE_CODE_SESSION_ID (its session) and CLAUDE_PID
# (itself); Codex gives its shell commands CODEX_THREAD_ID. Neither tool
# filters the hook's environment, so a helper's hook sees its parent's. A
# nested ``claude -p`` sets CLAUDE_CODE_SESSION_ID to its own session: its
# parent is found by process — the parent Claude Code is one of the hook's
# ancestors, and the parent's own hook wrote its CLAUDE_PID and that
# process's start time into its breadcrumb. Two candidates (a Codex inside
# a Claude Code inside a Codex …): the one started last is the nearest. A
# candidate whose time is unknown beside another: no parent, never a guess.

HELPER_KINDS = ("codex-exec", "codex-subagent", "claude-print", "opencode-run")


def codex_helper_kind(meta_line: Any) -> tuple[str, str]:
    """(helper kind, the parent thread id) of a Codex session from its
    session file's first record (or that record's payload); ("", "") for an
    interactive session or a line that is not one."""
    if not isinstance(meta_line, dict):
        return "", ""
    pl = meta_line.get("payload") if meta_line.get("type") == "session_meta" else meta_line
    if not isinstance(pl, dict):
        return "", ""
    source = pl.get("source")
    if isinstance(source, dict) and "subagent" in source:
        sub = source.get("subagent")
        spawn = sub.get("thread_spawn") if isinstance(sub, dict) else None
        parent = spawn.get("parent_thread_id") if isinstance(spawn, dict) else None
        return "codex-subagent", str(parent or pl.get("parent_thread_id") or "")
    if source == "exec" or pl.get("originator") == "codex_exec":
        return "codex-exec", ""
    return "", ""


def codex_session_meta(rollout: Any) -> dict[str, Any] | None:
    """The first record of a Codex session file when it is its
    ``session_meta``; None when the file cannot be read."""
    try:
        with open(rollout, encoding="utf-8", errors="replace") as fh:
            rec = json.loads(fh.readline() or "null")
    except (OSError, ValueError):
        return None
    return rec if isinstance(rec, dict) and rec.get("type") == "session_meta" else None


def claude_helper_kind(entrypoint: Any) -> str:
    """"claude-print" for a Claude Code run that is no interactive chat
    (``claude -p``, a program on the Agent SDK), else ""."""
    return "claude-print" if str(entrypoint or "").startswith("sdk") else ""


def claude_entrypoint(transcript: Any, max_lines: int = 40) -> str:
    """The ``entrypoint`` a Claude Code transcript names in its first lines
    ("" when none does, or it cannot be read)."""
    try:
        with open(transcript, encoding="utf-8", errors="replace") as fh:
            for i, raw in enumerate(fh):
                if i >= max_lines:
                    break
                if '"entrypoint"' not in raw:
                    continue
                try:
                    rec = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(rec, dict) and rec.get("entrypoint"):
                    return str(rec["entrypoint"])
    except OSError:
        pass
    return ""


def _uuid7_epoch(value: str) -> float | None:
    """When a UUIDv7 (Codex's thread ids) was made, from its first 48 bits."""
    hexa = (value or "").replace("-", "")
    if len(hexa) != 32 or hexa[12:13] != "7":
        return None
    try:
        return int(hexa[:12], 16) / 1000
    except ValueError:
        return None


def _same_session(tool: str, a: str, b: str) -> bool:
    return bool(a) and bool(b) and session_key(tool, a) == session_key(tool, b)


def _pid_of(env: Any) -> int:
    try:
        pid = int(str(env.get("CLAUDE_PID") or "0"))
    except ValueError:
        return 0
    return pid if pid > 1 else 0


def _crumb_parent(data_root: Any, own_pid: int, pids: list[int]) -> tuple[str, float | None]:
    """The chat whose tool process is the nearest of ``pids`` (this hook's
    ancestors, nearest first): its breadcrumb names that process and when it
    started, and the process now there started then (a number used again by
    another process is no match). ("", None) when none is, or two chats
    claim the process."""
    base = Path(data_root) / ".sessions"
    try:
        crumbs = list(base.glob("*/*.json")) if base.is_dir() else []
    except OSError:
        return "", None
    by_pid: dict[int, list[dict[str, Any]]] = {}
    for p in crumbs:
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(c, dict):
            continue
        pid = c.get("tool_pid")
        if isinstance(pid, int) and not isinstance(pid, bool) and pid > 1 and pid != own_pid:
            by_pid.setdefault(pid, []).append(c)
    for pid in pids:
        if pid == own_pid or pid not in by_pid:
            continue
        started = process_started(pid)
        if started is None:
            return "", None
        same = {str(c.get("agent_id") or "") for c in by_pid[pid]
                if isinstance(c.get("tool_started"), (int, float)) and not isinstance(c.get("tool_started"), bool)
                and abs(float(c["tool_started"]) - started) < 2}
        same.discard("")
        return (same.pop(), started) if len(same) == 1 else ("", None)
    return "", None


def helper_parent(tool: str, own_session: str, env: Any = None, data_root: Any = None,
                  pids: list[int] | None = None) -> str:
    """The agent id of the chat that started this helper, from the
    environment its hook inherited (see the section's note); "" when it is
    not known, or two candidates cannot be ordered. ``tool``: the helper's
    own tool; ``own_session``: its own session id (a variable that names it
    is no parent); ``pids``: the hook's ancestors (read when not given)."""
    env = os.environ if env is None else env
    cands: list[tuple[str, float | None]] = []
    codex_thread = str(env.get("CODEX_THREAD_ID") or "")
    if codex_thread and not (tool == "codex" and _same_session("codex", codex_thread, own_session)):
        cands.append(("codex-" + session_key("codex", codex_thread), _uuid7_epoch(codex_thread)))
    claude_session = str(env.get("CLAUDE_CODE_SESSION_ID") or "")
    own_claude = tool == "claude-code" and _same_session("claude-code", claude_session, own_session)
    if claude_session and not own_claude:
        pid = _pid_of(env)
        cands.append(("cc-" + session_key("claude-code", claude_session), process_started(pid) if pid else None))
    elif tool == "claude-code" and data_root is not None:
        # A claude -p inside a Claude Code chat: the variable names itself.
        found, started = _crumb_parent(data_root, _pid_of(env), ancestors() if pids is None else pids)
        if found:
            cands.append((found, started))
    if not cands:
        return ""
    if len(cands) == 1:
        return cands[0][0]
    if any(t is None for _, t in cands):
        return ""
    return max(cands, key=lambda c: c[1] or 0.0)[0]


def tool_process(env: Any = None) -> tuple[int, float | None]:
    """(pid, start time) of the Claude Code process a hook runs under
    (CLAUDE_PID): the breadcrumb keeps them, and a ``claude -p`` started by
    that chat finds its parent by them. (0, None) elsewhere."""
    pid = _pid_of(os.environ if env is None else env)
    return (pid, process_started(pid)) if pid else (0, None)


def helper_of_clean(agent_id: str, parent: str) -> str:
    """A parent that is the chat itself is none."""
    return "" if not parent or parent == agent_id else parent


# ---------------------------------------------------------------------------
# Usage: tokens per API message, plan limits (the Usage page, #usage)
# ---------------------------------------------------------------------------
#
# One meaning in every tool. ``new`` = input read for the first time + input
# written to cache; ``output`` = the reply's tokens, thinking inside it;
# ``cache`` = input read again from cache. Each tool counts its own way:
# Claude Code's input_tokens leaves the cache out; Codex's input_tokens holds
# the cached part (new = input − cached); OpenCode's output leaves its
# reasoning out (output = output + reasoning). The lines are written to
# ``chats/<agent>/usage.jsonl`` by the hook, and by sessionimport for a chat
# read from the tool's log afterwards.
#
# A line read from a log carries ``_t``, its time as epoch seconds (UTC, from
# the log's own timestamp: a local wall-clock string repeats an hour when the
# clocks go back), and a helper's line ``tool_use``, the Agent call that
# started it. Neither is written: assign_turns uses them and drops them.

#: The Claude Code tools that start a helper agent.
HELPER_TOOLS = frozenset({"Agent", "Task"})
#: A limits line is appended when a value changed, or the last one of the
#: tool is older than this.
LIMITS_REFRESH_S = 300
#: A session file of the status line older than this is removed.
SESSION_FILE_DAYS = 7
#: The prompts meta.json keeps (``turns``): [turn, started epoch, quiet].
TURN_HISTORY = 500
#: What is written before a chat's first prompt by more than this is earlier
#: history copied into the transcript (a resumed or branched session).
HISTORY_SLACK_S = 60


def _n(value: Any) -> int:
    """A token count as a whole number ≥ 0; anything else (text, a bool,
    NaN, an infinity such as ``1e999`` in the log) is 0."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float) and math.isfinite(value):
        return max(0, int(value))
    return 0


def _pct(value: Any) -> float | None:
    """A percentage as a finite float; None when it is none."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    v = float(value)
    return v if math.isfinite(v) else None


def pct_whole(percent: Any) -> int | None:
    """A percentage (62.5) as a whole one by the Usage page's one rule
    (usagelib._pct): the nearest, a tie down — 62.5 is 62, 62.51 is 63.
    None when it is no finite number."""
    f = _pct(percent)
    if f is None:
        return None
    if f <= 0:
        return 0
    v = round(f, 6)          # float noise off: 0.699 * 100 is 69.9, not 69.899…
    whole = math.floor(v)
    return whole + 1 if v - whole > 0.5 else whole


def epoch_of(ts: Any) -> float | None:
    """A log's timestamp (ISO with ``Z`` or an offset; a naive one is local
    time) as epoch seconds; None when it is none."""
    if not isinstance(ts, str) or not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except (ValueError, OverflowError, OSError):
        return None


def _fixed_now() -> datetime | None:
    """``SP_NOW`` as given (naive: local time; with an offset: that instant)."""
    fixed = os.environ.get("SP_NOW", "").strip()
    if not fixed:
        return None
    try:
        return datetime.fromisoformat(fixed.replace("Z", "+00:00"))
    except ValueError:
        return None


def now_dt() -> datetime:
    """The local time now, as a naive datetime. ``SP_NOW`` (a local ISO time,
    ``2026-11-01T14:48:00``, or one with an offset) fixes it: a test switch,
    read the same way by the server (usagelib.now)."""
    d = _fixed_now()
    if d is None:
        return datetime.now()
    return d.astimezone().replace(tzinfo=None) if d.tzinfo is not None else d


def now_epoch() -> float:
    """The time now as epoch seconds (``SP_NOW`` honoured; give it an offset
    inside the hour the clocks go back, where local time says two instants)."""
    d = _fixed_now()
    return d.timestamp() if d is not None else time.time()


#: The reasoning efforts the tools name (Claude Code's /effort, Codex's
#: model_reasoning_effort, an OpenCode variant of these names). Anything else
#: (an OpenCode variant named otherwise, "default") is no effort: "".
EFFORTS = frozenset({"none", "minimal", "low", "medium", "high", "xhigh", "max"})


def effort_of(value: Any) -> str:
    """A reasoning effort as usage.jsonl keeps it: one of EFFORTS, else ""."""
    v = str(value or "").strip().lower()
    return v if v in EFFORTS else ""


def _usage_line(*, at: str, id: str, tool: str, model: str, new: int, cache_write: int, cache: int,
                output: int, thinking: int, ttl: str = "", helper: str = "", effort: str = "",
                limit: dict[str, float] | None = None, t: float | None = None) -> dict[str, Any]:
    """One line of usage.jsonl, its keys in one order (``turn`` is put in
    front by assign_turns, ``compacted`` at the end). ``effort``: the
    reasoning effort the reply ran with, "" when the log does not say."""
    line: dict[str, Any] = {"at": at, "id": id, "tool": tool, "model": model, "new": new,
                            "cache_write": cache_write, "cache": cache, "output": output,
                            "thinking": thinking, "ttl": ttl, "helper": helper, "effort": effort_of(effort)}
    if limit:
        line["limit"] = limit
    line["_t"] = t
    return line


def is_compact(rec: dict[str, Any]) -> bool:
    """A Claude Code record that marks a compaction of the context: the
    boundary record, or the summary that follows it."""
    return (rec.get("type") == "system" and rec.get("subtype") == "compact_boundary") \
        or bool(rec.get("isCompactSummary"))


def usage_line_claude(rec: dict[str, Any], session_id: str = "", helper: str = "") -> dict[str, Any] | None:
    """The usage of one Claude Code transcript record, or None when it has
    none to count: not an API reply, a ``<synthetic>`` record Claude Code
    makes itself, or a record copied from another session (a resumed or
    branched chat copies the old history with ``forkedFrom``; a record of
    another ``sessionId``). The top-level numbers only: ``iterations`` is
    the same request again. A helper's record (``helper``: read from its own
    transcript; ``isSidechain`` in the main one) names the helper: its
    ``agentId``, else ``helper``, else "sidechain"."""
    if rec.get("type") != "assistant" or "forkedFrom" in rec:
        return None
    if session_id and rec.get("sessionId") and str(rec.get("sessionId")) != session_id:
        return None
    msg = rec.get("message")
    if not isinstance(msg, dict) or not isinstance(msg.get("usage"), dict):
        return None
    model = str(msg.get("model") or "")
    if model == "<synthetic>":
        return None
    key = str(msg.get("id") or rec.get("requestId") or "")
    if not key:
        return None
    u = msg["usage"]
    written = _n(u.get("cache_creation_input_tokens"))
    split = u.get("cache_creation") if isinstance(u.get("cache_creation"), dict) else {}
    ttl = "1h" if _n(split.get("ephemeral_1h_input_tokens")) else "5m" if _n(split.get("ephemeral_5m_input_tokens")) else ""
    details = u.get("output_tokens_details") if isinstance(u.get("output_tokens_details"), dict) else {}
    who = str(rec.get("agentId") or helper) if helper else \
        (str(rec.get("agentId") or "sidechain") if rec.get("isSidechain") else "")
    ts = rec.get("timestamp") or ""
    return _usage_line(
        at=local_iso(ts), id=key, tool="claude-code", model=model,
        new=_n(u.get("input_tokens")) + written, cache_write=written,
        cache=_n(u.get("cache_read_input_tokens")), output=_n(u.get("output_tokens")),
        thinking=_n(details.get("thinking_tokens")), ttl=ttl, helper=who, t=epoch_of(ts),
        # The record's own effort (Claude Code 2.1.322 writes it on every
        # assistant record of a model that has one; /effort changes it).
        effort=rec.get("effort") or "",
    )


def usage_records_claude(records: Any, session_id: str = "", helper: str = "") -> list[dict[str, Any]]:
    """The usage lines of Claude Code transcript records: one per API message.
    Claude Code writes a record per content block (thinking, text, tool use)
    and copies the message's usage into each; ``output_tokens`` may grow
    from one to the next, so the last record of a message wins. In the order
    the messages first appear. A record that cannot be read is skipped."""
    out: dict[str, dict[str, Any]] = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        try:
            line = usage_line_claude(rec, session_id, helper)
        except Exception:  # noqa: BLE001 — one bad record never stops the batch
            continue
        if line is not None:
            out[line["id"]] = line   # a dict keeps the first position, the last value
    return list(out.values())


def helper_starts(rec: dict[str, Any]) -> list[str]:
    """The ids of the Agent (Task) calls in one Claude Code record: a helper
    agent's meta file names the call that started it (``toolUseId``)."""
    content = (rec.get("message") or {}).get("content") if isinstance(rec.get("message"), dict) else None
    if rec.get("type") != "assistant" or not isinstance(content, list):
        return []
    return [str(p.get("id")) for p in content
            if isinstance(p, dict) and p.get("type") == "tool_use" and p.get("name") in HELPER_TOOLS and p.get("id")]


def assign_turns(lines: list[dict[str, Any]], turns: Any, *, calls: dict[str, int] | None = None,
                 starts: dict[str, Any] | None = None, compacts: list[float] | None = None,
                 cutoff: float | None = None, default: int = 0) -> tuple[list[dict[str, Any]], list[float]]:
    """Give each usage line its chat turn: the one rule of the hook and of
    the import (sessionimport), so the two write the same usage.jsonl.

    ``turns``: [[turn, started epoch, quiet], …] in order — the hook's
    history from meta.json, or the import's human prompts. A line goes to
    the last turn begun at or before its time that is not quiet (a #usage
    the hook answered never gets tokens); a line from before the first turn
    goes to the first one. A line with no time goes to ``default``.

    A helper's line goes to the turn of the Agent call that started it
    (``tool_use``): ``calls`` {call: turn} is what earlier reads resolved
    (the hook keeps it in meta.json) and is updated in place with ``starts``
    {call: {"t": epoch, "parent": call}} — a call is given the turn of its
    time, or, made inside a helper (``parent``), that helper's turn. A
    helper whose call is unknown goes by its own time.

    ``cutoff``: lines written before it (epoch) are earlier history copied
    in, not this chat's: dropped (a helper's only when its call is unknown;
    a call made before it is not known).
    ``compacts``: times of compaction boundaries; the first main line at or
    after each is marked ``compacted``. Answers (the lines, the boundaries
    no line came after yet)."""
    open_turns: list[tuple[float, int]] = []
    for item in turns if isinstance(turns, list) else []:
        try:
            n, start, quiet = int(item[0]), item[1], bool(item[2]) if len(item) > 2 else False
        except (TypeError, ValueError, IndexError):
            continue
        if not quiet and isinstance(start, (int, float)) and math.isfinite(start):
            open_turns.append((float(start), n))
    open_turns.sort()
    begins = [s for s, _ in open_turns]

    def turn_at(t: Any) -> int:
        if not isinstance(t, (int, float)) or not open_turns:
            return default or (open_turns[-1][1] if open_turns else 0)
        i = bisect.bisect_right(begins, t) - 1
        return open_turns[max(0, i)][1]

    known = calls if calls is not None else {}
    waiting = {}
    for call, s in (starts or {}).items():
        if call in known:
            continue
        if isinstance(s, dict):
            t, parent = s.get("t"), str(s.get("parent") or "")
        else:
            t, parent = (s if isinstance(s, (int, float)) else epoch_of(s)), ""
        if cutoff is not None and isinstance(t, (int, float)) and t < cutoff:
            continue          # a call in the history copied in (or made inside its helpers): not this chat's
        waiting[str(call)] = (t, parent)
    for _ in range(8):     # a helper's call inside a helper inside a helper …
        progressed = False
        for call, (t, parent) in list(waiting.items()):
            if parent and parent not in known and parent in waiting:
                continue
            known[call] = known[parent] if parent and parent in known else turn_at(t)
            del waiting[call]
            progressed = True
        if not waiting or not progressed:
            break
    for call, (t, _parent) in waiting.items():
        known[call] = turn_at(t)

    out: list[dict[str, Any]] = []
    for ln in lines:
        t = ln.get("_t")
        call = str(ln.get("tool_use") or "")
        if ln.get("helper") and call and call in known:
            n = known[call]
        else:
            if cutoff is not None and isinstance(t, (int, float)) and t < cutoff:
                continue
            n = turn_at(t)
        if n < 1:
            continue
        out.append({"turn": int(n), **{k: v for k, v in ln.items() if k not in ("_t", "tool_use", "turn")},
                    "_t": t})
    left: list[float] = []
    for b in sorted(c for c in compacts or [] if isinstance(c, (int, float))):
        after = [x for x in out if not x.get("helper") and isinstance(x["_t"], (int, float)) and x["_t"] >= b]
        if after:
            min(after, key=lambda x: x["_t"])["compacted"] = True
        else:
            left.append(b)
    for x in out:
        x.pop("_t", None)
    return out, left


def _codex_limit_pct(rate_limits: Any) -> dict[str, float]:
    """{five_hour, seven_day} used percent from a Codex rate_limits block."""
    windows = codex_windows(rate_limits)
    return {k: float(v["used"]) for k, v in windows.items() if v.get("used") is not None}


def codex_windows(rate_limits: Any) -> dict[str, dict[str, Any]]:
    """A Codex rate_limits block as {five_hour, seven_day}: {used, resets_at}.
    The window is named by its length (300 minutes, 10 080 minutes); without
    one, primary is the 5-hour window and secondary the weekly one."""
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(rate_limits, dict):
        return out
    for pos, default in (("primary", "five_hour"), ("secondary", "seven_day")):
        w = rate_limits.get(pos)
        if not isinstance(w, dict):
            continue
        minutes = w.get("window_minutes")
        name = "five_hour" if minutes == 300 else "seven_day" if minutes == 10080 else default
        out[name] = {"used": _pct(w.get("used_percent")), "resets_at": epoch_local(w.get("resets_at"))}
    return out


def _codex_id(rec: dict[str, Any], info: dict[str, Any]) -> str:
    """A Codex call's key: the thread's running total after it
    (total_token_usage.total_tokens grows with every call), so the same call
    reported again — at a later time, after the next task_started — is one
    line; the event's time when the total is missing."""
    total = info.get("total_token_usage")
    n = total.get("total_tokens") if isinstance(total, dict) else None
    if isinstance(n, int) and not isinstance(n, bool) and n > 0:
        return str(n)
    return str(rec.get("timestamp") or "")


def codex_effort(turn_context: Any) -> str:
    """The reasoning effort a Codex ``turn_context`` payload names: ``effort``,
    else its collaboration mode's ``reasoning_effort``."""
    if not isinstance(turn_context, dict):
        return ""
    mode = turn_context.get("collaboration_mode")
    settings = mode.get("settings") if isinstance(mode, dict) else None
    return effort_of(turn_context.get("effort")
                     or (settings.get("reasoning_effort") if isinstance(settings, dict) else ""))


def usage_records_codex(records: Any, model: str = "",
                        limits_out: list[dict[str, Any]] | None = None, session: str = "",
                        effort: str = "") -> list[dict[str, Any]]:
    """The usage lines of Codex rollout records: one per API call, from the
    ``last_token_usage`` of its ``token_count`` event (``total_token_usage``
    grows over the thread and is not summed). A call reported again keeps
    its first report (its time decides its turn). The model and the effort
    are the last ``turn_context``'s. ``limits_out`` receives the last limits
    line seen."""
    out: dict[str, dict[str, Any]] = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        pl = rec.get("payload")
        if not isinstance(pl, dict):
            continue
        if rec.get("type") == "turn_context":
            model = str(pl.get("model") or model)
            effort = codex_effort(pl)
            continue
        if rec.get("type") != "event_msg" or pl.get("type") != "token_count":
            continue
        try:
            at = local_iso(rec.get("timestamp") or "")
            if limits_out is not None and isinstance(pl.get("rate_limits"), dict):
                reading = limits_line_codex(pl["rate_limits"], at, model, session=session)
                if "five_hour" in reading or "seven_day" in reading:   # an empty block keeps the last reading
                    limits_out[:] = [reading]
            info = pl.get("info")
            if not isinstance(info, dict) or not isinstance(info.get("last_token_usage"), dict):
                continue
            key = _codex_id(rec, info)
            if not key or key in out:
                continue
            u = info["last_token_usage"]
            cached = _n(u.get("cached_input_tokens"))
            written = _n(u.get("cache_write_input_tokens"))
            out[key] = _usage_line(
                at=at, id=key, tool="codex", model=model,
                new=max(0, _n(u.get("input_tokens")) - cached) + written, cache_write=written, cache=cached,
                output=_n(u.get("output_tokens")), thinking=_n(u.get("reasoning_output_tokens")),
                effort=effort, limit=_codex_limit_pct(pl.get("rate_limits")) or None, t=epoch_of(rec.get("timestamp")),
            )
        except Exception:  # noqa: BLE001 — one bad record never stops the batch
            continue
    return list(out.values())


def codex_turn_usage(rollout: Path, turn_id: str = "", back: int = 0,
                     since: float | None = None) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """(usage lines, the last limits line) of a Codex session file: the turn
    ``turn_id`` names (the last one when it names none, or one the file does
    not have), from its ``task_started`` to the next; with ``back``, that
    many turns before it too. With ``since`` (epoch), instead every call
    written after that time, of any turn: a call the previous read came too
    early for is kept now. ([], None) when the file cannot be read."""
    model = effort = ""
    # (turn id, model at its start, records, effort at its start)
    turns: list[tuple[str, str, list[dict[str, Any]], str]] = []
    try:
        with open(rollout, encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                try:
                    rec = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(rec, dict):
                    continue
                pl = rec.get("payload")
                if rec.get("type") == "event_msg" and isinstance(pl, dict) and pl.get("type") == "task_started":
                    turns.append((str(pl.get("turn_id") or ""), model, [], effort))
                    continue
                if rec.get("type") == "turn_context" and isinstance(pl, dict):
                    model = str(pl.get("model") or model)
                    effort = codex_effort(pl)
                if turns:
                    turns[-1][2].append(rec)
    except OSError:
        return [], None
    if not turns:
        return [], None
    limits: list[dict[str, Any]] = []
    # The thread's id from the file's name; its last 8 characters, as in
    # the chat's agent id (Codex's ids begin with the time).
    named = re.match(r"rollout-\d{4}-\d\d-\d\dT\d\d-\d\d-\d\d-(.+)\.jsonl$", Path(rollout).name)
    session = session_key("codex", named.group(1)) if named else ""
    if since is not None:
        every = [r for _id, _m, recs, _e in turns for r in recs]
        # From the mark itself: a call written later with the same time is
        # read too (the ones kept already are skipped by id).
        lines = [x for x in usage_records_codex(every, turns[0][1], limits, session, turns[0][3])
                 if isinstance(x["_t"], (int, float)) and x["_t"] >= since]
        return lines, (limits[0] if limits else None)
    at = next((i for i in range(len(turns) - 1, -1, -1) if turns[i][0] == turn_id), None) if turn_id else None
    if at is None:
        at = len(turns) - 1
    picked = turns[max(0, at - back):at + 1]
    recs = [r for _id, _m, rs, _e in picked for r in rs]
    return usage_records_codex(recs, picked[0][1], limits, session, picked[0][3]), (limits[0] if limits else None)


def usage_records_opencode(messages: Any) -> list[dict[str, Any]]:
    """Usage lines from the OpenCode plugin's message tokens: [{id, at (epoch
    ms), model, input, output, reasoning, cache_read, cache_write, helper,
    variant}].
    OpenCode counts reasoning beside output (total = input + output +
    reasoning + cache), so here it is added to output, where the other tools
    count it. A message that cannot be read is skipped."""
    out: dict[str, dict[str, Any]] = {}
    for m in messages if isinstance(messages, list) else []:
        if not isinstance(m, dict) or not m.get("id"):
            continue
        try:
            at = m.get("at")
            t = float(at) / 1000 if isinstance(at, (int, float)) and not isinstance(at, bool) \
                and math.isfinite(at) and at > 0 else None
            try:
                when = datetime.fromtimestamp(t).strftime("%Y-%m-%dT%H:%M:%S") if t is not None else ""
            except (OverflowError, OSError, ValueError):
                when, t = "", None
            written = _n(m.get("cache_write"))
            reasoning = _n(m.get("reasoning"))
            out[str(m["id"])] = _usage_line(
                at=when, id=str(m["id"]), tool="opencode", model=str(m.get("model") or ""),
                new=_n(m.get("input")) + written, cache_write=written, cache=_n(m.get("cache_read")),
                output=_n(m.get("output")) + reasoning, thinking=reasoning, helper=str(m.get("helper") or ""),
                # The reply's reasoning variant (`--variant high`): an effort
                # only when it is named as one (EFFORTS).
                effort=m.get("variant") or "", t=t,
            )
        except Exception:  # noqa: BLE001 — one bad message never stops the batch
            continue
    return list(out.values())


_SAME_KEYS = ("model", "new", "cache_write", "cache", "output", "thinking", "ttl", "helper", "compacted")


def _known_usage(path: Path, whole: bool) -> dict[str, dict[str, Any]]:
    """{id: its last line} of usage.jsonl: the end of the file, or with
    ``whole`` every line (read once, line by line)."""
    known: dict[str, dict[str, Any]] = {}

    def take(raw: str) -> None:
        try:
            rec = json.loads(raw)
        except ValueError:
            return
        if isinstance(rec, dict) and rec.get("id"):
            known[str(rec["id"])] = rec

    if whole:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                for raw in fh:
                    take(raw)
        except OSError:
            pass
    else:
        for raw in tail_lines(path):
            take(raw)
    return known


def _codex_same(line: dict[str, Any]) -> tuple:
    return (line.get("at"), line.get("new"), line.get("cache"), line.get("output"), line.get("thinking"))


def usage_append(path: Any, lines: list[dict[str, Any]], whole: bool = False) -> list[dict[str, Any]]:
    """Append usage lines to ``path`` (usage.jsonl), skipping ids the file
    already holds with the same numbers: a retried Stop, or a transcript
    read again, hands the same records again. The look and the append are
    one step under the file's lock. Known ids are looked for in the end of
    the file; with ``whole`` (a log read again from its start) in all of it.

    A known id with other numbers (a later content block of the message,
    with more output) is appended again, under its first turn: the server
    reads the last line of an id (last wins), so nothing is rewritten. One
    whose output is smaller is an older copy and is skipped. Answers the
    lines written."""
    if not lines:
        return []
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with locked(p):
        known = _known_usage(p, whole or False)
        # A Codex call kept before its key was the running total (an older
        # hook keyed it by the event's time): the same call by its numbers.
        legacy = {_codex_same(x) for k, x in known.items() if x.get("tool") == "codex" and not k.isdigit()}
        fresh: list[dict[str, Any]] = []
        for line in lines:
            key = str(line.get("id") or "")
            if not key:
                continue
            if legacy and line.get("tool") == "codex" and key.isdigit() and _codex_same(line) in legacy:
                continue
            old = known.get(key)
            if old is not None:
                if all(old.get(k) == line.get(k) for k in _SAME_KEYS if k != "compacted") \
                        and (bool(old.get("compacted")) or not line.get("compacted")):
                    continue
                if _n(line.get("output")) < _n(old.get("output")):
                    continue
                line = {**line, "turn": old.get("turn", line.get("turn"))}
                if old.get("compacted"):
                    line["compacted"] = True
            known[key] = line
            fresh.append(line)
        if fresh:
            _append_bytes(p, "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in fresh))
    return fresh


def epoch_local(value: Any) -> str:
    """Epoch seconds as local, naive ``YYYY-MM-DDTHH:MM:SS`` ("" if none)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        return ""
    try:
        return datetime.fromtimestamp(float(value)).strftime("%Y-%m-%dT%H:%M:%S")
    except (OverflowError, OSError, ValueError):
        return ""


def config_key(folder: Any) -> str:
    """Which account a limits reading belongs to: 12 hex characters of the
    tool's config folder (its real path; ``~`` expanded). Claude Code keeps
    one sign-in per config folder (``CLAUDE_CONFIG_DIR``), Codex per
    ``CODEX_HOME``; the folder is not written, only its key."""
    try:
        text = os.path.realpath(os.path.expanduser(str(folder)))
    except (OSError, ValueError):
        text = str(folder)
    return hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()[:12]


def claude_config_dir() -> Path:
    """Claude Code's config folder: $CLAUDE_CONFIG_DIR, else ~/.claude."""
    return Path(os.environ["CLAUDE_CONFIG_DIR"]) if os.environ.get("CLAUDE_CONFIG_DIR") else Path.home() / ".claude"


def _short_session(session: Any) -> str:
    """A session id's first 8 characters, kept with a limits line to tell
    readings apart when something looks wrong (not to find the chat)."""
    return re.sub(r"[^0-9A-Za-z_-]", "", str(session or ""))[:8]


def limits_line_claude(rate_limits: Any, at: str, account: str = "", model: str = "",
                       session: str = "") -> dict[str, Any] | None:
    """A limits line from the Claude Code status line's ``rate_limits``
    ({five_hour, seven_day}: {used_percentage, resets_at epoch seconds});
    a window Claude Code left out is left out. None without either.
    The limits are the account's: the line names it (``account``, the
    config folder's key) and, as data, the status line's model id and the
    session it came from (its first 8 characters)."""
    if not isinstance(rate_limits, dict):
        return None
    line: dict[str, Any] = {"at": at, "tool": "claude-code", "account": str(account or ""),
                            "model": str(model or ""), "session": _short_session(session)}
    for name in ("five_hour", "seven_day"):
        w = rate_limits.get(name)
        if not isinstance(w, dict):
            continue
        used = _pct(w.get("used_percentage"))
        if used is None:
            continue
        line[name] = {"used": used, "resets_at": epoch_local(w.get("resets_at"))}
    if "five_hour" not in line and "seven_day" not in line:
        return None
    line["source"] = "statusline"
    return line


def limits_line_codex(rate_limits: Any, at: str, model: str = "", account: str | None = None,
                      session: str = "") -> dict[str, Any]:
    """A limits line from a Codex token_count event's ``rate_limits``: the
    account is CODEX_HOME's key (``account`` None: this process's); the
    model, the rollout's at that moment, is data (the series is the
    account's, limits_series_key)."""
    line: dict[str, Any] = {"at": at, "tool": "codex",
                            "account": config_key(codex_home()) if account is None else str(account),
                            "model": str(model or ""), "session": _short_session(session)}
    for name, w in codex_windows(rate_limits).items():
        if w.get("used") is not None:
            line[name] = w
    if isinstance(rate_limits, dict) and rate_limits.get("plan_type"):
        line["plan"] = str(rate_limits["plan_type"])
    line["source"] = "rollout"
    return line


def limits_series_key(rec: dict[str, Any]) -> tuple[str, str]:
    """(tool, account) of a limits line: the readings that are one series.
    The limits are the account's (two chats on two models read the same
    numbers); ``model`` and ``session`` are kept on the line as data. A
    line written before readings named the account has ""."""
    return (str(rec.get("tool") or ""), str(rec.get("account") or ""))


def _limits_news(seen: list[dict[str, Any]], line: dict[str, Any]) -> bool:
    """Whether ``line`` tells more than the lines of its series ``seen``
    (oldest first): a window with a later reset than any written, or a
    higher percentage than the highest written for the same reset. Within
    one window the percentage never goes down, so an equal or lower one is
    an idle session's status line sending its last reading again."""
    for w in ("five_hour", "seven_day"):
        v = line.get(w)
        if not isinstance(v, dict):
            continue
        resets = str(v.get("resets_at") or "")
        top: float | None = None
        newest = ""
        for rec in seen:
            x = rec.get(w)
            if not isinstance(x, dict):
                continue
            r = str(x.get("resets_at") or "")
            newest = max(newest, r)
            if r == resets and _finite_or_none(x.get("used")) is not None:
                top = max(top if top is not None else -1.0, float(x["used"]))
        if resets > newest:
            return True
        used = _finite_or_none(v.get("used"))
        if resets == newest and used is not None and (top is None or used > top):
            return True
    return False


def _finite_or_none(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        return None
    return float(v)


def limits_append(data_root: Any, line: dict[str, Any] | None, now: float | None = None) -> bool:
    """Append a plan-limits reading to ``<data root>/.usage/limits.jsonl``
    (history kept) for its series — tool and account (limits_series_key) —
    when it tells something new (``_limits_news``: a window reset later
    than any written, or a percentage higher than the highest written for
    that reset), when the plan changed, or when the series' last line is
    older than LIMITS_REFRESH_S (a heartbeat: the page's "read HH:MM" stays
    fresh). An equal or lower reading of the same reset within that time
    is skipped. The series' lines looked at are those in the last 64 KB.
    The look and the append are one step under the file's lock. Never
    builds a data root. True when a line was written."""
    if not line or not line.get("tool") or not Path(data_root).is_dir():
        return False
    if "five_hour" not in line and "seven_day" not in line:
        return False
    path = Path(data_root) / ".usage" / "limits.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    key = limits_series_key(line)
    with locked(path):
        seen: list[dict[str, Any]] = []
        for raw in tail_lines(path, max_bytes=64 * 1024):
            try:
                rec = json.loads(raw)
            except ValueError:
                continue
            if isinstance(rec, dict) and limits_series_key(rec) == key:
                seen.append(rec)
        if seen:
            last = seen[-1]
            try:
                age = (now or now_epoch()) - datetime.fromisoformat(str(last.get("at") or "")).timestamp()
            except (ValueError, OverflowError, OSError):
                age = LIMITS_REFRESH_S + 1
            if age < LIMITS_REFRESH_S and last.get("plan") == line.get("plan") \
                    and not _limits_news(seen, line):
                return False
        _append_bytes(path, json.dumps(line, ensure_ascii=False) + "\n")
    return True


# ---------------------------------------------------------------------------
# The status line's wrapped command (Setup writes it, statusline.py runs it)
# ---------------------------------------------------------------------------
#
# Setup's status line hides the one the operator had. The command it runs
# after itself is not written into the shell line (quoting it for sh and for
# cmd broke both): it is kept in ``<data root>/.usage/statusline-then/<key>.json``
# — {"command", "from": "local" | "project" | "user", "entry", "folder",
# "user_settings"} — and the line carries ``--then-key <key>``. ``local``: the
# operator's line stood in the same file; its whole entry is kept, and put
# back when the folder is disconnected. ``project`` / ``user``: it stands in
# the project's shared settings or the user's, and is read from there at
# every run, so an edit to it is honoured.

#: The script of Setup's status line.
STATUSLINE_SCRIPT = "statusline.py"


def is_sp_statusline(entry: Any) -> bool:
    """A statusLine Setup wrote."""
    return isinstance(entry, dict) and STATUSLINE_SCRIPT in str(entry.get("command", "")) \
        and "--data-root" in str(entry.get("command", ""))


def folder_key(cwd: str) -> str:
    """The one spelling of a working folder, so the hook that writes a chat's
    breadcrumb and the MCP server that asks for it name one folder alike.
    The tool and the server spelled it apart: ``c:\\x`` against ``C:\\x``
    (Windows), ``/var/…`` against ``/private/var/…`` (macOS), a name in NFD
    against NFC, a trailing separator, a link to the folder. Each was another
    sha1 and a 404 ("no captured session"; round 5)."""
    import unicodedata
    if not cwd:
        return ""
    try:
        real = os.path.realpath(cwd)
    except (OSError, ValueError):
        real = cwd
    return os.path.normcase(unicodedata.normalize("NFC", real))


def folder_digest(cwd: str) -> str:
    """12 hex characters of the folder's one spelling: the breadcrumb's name."""
    return hashlib.sha1(folder_key(cwd).encode("utf-8", errors="replace")).hexdigest()[:12]


def statusline_key(folder: Any) -> str:
    """The name of a folder's side file: 12 hex characters of its path."""
    return hashlib.sha1(str(folder).encode("utf-8")).hexdigest()[:12]


def statusline_then_path(data_root: Any, key: str) -> Path | None:
    """Where the side file of ``key`` is; None for a key that is not one."""
    if not re.fullmatch(r"[0-9a-f]{12}", key or ""):
        return None
    return Path(data_root) / ".usage" / "statusline-then" / f"{key}.json"


def read_statusline_then(data_root: Any, key: str) -> dict[str, Any] | None:
    path = statusline_then_path(data_root, key)
    if path is None:
        return None
    try:
        got = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) else None


def _settings_statusline(path: Any) -> dict[str, Any] | None:
    """The ``statusLine`` entry of a settings file (None when it has none)."""
    try:
        got = json.loads(Path(path).read_text(encoding="utf-8-sig")).get("statusLine")
    except (OSError, ValueError, AttributeError, TypeError):
        return None
    return got if isinstance(got, dict) else None


def statusline_then_command(rec: dict[str, Any] | None) -> str:
    """The command a side file says to run after ours, as it stands now: the
    kept one (``local``), else the project's shared settings', else the
    user's — the first that is not ours. "" for none."""
    if not isinstance(rec, dict):
        return ""
    if rec.get("from") == "local":
        return str(rec.get("command") or "")
    for path in (Path(str(rec.get("folder") or "")) / ".claude" / "settings.json" if rec.get("folder") else None,
                 rec.get("user_settings")):
        if not path:
            continue
        entry = _settings_statusline(path)
        if entry is None or is_sp_statusline(entry):
            continue
        command = str(entry.get("command") or "").strip()
        if command:
            return command
    return ""
