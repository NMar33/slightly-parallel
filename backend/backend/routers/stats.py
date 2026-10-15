"""Task statistics (statslib.py).

``GET /api/stats/tasks?project=`` — one row per task worked in a chat or
finished: messages, chats, active minutes, agents, commits, files, lines,
created → first message → done, how it was closed (#done · board), whether
its stretch of the chat is exact (#done) or estimated, reopened, reports.
The pages aggregate in the browser; the rows are few.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Query

from .. import statslib
from ..db import ViewStore
from .deps import get_store

router = APIRouter()


@router.get("/api/stats/tasks")
async def stats_tasks(project: str = Query(""), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    rows = await asyncio.to_thread(statslib.task_rows, store)
    if project:
        rows = [r for r in rows if r["project"] == project]
    return {"total": len(rows), "tasks": rows}
