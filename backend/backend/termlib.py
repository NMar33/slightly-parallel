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

On Windows every terminal is plain: the pty is a ConPTY (conpty.py, through
pywinpty) and the shell is PowerShell 7, else Windows PowerShell, else cmd.
tmux does not exist there, so nothing survives a server restart, there is no
server-side history (capture, pos, bottom answer 409 as for any plain
terminal) and Restore never offers anything. A command typed into a terminal
is built for the shell it is typed into (``family_of``).

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
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from .csvio import read_rows
from .docs_md import resolve_under
from .file_safety import FileSafetyError, acquire_flock, edit_json, lock_path, safe_read_json
from . import chatstore, termlog

log = logging.getLogger("sp.terminal")

FOLDER = "terminal"
REGISTRY = "sessions.json"
SOCKET = "sp"
OLD_SOCKET = "merkhet"  # the socket's name before the product was renamed
PREFIX = "mk-"
QUIET_SECONDS = 4            # printed nothing this long: not working any more
SHELLS = {"bash", "zsh", "sh", "fish", "dash", "ksh", "tmux", "login",
          # Windows' shells, as foreground_of_pid names them (no ".exe").
          "pwsh", "powershell", "cmd"}
#: Windows: every terminal is a plain ConPTY, and commands are built for its shell.
WINDOWS = os.name == "nt"
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
# A middle click is the page's paste (the browser pastes the selection into
# the terminal), never tmux's too: its default pastes its own buffer as well,
# and a line just copied in the terminal reached the shell twice, glued.
# A program that reads the mouse still gets the click.
bind -n MouseDown2Pane select-pane -t = \\; if -F "#{||:#{pane_in_mode},#{mouse_any_flag}}" "send -M"
# Leave the selection on screen until the operator asks to copy it. A
# program which reads the mouse still receives its own drag and clicks.
unbind -T copy-mode MouseDragEnd1Pane
unbind -T copy-mode-vi MouseDragEnd1Pane
# tmux moves to the mouse cell before a copy-mode command. Newer tmux
# freezes selection endpoints on release. Reactivate the end, then restore
# the view captured before other-end moves it so the same mouse cell names
# the same line. run-shell -C expands the view and runs only tmux commands.
bind -T copy-mode S-MouseDown1Pane if-shell -F '#{&&:#{selection_present},#{&&:#{==:#{selection_active},0},#{!=:#{copy_position},}}}' {
    run-shell -C 'send-keys -X other-end ; send-keys -X goto-line #{copy_position} ; send-keys -X rectangle-off ; send-keys -X stop-selection'
} { send-keys -X rectangle-off }
bind -T copy-mode-vi S-MouseDown1Pane if-shell -F '#{&&:#{selection_present},#{&&:#{==:#{selection_active},0},#{!=:#{copy_position},}}}' {
    run-shell -C 'send-keys -X other-end ; send-keys -X goto-line #{copy_position} ; send-keys -X rectangle-off ; send-keys -X stop-selection'
} { send-keys -X rectangle-off }
bind -T copy-mode C-c send-keys -X cancel \\; send-keys C-c
bind -T copy-mode-vi C-c send-keys -X cancel \\; send-keys C-c
bind -T copy-mode DoubleClick1Pane select-pane \\; send-keys -X select-word
bind -T copy-mode-vi DoubleClick1Pane select-pane \\; send-keys -X select-word
bind -T copy-mode TripleClick1Pane select-pane \\; send-keys -X select-line
bind -T copy-mode-vi TripleClick1Pane select-pane \\; send-keys -X select-line
bind -n DoubleClick1Pane select-pane -t = \\; if -F "#{||:#{pane_in_mode},#{mouse_any_flag}}" { send-keys -M } { copy-mode -H ; send-keys -X select-word }
bind -n TripleClick1Pane select-pane -t = \\; if -F "#{||:#{pane_in_mode},#{mouse_any_flag}}" { send-keys -M } { copy-mode -H ; send-keys -X select-line }
# The wheel over a full-screen program that does not read the mouse (less,
# man, vim without mouse=a) moves it by arrow keys, as GNOME Terminal does.
# tmux's default enters copy mode there, which has no history on that
# screen: the wheel did nothing at all. A line per wheel report; the page
# sends one report per row the wheel moved.
bind -n WheelUpPane if -F "#{||:#{pane_in_mode},#{mouse_any_flag}}" { send -M } { if -F "#{alternate_on}" { send -t = Up } { copy-mode -e } }
bind -n WheelDownPane if -F "#{||:#{pane_in_mode},#{mouse_any_flag}}" { send -M } { if -F "#{alternate_on}" { send -t = Down } }
"""

_lock = threading.Lock()
_link_cache: tuple[Path | None, float, dict[str, dict[str, Any]]] = (None, 0.0, {})


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
    """tmux, where it can hold a terminal. Never on Windows: a tmux from MSYS
    or Cygwin on the PATH cannot hold a native Windows shell."""
    return None if WINDOWS else shutil.which("tmux")


def tmux_version() -> str:
    t = tmux_path()
    if not t:
        return ""
    try:
        return subprocess.run([t, "-V"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=READ_TIMEOUT).stdout.strip()
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
                           capture_output=True, timeout=READ_TIMEOUT)
        except (OSError, subprocess.SubprocessError):
            pass
    return [tmux_path() or "tmux", "-L", socket_of(data_root), "-f", str(conf), *args]


#: How long a tmux command may take. tmux answers in milliseconds; one that
#: takes longer is a server busy dying (the last session ended, a kill-server)
#: or stuck. A read (list-panes, has-session, display-message) runs on every
#: poll of the terminal list and must not hold it: 2 s. A capture of up to
#: CAPTURE_MAX_LINES lines, and a write (new-session, send-keys, load-buffer,
#: kill-session), wait 5 s.
READ_TIMEOUT = 2.0
WRITE_TIMEOUT = 5.0
TMUX_START_ATTEMPTS = 4
TMUX_START_RETRY_STEP_S = 0.05
SHELL_PROMPT_TIMEOUT_S = 4.0
SHELL_PROMPT_POLL_INTERVAL_S = 0.15
CODEX_HELP_TIMEOUT_S = 2
FOREGROUND_PS_TIMEOUT_S = 2


class TmuxError(RuntimeError):
    """tmux did not answer in time, or could not be run. A write lets it
    reach the route, which answers 503 with this message; a read never sees
    it (tmux_read)."""


def tmux(data_root: Path, *args: str, timeout: float | None = None, input: str | None = None) -> subprocess.CompletedProcess:
    """A tmux command. A failing command comes back with its returncode; a
    tmux that does not answer in `timeout` seconds (WRITE_TIMEOUT) raises TmuxError."""
    return _tmux(data_root, args, timeout=WRITE_TIMEOUT if timeout is None else timeout, input=input)


def _tmux(data_root: Path, args: tuple[str, ...], *, timeout: float, input: str | None = None,
          read_only: bool = False) -> subprocess.CompletedProcess:
    cmd = args[0] if args else "tmux"
    t0 = time.perf_counter()
    try:
        # Reads talk to an existing server without creating or loading its config.
        argv = ([tmux_path() or "tmux", "-L", socket_of(data_root), *args]
                if read_only else tmux_argv(data_root, *args))
        out = subprocess.run(argv, input=input, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=timeout)
        termlog.REC.tmux_call(cmd, (time.perf_counter() - t0) * 1000)
        return out
    except subprocess.TimeoutExpired:
        termlog.REC.tmux_call(cmd, (time.perf_counter() - t0) * 1000, timed_out=True)
        raise TmuxError(f"tmux did not answer in {timeout:g} s ({args[0] if args else 'tmux'})") from None
    except OSError as exc:
        raise TmuxError(f"tmux could not run: {exc}") from None


def tmux_read(data_root: Path, *args: str, timeout: float | None = None) -> subprocess.CompletedProcess:
    """A tmux read that never raises: a tmux that is slow, dying or gone
    answers like a session that is not there — returncode 1, nothing on
    stdout — so the terminal list, the restore offer and a capture answer
    from the registry instead of failing."""
    try:
        return _tmux(data_root, args, timeout=READ_TIMEOUT if timeout is None else timeout, read_only=True)
    except TmuxError as exc:
        log.info("%s: read as no answer", exc)
        return subprocess.CompletedProcess(list(args), 1, "", str(exc))


#: What a tmux client says when the server it reached went away under it.
#: tmux's server quits when its last session ends; a client that connects in
#: that moment talks to a server already on its way out and exits 1.
SERVER_GOING = ("server exited unexpectedly", "lost server")


def tmux_starting(data_root: Path, *args: str, tries: int = TMUX_START_ATTEMPTS) -> subprocess.CompletedProcess:
    """A command that starts tmux's server when none runs (new-session).
    Right after the last terminal closes, the old server may still take the
    connection and then quit: the command is lost, not refused. It is sent
    again, after a moment, to the next server — at most `tries` times, and
    only for that failure; any other error is raised at once."""
    for i in range(tries):
        got = tmux(data_root, *args)
        if got.returncode == 0:
            return got
        if i == tries - 1 or not any(s in (got.stderr or "") for s in SERVER_GOING):
            break
        log.info("tmux's server was going away as a terminal opened: sent again (%s)", (got.stderr or "").strip())
        time.sleep(TMUX_START_RETRY_STEP_S * (i + 1))
    raise subprocess.CalledProcessError(got.returncode, got.args, got.stdout, got.stderr)


def scrollback_of(settings: dict[str, Any]) -> int:
    """The lines a new terminal keeps (Settings › Terminal history)."""
    try:
        return max(1000, min(200_000, int(settings.get("terminal.scrollback", 50_000))))
    except (TypeError, ValueError):
        return 50_000


#: Each colour scheme's text and ground, as the page's xterm draws them
#: (frontend/src/features/terminal/schemes.ts holds the whole scheme; a test
#: there checks these agree).
SCHEME_COLOURS: dict[str, tuple[str, str]] = {
    "sp-now": ("#E6E8EB", "#0E1013"),
    "sp-graphite": ("#D3D9D6", "#171B1E"),
    "sp-paper": ("#1F2522", "#F6F5F1"),
    "catppuccin-mocha": ("#CDD6F4", "#1E1E2E"),
    "catppuccin-latte": ("#4C4F69", "#EFF1F5"),
    "tokyo-night": ("#C0CAF5", "#1A1B26"),
    "gruvbox-dark": ("#EBDBB2", "#282828"),
    "one-dark": ("#ABB2BF", "#282C34"),
    "nord": ("#D8DEE9", "#2E3440"),
    "solarized-light": ("#657B83", "#FDF6E3"),
    "dracula": ("#F8F8F2", "#282A36"),
    "rose-pine": ("#E0DEF4", "#191724"),
}


def window_style(settings: dict[str, Any]) -> str:
    """tmux's window-style for the scheme in force: the page's text and ground.

    tmux answers a program's question for the terminal's colours (OSC 10/11)
    from an attached client only, and a terminal's program starts before the
    page attaches (an agent's command is typed while the session is born, a
    restored session has no window yet). Codex asks once, at its start, and
    draws its input box in a shade of the ground it was told; told nothing,
    it draws no box at all (tk_11bd239e). With the style set, tmux answers
    at once, for every pane, whether a page is attached or not. The pane is
    painted in the same colours the page's xterm draws, so nothing shows."""
    fg, bg = SCHEME_COLOURS.get(str(settings.get("terminal.scheme") or ""), SCHEME_COLOURS["sp-now"])
    return f"fg={fg},bg={bg}"


