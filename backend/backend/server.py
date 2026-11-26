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
import errno
import json
import logging
import os
import re
import threading
import time
import urllib.parse
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator

from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .server_address import DEFAULT_PORT
from . import __version__, app_settings, backup as backup_engine, logbook, memberships
from .entitylib import project_codes
from .csvio import DamagedFile
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
    entrypoints,
    notes,
    keep,
    lenses,
    logs,
    marks,
    memberships as memberships_routes,
    messages as messages_routes,
    pins,
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
    termlog as termlog_routes,
    termwin as termwin_routes,
    time_tracking,
    evidence,
    calendar,
    cores,
    publish,
    story_release,
    usage,
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

MIN_GZIP_BODY_BYTES = 2048


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


#: Held by the server that serves a data folder (the served app, not a
#: test's): a second one on the same folder is refused, since two of them
#: would each rebuild, back up and time the same files. The lock goes with
#: the process, so a crash leaves nothing to clean; backups skip *.lock.
SERVER_LOCK = "server.lock"
ROOT_TAKEN = ("another Slightly Parallel server is using the data folder {root}. "
              "Stop that one (python sp.py down in its folder), or point this one at another data folder.")


def hold_data_root(root: Path) -> Any | None:
    """The open, locked ``server.lock`` of ``root``; None when another
    process holds it."""
    from .hookshared import try_lock
    root.mkdir(parents=True, exist_ok=True)
    fh = open(root / SERVER_LOCK, "a+", encoding="utf-8")
    if try_lock(fh):
        return fh
    fh.close()
    return None


def _backfill_turn_times(root: Path) -> None:
    try:
        from .turntimes import backfill
        n = backfill(root)
        if n:
            log.info("turn times: %d answers timed from the transcripts", n)
    except Exception:  # noqa: BLE001 — a missing time is shown as an estimate
        log.exception("turn times not backfilled")


def _backfill_usage(root: Path) -> None:
    from .usagebackfill import run_once
    run_once(root)


def _backfill_from_logs(root: Path) -> None:
    """The start's backfills from the tools' own logs, one after the other
    in one thread: the helper chats recorded before the hooks marked them
    (helperbackfill.py) first, so their commands stop acting soonest; the
    answers' ends; then the tokens of the chats recorded before the hooks
    kept them (usagebackfill.py)."""
    from .helperbackfill import run_once as mark_helpers
    t0 = time.perf_counter()
    mark_helpers(root)
    _backfill_turn_times(root)
    _backfill_usage(root)
    log.info("start backfills finished", extra={"ms": int((time.perf_counter() - t0) * 1000)})


def _start_watchers(root: Path, store: ViewStore) -> list[Watcher]:
    """Watch a data root: one recursive watcher on the root itself.

    Mutual CSVs, *_details folders, projects/ and snapshots/ all live under
    the root, so one watcher sees every write once. There were three, with
    projects/ and snapshots/ watched twice over — every hook write started
    two or three rebuilds — and the debounce coalesces the rest.
    """
    (root / "snapshots").mkdir(parents=True, exist_ok=True)
    watchers = [Watcher(root, on_change=store.rebuild, recursive=True)]
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


#: How often a message that waits is tried in its chat's terminal again.
MESSAGE_TICK_SECONDS = 3.0


async def _message_loop(app: FastAPI) -> None:
    """Messages between agents that could not be typed into their chat's
    terminal (the operator was typing, the agent showed a menu): tried
    again, off the request path. A round with nothing waiting is a stat."""
    from . import msgdeliver
    while True:
        await asyncio.sleep(MESSAGE_TICK_SECONDS)
        try:
            await asyncio.to_thread(msgdeliver.retry_waiting, app.state.store.data_root)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — one failed round must not end the loop
            log.exception("waiting messages not tried")


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
                "task_story", "task_move", "interpret", "skill_draft", "artifact_write", "doc_version",
                "architecture_page", "map_write", "standup_postpone", "undo_propose", "undo_apply", "undo_restore", "task_commits",
                "task_done", "next_tasks",
                "core_new", "core_note", "core_attach", "core_off", "publish_attach", "publish_write", "usage_prices_write",
                "entrypoint_stop", "entrypoint_way", "entrypoint_shot", "entrypoint_ask", "entrypoint_answer",
                "task_topic", "carry_brief", "note_write", "note_image", "message", "messages")
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
    r"/api/tasks/[^/]+/(update|report|evidence|story|commits|move)",
    r"/api/standups/(claim|postpone)",
    r"/api/architecture/page",
    r"/api/map",
    r"/api/undo/(propose|apply|restore)",
    r"/api/done-tags",
    r"/api/next-tasks/make",
    r"/api/cores",
    r"/api/cores/[^/]+/(notes|links|off)",
    r"/api/publishing/cards/[^/]+/write",
    r"/api/entrypoints/[^/]+/(stops|ways|shots)",
    r"/api/entrypoints/(ask|answer)",
    r"/api/tasks/[^/]+/topic",
    r"/api/usage/prices",
    r"/api/carries/brief",
    r"/api/notes/write",
    r"/api/notes/[^/]+/images",
    r"/api/messages",
    r"/api/messages/inbox",
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


