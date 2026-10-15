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

from fastapi import APIRouter, Depends, Query, Request
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


@router.get("/api/capture/health")
def capture_health(store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """Is capture working: turns of active Claude Code sessions in registered
    folders that were not recorded, and hook failures of the last day
    (capturewatch.py). ``ok`` false is what the top bar warns about."""
    from .. import capturewatch
    return capturewatch.check(store)