def apply_scheme(data_root: Path, settings: dict[str, Any]) -> None:
    """A new scheme for the terminals already open: tmux's panes (and its
    answers) take its colours. Nothing when no tmux server runs: the next
    terminal sets them as it opens."""
    if not tmux_path():
        return
    try:
        tmux(data_root, "set-option", "-g", "window-style", window_style(settings))
    except TmuxError as exc:
        log.info("the terminals' colours were not set: %s", exc)


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
        out = tmux_read(data_root, "display-message", "-p", "-t", PREFIX + str(row["id"]), "#{pane_current_path}")
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


def copy_selection(data_root: Path, sid: str) -> str | None:
    """Return the selected bytes from our buffer, even if OSC 52 is blocked."""
    prefix = f"sp-copy-{secrets.token_hex(8)}-"
    out = tmux(data_root, "if-shell", "-F", "-t", PREFIX + sid, "#{selection_present}",
               f"send-keys -X copy-selection-and-cancel {prefix} ; display-message -p copied")
    if out.returncode != 0:
        raise TmuxError((out.stderr or "").strip() or "tmux selection could not be copied")
    if out.stdout.strip() != "copied":
        return None
    buffers = tmux(data_root, "list-buffers", "-F", "#{buffer_name}")
    name = next((line for line in buffers.stdout.splitlines() if line.startswith(prefix)), None)
    if not name:
        raise TmuxError("tmux did not save the copied selection")
    contents = tmux(data_root, "save-buffer", "-b", name, "-")
    if contents.returncode != 0:
        raise TmuxError((contents.stderr or "").strip() or "tmux selection could not be read")
    return contents.stdout