_lens_creates: "re.Pattern[str] | None" = None


def lens_create(path: str) -> bool:
    """Is ``path`` a lens's create (POST /api/<base>)? There the translator's
    stamp (created_date, created_time) is in the body, and a lens's own
    columns are checked by entitylib."""
    global _lens_creates
    if _lens_creates is None:
        from .routers.schema_api import build_schema
        bases = sorted({re.escape(str(l["base"])) for l in build_schema()["lenses"]})
        _lens_creates = re.compile(rf"/api/({'|'.join(bases)})")
    return _lens_creates.fullmatch(path) is not None


def stamped_in_body(path: str, data: Any) -> list[str]:
    """Identity an agent's body names besides who it is (agent_id/actor):
    refused by name, as the MCP tools refuse it (mcp_args.IDENTITY). Routers
    used to drop it without a word (tk_0b8a32d2)."""
    if not isinstance(data, dict) or not mcp_may_write(path):
        # Outside the MCP's writes the routes keep their own rules: the
        # page's star names the chat's session, the prompt library refuses
        # an agent with its own reason.
        return []
    from . import mcp_args
    # A lens create's own dates are the body's: the translator stamps them
    # there. The task, scan and architecture creates have routes of their
    # own and dropped the rest without a word.
    own = ("agent_id", "actor", *(("created_date", "created_time") if lens_create(path) else ()))
    return sorted(k for k in data if k in mcp_args.STAMPED and k not in own and data[k] not in (None, ""))


def nested_in_body(path: str, data: Any) -> str:
    """The refusal for identity inside an object of an agent's body on the
    MCP's writes (an evidence item, a map row): it was dropped without a
    word (tk_0b8a32d2). The same reading as the translator's."""
    if not isinstance(data, dict) or not mcp_may_write(path):
        return ""
    from . import mcp_args
    hit = mcp_args.nested_identity(data)
    if hit is None:
        return ""
    key, where = hit
    if key == "project":
        return f"put project next to the other fields, not inside {where}"
    return f"{mcp_args.stamped_refusal([key])} (inside {where})"


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
    return f"sp_operator_{getattr(app.state.settings, 'port', DEFAULT_PORT)}"


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


def _task_project(store: ViewStore, task_id: str) -> tuple[str, ...] | None:
    """The projects a task is worked in: its project first, then the codes
    of its ``projects`` (the operator's answer (a) to B3: a member of any of
    them works on it, as the boards show it there)."""
    from .entitylib import project_codes
    row = store.query_one("SELECT project, projects FROM tasks_mutual WHERE id = ?", (task_id,))
    if row is None:
        return None
    main = str(row.get("project") or "")
    return tuple(dict.fromkeys([main, *project_codes(row.get("projects"))]))


def _via_task(sql: str) -> "Any":
    """A row that belongs to a task (its note, link, evidence item): the task's project."""
    def resolve(store: ViewStore, rid: str) -> tuple[str, ...] | None:
        row = store.query_one(sql, (rid,))
        return None if row is None else _task_project(store, str(row.get("task_id") or ""))
    return resolve


def _link_projects(store: ViewStore, rid: str) -> list[tuple[str, ...]] | None:
    """A link joins two tasks: each task's projects, both checked."""
    row = store.query_one("SELECT from_id, to_id FROM task_links_mutual WHERE id = ?", (rid,))
    if row is None:
        return None
    got = [_task_project(store, str(row.get(k) or "")) for k in ("from_id", "to_id")]
    return [p for p in got if p is not None]


