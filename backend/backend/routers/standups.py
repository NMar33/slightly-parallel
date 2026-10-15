"""The project's daily standup: is one owed, what happened, who writes it.

    GET  /api/standups/material?project=&date=   state + the day's messages + how to write it
    POST /api/standups/claim    {project, date, agent_id}   "I am writing it"
    POST /api/standups/postpone {project, date, hours}      the operator put it off

The standup itself is an ordinary entry (write_entry, lens standup) that
says which day it covers in ``for_date``. See standuplib.py.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from .. import app_settings, daynumbers, standuplib
from ..db import ViewStore
from .deps import get_store, identity_of, known_project

router = APIRouter()
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DAY_RE = re.compile(r"^\d{4}-\d{2}$")


def _day(value: str | None) -> str:
    day = (value or "").strip() or standuplib.yesterday()
    if not _DAY_RE.match(day):
        raise HTTPException(status_code=422, detail="date is YYMM-DD, for example 2609-20")
    return day




def _numbers_and_tasks(store: ViewStore, project: str, day: str) -> dict:
    """The day's numbers beside the tasks that changed on it. One reading:
    a day's numbers cost a month of ledgers and a git walk."""
    counted = daynumbers.day(store, project, day)
    return {"numbers": {k: v for k, v in counted.items() if k != "tasks"},
            "tasks_changed": counted["tasks"]}


@router.get("/api/standups/material")
def standup_material(
    request: Request,
    project: str = Query(...),
    date: str | None = Query(None),
    clip: bool = Query(False),
    store: ViewStore = Depends(get_store),
) -> dict:
    code, day = known_project(store, project), _day(date)
    values = app_settings.load(store.data_root)
    root = getattr(request.app.state, "prompt_root", None) or _REPO_ROOT
    return {
        **standuplib.state(store, code, day),
        "model": str(values.get("standup.model") or "opus"),
        "ask_first": bool(values.get("standup.ask", True)),
        **standuplib.material(store, code, day, clip),
        **_numbers_and_tasks(store, code, day),
        "instructions": standuplib.instructions(Path(root)),
        "next": (
            'MCP tool write_entry {lens: "standup", fields: {summary, story, deviation, '
            f'movement, decisions, forgotten, detail, for_date: "{day}"}}}}'
        ),
    }


@router.get("/api/standups/day")
def standup_day(project: str = Query(...), date: str | None = Query(None),
                store: ViewStore = Depends(get_store)) -> dict:
    """Beside a standup's text: the day's tasks, agents and what it created,
    from the record (no model)."""
    code, day = known_project(store, project), _day(date)
    tasks = daynumbers.day(store, code, day).get("tasks") or []
    return {"project": code, "date": day, **standuplib.day_record(store, code, day, tasks)}


@router.post("/api/standups/claim")
def standup_claim(body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    code, day = known_project(store, body.get("project")), _day(body.get("date"))
    who = identity_of(body)
    if not who:
        raise HTTPException(status_code=422, detail="agent_id is required")
    done = standuplib.written(store, code, day)
    if done:
        return {"claimed": False, "standup_id": done, "why": "the standup for this day is written"}
    return standuplib.claim(store, code, day, who)


@router.post("/api/standups/postpone")
def standup_postpone(body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    code, day = known_project(store, body.get("project")), _day(body.get("date"))
    try:
        hours = float(body.get("hours") or 4)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="hours must be a number")
    return standuplib.postpone(store, code, day, hours)


@router.get("/api/standups/calendar")
def standup_calendar(
    project: str = Query(...),
    month: str = Query(..., description="YYYY-MM"),
    store: ViewStore = Depends(get_store),
) -> dict:
    """Every day of one month with its numbers: messages, agents, tasks made
    and finished, commits, files and lines, tracked time, and the standup
    that covers it. The Standups page draws its month from this."""
    code = known_project(store, project)
    if not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", month or ""):
        raise HTTPException(status_code=422, detail="month is YYYY-MM, for example 2026-09")
    days = daynumbers.month(store, code, month)
    slim = {d: {k: v for k, v in n.items() if k != "tasks"} for d, n in days.items()}
    return {"project": code, "month": month, "days": slim}