def cancel_selection(data_root: Path, sid: str) -> None:
    """Leave copy mode if it currently holds a selection."""
    out = tmux(data_root, "if-shell", "-F", "-t", PREFIX + sid, "#{selection_present}",
               "send-keys -X cancel")
    if out.returncode != 0:
        raise TmuxError((out.stderr or "").strip() or "tmux selection could not be cancelled")


def uses_tmux(settings: dict[str, Any]) -> bool:
    # False on Windows whatever the setting says: tmux_path() is None there.
    return settings.get("terminal.keep", "tmux") == "tmux" and tmux_path() is not None


# ---------------------------------------------------------------------------
# The shell a terminal runs, and the family its commands are written for
# ---------------------------------------------------------------------------

#: How commands are quoted: bash ($'…'), PowerShell, or cmd.
FAMILIES = ("bash", "powershell", "cmd")


def windows_shell(which=shutil.which, env: Mapping[str, str] | None = None) -> list[str]:
    """The shell a Windows terminal runs, as argv: PowerShell 7 (pwsh), else
    Windows PowerShell, else cmd (%ComSpec%). Its output is UTF-8: PowerShell
    sets its console encodings at start, cmd switches to code page 65001.
    There is no setting for it: $SHELL on Windows is Git Bash's, a Unix path."""
    env = os.environ if env is None else env
    for name in ("pwsh", "powershell"):
        exe = which(name)
        if exe:
            # A bare string (no quotes, no $ the command line could take):
            # -EncodedCommand is UTF-16LE base64, as PowerShell documents.
            utf8 = ("$OutputEncoding = [Console]::InputEncoding = [Console]::OutputEncoding"
                    " = New-Object System.Text.UTF8Encoding $false")
            packed = base64.b64encode(utf8.encode("utf-16-le")).decode("ascii")
            return [exe, "-NoLogo", "-NoExit", "-EncodedCommand", packed]
    comspec = env.get("ComSpec") or env.get("COMSPEC") or which("cmd") or "cmd.exe"
    return [comspec, "/K", "chcp 65001>nul"]


def plain_shell() -> list[str]:
    """argv of the shell a plain terminal runs on this system."""
    if WINDOWS:
        return windows_shell()
    return [os.environ.get("SHELL") or "bash", "-l"]


def family_of(shell: str) -> str:
    """The quoting family of a shell, by its program name."""
    name = Path(shell or "bash").name.lower().replace("\\", "/").rsplit("/", 1)[-1]
    name = name[:-4] if name.endswith(".exe") else name
    if name in ("pwsh", "powershell"):
        return "powershell"
    if name == "cmd":
        return "cmd"
    return "bash"


def command_family() -> str:
    """The family the terminals' commands are built for here: bash on macOS
    and Linux (typed_form hands a command to bash in other shells), the
    shell's own on Windows, where there is no bash to hand it to."""
    return family_of(plain_shell()[0]) if WINDOWS else "bash"


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


#: The longest text one argument carries on Windows: cmd.exe takes a command
#: line of 8191 characters, and an npm-installed agent is a .cmd that cmd runs.
WINDOWS_ARG_MAX = 7000


def windows_arg_text(text: str) -> str:
    """Text that stays one argument on its way through PowerShell or cmd to a
    Windows program, and through cmd again when that program is a .cmd (an
    npm-installed claude or codex). Control characters are dropped, a line
    break or tab becomes a space (a newline ends a cmd line), a double quote
    becomes a single one (Windows PowerShell and a .cmd both split an
    argument at an inner "), and % becomes the full-width ％ (cmd expands
    %NAME% even inside quotes). Cut at WINDOWS_ARG_MAX, and without a
    trailing backslash, which would escape the quote a program's command
    line closes the argument with."""
    text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").replace("\t", " ")
    text = re.sub(r"[\x00-\x1f\x7f]", "", text)
    text = text.replace('"', "'").replace("%", "\uff05")
    return text[:WINDOWS_ARG_MAX].rstrip("\\")


