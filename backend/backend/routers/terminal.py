"""Terminals — a real shell in Slightly Parallel's pages (termlib.py holds the model).

Security model: a terminal runs a shell on this computer, so

- it is **off** until the operator switches it on (setting
  ``terminal.enabled``, one click in the drawer; ``SP_ENABLE_TERMINAL``
  still forces it on);
- every socket must carry the token, and the token is handed out only to
  Slightly Parallel's own pages: ``GET /api/terminal/state`` refuses a request whose
  ``Origin`` is not one of Slightly Parallel's, or that a browser marks cross-site.
  The server makes the token at every start; nobody
  types it;
- a WebSocket carries no CORS, so the socket checks the Origin itself — any
  other page the operator visits cannot open one.

Routes:

- ``GET  /api/terminal/state`` — on or off, the token, tmux, the settings.
- ``GET  /api/terminal/sessions?project=`` — every terminal with its state
  (shell · working · waiting · ended), program and agent.
- ``POST /api/terminal/sessions`` — open one: ``{kind: shell|resume|start,
  project, cwd?, agent?, task_id?, label?, command?}``. Resume and start
  build their command here, from the agent's chat and the task.
- ``POST /api/terminal/sessions/{id}/type`` ``{text, enter}`` · ``/rename``
  ``{label}`` · ``/close``.
- ``WS   /ws/terminal/{id}?token=&project=&cols=&rows=`` — the screen.

The pty: a Unix pty (``PtySession``) on macOS and Linux; on Windows a ConPTY
through pywinpty (``WinPtySession``, conpty.py), plain terminals only.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import re
import secrets
import signal
import struct
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool

from .. import app_settings, conpty, termlib, timeauto
from ..config import Settings
from ..db import ViewStore
from .deps import foreign_origin, get_store, not_found, operator_only, to_int

log = logging.getLogger("sp.terminal")

# The folder rule moved to termlib; the old name stays for its callers.
resolve_terminal_cwd = termlib.resolve_cwd

_MAX_SESSIONS = 32
# What a terminal asks the screen (who are you, where is the cursor): kept
# out of a replay, or the new screen answers into the shell as if typed.
_QUERIES = re.compile(rb"\x1b\[[>=?]?[0-9;]*c|\x1b\[[56]n")
_REPLAY_BYTES = 65_536
_BUFFER_BYTES = 131_072


# A terminal is a Unix pty on macOS and Linux, a ConPTY on Windows (pywinpty,
# installed there by requirements.txt). Without it the server still starts
# (every other page works), and the terminal says what to install.
if os.name == "nt":  # pragma: no cover — Windows
    SUPPORTED = conpty.available()
    UNSUPPORTED = conpty.MISSING
else:
    import fcntl
    import pty
    import termios
    SUPPORTED = True
    UNSUPPORTED = ""
#: The socket's close reason when there is no terminal here (4403).
UNSUPPORTED_WS = "the terminal needs pywinpty"

#: The pty's size limits: a Unix winsize and a Windows COORD are 16-bit.
_MAX_ROWS, _MAX_COLS = 500, 1000


def _size(cols: int, rows: int) -> tuple[int, int]:
    return min(max(cols, 1), _MAX_COLS), min(max(rows, 1), _MAX_ROWS)


# The pumps' own threads. Each open terminal holds one in a blocking read for
# as long as it lives; in the default executor about eight idle terminals
# took every thread asyncio.to_thread uses, and the server stalled.
# Sized from the caps below: every plain terminal and every tmux view can
# hold one read at once.
_PTY_READS = ThreadPoolExecutor(max_workers=_MAX_SESSIONS * 5, thread_name_prefix="pty")

# Set by build_router: closes every pty the router holds. Called at
# shutdown, so no thread is left blocked in a read of a shell still open
# (the pool joins its threads at exit, and the server would hang there).
# The pool itself stays: a test client starts and stops the app many
# times in one process, and a pump must still find a thread afterwards.
_close_all: "Callable[[], None] | None" = None


def close_all() -> None:
    if _close_all is not None:
        _close_all()


async def _read_pty(fd: int) -> bytes:
    """The next output of a pty, read on the pumps' own threads."""
    return await asyncio.get_running_loop().run_in_executor(_PTY_READS, os.read, fd, 8192)


async def _read_session(session: "PtySession") -> bytes:
    """The next output of a terminal (either kind of pty), on the pumps' threads."""
    return await asyncio.get_running_loop().run_in_executor(_PTY_READS, session.read_chunk)


