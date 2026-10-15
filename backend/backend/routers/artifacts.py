"""Artifacts over HTTP — the record of a folder an agent wrote.

- ``POST /api/artifacts/{id}/write`` — the MCP tool's target: the folder is
  there, make (or refresh) the record.
- ``POST /api/artifacts/new`` — the operator registers a folder written by
  hand.
- ``GET /api/artifacts/{id}/tree`` and ``GET /api/artifacts/{id}/files/…`` —
  what the page shows and serves for previews.

Reading an artifact is the lens detail (``GET /api/artifacts/{id}``), which
carries the kept message and the folder under ``artifact``. Registered
before the lens router.
"""

from __future__ import annotations

import mimetypes
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import FileResponse

from .. import artifactlib, keeplib
from ..db import ViewStore
from ..docs_md import read_detail, resolve_under
from .deps import create_answer, get_store, identity_of, not_found, operator_only

router = APIRouter()


def _row(store: ViewStore, item_id: str) -> dict[str, Any]:
    row = keeplib.row_of(store, "artifact", item_id)
    if row is None:
        raise not_found("artifact", item_id)
    return row


def _detail(store: ViewStore, item_id: str) -> dict[str, Any]:
    row = _row(store, item_id)
    l2, l3, l4 = read_detail(store.data_root, str(row.get("md_ref") or ""))
    return {"metadata": row, "l2": l2, "l3": l3, "l4": l4, **artifactlib.enrich(store, row)}


# Plain functions, run on a worker thread: the write and the answer both
# walk the folder (scan, previews), and as coroutines the answer did that
# on the event loop, holding every other request and socket meanwhile.
@router.post("/api/artifacts/new", status_code=201)
def artifacts_new(body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    """``{project, name, kind, description, tags?}`` — register a folder the
    operator wrote at artifacts/<project>/<name>/. Operator only."""
    operator_only(body, "registering a folder by hand", "an agent answers #artifact with artifact_write")
    try:
        kid = artifactlib.create_written(
            store,
            project=str(body.get("project") or "").strip(), name=str(body.get("name") or "").strip(),
            kind=str(body.get("kind") or "").strip(), description=str(body.get("description") or ""),
            tags=str(body.get("tags") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return create_answer(_detail(store, kid))


@router.post("/api/artifacts/{item_id}/write")
def artifact_write(item_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    """``{agent_id | actor, name, kind, description}`` — the folder is written;
    make the record, or refresh it after edits."""
    row = _row(store, item_id)
    actor = identity_of(body)
    try:
        artifactlib.write_record(
            store, row,
            name=str(body.get("name") or ""), kind=str(body.get("kind") or ""),
            description=str(body.get("description") or ""), actor=actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _detail(store, item_id)


@router.get("/api/artifacts/{item_id}/tree")
def artifact_tree(item_id: str, store: ViewStore = Depends(get_store)) -> dict:
    row = _row(store, item_id)
    dest = artifactlib._folder_of(store, row)
    if dest is None:
        raise HTTPException(status_code=404, detail="The artifact's folder was not found.")
    return {"id": item_id, "path": str(dest), "tree": artifactlib.tree(dest)}


@router.get("/api/artifacts/{item_id}/files/{path:path}")
def artifact_file(item_id: str, path: str, store: ViewStore = Depends(get_store)):
    """One file of the folder, for previews. Html is served sandboxed."""
    row = _row(store, item_id)
    dest = artifactlib._folder_of(store, row)
    if dest is None:
        raise HTTPException(status_code=404, detail="The artifact's folder was not found.")
    target = resolve_under(dest, path)
    if target is None or not target.is_file():
        raise HTTPException(status_code=404, detail=f"no such file in the artifact: {path}")
    media, _enc = mimetypes.guess_type(str(target))
    media = media or ("text/plain; charset=utf-8" if artifactlib._is_text(target) else "application/octet-stream")
    # An agent wrote these files. Whatever one is opened as a document — a
    # page, but also an SVG or XML file, which carry scripts too — runs in a
    # sandbox with no origin, so nothing in it reaches the dashboard. A page
    # may run its own scripts there; the rest run none. The type is the one
    # named here, never guessed by the browser.
    if media.startswith("text/html"):
        policy = "sandbox allow-scripts; default-src 'self' data: blob:; style-src 'self' 'unsafe-inline'"
    else:
        policy = "sandbox; default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'"
    headers = {"Content-Security-Policy": policy, "X-Content-Type-Options": "nosniff"}
    return FileResponse(str(target), media_type=media, headers=headers)