def ps_quote(text: str, *, literal: bool = False) -> str:
    """One PowerShell argument holding `text`: single quotes, where nothing is
    expanded and a quote is written twice (PowerShell also reads the curly
    single quotes as quotes). `literal`: a path, kept as it is otherwise."""
    body = text if literal else windows_arg_text(text)
    return "'" + re.sub("['\u2018\u2019\u201a\u201b]", lambda m: m.group(0) * 2, body) + "'"


def cmd_quote(text: str, *, literal: bool = False) -> str:
    """One cmd argument holding `text`: double quotes, inside which & | < > ^
    are plain characters; windows_arg_text took out the " and % that could
    still act. `literal`: a path (a Windows path has no ")."""
    return '"' + (text.replace('"', "") if literal else windows_arg_text(text)) + '"'


def quote_for(family: str, text: str) -> str:
    """`text` as one argument of a command in `family`."""
    if family == "powershell":
        return ps_quote(text)
    if family == "cmd":
        return cmd_quote(text)
    return ansi_quote(text)


def ansi_quote(text: str) -> str:
    """One line of bash that holds any text: $'…' with the escapes spelled.
    Other control characters are dropped: typed, ESC or ^U act as keys."""
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)
    body = (text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
            .replace("\r", "").replace("\t", "\\t"))
    return f"$'{body}'"


@lru_cache(maxsize=8)
def _codex_has_no_daemon(exe: str) -> bool:
    try:
        got = subprocess.run([exe, "--help"], capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=CODEX_HELP_TIMEOUT_S, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return got.returncode == 0 and bool(re.search(r"^\s+--no-daemon\b", got.stdout, re.MULTILINE))


def codex_in_terminal() -> str:
    """Keep Codex hooks in the calling terminal's environment when the CLI supports it."""
    exe = shutil.which("codex")
    return "codex --no-daemon" if exe and _codex_has_no_daemon(exe) else "codex"


def resume_command(tool: str, session_ref: str) -> str:
    # A ref starting with "-" would be read as an option of the tool.
    if not session_ref or not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$", session_ref):
        return ""
    if tool == "claude-code":
        return f"claude -r {session_ref}"
    if tool == "codex":
        return f"{codex_in_terminal()} resume {session_ref}"
    if tool == "opencode":
        return f"opencode --session {session_ref}"
    return ""


#: The longest first prompt a fork command carries: one argument of a
#: command line is at most 128 KiB on Linux.
FORK_PROMPT_MAX = 100_000


def fork_command(tool: str, session_ref: str, cwd: str, prompt: str, family: str | None = None) -> str:
    """The command that starts a copy of a chat with ``prompt`` as its first
    message, in the chat's folder: Claude Code resumes the session into a
    new one (``--fork-session``), Codex forks it (``codex fork``). "" for a
    tool that cannot, or a chat with no session or folder known. The server
    never runs it: the operator copies it, or the page types it into a
    terminal — so it is written for the terminals' shell (``family``)."""
    if not cwd or not prompt.strip() or not session_ref \
            or not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$", session_ref):
        return ""
    family = family or command_family()
    q = quote_for(family, prompt if family != "bash" else prompt[:FORK_PROMPT_MAX])
    if tool == "claude-code":
        run = f"claude -r {session_ref} --fork-session {q}"
    elif tool == "codex":
        run = f"{codex_in_terminal()} fork {session_ref} {q}"
    else:
        return ""
    if family == "powershell":
        # Windows PowerShell 5.1 has no &&: the run waits on Set-Location's success.
        return f"Set-Location -LiteralPath {ps_quote(cwd, literal=True)}; if ($?) {{ {run} }}"
    if family == "cmd":
        return f"cd /d {cmd_quote(cwd, literal=True)} && {run}"
    return f"cd {shlex.quote(cwd)} && {run}"


def task_prompt(task: dict[str, Any]) -> str:
    title = str(task.get("title") or "").strip()
    desc = str(task.get("description") or "").strip()
    head = f"Work on the Slightly Parallel task {task.get('id')} · {title}."
    body = f"{head}\n\n{desc[:3000]}" if desc else head
    return body


def start_command(tool: str, task: dict[str, Any], family: str | None = None) -> str:
    """The command that starts `tool` on a task, written for the terminals'
    shell (``family``; bash on macOS and Linux)."""
    q = quote_for(family or command_family(), task_prompt(task))
    if tool == "codex":
        return f"{codex_in_terminal()} {q}"
    if tool == "opencode":
        return f"opencode --prompt {q}"
    return f"claude {q}"


def typed_form(command: str, shell: str) -> str:
    """`command` as it is typed into `shell`. The commands built above use
    bash's ``$'…'`` quoting, and a task's text is inside them: typed as they
    are into another shell, a quote in that text would end the string and
    the rest would run. bash and zsh read it as written; a POSIX shell hands
    it to bash in one quoted word; any other shell (fish, nu — their quoting
    rules differ) gets it as base64, which holds nothing to quote.

    On Windows a command was built for the shell it goes into (start_command
    and fork_command quote for PowerShell or cmd there): typed as it is."""
    if WINDOWS:
        return command
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
                 sid: str = "", role: str = "", group: str = "") -> dict[str, Any]:
    """A new terminal: its row, and — with tmux — the session, running `command`."""
    if command == "codex":
        command = codex_in_terminal()
    sid = sid if sid and SAFE_ID.match(sid) else new_id()
    where = str(resolve_cwd(data_root, project, cwd))
    backend = "tmux" if uses_tmux(settings) else "plain"
    # `created` orders the tabs (and alt+1…9). To the millisecond: two
    # terminals opened in the same second tied, the page broke the tie by
    # their random ids, and a new tab came first or second by chance.
    now = time.time()
    row = {
        "id": sid, "kind": kind, "label": label or (project or "shell"), "project": project,
        "cwd": where, "command": command, "agent_id": agent_id, "task_id": task_id,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now)) + f".{int(now * 1000) % 1000:03d}",
        "backend": backend,
        "launch": settings.get("terminal.launch", "run"),
    }
    if role in ROLES:
        row["role"] = role
    if group:
        row["group"] = group
    if backend == "tmux":
        shell = os.environ.get("SHELL") or "bash"
        # The history length is set just before the pane is made: tmux gives
        # a pane the limit in force when it is born, and keeps it.
        # The scheme's colours too, before the shell is born: its programs
        # learn the terminal's ground from tmux (window_style).
        tmux_starting(data_root, "set-option", "-g", "history-limit", str(scrollback_of(settings)), ";",
                      "set-option", "-g", "window-style", window_style(settings), ";",
                      "new-session", "-d", "-s", PREFIX + sid, "-x", "200", "-y", "50", "-c", where,
                      "-e", f"SP_TERMINAL={sid}", "-e", "TERM=xterm-256color", shell, "-l")
        if command:
            wait_for_prompt(data_root, sid)
            type_into(data_root, row, typed_form(command, shell), enter=row["launch"] == "run")
        # Which tmux server holds it: a terminal whose server is gone was not
        # closed by anyone (a reboot, a crash), and Restore offers it back.
        row["server"] = tmux_server_pid(data_root)
    # Awake again, whatever it was: sleep() and a restore go through here.
    row["asleep"] = False
    return put(data_root, row)


