"""FastAPI app assembly: middleware, routers, watchers, static frontend.

The filesystem is the source of truth; DuckDB views over it are a disposable
in-memory cache (see ``db.py``). Endpoints live in ``routers/``:

    core.py           health, snapshot, project, agent, chat, search,
                      timeline, heatmap
    scans.py          SCAN snapshots (list / detail / create)
    lenses.py         generic list / detail / create for every registered
                      entity (standups, goals, decisions, … — see entities.py)
    files_extra.py    file heatmap + checkpoint diff
    architecture.py   the architecture ledger folded into what stands
    prompts.py        the agent prompt files: edit, version, restore
    tasks_extra.py    task updates + event history, archive, create, detail
    task_links.py     links between tasks
    task_mentions.py  chat mentions of tasks + the task timeline
    sprints.py        sprint board, series, timeline, dossier
    sprint_deck.py    the cross-project sprint deck
    snippets_extra.py snippet update / delete
    terminal.py       opt-in pty shell over WebSocket

Every 200 ships an ETag; a matching ``If-None-Match`` short-circuits to 304.
Missing data degrades to empty payloads. Requests log as JSON lines.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import os
import re
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator

from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse

from . import app_settings, backup as backup_engine, logbook
from .config import Settings, lan_refusal
from .db import FIXTURES, ViewStore
from .routers import (
    deps,
    agents_extra,
    architecture,
    artifacts,
    backup as backup_router,
    boards,
    prompts,
    promptlib,
    doctor,
    schema_api,
    prefs,
    core,
    files_extra,
    integrate,
    keep,
    lenses,
    logs,
    marks,
    done,
    undo,
    stats,
    analytics,
    monitor,
    scans,
    sessions_api,
    settings_api,
    setup,
    sets,
    skills,
    snippets_extra,
    story,
    standups,
    sprint_deck,
    sprints,
    task_links,
    task_mentions,
    tasks_extra,
    timelapse,
    tour,
    terminal,
    time_tracking,
    evidence,
    calendar,
    story_release,
)
from .turns import migrate_task_docs
from .watcher import Watcher

_REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Logging: JSON lines to stdout, one per request
# ---------------------------------------------------------------------------


def _configure_logging() -> None:
    """The log lives in logbook.py: a ring in memory for the health page, a
    rotating file beside the server, warnings and errors to stdout."""
    logbook.install(file=os.environ.get("SP_LOG_FILE", "1") != "0")


_configure_logging()
log = logging.getLogger("sp.server")


# ---------------------------------------------------------------------------
# App factory (used by uvicorn AND by tests)
# ---------------------------------------------------------------------------


def _warm_git(store: ViewStore) -> None:
    """Read each repository's commit log once, then the task statistics
    built on them, so no page pays for either."""
    from . import gitwork

    t0 = time.perf_counter()
    repos: set[Path] = set()
    for a in store.agents():
        chat = Path(str(a.get("_chat_path") or ""))
        if not chat.exists():
            continue
        try:
            repo = gitwork.repo_for_chat(chat)
        except Exception:  # noqa: BLE001 — a bad capture must not stop the warm-up
            continue
        if repo is not None and repo not in repos:
            repos.add(repo)
            try:
                gitwork.commits(repo)
            except Exception:  # noqa: BLE001
                log.exception("could not read the log of %s", repo)
    log.info("git logs warm: %d repositories", len(repos),
             extra={"ms": int((time.perf_counter() - t0) * 1000)})
    # The task statistics and the analytics copy stand on those logs: the
    # first project page after a start paid 4–6 s for them. Same caches the
    # requests use, filled once here; a rebuild refills them as before.
    t1 = time.perf_counter()
    try:
        from . import analytics
        analytics.schema(store)
    except Exception:  # noqa: BLE001 — a request computes them again
        log.exception("task statistics not warmed")
    log.info("task statistics warm", extra={"ms": int((time.perf_counter() - t1) * 1000)})


def _backfill_turn_times(root: Path) -> None:
    try:
        from .turntimes import backfill
        n = backfill(root)
        if n:
            log.info("turn times: %d answers timed from the transcripts", n)
    except Exception:  # noqa: BLE001 — a missing time is shown as an estimate
        log.exception("turn times not backfilled")


def _start_watchers(root: Path, store: ViewStore) -> list[Watcher]:
    """Watch a data root: one recursive watcher on the root itself.

    Mutual CSVs, *_details folders, projects/ and snapshots/ all live under
    the root, so one watcher sees every write once. There were three, with
    projects/ and snapshots/ watched twice over — every hook write started
    two or three rebuilds — and the debounce coalesces the rest.
    """
    (root / "snapshots").mkdir(parents=True, exist_ok=True)
    watchers = [Watcher(root, on_change=store.rebuild, delay_ms=200, recursive=True)]
    for w in watchers:
        w.start()
    return watchers


# How often the scheduler wakes to ask whether a backup is due. The interval
# itself is a setting in hours; this is only the resolution of the question,
# and it is cheap — a look at the clock; the stat walk of the data root only
# once the interval has passed, and no archive unless the data changed too.
BACKUP_TICK_SECONDS = 300


def _scheduled_backup(root: Path, dest: Path, every: int) -> tuple[Any, str]:
    """One scheduled turn: (the archive taken or None, why)."""
    from .routers.backup import keep_budget

    # A backup, restore or trial the operator started is running: this
    # turn is skipped, the next tick asks again.
    if not backup_engine.BUSY.acquire(blocking=False):
        log.info("scheduled backup skipped: another backup operation is running")
        return None, "another backup operation is running"
    try:
        now = datetime.now()
        # The clock first; the data root is walked only when it says yes.
        ready, why, _ = backup_engine.due_now(root, dest, now, every)
        if not ready:
            return None, why
        made = backup_engine.create(root, dest, kind="auto", now=now)
        backup_engine.prune(dest, now, keep_budget(root))
        # Proved, not assumed: the new archive is restored into a
        # temporary folder and read as the dashboard would.
        checked = backup_engine.trial(dest, made.name)
        if not checked["ok"]:
            log.warning("backup %s failed its trial restore: %s", made.name, "; ".join(checked["problems"][:3]))
        return made, why
    finally:
        backup_engine.BUSY.release()


async def _memory_loop() -> None:
    """The process's memory into the log every few minutes (logbook.note_memory):
    the report reads it back across restarts. Reading it is a few
    microseconds of the OS's own counters."""
    while True:
        try:
            logbook.note_memory()
        except Exception:  # noqa: BLE001 — a missing line is no reason to stop
            log.exception("memory line not written")
        await asyncio.sleep(logbook.MEMORY_EVERY_S)


