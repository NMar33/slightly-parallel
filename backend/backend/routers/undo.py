"""#undo — the operator archives entries made by mistake (undolib.py).

- ``GET /api/undo/candidates?agent_id=`` — the chat's live #undo request
  and the entries it could mean, numbered. Refused (409) without a request.
- ``POST /api/undo/propose`` ``{agent_id, ids}`` — records the operator's
  choice and answers the confirmation text, with the reply that confirms.
- ``POST /api/undo/apply`` ``{agent_id}`` — archives the choice, only when
  the operator's next message after the proposal carries ``#undo-yes``.
  Any other next message cancels the request.
- ``POST /api/undo/restore`` ``{id, agent_id}`` — brings one entry back.
- ``GET /api/undo`` — every request, for reading.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from .. import undolib
from ..db import ViewStore
from .deps import get_store

router = APIRouter()


def _refused(e: undolib.UndoRefused) -> HTTPException:
    return HTTPException(status_code=409, detail=str(e))


@router.get("/api/undo")
def undo_list(store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    rows = undolib.requests(store)
    return {"total": len(rows), "requests": rows}


@router.get("/api/undo/candidates")
def undo_candidates(agent_id: str = Query(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    store.rebuild()          # the #undo message may be seconds old
    try:
        return undolib.candidates(store, agent_id)
    except undolib.UndoRefused as e:
        raise _refused(e)


@router.post("/api/undo/propose")
def undo_propose(body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    ids = body.get("ids")
    if not isinstance(ids, list):
        raise HTTPException(status_code=422, detail="ids must be a list of entry ids")
    store.rebuild()
    try:
        return undolib.propose(store, str(body.get("agent_id") or ""), ids)
    except undolib.UndoRefused as e:
        raise _refused(e)


@router.post("/api/undo/apply")
def undo_apply(body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    store.rebuild()          # the #undo-yes message may be seconds old
    try:
        return undolib.apply(store, str(body.get("agent_id") or ""))
    except undolib.UndoRefused as e:
        raise _refused(e)


@router.post("/api/undo/restore")
def undo_restore(body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    try:
        return undolib.restore(store, str(body.get("id") or ""), str(body.get("agent_id") or "operator"))
    except undolib.UndoRefused as e:
        raise _refused(e)