def pane_pos(data_root: Path, sid: str) -> dict[str, int]:
    """Where the pane stands: how much history is above the screen, how far
    the view is scrolled up into it, the screen height, and the cursor row.
    Everything the page needs to anchor a clicked row to an absolute line."""
    out = tmux_read(data_root, "display-message", "-p", "-t", PREFIX + sid,
                    "#{history_size}:#{scroll_position}:#{pane_height}:#{cursor_y}"
                    ":#{pane_width}:#{alternate_on}:#{mouse_any_flag}:#{pane_in_mode}:#{selection_present}")
    parts = (out.stdout or "").strip().split(":")
    def n(i: int) -> int:
        try:
            return int(parts[i])
        except (IndexError, ValueError):
            return 0
    # What the wheel should do in the page (Screen.tsx): a full-screen program
    # (alt) or one that reads the mouse gets it; otherwise the history scrolls.
    return {"history": n(0), "scroll": n(1), "rows": n(2), "cursor": n(3), "cols": n(4),
            "alt": bool(n(5)), "mouse": bool(n(6)), "in_mode": bool(n(7)), "selecting": bool(n(8))}


#: The most rows the page's reader asks for at once (about 0.4 s and 5 MB at 50 000).
HISTORY_MAX_ROWS = 50_000


def history_rows(data_root: Path, sid: str, rows: int) -> dict[str, Any]:
    """The last ``rows`` rows of the pane's history and its screen, as tmux
    shows them: one row per line (wrapped lines stay wrapped, so they line up
    with the page's own rows), colours kept (escape sequences). The page's
    smooth reader draws them in an xterm of its own and scrolls by pixels.
    ``history`` is the history above the screen at that moment: row i of the
    answer is absolute line ``history - (rows above the screen) + i``."""
    pos = pane_pos(data_root, sid)
    want = max(0, min(int(rows), HISTORY_MAX_ROWS, pos["history"]))
    out = tmux_read(data_root, "capture-pane", "-p", "-e", "-t", PREFIX + sid, "-S", str(-want), "-E", str(pos["rows"] - 1),
                    timeout=WRITE_TIMEOUT)
    text = out.stdout or ""
    if text.endswith("\n"):
        text = text[:-1]
    return {**pos, "text": text, "above": want, "complete": want >= pos["history"]}


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
    out = tmux_read(data_root, *args, timeout=WRITE_TIMEOUT)  # up to CAPTURE_MAX_LINES lines
    text = (out.stdout or "").rstrip("\n")
    lines = text.split("\n") if text else []
    while lines and not lines[-1].strip():
        lines.pop()
    return {"text": "\n".join(lines), "lines": len(lines), "truncated": truncated}


def wait_for_prompt(data_root: Path, sid: str, timeout: float = SHELL_PROMPT_TIMEOUT_S) -> None:
    """Until the shell has printed its prompt and gone quiet (a login shell can
    print a page first) — typed sooner, the command lands before the prompt."""
    end = time.time() + timeout
    last = ""
    while time.time() < end:
        got = tmux_read(data_root, "capture-pane", "-p", "-t", PREFIX + sid).stdout.rstrip()
        if got and got == last and got.splitlines()[-1].rstrip().endswith(("$", "#", "%", ">", "❯")):
            return
        last = got
        time.sleep(SHELL_PROMPT_POLL_INTERVAL_S)



# All SP writers of a tmux session share its input lock. Intent is recorded
# before the lock wait, so the automatic sender gives the operator priority.
_input_state_lock = threading.Lock()
_operator_waiters: dict[tuple[Path, str], int] = {}
_sp_clients: dict[tuple[Path, str], set[int]] = {}


def input_lock(data_root: Path, sid: str) -> Path:
    return lock_path(folder(data_root) / ("deliver-" + sid))