class PtySession:
    """One pty the server holds: a shell (plain) or a tmux client (tmux)."""

    def __init__(self, session_id: str, argv: list[str], cwd: str, cols: int, rows: int, env: dict[str, str]):
        self.session_id = session_id
        # Built before the fork: the child of a threaded server only chdirs
        # and execs, it does not touch os.environ.
        full_env = {**os.environ, **env}
        pid, fd = pty.fork()
        if pid == 0:  # child
            try:
                os.chdir(cwd)
            except OSError:
                pass
            try:
                os.execvpe(argv[0], argv, full_env)
            finally:
                # The exec failed (no such shell, no tmux): this child is a copy
                # of the server and must end here, whatever happened.
                os._exit(127)
        self.pid = pid
        self.fd = fd
        self.resize(cols, rows)
        self.buffer = bytearray()  # recent output, replayed on reconnect
        self.subscribers: set[WebSocket] = set()
        self.pump_task: asyncio.Task | None = None
        self.type_task: asyncio.Task | None = None
        self.last_output = time.time()
        self.closed = False

    def read_chunk(self) -> bytes:
        """The next output, blocking (a pump thread); b"" or OSError at the end."""
        return os.read(self.fd, 8192)

    def foreground(self) -> str:
        return termlib.foreground_of_fd(self.fd)

    def resize(self, cols: int, rows: int) -> None:
        # The pty takes 16-bit sizes: past them struct.pack raised after the
        # fork, and the shell lived on with no owner.
        cols, rows = _size(cols, rows)
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        try:
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, winsize)
        except OSError:
            pass

    def write(self, data: bytes) -> None:
        if self.closed:
            return
        try:
            os.write(self.fd, data)
        except OSError:
            pass

    def alive(self) -> bool:
        try:
            return os.waitpid(self.pid, os.WNOHANG) == (0, 0)
        except ChildProcessError:
            return False

    def close(self) -> None:
        """Once only. Kill the child and reap it (off this thread: a zombie per
        closed view otherwise). The fd is closed by whoever reads it, when its
        read returns — closed under a read, its number could go to the next pty
        and the stale read would swallow that terminal's output."""
        if self.closed:
            return
        self.closed = True
        try:
            os.kill(self.pid, signal.SIGKILL)
        except OSError:
            pass

        def reap(pid: int = self.pid) -> None:
            try:
                os.waitpid(pid, 0)
            except ChildProcessError:
                pass
        threading.Thread(target=reap, daemon=True).start()
        if self.pump_task is None or self.pump_task.done():
            self.release()

    def release(self) -> None:
        """Close the fd, once, when nothing reads it any more."""
        if self.fd < 0:
            return
        fd, self.fd = self.fd, -1
        try:
            os.close(fd)
        except OSError:
            pass


class WinPtySession(PtySession):
    """A plain terminal on Windows: the same session (buffer, views, pump),
    its pty a ConPTY (conpty.py). There is no fd: ``fd`` stays -1, and the
    pump reads through ``read_chunk``."""

    def __init__(self, session_id: str, argv: list[str], cwd: str, cols: int, rows: int, env: dict[str, str],
                 module: Any = None):
        self.session_id = session_id
        cols, rows = _size(cols, rows)
        self.con = conpty.ConPty(argv, cwd, cols, rows, {**os.environ, **env}, module=module)
        self.pid = self.con.pid
        self.fd = -1
        self.buffer = bytearray()
        self.subscribers: set[WebSocket] = set()
        self.pump_task: asyncio.Task | None = None
        self.type_task: asyncio.Task | None = None
        self.last_output = time.time()
        self.closed = False

    def read_chunk(self) -> bytes:
        return self.con.read()

    def foreground(self) -> str:
        return self.con.foreground()

    def resize(self, cols: int, rows: int) -> None:
        self.con.resize(*_size(cols, rows))

    def write(self, data: bytes) -> None:
        if not self.closed:
            self.con.write(data)

    def alive(self) -> bool:
        return self.con.alive()

    def close(self) -> None:
        """Once only: the shell and its whole tree end, a blocked read wakes;
        the pseudo console goes when nothing reads it (release)."""
        if self.closed:
            return
        self.closed = True
        self.con.kill()
        if self.pump_task is None or self.pump_task.done():
            self.release()

    def release(self) -> None:
        self.con.release()


def open_pty(session_id: str, argv: list[str], cwd: str, cols: int, rows: int, env: dict[str, str]) -> PtySession:
    """A pty of this system's kind running `argv`."""
    kind = WinPtySession if os.name == "nt" else PtySession
    return kind(session_id, argv, cwd, cols, rows, env)


def _cfg(data_root: Path) -> dict[str, Any]:
    try:
        return app_settings.load(data_root)
    except Exception:  # noqa: BLE001 — a bad settings file must not open a shell
        return app_settings.defaults()


def enabled(request_app: Any) -> bool:
    boot: Settings = request_app.state.settings
    return bool(boot.terminal_enabled) or bool(_cfg(boot.data_root).get("terminal.enabled"))


_token_lock = threading.Lock()


def token_of(app: Any) -> str:
    """This server's token, new at each start (create_app makes it before the
    first request; the lock keeps two first asks from making two)."""
    tok = getattr(app.state, "terminal_token", "")
    if not tok:
        with _token_lock:
            tok = getattr(app.state, "terminal_token", "") or secrets.token_urlsafe(24)
            app.state.terminal_token = tok
    return tok


def token_matches(app: Any, given: str) -> bool:
    """Compared as bytes: compare_digest refuses a str with non-ASCII in it,
    and a typed or mangled token must be a refusal, not an error."""
    if not given or len(given) > 256:
        return False
    return hmac.compare_digest(given.encode("utf-8"), token_of(app).encode("utf-8"))


