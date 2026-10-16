"""The health page's data: the server's log, summed up and as a tail.

``GET /api/logs`` answers with the summary (uptime, data, rebuilds, requests
by path, errors) and the last lines; ``GET /api/logs/text`` is the same as
plain text, which is what the page's copy button hands to the clipboard and
what ``curl`` gives a person at a terminal.
"""

from __future__ import annotations

import os
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


def _rss_mb() -> float:
    try:
        with open("/proc/self/status", encoding="utf-8") as fh:
            for ln in fh:
                if ln.startswith("VmRSS:"):
                    return round(int(ln.split()[1]) / 1024, 1)
    except (OSError, ValueError, IndexError):
        pass
    return 0.0


def _threads() -> int:
    try:
        return len(os.listdir("/proc/self/task"))
    except OSError:
        return 0


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
        "rss_mb": _rss_mb(),
        "threads": _threads(),
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
