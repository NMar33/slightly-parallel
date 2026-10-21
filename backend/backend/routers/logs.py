"""The health page's data: the server's log, summed up and as a tail.

``GET /api/logs`` answers with the summary (uptime, data, rebuilds, requests
by path, errors) and the last lines; ``GET /api/logs/text`` is the same as
plain text, which is what the page's copy button hands to the clipboard and
what ``curl`` gives a person at a terminal.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from .. import logbook
from ..db import ViewStore
from .deps import get_store
from .terminal import enabled as terminal_on

router = APIRouter()

LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


def summary(store: ViewStore, request: Request) -> dict[str, Any]:
    s = logbook.stats()
    log_file = logbook.LOG_FILE
    try:
        size = log_file.stat().st_size if log_file else 0
    except OSError:
        size = 0
    fs = store.view_mtime
    return {
        **s,
        "started_at": logbook.STARTED_AT,
        "uptime_s": int(time.time() - logbook.STARTED_AT),
        "data_root": str(store.data_root),
        "log_file": str(log_file) if log_file else "",
        "log_file_bytes": size,
        "view_age_ms": max(0, int((time.time() - fs) * 1000)) if fs else 0,
        "load_errors": list(getattr(store, "load_errors", [])),
        "stamps": store.stamps,
        **logbook.process_memory(),
        "slow_request_ms": logbook.SLOW_REQUEST_MS,
        # The answer /api/terminal/state gives: the variable or the switch.
        "terminal_enabled": terminal_on(request.app),
    }


@router.get("/api/logs")
def logs(
    request: Request,
    level: str = Query("INFO"),
    limit: int = Query(300, ge=1, le=logbook.RING_SIZE),
    store: ViewStore = Depends(get_store),
) -> dict[str, Any]:
    lvl = level.upper() if level.upper() in LEVELS else "INFO"
    return {"summary": summary(store, request), "records": logbook.RING.tail(limit, lvl)}


@router.get("/api/logs/text", response_class=PlainTextResponse)
def logs_text(
    request: Request,
    level: str = Query("INFO"),
    limit: int = Query(300, ge=1, le=logbook.RING_SIZE),
    store: ViewStore = Depends(get_store),
) -> str:
    lvl = level.upper() if level.upper() in LEVELS else "INFO"
    return logbook.text(summary(store, request), logbook.RING.tail(limit, lvl))


@router.get("/api/checkup")
def checkup(
    request: Request,
    cwd: str = Query("", description="the folder the agent or the command runs in"),
    agent_id: str = Query("", description="the chat asking, when an agent asks"),
    identity: str = Query("given", description="how agent_id was found: process (its tool), shared-parent or folder (guesses), given"),
    store: ViewStore = Depends(get_store),
) -> dict[str, Any]:
    """#sp: is Slightly Parallel working for this chat and folder (checkup.py).
    Each finding: ok, note, concern or unknown, its evidence and the next
    step. Through the MCP tool the call itself proves MCP from that chat."""
    from .. import checkup as lib
    via_mcp = request.headers.get("x-sp-via", "").lower() == "mcp"
    return lib.run(store, cwd=cwd, agent_id=agent_id, identity=identity, via_mcp=via_mcp)


@router.get("/api/checkup/fix/{reason}")
def checkup_fix(reason: str) -> dict[str, Any]:
    """The recipe for one reason a #sp check gives (checkup_fixes.md): how to
    confirm, who acts, the steps, how to verify — with the rules every
    recipe carries."""
    from .. import checkup as lib
    book = lib.recipes()
    if reason not in book or reason.startswith("_"):
        raise HTTPException(status_code=404, detail=f"no recipe for {reason!r}; reasons: {', '.join(k for k in book if not k.startswith('_'))}")
    return {"reason": reason, "recipe": book[reason], "rules": book["_rules"]}


@router.get("/api/diagnostics/report", response_class=PlainTextResponse)
def diagnostics_report(request: Request, store: ViewStore = Depends(get_store)) -> PlainTextResponse:
    """One file to send when something is wrong (backend/diagnostics.py):
    the machine, memory over a day, the log's warnings, the monitor's
    events, the hook's errors, the data's size. No chat text, no .env."""
    from pathlib import Path

    from .. import diagnostics
    text = diagnostics.report(
        app_root=Path(__file__).resolve().parents[3],
        data_root=store.data_root,
        log_file=logbook.LOG_FILE or logbook.log_dir() / "sp.log",
        supervisor_file=logbook.log_dir() / "server.log",
        live=logbook.text(summary(store, request), logbook.RING.tail(200, "WARNING")),
        server=logbook.process_memory(),
    )
    name = time.strftime("slightly-parallel-report-%y%m%d-%H%M%S.md")
    return PlainTextResponse(text, media_type="text/markdown; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/api/capture/ignore")
def capture_ignore(body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """The operator says a tool needs no recording in a project (``ignored``
    true), or takes that back: its lost sessions and its Connect line stop
    asking for attention."""
    from .. import capturewatch
    project, tool = str(body.get("project") or "").strip(), str(body.get("tool") or "").strip()
    if not project or tool not in ("claude", "codex", "opencode", "cursor"):
        raise HTTPException(status_code=422, detail="project, and tool one of claude, codex, opencode, cursor")
    pairs = capturewatch.set_ignored(store.data_root, project, tool, bool(body.get("ignored", True)))
    return {"ignored": sorted(pairs)}


@router.get("/api/capture/import")
def capture_import_preview(project: str = Query(...), tool: str = Query(...),
                           store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """The sessions of a project and tool that nothing recorded and that can
    be read from the tool's own log (sessionimport.py): what an import would
    write. Nothing is written."""
    from .. import sessionimport
    if tool not in ("claude", "codex"):
        raise HTTPException(status_code=422, detail="tool must be claude or codex")
    return {"project": project, "tool": tool, "sessions": sessionimport.preview(store, project, tool)}


@router.post("/api/capture/import")
def capture_import(body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """Import them as chats: the operator's click. Only the chat is written —
    no command in an old message is carried out. ``sessions`` narrows it to
    the ids given; a session recorded meanwhile is skipped."""
    from .. import sessionimport
    project, tool = str(body.get("project") or "").strip(), str(body.get("tool") or "").strip()
    if not project or tool not in ("claude", "codex"):
        raise HTTPException(status_code=422, detail="project, and tool one of claude, codex")
    ids = body.get("sessions")
    return sessionimport.run(store, project, tool, [str(x) for x in ids] if isinstance(ids, list) else None)


@router.get("/api/capture/health")
def capture_health(store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """Is capture working: turns of active Claude Code sessions in registered
    folders that were not recorded, and hook failures of the last day
    (capturewatch.py). ``ok`` false is what the top bar warns about."""
    from .. import capturewatch
    return capturewatch.check(store)
