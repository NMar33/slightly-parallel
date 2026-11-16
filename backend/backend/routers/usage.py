"""Usage — the tokens agents used, and how much of each plan is used (usagelib.py).

Routes:
  GET /api/usage?project=<code|all>&range=today|7d|30d   the Usage page
  GET /api/usage/limits                                  the plan limits, per tool; codex_poll: the background reading's state
  POST /api/usage/limits/refresh                         the operator's page asks for Codex's limits now (codexlimits.py)
  GET /api/usage/prices/material                         what an update of the API prices is written from
  POST /api/usage/prices                                 one update of the API prices (MCP usage_prices_write)
  GET /api/usage/insights                                the feed of insights (writes the day's messages first)
  POST /api/usage/insights/{id}/pin                      {pinned}: pin a message or unpin it
  POST /api/usage/insights/{id}/hide                     hide a message
  POST /api/usage/insights/clear                         hide every message that is not pinned
  GET /api/usage/chat/{agent_id}?block=                  one chat, turn by turn (and the #usage text)

Read only but the two posts. The answers also depend on the clock (a reading goes stale, a
window resets, the day turns) and on ``.usage/limits.jsonl``, which the
store does not watch: the tags carry the minute and the file's stamp. The
clock is usagelib.now(), which ``SP_NOW`` fixes for tests.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response

from .. import app_settings, codexlimits, usageinsights, usagelib
from ..actors import identity_of, refuse_agent
from ..db import ViewStore
from .deps import etag_for, get_store, json_response, known_project, maybe_304, not_found

router = APIRouter()

# The last few summaries, by tag: the page polls, and one summary reads
# every usage file of the range.
_answers: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()
_KEEP = 16


def _minute(at: datetime) -> str:
    return at.strftime("%Y%m%d%H%M")


def _scope(store: ViewStore, project: str) -> str | None:
    code = str(project or "").strip()
    if code in ("", "all"):
        return None
    return known_project(store, code)


@router.get("/api/usage")
def usage_summary(request: Request, project: str = Query("all"),
                  range: str = Query("today", pattern="^(today|7d|30d)$"),  # noqa: A002 — the published name
                  store: ViewStore = Depends(get_store)) -> Response:
    """Totals of the range, by tool and model, the chats and tasks that used
    the most, the usual day, the plan limits and what was not recorded."""
    code = _scope(store, project)
    at = usagelib.now()
    sig = usagelib.signature(store.data_root) + usagelib.clock_marks(store.data_root, at)
    etag = etag_for(f"usage:{code or 'all'}:{range}:{_minute(at)}:{sig}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r
    with _lock:
        got = _answers.get(etag)
    if got is None:
        got = usagelib.summary(store, code, range, now=at)
        with _lock:
            if len(_answers) >= _KEEP:
                _answers.clear()
            _answers[etag] = got
    return json_response(got, etag)


@router.get("/api/usage/limits")
def usage_limits(request: Request, store: ViewStore = Depends(get_store)) -> Response:
    """The latest reading of each tool's plan limits."""
    at = usagelib.now()
    sig = usagelib.signature(store.data_root) + usagelib.clock_marks(store.data_root, at)
    values = app_settings.load(store.data_root)
    poll = codexlimits.state(store.data_root, values)
    etag = etag_for(f"usage-limits:{_minute(at)}:{sig}:{poll['last_attempt']}:{poll['enabled']}:{poll['every_hours']}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r
    return json_response({"limits": usagelib.limits(store.data_root, at), "codex_poll": poll}, etag)


@router.post("/api/usage/limits/refresh")
def usage_limits_refresh(body: dict = Body(default={}), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """The operator's page asks for Codex's limits now. A reading younger
    than 15 minutes is kept (``{refreshed: false, why: "fresh"}``); Codex
    not on this machine answers ``why: "absent"``; else the poll runs in
    the background and ``{refreshed: true}`` comes at once — the page reads
    the limits again a few seconds later."""
    if identity_of(body) not in ("", "operator"):
        refuse_agent("the plan limits are read for the operator's page", "nothing is written for it")
    if not codexlimits.detect()["found"]:
        return {"refreshed": False, "why": "absent"}
    if not codexlimits.refresh_wanted(store.data_root):
        return {"refreshed": False, "why": "fresh"}
    threading.Thread(target=codexlimits.poll, args=(store.data_root,), name="codex-limits-refresh", daemon=True).start()
    return {"refreshed": True}


@router.get("/api/usage/prices/material")
def usage_prices_material(store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """The models the chats used, the prices now, the pages to read. MCP: usage_prices_material."""
    return usagelib.price_material(store.data_root, store)


@router.post("/api/usage/prices", status_code=201)
def usage_prices_write(body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """One update of the API prices; the days before keep theirs. MCP: usage_prices_write."""
    try:
        return usagelib.write_prices(store.data_root, body, identity_of(body) or "operator")
    except usagelib.PricesRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc))


def _operator(body: dict) -> None:
    if identity_of(body) not in ("", "operator"):
        refuse_agent("the feed of insights is the operator's", "nothing is written for it")


def _unreadable(exc: usageinsights.Unreadable) -> HTTPException:
    return HTTPException(409, f"The feed of insights cannot be read, so nothing was changed: {exc}")


@router.get("/api/usage/insights")
def usage_insights(store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """``{items: [{id, at, kind, key, params, pinned}], hidden}``: pinned first, then newest first."""
    return usageinsights.feed(store)


@router.post("/api/usage/insights/clear")
def usage_insights_clear(body: dict = Body(default={}), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    _operator(body)
    try:
        return {"hidden": usageinsights.clear(store)}
    except usageinsights.Unreadable as exc:
        raise _unreadable(exc)


@router.post("/api/usage/insights/{item_id}/pin")
def usage_insight_pin(item_id: str, body: dict = Body(default={}), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    _operator(body)
    try:
        return {"item": usageinsights.change(store, item_id, pinned=bool(body.get("pinned", True)))}
    except LookupError:
        raise not_found("insight", item_id)
    except usageinsights.Unreadable as exc:
        raise _unreadable(exc)


@router.post("/api/usage/insights/{item_id}/hide")
def usage_insight_hide(item_id: str, body: dict = Body(default={}), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    _operator(body)
    try:
        return {"item": usageinsights.change(store, item_id, hide=True)}
    except LookupError:
        raise not_found("insight", item_id)
    except usageinsights.Unreadable as exc:
        raise _unreadable(exc)


def _chat(store: ViewStore, agent_id: str) -> dict[str, Any]:
    for a in store.agents():
        if str(a.get("agent_id") or "") == agent_id:
            return a
    raise not_found("agent", agent_id)


@router.get("/api/usage/chat/{agent_id}")
def usage_chat(agent_id: str, request: Request, block: bool = Query(False),
               store: ViewStore = Depends(get_store)) -> Response:
    """``{agent_id, project, show, turns: {n: TurnUsage}}``; with ``block``
    also the text #usage prints for this chat."""
    a = _chat(store, agent_id)
    folder = usagelib.chat_folder(a)
    if folder is None:
        # A chat without a path has no usage file: never the server's own folder.
        raise not_found("agent", agent_id)
    project = str(a.get("project") or "")
    at = usagelib.now()
    sig = usagelib.signature(store.data_root, folder) + usagelib.clock_marks(store.data_root, at, folder)
    etag = etag_for(f"usage-chat:{agent_id}:{int(block)}:{_minute(at)}:{sig}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r
    turns = usagelib.turns_in(folder, store.data_root)
    out: dict[str, Any] = {
        "agent_id": agent_id, "project": project,
        "show": usagelib.show_usage(store.data_root, folder),
        "turns": {str(n): t for n, t in turns.items()},
    }
    if block:
        out["block"] = usagelib.usage_block(store.data_root, project, agent_id,
                                            str(request.base_url).rstrip("/"), now=at, folder=folder)
    return json_response(out, etag)