def _in_view(view: str) -> "Any":
    def resolve(store: ViewStore, rid: str) -> str | None:
        row = store.query_one(f"SELECT project FROM {view} WHERE id = ?", (rid,))
        return None if row is None else str(row.get("project") or "")
    return resolve


def _core_project(store: ViewStore, rid: str) -> str | None:
    from .corelib import CORES_FILE
    from .csvio import read_rows
    row = next((r for r in read_rows(store.data_root / CORES_FILE) if r.get("id") == rid), None)
    return None if row is None else str(row.get("project") or "")


def _lens_project(store: ViewStore, rid: str, base: str) -> str | None:
    from .entities import ENTITIES
    ent = next((e for e in ENTITIES.values() if e.view.removesuffix("_mutual") == base.replace("-", "_")), None)
    if ent is None or "project" not in ent.columns:
        return None
    return _in_view(ent.view)(store, rid)


#: The writes on one row by its id, and how the gate finds that row's project
#: (note nt_258a7ed7 §2: writes by id are checked against the row). Tried in
#: order; the first pattern that matches decides. A row not found passes: its
#: router answers 404 (or, for a new id, the create is checked by its body).
#: Notes' pictures, publishing cards, entry point stops and ways and the lens
#: updates check their row in their libraries too (memberships.may_write_row).
_ROW_WRITES: tuple[tuple["re.Pattern[str]", str, Any], ...] = (
    (re.compile(r"/api/tasks/notes/([^/]+)/.+"), "task",
     _via_task("SELECT task_id FROM task_notes_mutual WHERE id = ?")),
    (re.compile(r"/api/tasks/links/([^/]+)/.+"), "task", _link_projects),
    (re.compile(r"/api/tasks/evidence/([^/]+)/.+"), "task",
     _via_task("SELECT task_id FROM task_evidence_mutual WHERE id = ?")),
    (re.compile(r"/api/tasks/([^/]+)/.+"), "task", _task_project),
    (re.compile(r"/api/cores/([^/]+)/.+"), "core", _core_project),
    (re.compile(r"/api/docs/([^/]+)/.+"), "document", _in_view("docs_mutual")),
    (re.compile(r"/api/(visions|rules|problems|entrypoints|artifacts|skills)/([^/]+)/.+"), "",
     None),
)
#: The MCP write paths that name a row by its id and are checked in their
#: libraries instead (the guard test reads both lists).
ROW_CHECKED_IN_LIBRARIES: tuple[str, ...] = (
    "/api/publishing/cards/", "/api/notes/", "/api/entrypoints/",
)


#: What finish-a-task writes after a #done: on a task the operator's #done
#: closed in this chat, these go through in any project (answer 2,
#: dc_f6ec18c8: an id next to #done closes a task in any project).
_DONE_FOLLOWUP = re.compile(r"/api/tasks/([^/]+)/(report|evidence|story)")


def closed_here(store: ViewStore, actor: str, path: str) -> bool:
    """Did the operator's #done in this agent's chat close the task this
    report, evidence or story is for? Only a #done that moved it (done.csv
    result «moved»): one naming a task already done or archived closed
    nothing, and gives no rights on it."""
    hit = _DONE_FOLLOWUP.fullmatch(path)
    if hit is None:
        return False
    from . import donelib
    task_id = urllib.parse.unquote(hit.group(1))
    return any(r.get("agent_id") == actor and r.get("task_id") == task_id
               and r.get("result") == "moved" for r in donelib.rows(store))


def row_of_write(store: ViewStore, path: str) -> tuple[list[tuple[str, ...]], str] | None:
    """``(groups, what)`` of the row a by-id write names: one group of
    project codes per row (a task's project and projects; a link's two
    tasks are two groups), a member of any code of a group may write on
    that row. None: no such route, or no such row."""
    for pattern, what, resolve in _ROW_WRITES:
        hit = pattern.fullmatch(path)
        if hit is None:
            continue
        if resolve is None:
            base, rid = hit.group(1), urllib.parse.unquote(hit.group(2))
            got = _lens_project(store, rid, base)
            what = {"entrypoints": "topic"}.get(base, base.rstrip("s"))
        else:
            got = resolve(store, urllib.parse.unquote(hit.group(1)))
        if got is None:
            return None
        groups = got if isinstance(got, list) else [got]
        return [g if isinstance(g, tuple) else (g,) for g in groups], what
    return None
