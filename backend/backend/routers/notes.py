"""Notes — the long texts agents write for the operator (notelib.py).

Included before the lens router: its fixed paths (``/feed``, ``/write``,
``/images/…``) come before the lens's ``/api/notes/{id}``. The lens keeps
the plain list and the detail document.

Reads:
  GET  /api/notes/feed?project=&task=&archived=   every note whole, with marks, open counts and chip titles
  GET  /api/notes/list?project=&task=             one line per note (the MCP `notes` tool)
  GET  /api/notes/{id}/full?v=                    one note (a version), its history and marks
  GET  /api/notes/{id}/agent                      one note as an agent reads it back: what the operator ticked and answered
  GET  /api/notes/images/{image_id}/file          a picture
Writes:
  POST /api/notes/write                {agent_id, project, title?, kind, text, task_id?, entrypoint_id?, replaces?, id?, base?, images?}  MCP note_write
  POST /api/notes/{id}/images          {agent_id, data_base64, caption?}  MCP note_image
  POST /api/notes/{id}/marks           {item, kind: tick|answer|copy, value}  the operator
  POST /api/notes/{id}/archive         {archived: bool}  the operator
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse

from .. import notelib as N
from ..db import ViewStore
from .deps import etag_for, get_store, json_response, maybe_304, not_found, operator_only

router = APIRouter()

_MEDIA = {"png": "image/png", "jpg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}


def _refused(exc: N.NoteRefused) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


@router.get("/api/notes/feed")
def notes_feed(request: Request, project: str = Query(""), task: str = Query(""), archived: bool = Query(False),
               store: ViewStore = Depends(get_store)) -> Response:
    etag = etag_for(f"notes-feed:{project}:{task}:{int(archived)}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r
    return json_response(N.feed(store, project=project.strip(), task=task.strip(), archived=archived), etag)


@router.get("/api/notes/list")
def notes_list(project: str = Query(""), task: str = Query(""), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    return N.listing(store, project.strip(), task.strip())


@router.get("/api/notes/images/{image_id}/file")
def note_image_file(image_id: str, store: ViewStore = Depends(get_store)) -> FileResponse:
    path = N.image_file(store, image_id)
    if path is None:
        raise not_found("picture", image_id)
    return FileResponse(path, media_type=_MEDIA.get(path.suffix.lstrip("."), "application/octet-stream"),
                        headers={"Cache-Control": "private, max-age=31536000, immutable"})


@router.get("/api/notes/{note_id}/full")
def note_full(note_id: str, v: int | None = Query(None), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    try:
        return N.one(store, note_id, v)
    except LookupError:
        raise not_found("note", note_id if v is None else f"{note_id} v{v}") from None


@router.get("/api/notes/{note_id}/agent")
def note_for_agent(note_id: str, store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    try:
        return N.for_agent(store, note_id)
    except LookupError:
        raise not_found("note", note_id) from None


@router.post("/api/notes/write")
def note_write(body: Any = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    try:
        return N.write(store, body)
    except N.NoteRefused as exc:
        raise _refused(exc) from None


@router.post("/api/notes/{note_id}/images")
def note_image(note_id: str, body: Any = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    try:
        return N.add_image(store, note_id, body)
    except N.NoteRefused as exc:
        raise _refused(exc) from None
    except LookupError:
        raise not_found("note", note_id) from None


@router.post("/api/notes/{note_id}/marks")
def note_mark(note_id: str, body: Any = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    operator_only(body, "a tick, an answer or a copy on a note", "read them back with the notes tool")
    try:
        return N.mark(store, note_id, body)
    except N.NoteRefused as exc:
        raise _refused(exc) from None
    except LookupError:
        raise not_found("note", note_id) from None


@router.post("/api/notes/{note_id}/archive")
def note_archive(note_id: str, body: Any = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    operator_only(body, "archiving a note", "write a new note that replaces it (note_write with replaces)")
    on = not isinstance(body, dict) or body.get("archived", True) not in (False, "false", 0)
    try:
        return {"note": N.archive(store, note_id, on)}
    except LookupError:
        raise not_found("note", note_id) from None