async def _backup_loop(app: FastAPI) -> None:
    """Scheduled archives of the data root, taken off the request path.

    Tarring and hashing tens of megabytes is seconds of solid CPU, and the
    browser reads its data from this same process — so the work happens in a
    thread and the loop only ever awaits. One failed run must not end the
    schedule, which is why everything below the sleep is inside the guard.
    """
    # What an interrupted run left (a .part, an unpacking folder) is
    # removed once at the start, and again at every prune.
    try:
        await asyncio.to_thread(
            backup_engine.clean_leftovers, backup_engine.backup_root_for(app.state.store.data_root))
    except Exception:
        log.exception("could not clean the backup folder's leftovers")

    while True:
        await asyncio.sleep(BACKUP_TICK_SECONDS)
        try:
            root = app.state.store.data_root
            values = app_settings.load(root)
            if not values.get("backup.enabled", True):
                continue
            every = int(values.get("backup.every_hours", 6))
            dest = backup_engine.backup_root_for(root)

            made, why = await asyncio.to_thread(_scheduled_backup, root, dest, every)
            if made is not None:
                log.info(
                    "scheduled backup %s — %d files, %d bytes (%s)",
                    made.name, made.files, made.bytes, why,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("scheduled backup failed — the schedule continues")


# The largest JSON body the server reads: a story with its pictures is the
# biggest write, well under it. Uploads are not JSON and do not pass here.
MAX_JSON_BODY = 64 * 1024 * 1024

MCP_VIA_HEADER = b"x-sp-via"
# An MCP server started before the rename (a session still running since)
# sends the old header; it is the same translator, so it passes too.
MCP_VIA_HEADERS = (MCP_VIA_HEADER, b"x-merkhet-via")
from .mcp import TOOLS as _MCP_TOOLS  # noqa: E402 — the one tool list

_WRITE_TOOLS = ("write_entry", "update_entry", "task_update", "task_report", "task_evidence",
                "task_story", "interpret", "skill_draft", "artifact_write", "doc_version",
                "architecture_page", "map_write", "standup_postpone", "undo_propose", "undo_apply", "undo_restore")
assert set(_WRITE_TOOLS) <= set(_MCP_TOOLS), "a write tool named here is not served"
MCP_REFUSAL = (
    f"agents write through the Slightly Parallel MCP tools ({', '.join(_WRITE_TOOLS)}), not by HTTP. "
    "The `slightly-parallel` MCP server is wired into the project by Setup; if it is "
    "not connected in this session, tell the user."
)


# The one MCP write that names no agent: putting off the standup question
# for some hours. A forged request can do that and nothing else.
MCP_WITHOUT_AGENT: frozenset[str] = frozenset({"/api/standups/postpone"})
MCP_NEEDS_AGENT = (
    "a request marked as the Slightly Parallel MCP server names the agent it writes for; "
    "this one names none. The MCP tools stamp it themselves: write through them."
)

# The writes the MCP translator makes (mcp.Translator.call), and only those.
# The mark is a header anyone on this computer can send: without this list a
# marked agent write reached every router that does not refuse agents itself
# (settings, setup, backup, terminals, boards …).
_MCP_WRITE_PATHS = (
    r"/api/(visions|rules|problems|entrypoints)/[^/]+/interpretation",
    r"/api/artifacts/[^/]+/write",
    r"/api/docs/[^/]+/versions",
    r"/api/skills/[^/]+/draft",
    r"/api/tasks/[^/]+/(update|report|evidence|story)",
    r"/api/standups/(claim|postpone)",
    r"/api/architecture/page",
    r"/api/map",
    r"/api/undo/(propose|apply|restore)",
)
MCP_PATH_REFUSAL = (
    "the Slightly Parallel MCP tools do not write here, so an agent cannot either. "
    "This is a change for the operator to make on Slightly Parallel's own pages."
)
_mcp_paths: "re.Pattern[str] | None" = None


def mcp_may_write(path: str) -> bool:
    """Is ``path`` one the MCP translator posts to? The lens writes
    (write_entry, update_entry) go to each lens's base, read from the same
    schema the translator builds its tools from."""
    global _mcp_paths
    if _mcp_paths is None:
        from .routers.schema_api import build_schema
        bases = sorted({re.escape(str(l["base"])) for l in build_schema()["lenses"]})
        lens = rf"/api/({'|'.join(bases)})(/[^/]+/update)?"
        _mcp_paths = re.compile("|".join((lens, *_MCP_WRITE_PATHS)))
    return _mcp_paths.fullmatch(path) is not None


def _json_body(content_type: bytes | None) -> bool:
    """Would FastAPI read this body as JSON? Its own rule: no content type
    at all, or a subtype that is ``json`` or ends in ``+json``. The gate
    looked for the literal ``application/json`` and let the rest through."""
    if content_type is None:
        return True
    main, _, sub = content_type.decode("latin-1").split(";")[0].strip().lower().partition("/")
    return main == "application" and (sub == "json" or sub.endswith("+json"))


# ---------------------------------------------------------------------------
# The operator's cookie
# ---------------------------------------------------------------------------
#
# Slightly Parallel has no login, so a write that names no agent is the
# operator's. Before this, any program on the computer — an agent's curl
# among them — could post as the operator by leaving the agent out. Now the
# operator's pages carry a cookie the server hands to a browser page of its
# own, and a write as the operator without it is refused. A program that
# loads the page first and replays the cookie still gets through: this
# stops a plain request, not a deliberate one (the decision: option A).

OPERATOR_TOKEN_FILE = "operator.token"
OPERATOR_REFUSAL = (
    "a write as the operator comes from Slightly Parallel's own pages. Open the page "
    "again in the browser; an agent writes through the Slightly Parallel MCP tools."
)
# The browser's word that a page of this site, or the person at the address
# bar, made the request. A plain HTTP client sends no Sec-Fetch-Site.
_OWN_FETCH_SITES = ("same-origin", "none")


def load_operator_token(root: Path) -> str:
    """The token kept in the data root, made on the first start. Kept across
    restarts, so an open page's writes keep working; readable by the owner
    only. A root that cannot be written to gets one for this run."""
    import secrets
    path = Path(root) / OPERATOR_TOKEN_FILE
    try:
        tok = path.read_text(encoding="utf-8").strip()
        if len(tok) >= 32:
            return tok
    except OSError:
        pass
    tok = secrets.token_urlsafe(32)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(tok + "\n")
    except OSError as exc:
        log.warning("operator token not saved (%s): open pages need a reload after a restart", exc)
    return tok


def operator_cookie_name(app: Any) -> str:
    # By port: a sandbox on another port of 127.0.0.1 keeps its own cookie.
    return f"sp_operator_{getattr(app.state.settings, 'port', 8123)}"


def operator_cookie(app: Any) -> tuple[str, str]:
    """(name, value): for an in-process client that acts as the operator's
    pages — the tests and the demo builder."""
    return operator_cookie_name(app), app.state.operator_token


def has_operator_cookie(headers: dict, app: Any) -> bool:
    import hmac
    from http.cookies import SimpleCookie
    raw = headers.get(b"cookie", b"").decode("latin-1")
    if not raw:
        return False
    jar = SimpleCookie()
    try:
        jar.load(raw)
    except Exception:  # noqa: BLE001 — a cookie header we cannot read holds no token
        return False
    got = jar.get(operator_cookie_name(app))
    tok = getattr(app.state, "operator_token", "")
    # As bytes: compare_digest raises on a str that is not ASCII, and a
    # cookie value may be any Latin-1 text.
    return bool(got and tok) and hmac.compare_digest(got.value.encode("utf-8"), tok.encode("utf-8"))


class OperatorCookie:
    """Hand the operator's cookie to a page of Slightly Parallel's own.

    A read the browser marks as this site's (or as typed at the address
    bar) and that does not carry the cookie yet gets it on the answer.
    HttpOnly, so no script reads it; SameSite=Strict, so no other site's
    page sends it. Pure ASGI, below the Host and Origin check.
    """

    def __init__(self, app, app_ref) -> None:
        self.app = app
        self.app_ref = app_ref

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in ("GET", "HEAD"):
            await self.app(scope, receive, send)
            return
        headers = {k.lower(): v for k, v in scope.get("headers") or []}
        site = headers.get(b"sec-fetch-site", b"").decode("latin-1").lower()
        if site not in _OWN_FETCH_SITES or has_operator_cookie(headers, self.app_ref):
            await self.app(scope, receive, send)
            return
        cookie = (
            f"{operator_cookie_name(self.app_ref)}={self.app_ref.state.operator_token}; "
            "Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000"
        ).encode("latin-1")

        async def with_cookie(message):
            if message["type"] == "http.response.start":
                message = {**message, "headers": [*message.get("headers", []), (b"set-cookie", cookie)]}
            await send(message)

        await self.app(scope, receive, with_cookie)


class AgentsViaMcp:
    """Refuse an agent's write that did not come through the MCP translator.

    The decision behind it: every agent write goes through one path that
    stamps identity and checks vocabulary before a request exists, so no
    agent copies an endpoint out of the docs and finds a side door. The
    operator's pages carry a house actor and pass; a body with no identity
    is the board's own. Pure ASGI, so the body is read once and replayed.
    """

    def __init__(self, app, app_ref) -> None:
        self.app = app
        self.app_ref = app_ref

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in ("POST", "PUT", "PATCH", "DELETE"):
            await self.app(scope, receive, send)
            return
        path = scope.get("path") or ""
        if not path.startswith("/api/"):
            await self.app(scope, receive, send)
            return
        headers = {k.lower(): v for k, v in scope.get("headers") or []}
        via_mcp = any(headers.get(h, b"").decode("latin-1").lower() == "mcp" for h in MCP_VIA_HEADERS)
        if via_mcp and path in MCP_WITHOUT_AGENT:
            await self.app(scope, receive, send)
            return
        if via_mcp and not mcp_may_write(path) and self._enforced():
            await JSONResponse({"detail": MCP_PATH_REFUSAL}, status_code=403)(scope, receive, send)
            return
        operator = has_operator_cookie(headers, self.app_ref)
        if not _json_body(headers.get(b"content-type")):
            # An upload or a form: only the operator's pages send those.
            if not operator:
                await JSONResponse({"detail": OPERATOR_REFUSAL}, status_code=403)(scope, receive, send)
                return
            await self.app(scope, receive, send)
            return
        # Chunks gathered once, not concatenated per chunk (each += copied the
        # body so far), and a ceiling: no JSON write here is near it.
        chunks: list[bytes] = []
        size = 0
        more = True
        while more:
            message = await receive()
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > MAX_JSON_BODY:
                await JSONResponse({"detail": f"a JSON body is at most {MAX_JSON_BODY // 1_000_000} MB"},
                                   status_code=413)(scope, receive, send)
                return
            chunks.append(chunk)
            more = message.get("more_body", False)
        body = b"".join(chunks)

        async def replay():
            return {"type": "http.request", "body": body, "more_body": False}

        try:
            data = json.loads(body.decode("utf-8")) if body else {}
        except (ValueError, UnicodeDecodeError):
            data = {}
        actor = deps.identity_of(data)
        if via_mcp:
            # The MCP translator stamps the agent on every write. The mark
            # with no agent is a hand-made request: anyone can send the
            # header, and it is not a way to write as the operator.
            if not deps.is_agent(actor):
                await JSONResponse({"detail": MCP_NEEDS_AGENT}, status_code=403)(scope, replay, send)
                return
            await self.app(scope, replay, send)
            return
        if actor and deps.is_agent(actor) and self._enforced():
            # The same status every other refusal of an agent carries
            # (routers/deps.refuse_agent) — this one cannot raise, it is
            # ASGI below FastAPI, so it spells the answer by hand.
            resp = JSONResponse(
                {"detail": MCP_REFUSAL}, status_code=deps.AGENT_REFUSED
            )
            await resp(scope, replay, send)
            return
        if not deps.is_agent(actor) and not operator:
            # A write that names no agent is the operator's, and the
            # operator's pages carry the cookie (OperatorCookie). Anything
            # else on this computer posting as the operator is refused.
            await JSONResponse({"detail": OPERATOR_REFUSAL}, status_code=403)(scope, replay, send)
            return
        await self.app(scope, replay, send)

    def _enforced(self) -> bool:
        try:
            root = self.app_ref.state.settings.data_root
            return bool(app_settings.load(root).get("agents.mcp_only", True))
        except Exception:  # noqa: BLE001 — a setting we cannot read is the default
            return True


class OwnPagesOnly:
    """Refuse a browser request that another site's page made.

    Slightly Parallel has no login; it is reached on this computer only. Two things a
    hostile web page could still do are closed here. A page whose own name
    is re-pointed at 127.0.0.1 (DNS rebinding) sends that name as ``Host``:
    a Host that is not this computer's is refused, for every path. A page
    that posts across origins names itself in ``Origin``: a write whose
    Origin is not one of Slightly Parallel's is refused. The hooks and the MCP
    translator send neither header and pass. Pure ASGI, so sockets are
    covered too.
    """

    _READS = ("GET", "HEAD", "OPTIONS")

    def __init__(self, app, app_ref) -> None:
        self.app = app
        self.app_ref = app_ref

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        settings = self.app_ref.state.settings
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}
        why = ""
        if deps.foreign_host(headers.get("host", ""), settings):
            why = "this address is not Slightly Parallel's: open it as http://127.0.0.1 or list the name in SP_CORS_ORIGINS"
        elif scope["type"] == "http" and scope.get("method") not in self._READS and deps.foreign_origin(headers, settings):
            why = "another site's page cannot change anything in Slightly Parallel"
        elif scope["type"] == "websocket" and deps.foreign_origin(headers, settings):
            # A socket carries no CORS: every one is refused here, not only
            # the terminal's, which checks again after its token.
            why = "another site's page cannot open a socket to Slightly Parallel"
        if not why:
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 4403, "reason": why})
            return
        await JSONResponse({"detail": why}, status_code=403)(scope, receive, send)


