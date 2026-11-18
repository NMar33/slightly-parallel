"""The terminal log's routes (termlog.py).

- ``POST /api/terminal/log`` — a page's batch: its minute rows and, in Full,
  its events. Validated whole first: a refused batch writes nothing. The
  answer is the mode in force, so a page learns of a change within a batch.
- ``GET  /api/terminal/log/mode`` · ``POST /api/terminal/log/mode``
  ``{mode: off|light|full, hours?}`` — read or switch the log.
- ``GET  /api/terminal/log/summary?day=YYYY-MM-DD`` — a day for the Monitor.
- ``GET  /api/terminal/log/report`` — the bundle for a bug report, a file.
"""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import Response

from .. import termlib, termlog
from .deps import operator_only

router = APIRouter()


def _root(request: Request):
    return request.app.state.settings.data_root


@router.post("/api/terminal/log")
async def terminal_log_batch(request: Request) -> dict[str, Any]:
    raw = await request.body()
    if len(raw) > termlog.MAX_BATCH_BYTES:
        raise HTTPException(status_code=413, detail=f"a batch is at most {termlog.MAX_BATCH_BYTES // 1_000_000} MB")
    try:
        batch = json.loads(raw.decode("utf-8")) if raw else {}
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=422, detail="a batch is JSON") from None
    if isinstance(batch, dict):
        operator_only(batch, "Writing the terminal log")
    try:
        return termlog.accept(_root(request), batch)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.get("/api/terminal/log/mode")
def terminal_log_mode(request: Request) -> dict[str, Any]:
    return termlog.mode(_root(request))


@router.post("/api/terminal/log/mode")
def terminal_log_set_mode(request: Request, body: dict = Body(...)) -> dict[str, Any]:
    operator_only(body, "Switching the terminal log")
    new = body.get("mode")
    hours = body.get("hours")
    if new not in termlog.MODES:
        raise HTTPException(status_code=422, detail=f"mode is one of {', '.join(termlog.MODES)}")
    if hours is not None and (isinstance(hours, bool) or not isinstance(hours, (int, float)) or not 0 < hours <= 24):
        raise HTTPException(status_code=422, detail="hours is a number from 0 to 24")
    return termlog.set_mode(_root(request), new, hours)


@router.get("/api/terminal/log/summary")
def terminal_log_summary(request: Request, day: str = Query("")) -> dict[str, Any]:
    if day and not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
        raise HTTPException(status_code=422, detail="day is YYYY-MM-DD")
    out = termlog.summary(_root(request), day)
    out["days"] = termlog.days_kept(_root(request))
    return out


@router.get("/api/terminal/log/report")
def terminal_log_report(request: Request) -> Response:
    got = termlog.report(_root(request), tmux_version=termlib.tmux_version())
    name = f"sp-terminal-log-{got['made'][:16].replace(':', '').replace('T', '-')}.json"
    return Response(json.dumps(got, ensure_ascii=False, separators=(",", ":")), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
