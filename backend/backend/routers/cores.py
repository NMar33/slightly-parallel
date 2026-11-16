"""Cores — the program's core elements, named by the operator (corelib.py).

Routes:
  GET  /api/cores?project=                   every core of a project, as the tiles show them
  POST /api/cores                            a new core (#core-new runs through here)
  GET  /api/cores/{id}                       one core: notes, links, tasks, files, nearby commits, grid
  POST /api/cores/{id}/notes                 a note on the story (#core-note, an agent's auto note)
  POST /api/cores/{id}/notes/{nid}/approve   the operator endorses an agent's note
  POST /api/cores/{id}/links                 attach {kind, target, note?}; {remove: link id} detaches
  POST /api/cores/{id}/update                name, type, reason, position, status (operator)
  POST /api/cores/{id}/tracking              {on, span? | until?} (operator)
  POST /api/cores/{id}/off                   out of view (#core-off, run by the agent)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response

from .. import corelib
from ..db import ViewStore
from ..entities import CORE_TYPES
from .deps import create_answer, etag_for, get_store, json_response, known_project, maybe_304, not_found

router = APIRouter()


def _refused(exc: corelib.CoreRefused) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


@router.get("/api/cores")
def cores_list(request: Request, project: str = Query(...), store: ViewStore = Depends(get_store)) -> Response:
    """The project's cores, in view first, tracked first, by position."""
    code = known_project(store, project)
    etag = etag_for(f"cores:{code}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r
    return json_response({"cores": corelib.summary_rows(store, code), "types": list(CORE_TYPES)}, etag)


@router.get("/api/cores/timeline")
def cores_timeline(request: Request, project: str = Query(...), days: int = Query(30, ge=7, le=120),
                   store: ViewStore = Depends(get_store)) -> Response:
    """The cores over the last ``days`` days, one lane each, with the day's
    standup and the release tags above them (corelib.timeline)."""
    code = known_project(store, project)
    etag = etag_for(f"cores-timeline:{code}:{days}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r
    return json_response(corelib.timeline(store, code, days), etag)


@router.get("/api/cores/tasks")
def cores_task_index(request: Request, project: str = Query(...), store: ViewStore = Depends(get_store)) -> Response:
    """Task id → the cores it belongs to, for the board's cards."""
    code = known_project(store, project)
    etag = etag_for(f"cores-tasks:{code}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r
    return json_response({"tasks": corelib.task_index(store, code)}, etag)


@router.get("/api/cores/map")
def cores_map(request: Request, project: str = Query(...), store: ViewStore = Depends(get_store)) -> Response:
    """The map's rows, each with the cores that claim it and how."""
    code = known_project(store, project)
    etag = etag_for(f"cores-map:{code}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r
    return json_response(corelib.map_overlay(store, code), etag)


@router.get("/api/tasks/{task_id}/cores")
def task_cores(task_id: str, store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    return {"task_id": task_id, "cores": corelib.cores_of_task(store, task_id)}


@router.post("/api/tasks/{task_id}/cores")
def task_cores_set(task_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """``{cores: [id …]}`` — the operator sets the task's cores."""
    try:
        out = corelib.set_task_cores(store, task_id, body)
    except LookupError:
        raise not_found("task", task_id)
    except corelib.CoreRefused as exc:
        raise _refused(exc)
    store.rebuild()
    return {"task_id": task_id, "cores": out}


@router.post("/api/cores", status_code=201)
def cores_create(response: Response, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """``{project, name, type, reason?, text?, anchors?, task_id?, actor|agent_id}``.
    The same name in view answers with the existing core (200)."""
    try:
        got = corelib.create(store, body)
    except corelib.CoreRefused as exc:
        raise _refused(exc)
    if got["existing"]:
        response.status_code = 200
    store.rebuild()
    return create_answer({"core": got["core"]}, response, existing=got["existing"])


@router.get("/api/cores/{core_id}")
def core_read(core_id: str, store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    try:
        return corelib.detail(store, core_id)
    except LookupError:
        raise not_found("core", core_id)


@router.post("/api/cores/{core_id}/notes", status_code=201)
def core_note(core_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """``{text, comment?, kind?: note|auto, task_id?, actor|agent_id}``."""
    try:
        note = corelib.add_note(store, core_id, body)
    except LookupError:
        raise not_found("core", core_id)
    except corelib.CoreRefused as exc:
        raise _refused(exc)
    store.rebuild()
    return {"note": note, "core": corelib.core_of(store, core_id)}


@router.post("/api/cores/{core_id}/notes/{note_id}/approve")
def core_note_approve(core_id: str, note_id: str, body: dict = Body(default={}),
                      store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    try:
        note = corelib.approve(store, core_id, note_id, body)
    except LookupError:
        raise not_found("note", note_id)
    store.rebuild()
    return {"note": note}


@router.post("/api/cores/{core_id}/links")
def core_links(core_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """``{kind, target, note?}`` attaches; ``{remove: link_id}`` detaches (operator)."""
    if corelib.core_of(store, core_id) is None:
        raise not_found("core", core_id)
    try:
        if body.get("remove"):
            removed = corelib.unlink(store, core_id, str(body["remove"]), body)
            store.rebuild()
            return {"removed": bool(removed)}
        link = corelib.link(store, core_id, body)
    except corelib.CoreRefused as exc:
        raise _refused(exc)
    store.rebuild()
    return {"link": link, "existing": link is None}


@router.post("/api/cores/{core_id}/update")
def core_update(core_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    try:
        core = corelib.update(store, core_id, body)
    except LookupError:
        raise not_found("core", core_id)
    except corelib.CoreRefused as exc:
        raise _refused(exc)
    store.rebuild()
    return {"core": core}


@router.post("/api/cores/{core_id}/tracking")
def core_tracking(core_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    try:
        core = corelib.set_tracking(store, core_id, body)
    except LookupError:
        raise not_found("core", core_id)
    except corelib.CoreRefused as exc:
        raise _refused(exc)
    store.rebuild()
    return {"core": core, "tracking": corelib.tracking_state(core)}


@router.post("/api/cores/{core_id}/off")
def core_off(core_id: str, body: dict = Body(default={}), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    try:
        core = corelib.off(store, core_id, body)
    except LookupError:
        raise not_found("core", core_id)
    store.rebuild()
    return {"core": core}