@contextmanager
def operator_intent(data_root: Path, sid: str) -> Iterator[None]:
    key = (data_root, sid)
    with _input_state_lock:
        _operator_waiters[key] = _operator_waiters.get(key, 0) + 1
    try:
        yield
    finally:
        with _input_state_lock:
            if _operator_waiters[key] == 1:
                del _operator_waiters[key]
            else:
                _operator_waiters[key] -= 1


def operator_waiting(data_root: Path, sid: str) -> bool:
    with _input_state_lock:
        return bool(_operator_waiters.get((data_root, sid)))


def register_client(data_root: Path, sid: str, pid: int) -> Callable[[], None]:
    """Identify only the tmux child actually created for a server-owned view."""
    key = (data_root, sid)
    with _input_state_lock:
        _sp_clients.setdefault(key, set()).add(pid)

    def release() -> None:
        with _input_state_lock:
            clients = _sp_clients[key]
            clients.remove(pid)
            if not clients:
                del _sp_clients[key]

    return release


def owns_clients(data_root: Path, sid: str, pids: set[int]) -> bool:
    with _input_state_lock:
        return pids <= _sp_clients.get((data_root, sid), set())


def write_operator(data_root: Path, sid: str, write: Callable[[bytes], None], data: bytes) -> None:
    try:
        with acquire_flock(input_lock(data_root, sid)):
            write(data)
    except FileSafetyError as exc:
        raise TmuxError("terminal input is busy") from exc



def type_into(data_root: Path, row: dict[str, Any], text: str, *, enter: bool, delay: float = 0.0) -> bool:
    """Type into a tmux terminal as if at the keyboard (a plain one: routers/terminal.py)."""
    if row.get("backend") != "tmux":
        return False
    if delay:
        time.sleep(delay)
    sid = row["id"]
    with operator_intent(data_root, sid):
        try:
            with acquire_flock(input_lock(data_root, sid)):
                return _type_into_locked(data_root, sid, text, enter)
        except FileSafetyError as exc:
            raise TmuxError("terminal input is busy") from exc


def _type_into_locked(data_root: Path, sid: str, text: str, enter: bool) -> bool:
    target = PREFIX + sid
    # Through a paste buffer, not send-keys: tmux reads a trailing ";" in an
    # argument as a command separator and a leading "-" as an option.
    buf = f"mk-type-{sid}"
    load = tmux(data_root, "load-buffer", "-b", buf, "-", input=text)
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
    return tmux_path() is not None and tmux_read(data_root, "has-session", "-t", PREFIX + sid).returncode == 0


# ---------------------------------------------------------------------------
# Roles, sleep, restore, groups, typing
# ---------------------------------------------------------------------------

#: What a terminal is for: an agent's chat, a local server kept apart from
#: the chats, or a plain shell.
ROLES = ("chat", "server", "shell")
GROUPS = "groups.json"
TYPING = "typing.csv"


def role_of(row: dict[str, Any]) -> str:
    role = str(row.get("role") or "")
    if role in ROLES:
        return role
    return "chat" if row.get("kind") in ("resume", "start") or row.get("agent_id") else "shell"


def tmux_server_pid(data_root: Path) -> str:
    """The pid of Slightly Parallel's tmux server, "" when none runs."""
    exe = tmux_path()
    if exe is None:
        return ""
    # Asked without the config file: a read writes nothing, and with no
    # server running tmux answers an error instead of starting one.
    try:
        got = subprocess.run([exe, "-L", socket_of(data_root), "display-message", "-p", "#{pid}"],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=READ_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return ""
    return got.stdout.strip() if got.returncode == 0 else ""


def wake_command(row: dict[str, Any], resume: str = "") -> str:
    """What a terminal runs when it comes back. An agent's chat resumes its
    session (`resume`, worked out by the caller from the chat's record); a
    server runs its command again; a plain shell comes back empty — its
    one-off command is not repeated, and a terminal that started an agent on
    a task never starts a second one."""
    if resume:
        return resume
    if row.get("kind") == "resume":
        return str(row.get("command") or "")
    if role_of(row) == "server":
        return str(row.get("command") or "")
    return ""


def sleep(data_root: Path, sid: str, wake: str) -> dict[str, Any] | None:
    """Stop what runs in the terminal and keep its row: `wake` is what it
    runs when woken. The tmux session is killed; the caller drops a plain pty."""
    row = get(data_root, sid)
    if row is None:
        return None
    if row.get("backend") == "tmux":
        tmux(data_root, "kill-session", "-t", PREFIX + sid)
    return put(data_root, {"id": sid, "asleep": True, "wake": wake,
                           "slept_at": time.strftime("%Y-%m-%dT%H:%M:%S")})


def wake(data_root: Path, settings: dict[str, Any], sid: str, command: str | None = None) -> dict[str, Any] | None:
    """The terminal again, under its own id, running `command` (default: what
    sleep() kept). Its label, role, group, agent and task stay."""
    row = get(data_root, sid)
    if row is None:
        return None
    if row.get("backend") == "tmux" and alive_tmux(data_root, sid):
        return put(data_root, {"id": sid, "asleep": False})
    cmd = str(row.get("wake") or "") if command is None else command
    created = row.get("created")
    cwd = str(row.get("cwd") or "")
    if cwd and not Path(cwd).is_dir():
        cwd = ""  # the folder is gone: the project's folder, or home
    out = open_session(data_root, settings, kind=str(row.get("kind") or "shell"), project=str(row.get("project") or ""),
                       cwd=cwd, command=cmd, label=str(row.get("label") or ""),
                       agent_id=str(row.get("agent_id") or ""), task_id=str(row.get("task_id") or ""), sid=sid)
    # The command a terminal was opened with stays its own; what woke it is `wake`.
    # A plain terminal types `wake` when its new shell starts (routers/terminal.py
    # _pending): not typed yet. Before, it kept `typed` from its first life and a
    # woken chat came back as an empty shell.
    now = time.time()
    woken_at = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now)) + f".{int(now * 1000) % 1000:03d}"
    return put(data_root, {"id": sid, "created": created or out.get("created"),
                           "command": row.get("command") or "", "wake": cmd, "typed": False,
                           "woken_at": woken_at})