def _trusted(headers: Any, settings: Settings) -> bool:
    """Only Slightly Parallel's own pages: no foreign Origin, not marked cross-site.
    The same rule the whole API keeps for writes (server.OwnPagesOnly); the
    terminal keeps it for reads too, because its state carries the token."""
    return not foreign_origin(headers, settings)


def _guard(request: Request) -> None:
    if not _trusted(request.headers, request.app.state.settings):
        raise HTTPException(status_code=403, detail="only Slightly Parallel's own pages can use the terminal")


def _operator_page(headers: Any, app: Any) -> bool:
    """The request carries the operator's cookie: the pages have it, a
    program on this computer that only knows the port does not."""
    from ..server import has_operator_cookie
    return has_operator_cookie(dict(headers.raw), app)


def _need_on(request: Request) -> None:
    _guard(request)
    if not SUPPORTED:
        raise HTTPException(status_code=501, detail=UNSUPPORTED or "The terminal is not available on this system.")
    if not enabled(request.app):
        raise HTTPException(status_code=409, detail="the terminal is off: turn it on in the terminal drawer or in Settings › Terminal")


def _group_or_422(root: Path, value: Any) -> str:
    """A group's id as sent, "" for none; a group that does not exist is refused."""
    gid = str(value or "")
    if gid and not any(g.get("id") == gid for g in termlib.groups(root)):
        raise HTTPException(status_code=422, detail=f"no group {gid}")
    return gid


