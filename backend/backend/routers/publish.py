"""Publish — the operator's page of what shipped, worth telling (publishlib.py, docs/publish.md).

Every route is under /api/publishing (the kept entity's own lens list is
/api/publish). All of it is the operator's: an agent's write is refused.

  GET  /api/publishing?project=                 the cards with their life, the documents with their versions
  GET  /api/publishing/cards/{id}               one card, with its history
  POST /api/publishing/cards/{id}/text          {text, note?}: a new version of the card's text
  POST /api/publishing/docs                     {project, name}: a document (the same name answers the existing one)
  POST /api/publishing/docs/{id}/update         {name?, archived?}
  POST /api/publishing/docs/{id}/versions       {note?}: the next version, the current items copied
  POST /api/publishing/docs/{id}/items          {card_id, text?, before?}: a card into the current version
  GET  /api/publishing/docs/{id}/markdown?n=    the version as markdown
  POST /api/publishing/items/{id}/update        {text?, before?}
  POST /api/publishing/items/{id}/remove
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse

from .. import keeplib, publishlib
from ..actors import identity_of, refuse_agent
from ..db import ViewStore
from .deps import adopt_when_changed, create_answer, etag_for, get_store, json_response, known_project, maybe_304, not_found

router = APIRouter()


def _operator(body: dict) -> None:
    if identity_of(body) not in ("", "operator"):
        refuse_agent("the Publish page is the operator's", "a card comes from the operator's own #publish in a chat; nothing is written for it")


def _refused(exc: publishlib.PublishRefused) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


@router.get("/api/publishing")
def publishing_board(request: Request, project: str = Query(...), store: ViewStore = Depends(get_store)) -> Response:
    code = known_project(store, project)
    # A #publish typed a moment ago joins the cards on the way past, as the lists do.
    adopt_when_changed(store, "keep", keeplib.adopt)
    etag = etag_for(f"publishing:{code}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r
    return json_response(publishlib.board(store, code), etag)


@router.get("/api/publishing/cards/{card_id}")
def publishing_card(card_id: str, store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    adopt_when_changed(store, "keep", keeplib.adopt)
    got = publishlib.card(store, card_id)
    if got is None:
        raise not_found("card", card_id)
    return got


@router.post("/api/publishing/cards", status_code=201)
def publishing_card_create(response: Response, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """``{project, text}`` — a card written by hand on the page (the operator's)."""
    _operator(body)
    try:
        got = publishlib.create_card(store, body)
    except publishlib.PublishRefused as exc:
        raise _refused(exc)
    if got["existing"]:
        response.status_code = 200
    return create_answer({"card": got["card"]}, response, existing=got["existing"])


@router.post("/api/publishing/cards/{card_id}/text")
def publishing_card_text(card_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    _operator(body)
    try:
        return {"card": publishlib.edit_card(store, card_id, body)}
    except LookupError:
        raise not_found("card", card_id)
    except publishlib.PublishRefused as exc:
        raise _refused(exc)


@router.post("/api/publishing/cards/{card_id}/attach", status_code=201)
def publishing_card_attach(card_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """Images and links onto a card: the operator on the page, or the agent
    (MCP publish_attach) with what the operator may need to tell about it.
    The text stays the operator's."""
    try:
        return publishlib.attach(store, card_id, body, identity_of(body) or "operator")
    except LookupError:
        raise not_found("card", card_id)
    except publishlib.PublishRefused as exc:
        raise _refused(exc)


@router.get("/api/publishing/attachments/{attachment_id}/file")
def publishing_attachment_file(attachment_id: str, store: ViewStore = Depends(get_store)):
    path = publishlib.attachment_file(store, attachment_id)
    if path is None:
        raise not_found("attachment", attachment_id)
    return FileResponse(path)


@router.post("/api/publishing/attachments/{attachment_id}/remove")
def publishing_attachment_remove(attachment_id: str, body: dict = Body(default={}), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    _operator(body)
    try:
        return {"removed": publishlib.remove_attachment(store, attachment_id)}
    except LookupError:
        raise not_found("attachment", attachment_id)


@router.post("/api/publishing/docs", status_code=201)
def publishing_doc_create(response: Response, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    _operator(body)
    try:
        got = publishlib.create_doc(store, body)
    except publishlib.PublishRefused as exc:
        raise _refused(exc)
    if got["existing"]:
        response.status_code = 200
    return create_answer({"doc": got["doc"]}, response, existing=got["existing"])


@router.post("/api/publishing/docs/{doc_id}/update")
def publishing_doc_update(doc_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    _operator(body)
    try:
        return {"doc": publishlib.update_doc(store, doc_id, body)}
    except LookupError:
        raise not_found("document", doc_id)
    except publishlib.PublishRefused as exc:
        raise _refused(exc)


@router.post("/api/publishing/docs/{doc_id}/versions", status_code=201)
def publishing_doc_version(doc_id: str, body: dict = Body(default={}), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    _operator(body)
    try:
        return {"doc": publishlib.new_version(store, doc_id, body)}
    except LookupError:
        raise not_found("document", doc_id)


@router.post("/api/publishing/docs/{doc_id}/items", status_code=201)
def publishing_doc_place(doc_id: str, response: Response, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    _operator(body)
    try:
        got = publishlib.place(store, doc_id, body)
    except LookupError:
        raise not_found("document", doc_id)
    except publishlib.PublishRefused as exc:
        raise _refused(exc)
    if got["existing"]:
        response.status_code = 200
    return got


@router.get("/api/publishing/docs/{doc_id}/markdown")
def publishing_doc_markdown(doc_id: str, n: int | None = Query(None, ge=1), store: ViewStore = Depends(get_store)) -> Response:
    try:
        text = publishlib.markdown(store, doc_id, n)
    except LookupError:
        raise not_found("document", doc_id)
    return PlainTextResponse(text, media_type="text/markdown; charset=utf-8")


@router.post("/api/publishing/items/{item_id}/update")
def publishing_item_update(item_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    _operator(body)
    try:
        return {"item": publishlib.update_item(store, item_id, body)}
    except LookupError:
        raise not_found("item", item_id)
    except publishlib.PublishRefused as exc:
        raise _refused(exc)


@router.post("/api/publishing/items/{item_id}/remove")
def publishing_item_remove(item_id: str, body: dict = Body(default={}), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    _operator(body)
    try:
        return {"removed": publishlib.remove_item(store, item_id)}
    except LookupError:
        raise not_found("item", item_id)