def lost(items: list[dict[str, Any]], server_pid: str) -> list[dict[str, Any]]:
    """Terminals that ended without anyone ending them: their tmux server is
    not the one running now (the computer restarted, tmux was killed). One
    put to sleep is not lost; one whose shell was left with `exit` under the
    server still running is not either, and neither is one from before the
    server was recorded (nobody can tell how that one ended)."""
    return [x for x in items if x.get("state") == "ended" and not x.get("asleep")
            and x.get("backend") == "tmux" and x.get("server") and str(x["server"]) != server_pid]


def groups(data_root: Path) -> list[dict[str, Any]]:
    p = Path(data_root) / FOLDER / GROUPS
    if not p.exists():
        return []
    try:
        data = safe_read_json(p)
    except (OSError, ValueError):
        return []
    return [g for g in (data.get("groups") if isinstance(data, dict) else []) or [] if isinstance(g, dict)]


def _edit_groups(data_root: Path, change) -> Any:
    out: list[Any] = []

    def apply(doc: Any) -> dict:
        doc = doc if isinstance(doc, dict) else {}
        gs = [g for g in doc.get("groups") or [] if isinstance(g, dict)]
        out.append(change(gs))
        return {"groups": gs}

    edit_json(folder(data_root) / GROUPS, apply)
    return out[0] if out else None


