"""Terminals: what they are, where they live, what runs in them.

A terminal is a row in ``<data root>/terminal/sessions.json`` — its id, its
label, the project and folder it opened in, the command it was opened for
(a resume, a start on a task, or none), and the agent and task it belongs
to. The shell itself lives in one of two places (setting ``terminal.keep``):

- **tmux** (the default when tmux is installed): each terminal is a session
  on Slightly Parallel's own tmux socket (``tmux -L sp-<hash of the data root>``), with no status bar and
  the mouse wheel scrolling its history. The browser attaches to it through
  a pty; a closed tab, a reload or a server restart detaches, and the next
  look attaches again — an agent in it keeps working meanwhile.
- **plain**: a pty the server holds (routers/terminal.py); it ends with the
  server.

What runs in a terminal is read, not guessed: tmux says the program in the
foreground and when the terminal last printed; the capture hook records the
terminal an agent was started in (``SP_TERMINAL`` → chat meta
``terminal``) and when the agent last finished an answer (``last_stop``).
From those, each terminal has a state:

- ``shell``   — a prompt, nothing running;
- ``working`` — a program is running and printing;
- ``waiting`` — an agent is running and has finished its answer, or has
  printed nothing for a while: your turn;
- ``running`` — any other program, quiet (a dev server, a watcher);
- ``ended``   — the terminal is gone.

The terminal folder is left out of the file watcher and of backups.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import secrets
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from .csvio import read_rows
from .docs_md import resolve_under
from .file_safety import edit_json, safe_read_json

log = logging.getLogger("sp.terminal")

FOLDER = "terminal"
REGISTRY = "sessions.json"
SOCKET = "sp"
OLD_SOCKET = "merkhet"  # the socket's name before the product was renamed
PREFIX = "mk-"
QUIET_SECONDS = 4            # printed nothing this long: not working any more
SHELLS = {"bash", "zsh", "sh", "fish", "dash", "ksh", "tmux", "login"}
TMUX_CONF = """\
# Slightly Parallel's own tmux: invisible, the browser is the window.
set -g status off
set -g mouse on
set -g history-limit 50000
set -g default-terminal "xterm-256color"
set -ga terminal-overrides ",xterm-256color:Tc"
set -g escape-time 0
set -g focus-events on
set -g set-clipboard on
set -g window-size latest
set -g aggressive-resize on
# Two views of one terminal at two sizes: the one typed in last sets the
# size, and the other's spare room is left blank, not dotted.
set -g fill-character " "
# tmux's own marks in the terminal's calm palette, not its default yellow:
# the scrolled-up position and a copy selection wear the screen's teal
# selection; the edge a wider view draws is a quiet line.
set -g mode-style "fg=#E6E8EB,bg=#1F4A40"
set -g pane-border-style "fg=#2A2E35"
set -g pane-active-border-style "fg=#2A2E35"
"""

_lock = threading.Lock()
_link_cache: tuple[float, dict[str, dict[str, Any]]] = (0.0, {})


# ---------------------------------------------------------------------------
# Places
# ---------------------------------------------------------------------------


def folder(data_root: Path) -> Path:
    p = Path(data_root) / FOLDER
    p.mkdir(parents=True, exist_ok=True)
    return p


def registered_project_dirs(data_root: Path) -> dict[str, Path]:
    """project code → source folder, from integrations.csv (the Setup page).

    These folders are the allowlist for where a terminal may open.
    """
    out: dict[str, Path] = {}
    for row in read_rows(Path(data_root) / "integrations.csv"):
        code = (row.get("project") or "").strip()
        raw = (row.get("path") or "").strip()
        if code and raw:
            out[code] = Path(raw)
    return out


def resolve_cwd(data_root: Path, project: str, cwd: str = "") -> Path:
    """Where a terminal opens: ``cwd`` when it lies under a registered project
    folder (or the data root), else the project's folder, else the data root."""
    projects = registered_project_dirs(data_root)
    if cwd:
        for root in (*projects.values(), Path(data_root)):
            # Resolved, both: `..` and symlinks must not walk out of the allowlist.
            got = Path(cwd).resolve() if Path(cwd).is_absolute() else None
            base = root.resolve()
            if got is not None and got.is_dir() and (got == base or base in got.parents):
                return got
            resolved = resolve_under(root, cwd)
            if resolved is not None and resolved.is_dir():
                return resolved
    candidate = projects.get(project)
    if candidate is not None and candidate.is_dir():
        return candidate
    return Path(data_root)


