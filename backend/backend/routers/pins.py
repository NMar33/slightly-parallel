"""Pins, carried messages and forks for later (pinlib.py) — one route set each.

``GET /api/pins`` · ``/api/carries`` · ``/api/forks`` answer the marks of
that list in force (``?project=&agent_id=&q=&full=1``), after adopting any
new tag. ``POST`` to the same path marks a message by hand
(``{chat_agent, turn, side?, project?, session_id?, excerpt?}``; a carry
also takes ``level``: ``carry`` or ``brief``); ``POST …/remove`` takes the
mark off (``{target}``). ``POST /api/forks/state`` sets a fork's state
(``{target, state}``: "", started, dropped). ``POST /api/carries/brief``
writes the brief of a #carry-brief message (``{target, text, agent_id}``) —
an agent's write, through the MCP tool ``carry_brief``.

Marking is the operator's; an agent marks by being told the tag in a chat.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from .. import hookshared, marklib, pinlib
from ..actors import identity_of
from ..db import ViewStore
from .deps import adopt_when_changed, get_store, operator_only

router = APIRouter()

_WORDS = {"pin": ("Pinning a message", "#pin"), "carry": ("Carrying a message", "#carry or #carry-brief"),
          "fork": ("Marking a message to fork later", "#fork-later")}


def _list(store: ViewStore, which: str, project: str, agent_id: str, q: str, full: bool) -> dict[str, Any]:
    if adopt_when_changed(store, "marks", marklib.adopt):
        store.rebuild()
    return pinlib.listing(store, which, project=project, agent_id=agent_id, q=q, full=full)


def _add(store: ViewStore, which: str, body: dict) -> dict[str, Any]:
    what, tag = _WORDS[which]
    operator_only({"actor": body.get("actor") or "operator", "agent_id": body.get("agent_id") or ""},
                  what, f"the operator types {tag} in the chat")
    kind = which
    if which == "carry":
        level = str(body.get("level") or "carry")
        if level not in ("carry", "brief"):
            raise HTTPException(status_code=422, detail="level is carry (the message whole) or brief")
        kind = "carry" if level == "carry" else "carry-brief"
    try:
        turn = int(body.get("turn") or 0)
        side = hookshared.REPLY_SIDE if str(body.get("side") or "") in (hookshared.REPLY_SIDE, "agent") else ""
        row = pinlib.mark(store, kind, str(body.get("chat_agent") or ""), turn, side, {
            "project": body.get("project") or "", "session_id": body.get("session_id") or "",
            "excerpt": body.get("excerpt") or ""})
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    store.rebuild()
    return {"mark": row}


def _remove(store: ViewStore, which: str, body: dict) -> dict[str, Any]:
    operator_only({"actor": body.get("actor") or "operator", "agent_id": body.get("agent_id") or ""},
                  f"Removing a {which} mark")
    target = str(body.get("target") or "")
    if hookshared.parse_target(target) is None:
        raise HTTPException(status_code=422, detail="target is <agent_id>#<turn> or <agent_id>#<turn>/reply")
    # A tag not adopted yet is adopted first, so the removal reaches it.
    if adopt_when_changed(store, "marks", marklib.adopt):
        store.rebuild()
    n = pinlib.unmark(store, pinlib.LISTS[which], target)
    if n:
        store.rebuild()
    return {"removed": n}


def _routes(which: str, path: str) -> None:
    @router.get(path, name=f"{which}_list")
    def listed(project: str = Query(""), agent_id: str = Query(""), q: str = Query(""),
               full: bool = Query(False), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
        return _list(store, which, project, agent_id, q, full)

    @router.post(path, status_code=201, name=f"{which}_add")
    def added(body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
        return _add(store, which, body)

    @router.post(f"{path}/remove", name=f"{which}_remove")
    def removed(body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
        return _remove(store, which, body)


_routes("pin", "/api/pins")
_routes("carry", "/api/carries")
_routes("fork", "/api/forks")


@router.post("/api/forks/state")
def fork_state(body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """``{target, state}`` — waiting (""), started or dropped."""
    operator_only({"actor": body.get("actor") or "operator", "agent_id": body.get("agent_id") or ""},
                  "Setting a fork's state")
    try:
        n = marklib.set_state(store, "fork", str(body.get("target") or ""), str(body.get("state") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not n and not any(r.get("kind") == "fork" and r.get("target") == body.get("target")
                         for r in marklib.active(store)):
        raise HTTPException(status_code=404, detail=f"no fork-later mark on {body.get('target')}")
    if n:
        store.rebuild()
    return {"changed": n}


@router.post("/api/carries/brief", status_code=201)
def carry_brief(body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """``{target, text, agent_id}`` — the brief given back for a #carry-brief message."""
    by = identity_of(body) or "operator"
    try:
        row = pinlib.write_brief(store, str(body.get("target") or ""), str(body.get("text") or ""), by)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"brief": row, "note": "Given back after the next compaction of that chat instead of the message."}