def group_put(data_root: Path, gid: str, name: str | None = None, color: int | None = None,
              *, project: str | None = None) -> dict[str, Any] | None:
    """Create or edit a terminal group. A project scope is set at creation.

    Groups without a scope are custom workspaces spanning projects.
    """
    def change(gs: list[dict[str, Any]]) -> dict[str, Any] | None:
        for g in gs:
            if g.get("id") == gid:
                if name is not None:
                    g["name"] = name
                if color is not None:
                    g["color"] = color
                return g
        if gid:
            return None
        g = {"id": "g" + secrets.token_hex(4), "name": name or f"Group {len(gs) + 1}",
             "color": color or (len(gs) % 8) + 1, "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
        if project is not None:
            g["project"] = project
        gs.append(g)
        return g
    return _edit_groups(data_root, change)


def group_remove(data_root: Path, gid: str) -> bool:
    """The group goes; its terminals return to their projects."""
    def change(gs: list[dict[str, Any]]) -> bool:
        n = len(gs)
        gs[:] = [g for g in gs if g.get("id") != gid]
        return len(gs) < n
    gone = bool(_edit_groups(data_root, change))

    def clear(sessions: list[dict[str, Any]]) -> None:
        for r in sessions:
            if r.get("group") == gid:
                r["group"] = ""
    if gone and rows(data_root):
        _edit(data_root, clear)
    return gone


def _selected_tabs(sessions: list[dict[str, Any]], tabs: set[str], project: str) -> list[dict[str, Any]]:
    selected = [s for s in sessions if s.get("id") in tabs]
    if len(selected) != len(tabs):
        raise ValueError("a selected terminal is no longer open")
    if any((s.get("project") or "") != project for s in selected):
        raise ValueError("select tabs from a single project")
    return selected


def set_tab_groups(data_root: Path, tabs: set[str], project: str, group: str) -> None:
    """Validate the entire selection before changing any of its memberships."""
    def change(sessions: list[dict[str, Any]]) -> None:
        for session in _selected_tabs(sessions, tabs, project):
            session["group"] = group

    _edit(data_root, change)


def group_selected_tabs(data_root: Path, tabs: set[str], project: str, name: str | None,
                        color: int | None) -> dict[str, Any]:
    """Create a group only after checking its selection under the session registry lock."""
    created: dict[str, Any] | None = None

    def change(sessions: list[dict[str, Any]]) -> dict[str, Any]:
        nonlocal created
        selected = _selected_tabs(sessions, tabs, project)
        created = group_put(data_root, "", name, color, project=project)
        assert created is not None
        for session in selected:
            session["group"] = created["id"]
        return created

    try:
        return _edit(data_root, change)
    except OSError:
        if created is not None:
            group_remove(data_root, created["id"])
        raise


#: What a terminal (xterm in the page) sends for itself, not for the operator:
#: mouse reports (SGR, urxvt, X10), focus in/out, its answers to a program's
#: questions — device attributes, cursor and status reports, mode reports,
#: window sizes, colours (OSC) and DCS replies. tmux with `mouse on` turns a
#: click into two of these, and attaching asks for the attributes and colours.
_REPLY = (
    r"\x1b\[<\d+;\d+;\d+[Mm]"            # SGR mouse
    r"|\x1b\[\d+;\d+;\d+M"               # urxvt mouse
    r"|\x1b\[M[\x20-\U0010ffff]{3}"      # X10 mouse
    r"|\x1b\[[IO]"                       # focus in / out
    r"|\x1b\[[?>=][\d;]*c"               # device attributes
    r"|\x1b\[\??\d+;\d+(?:;\d+)?R"       # cursor position (a modified F3 looks the same: the page marks keys)
    r"|\x1b\[\??\d*n"                    # status report
    r"|\x1b\[\??[\d;]*\$y"               # mode report
    r"|\x1b\[\d+(?:;\d+)*t"              # window size
    r"|\x1b\[\?\d*u"                     # keyboard flags
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC answer (colours)
    r"|\x1bP[^\x1b]*\x1b\\"              # DCS answer
)
_REPLIES_ONLY = re.compile(f"(?:{_REPLY})+")


def is_terminal_reply(data: str | bytes) -> bool:
    """Is this input only the terminal's own reports and replies, with no key
    the operator typed in it? Then it is not typing. The page marks its
    input (`typed`); this is for a message that does not say."""
    if isinstance(data, bytes):
        data = data.decode("utf-8", "replace")
    return bool(data) and _REPLIES_ONLY.fullmatch(data) is not None


def note_typing(data_root: Path, row: dict[str, Any], keys: int) -> None:
    """One line per report: when the operator typed into which terminal, and
    how many keys. Counts only — what was typed is never kept."""
    p = folder(data_root) / TYPING
    new = not p.exists()
    with p.open("a", encoding="utf-8", newline="") as f:
        if new:
            f.write("at,terminal,project,agent_id,keys\n")
        f.write(",".join([time.strftime("%Y-%m-%dT%H:%M:%S"), str(row.get("id") or ""),
                          str(row.get("project") or ""), str(row.get("agent_id") or ""), str(keys)]) + "\n")


def typing_minutes(data_root: Path, day: str) -> dict[str, int]:
    """project → minutes of `day` (YYYY-MM-DD) in which the operator typed."""
    p = Path(data_root) / FOLDER / TYPING
    if not p.exists():
        return {}
    seen: dict[str, set[str]] = {}
    for line in p.read_text(encoding="utf-8").splitlines()[1:]:
        parts = line.split(",")
        if len(parts) >= 5 and parts[0].startswith(day):
            seen.setdefault(parts[2], set()).add(parts[0][:16])
    return {k: len(v) for k, v in seen.items()}


# ---------------------------------------------------------------------------
# What runs where
# ---------------------------------------------------------------------------


def tmux_panes(data_root: Path) -> dict[str, dict[str, Any]]:
    """Every Slightly Parallel tmux session: foreground program, last print, its pid."""
    if tmux_path() is None:
        return {}
    got = tmux_read(data_root, "list-panes", "-a", "-F",
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


def _codex_in_pane(root: Path, agent: str, tid: str, panes: dict[str, dict[str, Any]]) -> bool:
    """A Codex chat runs in this terminal: the processes above its hook
    include the pane's shell (msgdeliver.occupant_why, the proof messages
    are typed by). A Codex chat's ``terminal`` is only a claim: Codex 0.170
    runs every chat's hooks in one app-server daemon, which keeps the
    SP_TERMINAL of the terminal it was started from, so every Codex chat
    named that one (tk_49aa81aa). No pane, or no proof: no link."""
    from . import msgdeliver  # it imports this module
    try:
        pane_pid = int((panes.get(tid) or {}).get("pid") or 0)
    except ValueError:
        return False
    return bool(pane_pid) and msgdeliver.occupant_why(root, agent, pane_pid) == ""


def agent_links(data_root: Path) -> dict[str, dict[str, Any]]:
    """terminal id → the agent the capture hook saw started in it (newest
    wins); a Codex chat only when it is proven to run in it (_codex_in_pane)."""
    global _link_cache
    root = Path(data_root)
    now = time.monotonic()
    cached_root, cached_at, cached_links = _link_cache
    if cached_root == root and now - cached_at < 3:
        return cached_links
    out: dict[str, dict[str, Any]] = {}
    panes: dict[str, dict[str, Any]] | None = None
    for _p, _a, chat in chatstore.iter_chats(root, has="meta.json", sort=False):
        meta_path = chat / "meta.json"
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        tid = str(meta.get("terminal") or "")
        if not tid:
            continue
        agent = str(meta.get("agent_id") or meta_path.parent.name)
        if meta.get("tool") == "codex" or agent.startswith("codex-"):
            if panes is None:
                panes = tmux_panes(root)
            if not _codex_in_pane(root, agent, tid, panes):
                continue
        prev = out.get(tid)
        if prev and str(prev.get("last_active") or "") >= str(meta.get("last_active") or ""):
            continue
        out[tid] = {"agent_id": agent, "project": meta.get("project") or "",
                    "last_active": meta.get("last_active") or "",
                    "last_stop": (meta.get("last_stop") or {}).get("at") or ""}
    _link_cache = (root, now, out)
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
        if st == "ended" and r.get("asleep"):
            st = "asleep"
        out.append({**r, "role": role_of(r), "state": st, "program": fg, "last_output": last,
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
                             encoding="utf-8", errors="replace", timeout=FOREGROUND_PS_TIMEOUT_S).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
    return os.path.basename(out)


#: A console host is a ConPTY's helper, not a program the operator runs.
_HOSTS = {"conhost", "openconsole"}


def foreground_of_pid(pid: int) -> str:
    """Windows has no foreground process group: the program a plain terminal
    runs is read from its shell's process tree instead — the newest process
    at the bottom of it (``claude`` under ``pwsh``; a build's last child),
    the shell itself when it has no children. "" when the shell is gone.
    It names what runs, not what holds the keyboard: a program left running
    in the background with ``Start-Process -NoNewWindow`` counts as running."""
    try:
        import psutil
    except ImportError:  # pragma: no cover — psutil is a backend dependency
        return ""

    def name_of(p: Any) -> str:
        n = os.path.basename(p.name() or "")
        return n[:-4] if n.lower().endswith(".exe") else n

    try:
        here = psutil.Process(pid)
        for _ in range(16):  # a chain of shells is short; a loop is never infinite
            kids = [k for k in here.children() if name_of(k).lower() not in _HOSTS]
            if not kids:
                return name_of(here)
            here = max(kids, key=lambda k: k.create_time())
    except (psutil.Error, OSError):
        return ""
    return name_of(here)