# ---------------------------------------------------------------------------
# tmux
# ---------------------------------------------------------------------------


def tmux_path() -> str | None:
    return shutil.which("tmux")


def tmux_version() -> str:
    t = tmux_path()
    if not t:
        return ""
    try:
        return subprocess.run([t, "-V"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _socket_dir() -> Path:
    """Where tmux keeps its sockets: $TMUX_TMPDIR or /tmp, then tmux-<uid>."""
    base = Path(os.environ.get("TMUX_TMPDIR") or tempfile.gettempdir())
    uid = os.getuid() if hasattr(os, "getuid") else 0
    return base / f"tmux-{uid}"


def socket_of(data_root: Path) -> str:
    """Each data root its own tmux socket: a test's terminals never meet yours.
    A server still running under the old name (terminals opened before the
    rename) is kept talking to until it is gone, so no session is lost."""
    tail = hashlib.sha1(str(Path(data_root).resolve()).encode()).hexdigest()[:8]
    new, old = f"{SOCKET}-{tail}", f"{OLD_SOCKET}-{tail}"
    sockets = _socket_dir()
    if (sockets / old).exists() and not (sockets / new).exists():
        return old
    return new


def tmux_argv(data_root: Path, *args: str) -> list[str]:
    conf = folder(data_root) / "tmux.conf"
    if not conf.exists() or conf.read_text(encoding="utf-8") != TMUX_CONF:
        conf.write_text(TMUX_CONF, encoding="utf-8")
        # A tmux already running reads the new settings now, not at its next start.
        try:
            subprocess.run([tmux_path() or "tmux", "-L", socket_of(data_root), "source-file", str(conf)],
                           capture_output=True, timeout=3)
        except (OSError, subprocess.SubprocessError):
            pass
    return [tmux_path() or "tmux", "-L", socket_of(data_root), "-f", str(conf), *args]


def tmux(data_root: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(tmux_argv(data_root, *args), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5, check=check)


def scrollback_of(settings: dict[str, Any]) -> int:
    """The lines a new terminal keeps (Settings › Terminal history)."""
    try:
        return max(1000, min(200_000, int(settings.get("terminal.scrollback", 50_000))))
    except (TypeError, ValueError):
        return 50_000


# ---------------------------------------------------------------------------
# Opening a path the terminal printed, in the operator's editor
# ---------------------------------------------------------------------------

#: The editors a printed path can open in, by their command-line launchers.
#: `{target}` is `path:line:col`; every one of these understands it.
EDITORS: dict[str, tuple[str, tuple[str, ...]]] = {
    "vscode": ("code", ("-g", "{target}")),
    "cursor": ("cursor", ("-g", "{target}")),
    "windsurf": ("windsurf", ("-g", "{target}")),
    "zed": ("zed", ("{target}",)),
    "sublime": ("subl", ("{target}",)),
}


def editor_of(settings: dict[str, Any]) -> str:
    """The editor paths open in: the chosen one if installed, the first
    installed one for "auto", "" when off or none is found."""
    choice = str(settings.get("terminal.editor", "auto"))
    if choice == "off":
        return ""
    names = list(EDITORS) if choice == "auto" else [choice]
    return next((n for n in names if n in EDITORS and shutil.which(EDITORS[n][0])), "")


def pane_dir(data_root: Path, row: dict[str, Any]) -> Path:
    """Where the terminal's shell stands now — after any `cd` — so a relative
    path it printed resolves where it was printed. A plain terminal (or a
    pane tmux cannot answer for) falls back to the folder it opened in."""
    if row.get("backend") == "tmux":
        out = tmux(data_root, "display-message", "-p", "-t", PREFIX + str(row["id"]), "#{pane_current_path}")
        here = (out.stdout or "").strip()
        if here and Path(here).is_dir():
            return Path(here)
    return Path(str(row.get("cwd") or Path.home()))


def resolve_printed(data_root: Path, row: dict[str, Any], raw: str) -> Path | None:
    """A path as printed (relative, ~/…, or absolute) → the file, if it exists."""
    text = raw.strip()
    if not text or "\0" in text or len(text) > 1024:
        return None
    p = Path(os.path.expanduser(text))
    if not p.is_absolute():
        p = pane_dir(data_root, row) / p
    try:
        p = p.resolve()
    except OSError:
        return None
    return p if p.exists() else None


def open_in_editor(editor: str, path: Path, line: int = 0, col: int = 0) -> None:
    """Start the editor on `path` at `line:col` — a fixed argument list, never
    a shell; detached, so the editor outlives nothing of ours."""
    binary, args = EDITORS[editor]
    target = str(path) + (f":{line}" if line > 0 else "") + (f":{col}" if line > 0 and col > 0 else "")
    _spawn([shutil.which(binary) or binary, *(a.replace("{target}", target) for a in args)])


def _spawn(argv: list[str]) -> None:
    """Start a program and let it go (the tests watch this seam)."""
    subprocess.Popen(  # noqa: S603 — fixed argv, never a shell
        argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def to_bottom(data_root: Path, sid: str) -> None:
    """Leave the pane's copy mode — the view jumps back to the newest line."""
    tmux(data_root, "send-keys", "-X", "-t", PREFIX + sid, "cancel")


def uses_tmux(settings: dict[str, Any]) -> bool:
    return settings.get("terminal.keep", "tmux") == "tmux" and tmux_path() is not None


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------


def registry_path(data_root: Path) -> Path:
    # Not folder(): reading the list must not create the terminal folder.
    return Path(data_root) / FOLDER / REGISTRY


def rows(data_root: Path) -> list[dict[str, Any]]:
    p = registry_path(data_root)
    if not p.exists():
        return []
    try:
        data = safe_read_json(p)
    except (OSError, ValueError):
        return []
    return [r for r in (data.get("sessions") if isinstance(data, dict) else []) or [] if isinstance(r, dict)]


def get(data_root: Path, sid: str) -> dict[str, Any] | None:
    return next((r for r in rows(data_root) if r.get("id") == sid), None)


def _edit(data_root: Path, change) -> Any:
    folder(data_root)  # a write makes the folder; a read never does
    out: list[Any] = []

    def apply(doc: Any) -> dict:
        doc = doc if isinstance(doc, dict) else {}
        sessions = [r for r in doc.get("sessions") or [] if isinstance(r, dict)]
        out.append(change(sessions))
        return {"sessions": sessions}

    edit_json(registry_path(data_root), apply)
    return out[0] if out else None


def put(data_root: Path, row: dict[str, Any]) -> dict[str, Any]:
    def change(sessions: list[dict[str, Any]]) -> dict[str, Any]:
        for i, r in enumerate(sessions):
            if r.get("id") == row["id"]:
                sessions[i] = {**r, **row}
                return sessions[i]
        sessions.append(row)
        return row
    return _edit(data_root, change)


def forget(data_root: Path, sid: str) -> bool:
    def change(sessions: list[dict[str, Any]]) -> bool:
        n = len(sessions)
        sessions[:] = [r for r in sessions if r.get("id") != sid]
        return len(sessions) < n
    return bool(_edit(data_root, change))


SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")


def new_id() -> str:
    return "t" + secrets.token_hex(4)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def ansi_quote(text: str) -> str:
    """One line of bash that holds any text: $'…' with the escapes spelled.
    Other control characters are dropped: typed, ESC or ^U act as keys."""
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)
    body = (text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
            .replace("\r", "").replace("\t", "\\t"))
    return f"$'{body}'"


def resume_command(tool: str, session_ref: str) -> str:
    # A ref starting with "-" would be read as an option of the tool.
    if not session_ref or not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$", session_ref):
        return ""
    if tool == "claude-code":
        return f"claude -r {session_ref}"
    if tool == "codex":
        return f"codex resume {session_ref}"
    if tool == "opencode":
        return f"opencode --session {session_ref}"
    return ""


def task_prompt(task: dict[str, Any]) -> str:
    title = str(task.get("title") or "").strip()
    desc = str(task.get("description") or "").strip()
    head = f"Work on the Slightly Parallel task {task.get('id')} · {title}."
    body = f"{head}\n\n{desc[:3000]}" if desc else head
    return body


def start_command(tool: str, task: dict[str, Any]) -> str:
    q = ansi_quote(task_prompt(task))
    if tool == "codex":
        return f"codex {q}"
    if tool == "opencode":
        return f"opencode --prompt {q}"
    return f"claude {q}"


def typed_form(command: str, shell: str) -> str:
    """`command` as it is typed into `shell`. The commands built above use
    bash's ``$'…'`` quoting, and a task's text is inside them: typed as they
    are into another shell, a quote in that text would end the string and
    the rest would run. bash and zsh read it as written; a POSIX shell hands
    it to bash in one quoted word; any other shell (fish, nu — their quoting
    rules differ) gets it as base64, which holds nothing to quote."""
    name = Path(shell or "bash").name
    if name in ("bash", "zsh"):
        return command
    if name in ("sh", "dash", "ash", "ksh"):
        return f"bash -lc {shlex.quote(command)}"
    packed = base64.b64encode(command.encode("utf-8")).decode("ascii")
    return f"bash -lc 'eval \"$(echo {packed} | base64 -d)\"'"


# ---------------------------------------------------------------------------
# Opening, typing, closing
# ---------------------------------------------------------------------------


def open_session(data_root: Path, settings: dict[str, Any], *, kind: str, project: str, cwd: str,
                 command: str = "", label: str = "", agent_id: str = "", task_id: str = "",
                 sid: str = "") -> dict[str, Any]:
    """A new terminal: its row, and — with tmux — the session, running `command`."""
    sid = sid if sid and SAFE_ID.match(sid) else new_id()
    where = str(resolve_cwd(data_root, project, cwd))
    backend = "tmux" if uses_tmux(settings) else "plain"
    row = {
        "id": sid, "kind": kind, "label": label or (project or "shell"), "project": project,
        "cwd": where, "command": command, "agent_id": agent_id, "task_id": task_id,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "backend": backend,
        "launch": settings.get("terminal.launch", "run"),
    }
    if backend == "tmux":
        shell = os.environ.get("SHELL") or "bash"
        # The history length is set just before the pane is made: tmux gives
        # a pane the limit in force when it is born, and keeps it.
        tmux(data_root, "set-option", "-g", "history-limit", str(scrollback_of(settings)), ";",
             "new-session", "-d", "-s", PREFIX + sid, "-x", "200", "-y", "50", "-c", where,
             "-e", f"SP_TERMINAL={sid}", "-e", "TERM=xterm-256color", shell, "-l", check=True)
        if command:
            wait_for_prompt(data_root, sid)
            type_into(data_root, row, typed_form(command, shell), enter=row["launch"] == "run")
    put(data_root, row)
    return row


def pane_pos(data_root: Path, sid: str) -> dict[str, int]:
    """Where the pane stands: how much history is above the screen, how far
    the view is scrolled up into it, the screen height, and the cursor row.
    Everything the page needs to anchor a clicked row to an absolute line."""
    out = tmux(data_root, "display-message", "-p", "-t", PREFIX + sid,
               "#{history_size}:#{scroll_position}:#{pane_height}:#{cursor_y}")
    parts = (out.stdout or "").strip().split(":")
    def n(i: int) -> int:
        try:
            return int(parts[i])
        except (IndexError, ValueError):
            return 0
    return {"history": n(0), "scroll": n(1), "rows": n(2), "cursor": n(3)}


#: More than this in one copy is a mistake, not a copy.
CAPTURE_MAX_LINES = 20_000


def capture(data_root: Path, sid: str, from_abs: int | None = None, to_abs: int | None = None) -> dict[str, Any]:
    """Text out of the pane, wrapped lines joined back into real lines.

    Absolute line ids count from the top of the pane's history (the id a
    clicked row got from ``pane_pos`` arithmetic), so a range keeps meaning
    while the view scrolls and new output streams in. Without a range: the
    visible screen. Trailing blank rows are dropped.
    """
    pos = pane_pos(data_root, sid)
    args = ["capture-pane", "-p", "-J", "-t", PREFIX + sid]
    truncated = False
    if from_abs is not None and to_abs is not None:
        a, b = sorted((int(from_abs), int(to_abs)))
        a = max(0, a)
        if b - a + 1 > CAPTURE_MAX_LINES:
            a, truncated = b - CAPTURE_MAX_LINES + 1, True
        args += ["-S", str(a - pos["history"]), "-E", str(b - pos["history"])]
    out = tmux(data_root, *args)
    text = (out.stdout or "").rstrip("\n")
    lines = text.split("\n") if text else []
    while lines and not lines[-1].strip():
        lines.pop()
    return {"text": "\n".join(lines), "lines": len(lines), "truncated": truncated}


def wait_for_prompt(data_root: Path, sid: str, timeout: float = 4.0) -> None:
    """Until the shell has printed its prompt and gone quiet (a login shell can
    print a page first) — typed sooner, the command lands before the prompt."""
    end = time.time() + timeout
    last = ""
    while time.time() < end:
        got = tmux(data_root, "capture-pane", "-p", "-t", PREFIX + sid).stdout.rstrip()
        if got and got == last and got.splitlines()[-1].rstrip().endswith(("$", "#", "%", ">", "❯")):
            return
        last = got
        time.sleep(0.15)


def type_into(data_root: Path, row: dict[str, Any], text: str, *, enter: bool, delay: float = 0.0) -> bool:
    """Type into a tmux terminal as if at the keyboard (a plain one: routers/terminal.py)."""
    if row.get("backend") != "tmux":
        return False
    if delay:
        time.sleep(delay)
    target = PREFIX + row["id"]
    # Through a paste buffer, not send-keys: tmux reads a trailing ";" in an
    # argument as a command separator and a leading "-" as an option.
    buf = f"mk-type-{row['id']}"
    load = subprocess.run(tmux_argv(data_root, "load-buffer", "-b", buf, "-"), input=text, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
    if load.returncode != 0:
        return False
    if tmux(data_root, "paste-buffer", "-d", "-b", buf, "-t", target).returncode != 0:
        return False
    if enter:
        return tmux(data_root, "send-keys", "-t", target, "Enter").returncode == 0
    return True


def close(data_root: Path, sid: str) -> None:
    row = get(data_root, sid)
    if row and row.get("backend") == "tmux":
        tmux(data_root, "kill-session", "-t", PREFIX + sid)
    forget(data_root, sid)


def attach_argv(data_root: Path, sid: str) -> list[str]:
    return tmux_argv(data_root, "attach-session", "-t", PREFIX + sid)


def alive_tmux(data_root: Path, sid: str) -> bool:
    return tmux_path() is not None and tmux(data_root, "has-session", "-t", PREFIX + sid).returncode == 0


# ---------------------------------------------------------------------------
# What runs where
# ---------------------------------------------------------------------------


def tmux_panes(data_root: Path) -> dict[str, dict[str, Any]]:
    """Every Slightly Parallel tmux session: foreground program, last print, its pid."""
    if tmux_path() is None:
        return {}
    got = tmux(data_root, "list-panes", "-a", "-F",
               "#{session_name}\t#{pane_current_command}\t#{window_activity}\t#{pane_dead}\t#{pane_pid}")
    out: dict[str, dict[str, Any]] = {}
    for line in got.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 5 or not parts[0].startswith(PREFIX):
            continue
        try:
            activity = float(parts[2])
        except ValueError:
            activity = 0.0
        out[parts[0][len(PREFIX):]] = {"fg": parts[1], "activity": activity, "dead": parts[3] == "1", "pid": parts[4]}
    return out


def agent_links(data_root: Path) -> dict[str, dict[str, Any]]:
    """terminal id → the agent the capture hook saw started in it (newest wins)."""
    global _link_cache
    now = time.time()
    if now - _link_cache[0] < 3:
        return _link_cache[1]
    out: dict[str, dict[str, Any]] = {}
    for meta_path in Path(data_root).glob("projects/*/chats/*/meta.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        tid = str(meta.get("terminal") or "")
        if not tid:
            continue
        prev = out.get(tid)
        if prev and str(prev.get("last_active") or "") >= str(meta.get("last_active") or ""):
            continue
        out[tid] = {"agent_id": meta.get("agent_id") or meta_path.parent.name, "project": meta.get("project") or "",
                    "last_active": meta.get("last_active") or "",
                    "last_stop": (meta.get("last_stop") or {}).get("at") or ""}
    _link_cache = (now, out)
    return out


AGENT_PROGRAMS = {"claude", "codex", "opencode", "aider", "gemini"}


def state_of(fg: str, activity: float, now: float, link: dict[str, Any] | None, dead: bool) -> str:
    """shell · working · waiting (an agent, your turn) · running (a quiet program) · ended."""
    if dead:
        return "ended"
    name = fg.split("/")[-1].lstrip("-") if fg else ""
    if not name or name in SHELLS:
        return "shell"
    if link and link.get("last_stop") and str(link["last_stop"]) >= str(link.get("last_active") or ""):
        # The agent finished its answer after your last message.
        return "waiting" if now - activity > 1.5 else "working"
    if now - activity < QUIET_SECONDS:
        return "working"
    # Quiet: an agent is waiting for you; a server or a sleep is only running.
    return "waiting" if (link or name in AGENT_PROGRAMS) else "running"


def listing(data_root: Path, plain: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Every terminal with its state; a tmux one that is gone is 'ended'."""
    now = time.time()
    rs = rows(data_root)
    if not rs:
        # Nothing to ask tmux about: a read must not write (its config, a folder).
        return []
    panes = tmux_panes(data_root)
    links = agent_links(data_root)
    plain = plain or {}
    out = []
    for r in rs:
        sid = r["id"]
        link = links.get(sid)
        if r.get("backend") == "tmux":
            p = panes.get(sid)
            st = state_of(p["fg"], p["activity"], now, link, p["dead"]) if p else "ended"
            fg, last = (p or {}).get("fg", ""), (p or {}).get("activity", 0.0)
        else:
            p = plain.get(sid)
            st = state_of(p["fg"], p["activity"], now, link, False) if p else "ended"
            fg, last = (p or {}).get("fg", ""), (p or {}).get("activity", 0.0)
        out.append({**r, "state": st, "program": fg, "last_output": last,
                    "agent_id": (link or {}).get("agent_id") or r.get("agent_id") or ""})
    out.sort(key=lambda x: x.get("created") or "")
    return out


_PROC = "/proc"


def foreground_of_fd(fd: int) -> str:
    """The program in the foreground of a pty: Linux's /proc, else ps
    (macOS has no /proc, and every plain terminal read as idle there)."""
    try:
        pgid = os.tcgetpgrp(fd)
    except (OSError, ValueError):
        return ""
    try:
        return Path(f"{_PROC}/{pgid}/comm").read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        pass
    try:
        out = subprocess.run(["ps", "-o", "comm=", "-p", str(pgid)], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=2).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
    return os.path.basename(out)