def create_app(
    data_root: Path | None = None, *, watch: bool = True, prompt_root: Path | None = None,
    autoinstall_skills: bool = False,
    run_monitor: bool = True,
) -> FastAPI:
    settings = Settings.from_env()
    if data_root is not None:
        settings = dataclasses.replace(settings, data_root=Path(data_root))
    root = settings.data_root
    # Task documents written in the old L2-with-markers shape are rewritten
    # into Description/Turn sections once, before the store reads anything.
    try:
        migrated = migrate_task_docs(root)
        if migrated:
            log.info("task documents migrated to Description/Turn sections: %d", migrated)
    except OSError as exc:
        log.warning("task document migration skipped: %s", exc)
    store = ViewStore(data_root=root)
    # A new data root starts with example visions, rules and problems, once.
    if os.environ.get("SP_EXAMPLES", "1") != "0":
        try:
            from .examples import seed as seed_examples
            seed_examples(store)
        except OSError as exc:
            log.warning("examples skipped: %s", exc)
    # The skills Slightly Parallel ships with (templates/skills): every data root has
    # them, and a changed template is the next version on the next start.
    try:
        from .skilllib import seed_builtin_skills
        seed_builtin_skills(store)
    except (OSError, ValueError) as exc:
        log.warning("built-in skills skipped: %s", exc)

    def install_builtin_skills() -> None:
        """Built-in skills are on from the start: each goes into All projects
        once. Only the served app does this — it writes under the home
        folder, which a test must never reach. Not on the shipped demo data
        inside the repository: the ledger of what was installed would be
        written into the fixtures."""
        if not autoinstall_skills or app.state.store.data_root.resolve() == FIXTURES.resolve():
            return
        try:
            from .skilllib import autoinstall_builtin
            for note in autoinstall_builtin(app.state.store):
                log.info("built-in skill %s: %s %s", note["skill"], note["action"], note["why"])
        except (OSError, ValueError) as exc:
            log.warning("built-in skills not installed: %s", exc)

    def offer_example() -> None:
        """A data root made empty gets the example project (example.py);
        never the shipped fixtures inside the repository."""
        if app.state.store.data_root.resolve() == FIXTURES.resolve():
            return
        from . import example
        example.on_start(app)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        install_builtin_skills()
        offer_example()
        if watch:
            app.state.watchers = _start_watchers(
                app.state.settings.data_root, app.state.store
            )
            app.state.backup_task = asyncio.create_task(_backup_loop(app))
            app.state.memory_task = asyncio.create_task(_memory_loop())
            # The first page that asks for a day's commits paid for reading
            # every repository's log — 4.8 s on the calendar after a start.
            # Read them now, off the request path, so the first ask is warm.
            threading.Thread(target=_warm_git, args=(app.state.store,), daemon=True).start()
            # The system monitor samples the machine in the background; it
            # reads its own settings and idles while they say off.
            try:
                if not run_monitor:
                    raise RuntimeError("off for this server (SP_SANDBOX)")
                from .sysmon import Monitor
                app.state.monitor = Monitor(app.state.settings.data_root)
                app.state.monitor.start()
            except Exception as exc:  # noqa: BLE001 — no psutil, no monitor; the rest runs
                log.warning("system monitor not started: %s", exc)
            # The smart timer reads the operator's idle time and pauses their
            # timers: the served app only, never a sandbox's demo data.
            if run_monitor:
                from . import timeauto
                timeauto.of(app).start()
                # Old Claude Code chats get their answers' ends from the
                # transcripts, once, off the request path (turntimes.py).
                threading.Thread(target=_backfill_turn_times, args=(app.state.settings.data_root,), daemon=True).start()
        try:
            yield
        finally:
            for w in app.state.watchers:
                w.stop()
            mon = getattr(app.state, "monitor", None)
            if mon is not None:
                mon.stop()
            timer = getattr(app.state, "timer", None)
            if timer is not None:
                timer.stop()
            terminal.close_all()
            for name in ("backup_task", "memory_task"):
                task = getattr(app.state, name, None)
                if task is not None:
                    task.cancel()

    app = FastAPI(
        title="Slightly Parallel API",
        version="1.0.0",
        description=(
            "Read-mostly projection of an agents filesystem. The filesystem "
            "is the source of truth; DuckDB views are a disposable cache."
        ),
        lifespan=lifespan,
    )
    app.state.store = store
    app.state.settings = settings
    app.state.operator_token = load_operator_token(settings.data_root)
    # The terminal's token, made once before the first request, new at every
    # start: two first asks made two before.
    terminal.token_of(app)
    app.state.monitor = None
    app.state.timer = None
    # Where the agent prompt files live (the repo); tests point it elsewhere.
    app.state.prompt_root = Path(prompt_root) if prompt_root else None
    app.state.watchers = []
    app.state.backup_task = None

    @app.exception_handler(ValueError)
    def _bad_value(request: Request, exc: ValueError) -> JSONResponse:
        """A ``ValueError`` is the caller's mistake, not a server fault.

        Eighteen routers already catch one and answer 422 with its own
        sentence. The ones that do not — a date parser deep in a helper, a
        validator in a library — handed it to the catch-all below, and a
        malformed date came back as an opaque ``error_id`` and a 500. This
        handler is the floor under all of them: the same 422 and the same
        ``detail`` key, so nothing a library raises is ever a 500 again.
        A router that wants a different status still catches it itself.
        """
        log.info(
            "invalid value: %s %s: %s", request.method, request.url.path, exc,
            extra={"method": request.method, "path": request.url.path,
                   "status": 422, "client": request.client.host if request.client else None},
        )
        return JSONResponse(
            status_code=422, content={"detail": str(exc) or f"invalid value in {request.method} {request.url.path}"}
        )

    @app.exception_handler(Exception)
    def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        """Any bug becomes a traceable JSON error, never a bare 500.

        The id ties what the user sees to the full traceback in the log, so
        "the page broke" is diagnosable from either end.
        """
        error_id = uuid4().hex[:8]
        log.error(
            "unhandled error %s: %s %s",
            error_id, request.method, request.url.path,
            exc_info=exc,
            extra={"method": request.method, "path": request.url.path,
                   "status": 500, "client": request.client.host if request.client else None},
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": f"internal error — id {error_id} (see server log)",
                "error_id": error_id,
            },
        )

    def swap_data_root(new_root: Path) -> None:
        """Re-point the running app at another data root, no restart needed.

        Stops the old watchers, materialises a fresh ViewStore, swaps
        ``app.state``, and starts watchers on the new root. Requests only
        ever read the store/settings through ``app.state``, so the swap is
        visible immediately.
        """
        for w in app.state.watchers:
            w.stop()
        new_store = ViewStore(data_root=new_root)
        app.state.store = new_store
        app.state.settings = dataclasses.replace(
            app.state.settings, data_root=new_root
        )
        app.state.watchers = (
            _start_watchers(new_root, new_store) if watch else []
        )
        # A root switched into at runtime gets what a root started on gets,
        # in create_app's order: its example entries, then the skills
        # Slightly Parallel ships with — now, not at the next restart.
        if os.environ.get("SP_EXAMPLES", "1") != "0":
            try:
                from .examples import seed as seed_examples
                seed_examples(new_store)
            except OSError as exc:
                log.warning("examples skipped on swap: %s", exc)
        try:
            from .skilllib import seed_builtin_skills
            seed_builtin_skills(new_store)
        except (OSError, ValueError) as exc:
            log.warning("built-in skills skipped on swap: %s", exc)
        install_builtin_skills()
        offer_example()
        # The monitor keeps its record in the data root: follow it there.
        old_mon = getattr(app.state, "monitor", None)
        if old_mon is not None:
            old_mon.stop()
            from .sysmon import Monitor
            app.state.monitor = Monitor(new_root)
            app.state.monitor.start()
        # So does the smart timer: it held the old store and the old root,
        # and went on pausing and writing entries there until a restart.
        old_timer = getattr(app.state, "timer", None)
        if old_timer is not None:
            was_running = getattr(old_timer, "_thread", None) is not None
            old_timer.stop()
            from . import timeauto
            app.state.timer = None
            new_timer = timeauto.of(app)
            if was_running:
                new_timer.start()
        # Four module caches are keyed on the old root's facts and one
        # repo's HEAD; each has a ``forget()`` written for exactly this
        # moment (the search index held the old root's text until now).
        try:
            from . import gitwork, projectfacts, repomap, searchlib
            gitwork.forget()
            projectfacts.forget()
            repomap.forget()
            searchlib.forget()
        except OSError as exc:  # pragma: no cover — a cache that will not clear
            log.warning("caches not cleared on swap: %s", exc)
        log.info("data root swapped to %s", new_root)

    app.state.swap_data_root = swap_data_root

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "HEAD", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["ETag"],
    )
    app.add_middleware(AgentsViaMcp, app_ref=app)
    app.add_middleware(OperatorCookie, app_ref=app)
    # The whole-history chat view is 3.6 MB of text in one answer and the
    # sessions list 170 KB; both go down to a fifth. Small answers are left
    # as they are.
    app.add_middleware(GZipMiddleware, minimum_size=2048)
    # Added last, so it is asked first.
    app.add_middleware(OwnPagesOnly, app_ref=app)

    @app.middleware("http")
    async def _access_log(request: Request, call_next):  # type: ignore[override]
        t0 = time.perf_counter()
        try:
            resp = await call_next(request)
            status = resp.status_code
        except Exception:
            log.exception(
                "request failed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": 500,
                    "client": request.client.host if request.client else None,
                },
            )
            raise
        ms = int((time.perf_counter() - t0) * 1000)
        # A slow one is named, so the health page and the file say so
        # without anyone summing the numbers.
        log.log(
            logging.WARNING if ms >= logbook.SLOW_REQUEST_MS else logging.INFO,
            "req",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": status,
                "ms": ms,
                "client": request.client.host if request.client else None,
                **({"why": "slow"} if ms >= logbook.SLOW_REQUEST_MS else {}),
            },
        )
        return resp

    # Order matters: specific routes (files/heatmap, tasks/{id}/events)
    # must register before the generic /api/<base>/{id} lens routes.
    app.include_router(core.router)
    app.include_router(doctor.router)
    app.include_router(schema_api.router)
    app.include_router(logs.router)
    app.include_router(marks.router)
    app.include_router(done.router)
    app.include_router(undo.router)
    app.include_router(stats.router)
    app.include_router(analytics.router)
    app.include_router(monitor.router)
    app.include_router(settings_api.router)
    app.include_router(setup.router)
    app.include_router(scans.router)
    app.include_router(sessions_api.router)
    app.include_router(time_tracking.router)
    app.include_router(files_extra.router)
    app.include_router(architecture.router)
    app.include_router(prompts.router)
    app.include_router(promptlib.router)
    app.include_router(tasks_extra.router)
    app.include_router(task_mentions.router)
    app.include_router(task_links.router)
    app.include_router(sprints.router)
    app.include_router(sprint_deck.router)
    app.include_router(evidence.router)
    app.include_router(agents_extra.router)
    app.include_router(boards.router)
    app.include_router(sets.router)
    app.include_router(integrate.router)
    app.include_router(prefs.router)
    app.include_router(story.router)
    app.include_router(story_release.router)
    app.include_router(calendar.router)
    app.include_router(snippets_extra.router)
    app.include_router(tasks_extra.detail_router)
    app.include_router(keep.router)
    app.include_router(standups.router)  # before the lens router: /api/standups/material
    app.include_router(skills.router)
    app.include_router(artifacts.router)
    app.include_router(lenses.router)
    app.include_router(timelapse.router)
    app.include_router(tour.router)
    app.include_router(backup_router.router)

    # The terminal is always routed and answers only while it is switched on
    # (setting terminal.enabled, or SP_ENABLE_TERMINAL); the token is
    # made here and handed to Slightly Parallel's own pages (routers/terminal.py).
    app.include_router(terminal.build_router(settings))

    _mount_frontend(app)
    return app