PROJECT_SHAPE = "project is one project code, as text"
PROJECTS_SHAPE = "projects is project codes: comma-separated text or a list of texts"


def membership_refusal(store: ViewStore, path: str, data: Any, actor: str) -> tuple[int, str] | None:
    """Why an agent's write may not go where it names (tk_d1d25a4d step 3,
    note nt_258a7ed7 §2): ``(status, line)``, or None.

    A create's ``project`` and every code in its ``projects`` must be the
    agent's member projects (memberships.may_write); a write on a task by
    its id must be on a task of a member project (the operator's answer 1,
    dc_f59e2918). Writes on other rows by id are checked in their libraries
    (memberships.may_write_row)."""
    if not isinstance(data, dict):
        return None
    codes: list[str] = []
    project = data.get("project")
    if project not in (None, ""):
        if not isinstance(project, str):
            return 422, PROJECT_SHAPE
        codes.append(project.strip())
    raw = data.get("projects")
    if raw not in (None, ""):
        if not (isinstance(raw, str) or (isinstance(raw, list) and all(isinstance(x, str) for x in raw))):
            return 422, PROJECTS_SHAPE
        codes += [c for c in project_codes(raw) if c not in codes]
    for code in codes:
        ok, line = memberships.may_write(store, actor, code)
        if not ok:
            return 403, line
    row = row_of_write(store, path)
    if row is not None and closed_here(store, actor, path):
        return None
    for group in (row[0] if row is not None else []):
        ok, line = memberships.may_write_row(store, actor, group[0], row[1] if row else "", also=group[1:])
        if not ok:
            return 403, line
    if _LINK_CREATE.fullmatch(path) and isinstance(data.get("to"), str):
        # A link joins two tasks: the other end is checked as the delete checks both.
        other = _task_project(store, data["to"].strip())
        if other is not None:
            ok, line = memberships.may_write_row(store, actor, other[0], "task", also=other[1:])
            if not ok:
                return 403, line
    return None