def build_router(settings: Settings) -> APIRouter:  # noqa: ARG001 — kept for the old call site
    router = APIRouter()
    sessions: dict[str, PtySession] = {}      # plain terminals, shared by their views
    clients: dict[str, PtySession] = {}       # one tmux client per view, "<id>#<n>"
    lock = threading.Lock()

    def _drop(sid: str) -> None:
        """Every pty of a terminal: its plain shell, and each view's tmux client."""
        with lock:
            gone = [sessions.pop(sid)] if sid in sessions else []
            gone += [clients.pop(k) for k in [k for k in clients if k.split("#")[0] == sid]]
        for g in gone:
            g.close()

    def _drop_all() -> None:
        with lock:
            gone = list(sessions.values()) + list(clients.values())
            sessions.clear()
            clients.clear()
        for g in gone:
            g.close()

    global _close_all
    _close_all = _drop_all

    def _reap_dead() -> None:
        with lock:
            dead = [(sid, sessions.pop(sid, None)) for sid, sess in list(sessions.items()) if not sess.alive()]
        for _, sess in dead:
            if sess is not None:
                sess.close()

    def _plain_status() -> dict[str, dict[str, Any]]:
        _reap_dead()
        with lock:
            live = list(sessions.items())
        return {sid: {"fg": s.foreground(), "activity": s.last_output} for sid, s in live}

    # ---------------------------------------------------------------- state
    @router.get("/api/terminal/state")
    def terminal_state(request: Request, response: Response) -> dict[str, Any]:
        _guard(request)
        if not _operator_page(request.headers, request.app):
            # The token opens the socket that types into a shell: a GET from
            # any program on this computer must not be handed it.
            raise HTTPException(status_code=403, detail="only the operator's pages read the terminal's state")
        # It carries the token: never from a cache, so after a restart the page
        # gets the new one.
        response.headers["Cache-Control"] = "no-store"
        boot: Settings = request.app.state.settings
        cfg = _cfg(boot.data_root)
        on = enabled(request.app)
        return {
            "enabled": on,
            # False only on Windows without pywinpty (the page says what to install).
            "supported": SUPPORTED,
            # Windows: plain terminals only — none survives a server restart.
            "windows": termlib.WINDOWS,
            "forced": bool(boot.terminal_enabled),
            "token": token_of(request.app) if on else "",
            "tmux": termlib.tmux_path() is not None,
            "tmux_version": termlib.tmux_version(),
            "keep": cfg.get("terminal.keep", "tmux"),
            "launch": cfg.get("terminal.launch", "run"),
            "agent": cfg.get("terminal.agent", "claude"),
            "font_size": cfg.get("terminal.font_size", 13),
            "scrollback": termlib.scrollback_of(cfg),
            # The editor a printed path opens in ("" = links off or none installed).
            "editor": termlib.editor_of(cfg),
            "projects": {k: str(v) for k, v in termlib.registered_project_dirs(boot.data_root).items()},
        }

    @router.get("/api/terminal/sessions")
    def terminal_sessions(request: Request, project: str = Query("")) -> dict[str, Any]:
        _guard(request)
        root = request.app.state.settings.data_root
        items = termlib.listing(root, _plain_status())
        if project:
            items = [x for x in items if x.get("project") == project]
        counts = {s: sum(1 for x in items if x["state"] == s)
                  for s in ("shell", "working", "waiting", "running", "ended", "asleep")}
        return {"sessions": items, "counts": counts}

    # ---------------------------------------------------------------- open
    @router.post("/api/terminal/sessions", status_code=201)
    def terminal_open(request: Request, body: dict = Body(default={}), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
        _need_on(request)
        # Whoever the body names, in either field: an agent named in
        # agent_id is an agent opening a terminal, as everywhere else.
        operator_only(body, "Opening a terminal")
        root = request.app.state.settings.data_root
        cfg = _cfg(root)
        kind = str(body.get("kind") or "shell")
        project = str(body.get("project") or "")
        cwd = str(body.get("cwd") or "")
        label = str(body.get("label") or "")
        # `agent`, not `agent_id`: a body naming an agent in agent_id reads
        # as written by that agent, and operator_only refused it above.
        agent_id = str(body.get("agent") or "")
        task_id = str(body.get("task_id") or "")
        command = ""
        if kind == "resume":
            agent = next((dict(a) for a in store.agents() if str(a.get("agent_id")) == agent_id), None)
            if not agent:
                raise not_found("agent", agent_id)
            command = termlib.resume_command(str(agent.get("tool") or ""), str(agent.get("session_ref") or ""))
            if not command:
                raise HTTPException(status_code=422, detail="This chat cannot be resumed: its tool or session id was not recorded.")
            project = project or str(agent.get("project") or "")
            cwd = cwd or str(agent.get("cwd") or "")
            # The name the pages show: a real name, else the chat's title, else the id.
            name = str(agent.get("agent_name") or "")
            label = label or (name if name and name != agent_id else str(agent.get("chat_title") or agent_id))
            # One terminal per resumed agent: an open one is reused.
            for r in termlib.listing(root, _plain_status()):
                if r.get("kind") == "resume" and r.get("agent_id") == agent_id and r["state"] != "ended":
                    return {"session": r, "existing": True}
        elif kind == "start":
            task = store.query_one("SELECT * FROM tasks_mutual WHERE id = ?", (task_id,))
            if not task:
                raise not_found("task", task_id)
            # The task's text lives in its own document, as the task window reads it.
            from ..turns import description_of
            from .tasks_extra import _task_doc
            _, turns = _task_doc(store, str(task.get("md_ref") or ""), dict(task), task_id)
            task = {**dict(task), "description": description_of(turns)}
            command = termlib.start_command(str(cfg.get("terminal.agent") or "claude"), task)
            project = project or str(task.get("project") or "")
            label = label or str(task.get("title") or task_id)
        elif kind == "shell":
            command = str(body.get("command") or "")
        else:
            raise HTTPException(status_code=422, detail="kind must be shell, resume or start")
        if sum(1 for r in termlib.listing(root, _plain_status()) if r["state"] not in ("ended", "asleep")) >= _MAX_SESSIONS:
            raise HTTPException(status_code=429, detail=f"{_MAX_SESSIONS} terminals are open: close one first.")
        group = _group_or_422(root, body.get("group"))
        try:
            row = termlib.open_session(root, cfg, kind=kind, project=project, cwd=cwd, command=command,
                                       label=label, agent_id=agent_id, task_id=task_id,
                                       role=str(body.get("role") or ""), group=group)
        except Exception as exc:  # noqa: BLE001 — tmux failing is the operator's to see
            raise HTTPException(status_code=500, detail=f"the terminal could not open: {exc}")
        return {"session": {**row, "state": "working" if command else "shell"}, "existing": False}

    # Where each terminal's last command was typed (absolute history line):
    # stamped when Enter crosses the socket, read by capture mode "last". In
    # memory only, so after a restart the button falls back to the screen.
    _last_enter: dict[str, int] = {}

    def _stamp_enter(root: Path, sid: str) -> None:
        try:
            pos = termlib.pane_pos(root, sid)
            _last_enter[sid] = pos["history"] - pos["scroll"] + pos["cursor"]
            if len(_last_enter) > 256:
                _last_enter.pop(next(iter(_last_enter)))
        except Exception:  # noqa: BLE001 — a missed stamp only weakens a button
            pass

    def _tmux_row(root: Path, sid: str) -> dict[str, Any]:
        row = termlib.get(root, sid)
        if row is None:
            raise not_found("terminal", sid)
        if row.get("backend") != "tmux":
            raise HTTPException(status_code=409, detail="A plain terminal keeps its history in the page, not on the server.")
        return row

    @router.get("/api/terminal/sessions/{sid}/pos")
    def terminal_pos(sid: str, request: Request) -> dict:
        """The pane's place in its history — the page anchors clicked rows with it."""
        _guard(request)
        root = request.app.state.settings.data_root
        _tmux_row(root, sid)
        return termlib.pane_pos(root, sid)

    @router.post("/api/terminal/sessions/{sid}/open")
    def terminal_open_path(sid: str, request: Request, body: dict = Body(...)) -> dict:
        """Open a path the terminal printed in the operator's editor, at its
        line. A relative path resolves where the shell stands now."""
        _guard(request)
        _need_on(request)
        root = request.app.state.settings.data_root
        row = termlib.get(root, sid)
        if row is None:
            raise not_found("terminal", sid)
        editor = termlib.editor_of(_cfg(root))
        if not editor:
            raise HTTPException(status_code=409, detail="no editor to open paths in: choose one in Settings › Terminal, or install VS Code, Cursor, Windsurf, Zed or Sublime")
        raw = str(body.get("path") or "")
        path = termlib.resolve_printed(root, row, raw)
        if path is None:
            raise not_found("file", raw[:200])
        line = _to_int(body.get("line"), 0)
        col = _to_int(body.get("col"), 0)
        try:
            termlib.open_in_editor(editor, path, line, col)
        except OSError as exc:
            raise HTTPException(status_code=503, detail=f"the editor did not start: {exc}") from None
        return {"path": str(path), "line": line, "editor": editor}

    @router.post("/api/terminal/sessions/{sid}/bottom")
    def terminal_bottom(sid: str, request: Request) -> dict:
        """Back to the newest line: the pane leaves its scrolled-up copy mode."""
        _guard(request)
        root = request.app.state.settings.data_root
        _tmux_row(root, sid)
        termlib.to_bottom(root, sid)
        return {"ok": True, **termlib.pane_pos(root, sid)}

    @router.post("/api/terminal/sessions/{sid}/capture")
    def terminal_capture(sid: str, request: Request, body: dict = Body(...)) -> dict:
        """Text out of the terminal: the visible screen, everything since the
        last command (mode "last"), or the lines between two absolute ids
        (mode "range", from, to). Wrapped lines come back joined."""
        _guard(request)
        root = request.app.state.settings.data_root
        _tmux_row(root, sid)
        mode = str(body.get("mode") or "screen")
        if mode == "range":
            try:
                a, b = int(body["from"]), int(body["to"])
            except (KeyError, TypeError, ValueError):
                raise HTTPException(status_code=422, detail="mode range needs from and to, the absolute line ids the page computed from /pos") from None
            return {**termlib.capture(root, sid, a, b), "mode": mode}
        if mode == "last":
            start = _last_enter.get(sid)
            pos = termlib.pane_pos(root, sid)
            if start is None:
                # Nothing typed since the server started: the screen is the answer.
                return {**termlib.capture(root, sid), "mode": "screen"}
            return {**termlib.capture(root, sid, start + 1, pos["history"] + pos["rows"] - 1), "mode": mode}
        if mode != "screen":
            raise HTTPException(status_code=422, detail="mode must be screen, last or range")
        return {**termlib.capture(root, sid), "mode": "screen"}

    @router.post("/api/terminal/sessions/{sid}/type")
    def terminal_type(sid: str, request: Request, body: dict = Body(...)) -> dict[str, Any]:
        _need_on(request)
        operator_only(body, "Typing into a terminal")
        root = request.app.state.settings.data_root
        row = termlib.get(root, sid)
        if not row:
            raise not_found("terminal", sid)
        text, enter = str(body.get("text") or ""), bool(body.get("enter"))
        if row.get("backend") == "tmux":
            if not termlib.type_into(root, row, text, enter=enter):
                raise HTTPException(status_code=409, detail="The terminal has closed. Nothing was typed.")
        else:
            s = sessions.get(sid)
            if s is None:
                raise HTTPException(status_code=409, detail="the terminal is not open")
            s.write((text + ("\r" if enter else "")).encode())
        return {"typed": True}

    @router.post("/api/terminal/sessions/{sid}/rename")
    def terminal_rename(sid: str, request: Request, body: dict = Body(...)) -> dict[str, Any]:
        _need_on(request)
        operator_only(body, "Renaming a terminal")
        root = request.app.state.settings.data_root
        if not termlib.get(root, sid):
            raise not_found("terminal", sid)
        return {"session": termlib.put(root, {"id": sid, "label": str(body.get("label") or "").strip()[:80]})}

    @router.post("/api/terminal/sessions/{sid}/close")
    def terminal_close(sid: str, request: Request, body: dict = Body(default={})) -> dict[str, Any]:
        _guard(request)
        operator_only(body, "Closing a terminal")
        root = request.app.state.settings.data_root
        _drop(sid)
        termlib.close(root, sid)
        return {"closed": sid}

    # ------------------------------------------------- sleep, wake, restore
    def _resume_of(store: ViewStore, row: dict[str, Any]) -> str:
        """The command that brings this terminal's agent back, "" for none."""
        agent_id = str(row.get("agent_id") or "")
        if not agent_id:
            return ""
        agent = next((dict(a) for a in store.agents() if str(a.get("agent_id")) == agent_id), None)
        if not agent:
            return ""
        return termlib.resume_command(str(agent.get("tool") or ""), str(agent.get("session_ref") or ""))

    def _listed(root: Path, sid: str) -> dict[str, Any]:
        row = next((r for r in termlib.listing(root, _plain_status()) if r["id"] == sid), None)
        if row is None:
            raise not_found("terminal", sid)
        return row

    def _wake(root: Path, cfg: dict[str, Any], store: ViewStore, row: dict[str, Any]) -> dict[str, Any]:
        awake = sum(1 for r in termlib.listing(root, _plain_status()) if r["state"] not in ("ended", "asleep"))
        if awake >= _MAX_SESSIONS:
            raise HTTPException(status_code=429, detail=f"{_MAX_SESSIONS} terminals are open: close one first.")
        # What sleep kept; a terminal lost to a restart never slept, so its
        # command is worked out now.
        cmd = str(row.get("wake") or "") if row.get("asleep") else termlib.wake_command(row, _resume_of(store, row))
        try:
            termlib.wake(root, cfg, row["id"], cmd)
        except Exception as exc:  # noqa: BLE001 — tmux failing is the operator's to see
            raise HTTPException(status_code=500, detail=f"the terminal could not open: {exc}")
        return _listed(root, row["id"])

    @router.post("/api/terminal/sessions/{sid}/sleep")
    def terminal_sleep(sid: str, request: Request, body: dict = Body(default={}),
                       store: ViewStore = Depends(get_store)) -> dict[str, Any]:
        """Stop what runs in a terminal and keep its tab: a chat's agent is
        resumed when it is woken, a server runs its command again."""
        _need_on(request)
        operator_only(body, "Putting a terminal to sleep")
        root = request.app.state.settings.data_root
        row = _listed(root, sid)
        if row["state"] == "asleep":
            return {"session": row}
        cmd = termlib.wake_command(row, _resume_of(store, row))
        _drop(sid)
        termlib.sleep(root, sid, cmd)
        return {"session": _listed(root, sid)}

    @router.post("/api/terminal/sessions/{sid}/wake")
    def terminal_wake(sid: str, request: Request, body: dict = Body(default={}),
                      store: ViewStore = Depends(get_store)) -> dict[str, Any]:
        _need_on(request)
        operator_only(body, "Waking a terminal")
        root = request.app.state.settings.data_root
        row = _listed(root, sid)
        if row["state"] not in ("asleep", "ended"):
            return {"session": row}
        return {"session": _wake(root, _cfg(root), store, row)}

    def _lost(root: Path) -> list[dict[str, Any]]:
        return termlib.lost(termlib.listing(root, _plain_status()), termlib.tmux_server_pid(root))

    @router.get("/api/terminal/restore")
    def terminal_restore_state(request: Request, store: ViewStore = Depends(get_store)) -> dict[str, Any]:
        """Terminals that ended without being closed or put to sleep — after
        a restart of the computer — and what each would run if restored."""
        _guard(request)
        root = request.app.state.settings.data_root
        items = [{**r, "wake": termlib.wake_command(r, _resume_of(store, r))} for r in _lost(root)]
        return {"needed": len(items), "sessions": items}

    @router.post("/api/terminal/restore")
    def terminal_restore(request: Request, body: dict = Body(default={}),
                         store: ViewStore = Depends(get_store)) -> dict[str, Any]:
        _need_on(request)
        operator_only(body, "Restoring terminals")
        root = request.app.state.settings.data_root
        cfg = _cfg(root)
        only = {str(x) for x in body.get("ids") or []}
        results = []
        for row in _lost(root):
            if only and row["id"] not in only:
                continue
            try:
                got = _wake(root, cfg, store, row)
                results.append({"id": row["id"], "label": row.get("label") or "", "ok": True, "error": "",
                                "command": got.get("wake") or ""})
            except HTTPException as exc:
                results.append({"id": row["id"], "label": row.get("label") or "", "ok": False,
                                "error": str(exc.detail), "command": ""})
        return {"results": results, "restored": sum(1 for r in results if r["ok"])}

    # ---------------------------------------------------------------- groups
    @router.get("/api/terminal/groups")
    def terminal_groups(request: Request) -> dict[str, Any]:
        _guard(request)
        return {"groups": termlib.groups(request.app.state.settings.data_root)}

    def _group_fields(body: dict) -> tuple[str | None, int | None]:
        name = body.get("name")
        name = str(name).strip()[:60] if name is not None else None
        if name == "":
            raise HTTPException(status_code=422, detail="a group needs a name")
        color = body.get("color")
        if color is not None:
            if not isinstance(color, int) or isinstance(color, bool) or not 1 <= color <= 8:
                raise HTTPException(status_code=422, detail="color is a number from 1 to 8")
        return name, color

    @router.post("/api/terminal/groups", status_code=201)
    def terminal_group_new(request: Request, body: dict = Body(default={})) -> dict[str, Any]:
        _need_on(request)
        operator_only(body, "Making a group of terminals")
        name, color = _group_fields(body)
        return {"group": termlib.group_put(request.app.state.settings.data_root, "", name, color)}

    @router.post("/api/terminal/groups/{gid}")
    def terminal_group_edit(gid: str, request: Request, body: dict = Body(default={})) -> dict[str, Any]:
        _need_on(request)
        operator_only(body, "Changing a group of terminals")
        name, color = _group_fields(body)
        g = termlib.group_put(request.app.state.settings.data_root, gid, name, color)
        if g is None:
            raise not_found("group", gid)
        return {"group": g}

    @router.post("/api/terminal/groups/{gid}/remove")
    def terminal_group_remove(gid: str, request: Request, body: dict = Body(default={})) -> dict[str, Any]:
        _need_on(request)
        operator_only(body, "Removing a group of terminals")
        if not termlib.group_remove(request.app.state.settings.data_root, gid):
            raise not_found("group", gid)
        return {"removed": gid}

    @router.post("/api/terminal/sessions/{sid}/group")
    def terminal_set_group(sid: str, request: Request, body: dict = Body(default={})) -> dict[str, Any]:
        """Move a terminal into a group, or with "" back to its project: it
        is in exactly one place."""
        _need_on(request)
        operator_only(body, "Moving a terminal")
        root = request.app.state.settings.data_root
        if not termlib.get(root, sid):
            raise not_found("terminal", sid)
        termlib.put(root, {"id": sid, "group": _group_or_422(root, body.get("group"))})
        return {"session": _listed(root, sid)}

    # ---------------------------------------------------------------- typing
    @router.post("/api/terminal/typing")
    def terminal_typing(request: Request, body: dict = Body(default={})) -> dict[str, Any]:
        """The operator typed into a terminal: how many keys since the last
        report. The time they spend, never the text."""
        _need_on(request)
        operator_only(body, "Reporting typing")
        root = request.app.state.settings.data_root
        row = termlib.get(root, str(body.get("sid") or ""))
        keys = body.get("keys")
        if row is None or not isinstance(keys, int) or isinstance(keys, bool) or keys <= 0:
            return {"noted": False}
        termlib.note_typing(root, row, min(keys, 20000))
        return {"noted": True}

    @router.get("/api/terminal/typing")
    def terminal_typing_day(request: Request, day: str = Query("")) -> dict[str, Any]:
        _guard(request)
        day = day if re.match(r"^\d{4}-\d{2}-\d{2}$", day) else time.strftime("%Y-%m-%d")
        minutes = termlib.typing_minutes(request.app.state.settings.data_root, day)
        return {"day": day, "minutes": minutes, "total": sum(minutes.values())}

    # ------------------------------------------------------------ the screen
    @router.websocket("/ws/terminal/{session_id}")
    async def terminal_ws(websocket: WebSocket, session_id: str) -> None:
        app = websocket.app
        boot: Settings = app.state.settings
        # Another site's page is turned away at the handshake: it learns nothing.
        if not _trusted(websocket.headers, boot):
            await websocket.close(code=4403, reason="origin not allowed")
            return
        # Every other refusal comes after the handshake, so the page reads its
        # code. Closed before it, a socket fails with HTTP 403 and the browser
        # reports 1006: a page holding the token of a server before a restart
        # never saw 4401, never asked for the new token, and reconnected with
        # the old one for good.
        await websocket.accept()
        if not SUPPORTED:
            # 4403 is a refusal the screen shows and does not retry.
            await websocket.close(code=4403, reason=UNSUPPORTED_WS)
            return
        if not enabled(app):
            await websocket.close(code=4409, reason="the terminal is off")
            return
        if not token_matches(app, websocket.query_params.get("token", "")):
            await websocket.close(code=4401, reason="invalid token")
            return
        if not _operator_page(websocket.headers, app):
            await websocket.close(code=4403, reason="only the operator's pages open a terminal")
            return
        if not termlib.SAFE_ID.match(session_id):
            await websocket.close(code=4400, reason="bad terminal id")
            return
        root = boot.data_root
        cfg = _cfg(root)
        cols = _to_int(websocket.query_params.get("cols"), 100)
        rows = _to_int(websocket.query_params.get("rows"), 30)

        # tmux and the registry are subprocesses and file locks: off the event
        # loop, or a slow tmux stalls every socket and route.
        row = await run_in_threadpool(termlib.get, root, session_id)
        if row is None:
            # Closed (here or in another view): it stays closed. A reconnect
            # must not bring a shell back under an old id.
            await websocket.close(code=4000, reason="ended")
            return
        if row.get("backend") == "tmux" and not await run_in_threadpool(termlib.alive_tmux, root, session_id):
            # The computer restarted: the terminal comes back as a shell where it was.
            row = await run_in_threadpool(lambda: termlib.open_session(
                root, cfg, kind=row.get("kind", "shell"), sid=session_id,
                project=row.get("project", ""), cwd=row.get("cwd", ""), label=row.get("label", ""),
                agent_id=row.get("agent_id", ""), task_id=row.get("task_id", "")))

        await run_in_threadpool(_reap_dead)
        env = {"TERM": "xterm-256color", "COLORTERM": "truecolor", "SP_TERMINAL": session_id}
        in_tmux = row.get("backend") == "tmux"
        if in_tmux:
            # Each view its own tmux client: tmux draws the screen for it, so
            # nothing is replayed — a replay made the new screen answer the
            # terminal's old questions into the shell.
            if len(clients) >= _MAX_SESSIONS * 4:
                await websocket.close(code=4429, reason="too many views")
                return
            key = f"{session_id}#{secrets.token_hex(3)}"
            session = open_pty(session_id, termlib.attach_argv(root, session_id), str(row.get("cwd") or root), cols, rows, env)
            with lock:
                clients[key] = session
            fresh = True
        else:
            key = session_id
            if session_id not in sessions and len(sessions) >= _MAX_SESSIONS:
                await websocket.close(code=4429, reason="too many terminals")
                return
            failed = ""
            with lock:
                found = sessions.get(session_id)
                fresh = found is None
                if found is None:
                    try:
                        found = open_pty(session_id, termlib.plain_shell(), str(row.get("cwd") or root), cols, rows, env)
                        sessions[session_id] = found
                    except Exception as exc:  # noqa: BLE001 — Windows: no shell, no pseudo console
                        failed = str(exc) or type(exc).__name__
            if found is None:
                log.warning("terminal %s did not open: %s", session_id, failed)
                await websocket.close(code=4500, reason=f"the shell did not start: {failed}"[:120])
                return
            session = found
        if not fresh:
            session.resize(cols, rows)
            if session.buffer:
                try:
                    await websocket.send_bytes(_QUERIES.sub(b"", bytes(session.buffer[-_REPLAY_BYTES:])))
                except Exception:  # noqa: BLE001 — reconnect replay is best-effort
                    pass
        elif row.get("backend") != "tmux" and not row.get("typed") and _pending(row):
            # A plain terminal types its command once, when it first opens —
            # and a woken one what it wakes with (termlib.wake), once.
            pending = _pending(row)

            async def type_later() -> None:
                await asyncio.sleep(0.4)
                typed = termlib.typed_form(pending, termlib.plain_shell()[0])
                await run_in_threadpool(session.write, (typed + ("\r" if row.get("launch") == "run" else "")).encode())
            # Held on the session: a task nothing references can be collected before it runs.
            session.type_task = asyncio.create_task(type_later())
            await run_in_threadpool(termlib.put, root, {"id": session_id, "typed": True})

        session.subscribers.add(websocket)

        async def pump_output() -> None:
            while not session.closed:
                try:
                    data = await _read_session(session)
                except OSError:
                    break
                if session.closed:
                    break
                if not data:
                    break
                session.last_output = time.time()
                session.buffer.extend(data)
                if len(session.buffer) > _BUFFER_BYTES:
                    del session.buffer[: len(session.buffer) - _BUFFER_BYTES]
                for ws in list(session.subscribers):
                    try:
                        await ws.send_bytes(data)
                    except Exception:  # noqa: BLE001 — drop dead subscribers
                        session.subscribers.discard(ws)
            if session.closed:
                session.release()
            # The shell ended (exit, or the tmux session was killed).
            for ws in list(session.subscribers):
                try:
                    await ws.close(code=4000, reason="ended")
                except Exception:  # noqa: BLE001
                    pass

        if session.pump_task is None or session.pump_task.done():
            session.pump_task = asyncio.create_task(pump_output())

        # Typing in a project's terminal is working on it (the smart timer).
        timer = timeauto.of(app)
        typed = lambda: timer.beat(str(row.get("project") or ""), str(row.get("task_id") or ""), "terminal")  # noqa: E731

        # A write to the terminal waits while the program in it reads no
        # input and the tty's queue is full (a long paste into a running
        # build): on a worker thread, never on the event loop.
        try:
            while True:
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                if msg.get("bytes") is not None:
                    # Stamp before the shell sees the Enter: read after, and
                    # the echo has already moved the cursor past the line.
                    if in_tmux and b"\r" in msg["bytes"]:
                        await run_in_threadpool(_stamp_enter, root, session_id)
                    await run_in_threadpool(session.write, msg["bytes"])
                    typed()
                elif msg.get("text"):
                    try:
                        payload = json.loads(msg["text"])
                        if not isinstance(payload, dict):
                            raise ValueError  # "5", "null", "[]": typed text, not a message
                    except ValueError:
                        if in_tmux and "\r" in msg["text"]:
                            await run_in_threadpool(_stamp_enter, root, session_id)
                        await run_in_threadpool(session.write, msg["text"].encode())
                        typed()
                        continue
                    kind = payload.get("type")
                    if kind == "resize":
                        session.resize(_to_int(payload.get("cols"), 100), _to_int(payload.get("rows"), 30))
                    elif kind == "input":
                        data = str(payload.get("data") or "")
                        if in_tmux and "\r" in data:
                            await run_in_threadpool(_stamp_enter, root, session_id)
                        await run_in_threadpool(session.write, data.encode())
                        typed()
                    elif kind == "close":
                        _drop(session_id)
                        await run_in_threadpool(termlib.close, root, session_id)
                        break
        except WebSocketDisconnect:
            pass
        finally:
            session.subscribers.discard(websocket)
            # A view's tmux client goes with the view: tmux keeps the shell.
            if in_tmux:
                with lock:
                    clients.pop(key, None)
                session.close()

    return router


def _pending(row: dict[str, Any]) -> str:
    """What a plain terminal types when its shell starts: the command it was
    opened with; once woken, what it wakes with ("" for a shell woken empty)."""
    if row.get("woken_at"):
        return str(row.get("wake") or "")
    return str(row.get("command") or "")


_to_int = to_int  # a whole number, or the default (deps)