PAGE_HEADERS = {"X-Frame-Options": "SAMEORIGIN", "Content-Security-Policy": "frame-ancestors 'self'"}


def _mount_frontend(app: FastAPI) -> None:
    """Serve the production frontend build when present (SPA fallback)."""
    frontend_dist = _REPO_ROOT / "frontend" / "dist"
    dev_ui = (os.environ.get("SP_UI_DEV") or "").strip().rstrip("/")
    if dev_ui:
        # The hot-reload start (sp.py with no --prod): the UI lives on the
        # Vite port, and a page asked of this port goes there, with its
        # path and query. frontend/dist here is whatever was built last.
        from fastapi.responses import RedirectResponse

        @app.get("/{full_path:path}", include_in_schema=False)
        def _to_dev_ui(full_path: str, request: Request):
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail=f"no API route {full_path}")
            query = f"?{request.url.query}" if request.url.query else ""
            return RedirectResponse(f"{dev_ui}/{full_path}{query}", status_code=307)

        log.info("hot-reload UI at %s: page requests are sent there", dev_ui)
        return
    if not frontend_dist.exists():
        @app.get("/", include_in_schema=False)
        def _root() -> dict[str, Any]:
            return {
                "name": "Slightly Parallel API",
                "docs": "/docs",
                "health": "/api/health",
                "note": f"frontend build not present at {frontend_dist}",
            }
        return

    index_file = frontend_dist / "index.html"
    dist_resolved = frontend_dist.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    def _spa_fallback(full_path: str):
        if full_path.startswith("api/"):
            # A sentence, like every other 404 in the backend: the SPA
            # fallback must not answer an unknown API path with a bare
            # "Not Found" that reads like the page failed to load.
            raise HTTPException(
                status_code=404, detail=f"no API route {full_path}"
            )
        candidate = (frontend_dist / full_path).resolve()
        # Containment check — the URL path must never escape dist/.
        if (
            full_path
            and candidate.is_file()
            and dist_resolved in candidate.parents
        ):
            return FileResponse(candidate, headers=PAGE_HEADERS if candidate.suffix == ".html" else None)
        # The page itself is never drawn inside another site's frame: one
        # framed under a decoy, a click there would be the operator's own
        # (clickjacking). Slightly Parallel's own frames stay allowed.
        return FileResponse(index_file, headers=PAGE_HEADERS)

    # No /assets mount: the route above is registered first and answers
    # every path, the built assets included, so a mount after it never ran.
    log.info("serving static frontend from %s (SPA fallback active)", frontend_dist)


# ---------------------------------------------------------------------------
# Module-level app for `uvicorn backend.server:app` / `python -m backend.server`
# ---------------------------------------------------------------------------

# SP_SANDBOX=1 — a server for tests (the browser tests start this very
# app on the demo fixtures): it neither installs skills into the home folder
# nor runs the system monitor, so it leaves nothing outside its data root and
# nothing new inside it.
#
# The app is built on first use of ``backend.server.app`` (uvicorn's
# getattr), not on import: importing this module for create_app or a helper
# must not settle on the default data folder and write into it.
_app: FastAPI | None = None


def __getattr__(name: str) -> Any:
    if name == "app":
        global _app
        if _app is None:
            sandbox = os.environ.get("SP_SANDBOX") == "1"
            _app = create_app(autoinstall_skills=not sandbox, run_monitor=not sandbox)
        return _app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def main() -> None:  # pragma: no cover
    import uvicorn

    settings = Settings.from_env()
    refusal = lan_refusal(settings.host)
    if refusal:
        raise SystemExit(refusal)
    uvicorn.run(
        "backend.server:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_config=None,  # keep our JSON formatter
    )


if __name__ == "__main__":  # pragma: no cover
    main()