_LINK_CREATE = re.compile(r"/api/tasks/[^/]+/link")


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
        if isinstance(data, dict):
            claims = {str(data.get(k) or "").strip() for k in ("actor", "agent_id")}
            agents = sorted(c for c in claims if deps.is_agent(c))
            if len(agents) > 1:
                # Two agents named as the writer: the actor used to win in
                # silence (tk_0b8a32d2). One writer, one name.
                await JSONResponse({"detail": f"actor and agent_id name different agents ({', '.join(agents)}): "
                                              "send one of them"}, status_code=422)(scope, replay, send)
                return
        if via_mcp:
            # The MCP translator stamps the agent on every write. The mark
            # with no agent is a hand-made request: anyone can send the
            # header, and it is not a way to write as the operator.
            if not deps.is_agent(actor):
                await JSONResponse({"detail": MCP_NEEDS_AGENT}, status_code=403)(scope, replay, send)
                return
        elif actor and deps.is_agent(actor) and self._enforced():
            # The same status every other refusal of an agent carries
            # (routers/deps.refuse_agent) — this one cannot raise, it is
            # ASGI below FastAPI, so it spells the answer by hand.
            resp = JSONResponse(
                {"detail": MCP_REFUSAL}, status_code=deps.AGENT_REFUSED
            )
            await resp(scope, replay, send)
            return
        elif not deps.is_agent(actor) and not operator:
            # A write that names no agent is the operator's, and the
            # operator's pages carry the cookie (OperatorCookie). Anything
            # else on this computer posting as the operator is refused.
            await JSONResponse({"detail": OPERATOR_REFUSAL}, status_code=403)(scope, replay, send)
            return
        if deps.is_agent(actor):
            # Every agent writer, through the MCP or (agents.mcp_only off)
            # over plain HTTP: the projects it names must be its own.
            refused = membership_refusal(self.app_ref.state.store, path, data, actor)
            if refused is not None:
                await JSONResponse({"detail": refused[1]}, status_code=refused[0])(scope, replay, send)
                return
            if memberships.agent_view(self.app_ref.state.store, actor) is None:
                # A writer Slightly Parallel has no chat of: the project gate
                # refused it, a write that names no project took it as it came
                # (usage prices, messages; tk_0b8a32d2).
                await JSONResponse({"detail": memberships.UNINDEXED.format(agent=actor)},
                                   status_code=403)(scope, replay, send)
                return
            stray = stamped_in_body(path, data)
            if stray:
                from . import mcp_args
                await JSONResponse({"detail": mcp_args.stamped_refusal(stray)}, status_code=422)(scope, replay, send)
                return
            nested = nested_in_body(path, data)
            if nested:
                await JSONResponse({"detail": nested}, status_code=422)(scope, replay, send)
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
    # Entry points written before ways in existed: their ways read out of
    # the record once (entrypointlib.migrate), never on the shipped fixtures.
    if root.resolve() != FIXTURES.resolve():
        try:
            from .entrypointlib import migrate as migrate_entrypoints
            got = migrate_entrypoints(root)
            if got["migrated"]:
                log.info("entry points migrated: %d, ways in read from their records: %d",
                         len(got["migrated"]), got["ways"])
        except (OSError, RuntimeError) as exc:
            log.warning("entry point migration skipped: %s", exc)
    # Time entries written before their moments carried a UTC offset get it,
    # once (timelib.migrate_offsets, tk_3a363c87; the file is copied to the
    # backup folder first). Never on the shipped fixtures.
    if root.resolve() != FIXTURES.resolve():
        try:
            from .timelib import migrate_offsets
            got = migrate_offsets(root)
            if got["changed"]:
                log.info("time entries migrated: %d of %d rows given their UTC offset (copy before: %s)",
                         got["changed"], got["rows"], got["backup"])
        except (OSError, RuntimeError, ValueError, DamagedFile) as exc:
            log.warning("time entry migration skipped: %s", exc)
    store = ViewStore(data_root=root)
    # The moments #now, #done and #think became commands here, made now if
    # missing (nowlib.stamp_starts); never on the shipped fixtures.
    if root.resolve() != FIXTURES.resolve():
        from .nowlib import stamp_starts
        stamp_starts(root)
    # Publish cards whose task the server used to guess at every read: the
    # sound guesses frozen into stored links once (publishlib.migrate).
    if root.resolve() != FIXTURES.resolve():
        try:
            from .publishlib import migrate as migrate_publish
            got = migrate_publish(store)
            if got["frozen"] or got["dropped"]:
                log.info("publish cards migrated: %d task links kept, %d of another project dropped",
                         got["frozen"], got["dropped"])
        except (OSError, RuntimeError, ValueError) as exc:
            log.warning("publish migration skipped: %s", exc)
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
            held = hold_data_root(app.state.settings.data_root)
            if held is None:
                log.error(ROOT_TAKEN.format(root=app.state.settings.data_root))
                raise RuntimeError(ROOT_TAKEN.format(root=app.state.settings.data_root))
            app.state.root_lock = held
            app.state.watchers = _start_watchers(
                app.state.settings.data_root, app.state.store
            )
            app.state.backup_task = asyncio.create_task(_backup_loop(app))
            app.state.memory_task = asyncio.create_task(_memory_loop())
            # Messages between agents that wait for their chat's terminal
            # (msgdeliver.py): tried again every few seconds.
            app.state.message_task = asyncio.create_task(_message_loop(app))
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
            # timers: the served app only, never a sandbox's demo data — but
            # SP_SMART_TIMER=1 runs it on a sandbox too (the terminal window's
            # end-to-end suite checks that typing there counts).
            if run_monitor or os.environ.get("SP_SMART_TIMER") == "1":
                from . import timeauto
                timeauto.of(app).start()
            if run_monitor:
                # Old Claude Code chats get their answers' ends from the
                # transcripts, once, off the request path (turntimes.py);
                # then old chats their tokens, once each (usagebackfill.py).
                threading.Thread(target=_backfill_from_logs, args=(app.state.settings.data_root,), daemon=True).start()
                # A folder connected before the status line existed gets it
                # now, beside its hooks: Claude Code's plan limits need it.
                from .routers.setup import ensure_statuslines
                threading.Thread(target=ensure_statuslines, args=(app.state.settings.data_root,), daemon=True).start()
                # Codex's plan limits, read on a schedule through codex
                # app-server (no chat, no tokens): the Usage page's Codex row.
                from . import toolwaits
                if toolwaits.enabled():
                    try:
                        collector = toolwaits.Collector(app.state.settings.data_root)
                        collector.start()
                        app.state.wait_collector = collector
                    except (OSError, RuntimeError) as exc:
                        log.warning("tool wait collection unavailable: %s", exc)
                from .codexlimits import Poller
                app.state.codex_poller = Poller(app.state.settings.data_root)
                app.state.codex_poller.start()
        try:
            yield
        finally:
            collector = getattr(app.state, "wait_collector", None)
            if collector is not None:
                collector.stop()
            for w in app.state.watchers:
                w.stop()
            mon = getattr(app.state, "monitor", None)
            if mon is not None:
                mon.stop()
            poller = getattr(app.state, "codex_poller", None)
            if poller is not None:
                poller.stop()
            timer = getattr(app.state, "timer", None)
            if timer is not None:
                timer.stop()
            terminal.close_all()
            held = getattr(app.state, "root_lock", None)
            if held is not None:
                held.close()
                app.state.root_lock = None
            for name in ("backup_task", "memory_task", "message_task"):
                task = getattr(app.state, name, None)
                if task is not None:
                    task.cancel()

    app = FastAPI(
        title="Slightly Parallel API",
        version=__version__,
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

    @app.exception_handler(DamagedFile)
    def _damaged(request: Request, exc: DamagedFile) -> JSONResponse:
        log.warning("refused: %s", exc, extra={"method": request.method, "path": request.url.path, "status": 409})
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    # The disk or the folder refuses a write: what to do, not an error id.
    # Atomic writes leave the old file as it was.
    _DISK = {errno.ENOSPC: (507, "The disk is full: nothing was written. Free some space and try again."),
             errno.EROFS: (503, "The data folder is read-only: nothing was written. Check where it is mounted."),
             errno.EACCES: (503, "The data folder cannot be written (permission denied): nothing was written. Check its permissions."),
             errno.EPERM: (503, "The data folder cannot be written (not permitted): nothing was written. Check its permissions.")}
    if hasattr(errno, "EDQUOT"):
        _DISK[errno.EDQUOT] = (507, "The disk quota is used up: nothing was written. Free some space and try again.")

    @app.exception_handler(OSError)
    def _os_error(request: Request, exc: OSError) -> JSONResponse:
        known = _DISK.get(exc.errno or -1)
        if known is None:
            raise exc               # any other OSError is a bug: the catch-all below takes it
        log.warning("write refused by the system: %s %s: %s", request.method, request.url.path, exc,
                    extra={"method": request.method, "path": request.url.path, "status": known[0]})
        return JSONResponse(status_code=known[0], content={"detail": known[1]})

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
        held = None
        if watch:
            held = hold_data_root(new_root)
            if held is None:
                raise ValueError(ROOT_TAKEN.format(root=new_root))
        for w in app.state.watchers:
            w.stop()
        if held is not None:
            old = getattr(app.state, "root_lock", None)
            app.state.root_lock = held
            if old is not None:
                old.close()
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
    app.add_middleware(GZipMiddleware, minimum_size=MIN_GZIP_BODY_BYTES)
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
    app.include_router(pins.router)
    app.include_router(messages_routes.router)
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
    app.include_router(memberships_routes.router)
    app.include_router(boards.router)
    app.include_router(sets.router)
    app.include_router(integrate.router)
    app.include_router(prefs.router)
    app.include_router(story.router)
    app.include_router(story_release.router)
    app.include_router(calendar.router)
    app.include_router(cores.router)
    app.include_router(publish.router)
    app.include_router(usage.router)
    app.include_router(snippets_extra.router)
    app.include_router(tasks_extra.detail_router)
    app.include_router(keep.router)
    app.include_router(entrypoints.router)  # before the lens router: /api/entrypoints/desk
    app.include_router(notes.router)  # before the lens router: /api/notes/feed, /api/notes/write
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
    # The terminal's own log (termlog.py): answers whether the terminal is on or not.
    app.include_router(termlog_routes.router)
    # The window's tab strip (termwin.py): titles, chat facts, the "+" menu's reads.
    app.include_router(termwin_routes.router)

    _mount_frontend(app)
    return app


PAGE_HEADERS = {
    "X-Frame-Options": "SAMEORIGIN",
    "Content-Security-Policy": "frame-ancestors 'self'",
    "Cache-Control": "no-cache",
}


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
