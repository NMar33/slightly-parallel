"""Analytics — query Slightly Parallel's data (analytics.py).

- ``GET /api/analytics/schema`` — the tables (messages, chats, tasks,
  task_events), their columns and row counts, and example queries.
- ``POST /api/analytics/query`` — ``{sql}``: one SELECT or WITH on an
  in-memory copy with no file access; ``{columns, rows, truncated, ms}``,
  or 422 with what is wrong.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from .. import analytics
from ..db import ViewStore
from .deps import get_store

router = APIRouter()


@router.get("/api/analytics/schema")
async def analytics_schema(store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    return await asyncio.to_thread(analytics.schema, store)


@router.post("/api/analytics/query")
async def analytics_query(body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(analytics.run, store, str(body.get("sql") or ""))
    except analytics.QueryError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
