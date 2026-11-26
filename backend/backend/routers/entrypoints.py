"""Entry points — the topics the operator comes back to (entrypointlib.py).

Included before the lens router: its fixed paths (``/desk``, ``/similar``,
``/shots/…``) come before the lens's ``/api/entrypoints/{id}``. The lens
keeps the list, the record and the #entrypoint interpretation.

Reads:
  GET  /api/entrypoints/desk?project=          every topic with what its tile shows
  GET  /api/entrypoints/similar?project=&text= topics like a name (an agent's offer)
  GET  /api/entrypoints/{id}/context           chats, tasks, decisions, commits, made, spend, briefing
  GET  /api/entrypoints/{id}/briefing          {text}: what Copy to agent gives
  GET  /api/entrypoints/{id}/ports             whether each way in is up now (local ports only)
  GET  /api/entrypoints/{id}/command           what an #entrypoint opened (the id the hook named)
  GET  /api/entrypoints/asks?agent_id=         every question an #entrypoint asked, with its answer
  GET  /api/entrypoints/shots/{shot_id}/file   a screenshot
Writes (the operator's pages; an agent through the MCP tools):
  POST /api/entrypoints/ask                    {agent_id, id, name?} the question after an #entrypoint
  POST /api/entrypoints/answer                 {agent_id, number, name?, id?} the operator's answer
  POST /api/entrypoints/{id}/stops             {text, task_id?} a "where it stopped" message
  POST /api/entrypoints/{id}/stops/{sid}/remove  the operator
  POST /api/entrypoints/{id}/ways              {way, id?} add or change a way in
  POST /api/entrypoints/{id}/ways/{wid}/remove   the operator
  POST /api/entrypoints/{id}/shots             {way_id, data_base64, caption?, replaces?}
  POST /api/entrypoints/{id}/state             {state} the operator
  POST /api/entrypoints/{id}/name              {name, home?, no_project?} the operator
  POST /api/tasks/{task_id}/topic              {entrypoint_id} ("" clears)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse

import logging

from .. import entrypointask as A
from .. import entrypointlib as E
from .. import keeplib
from ..actors import identity_of, is_agent
from ..db import ViewStore
from .deps import etag_for, get_store, json_response, maybe_304, not_found, operator_only, written_by_agent

router = APIRouter()
log = logging.getLogger("sp.entrypoints")

_MEDIA = {"png": "image/png", "jpg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}


def _refused(exc: E.EntryRefused) -> HTTPException:
    return HTTPException(status_code=403 if isinstance(exc, E.EntryForbidden) else 422, detail=str(exc))


def _row(store: ViewStore, ep_id: str) -> dict[str, str]:
    row = E.entry_of(store, ep_id)
    if row is None:
        raise not_found("entry point", ep_id)
    return row


@router.get("/api/entrypoints/desk")
def entrypoints_desk(request: Request, project: str = Query(""), store: ViewStore = Depends(get_store)) -> Response:
    """Every topic (of a project, or all), newest first by what was last
    written to it: name, state, what, ways in, the last five stops, shots."""
    # A #entrypoint typed a moment ago is kept on this read, as the lens
    # list keeps it (keeplib.adopt: idempotent, a write only when new).
    try:
        keeplib.adopt(store)
    except Exception:  # noqa: BLE001 — the desk answers from the ledger as it is
        log.warning("adopting kept messages failed on the entry points desk", exc_info=True)
    etag = etag_for(f"ep-desk:{project}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r
    return json_response(E.desk(store, project.strip()), etag)


@router.get("/api/entrypoints/similar")
def entrypoints_similar(project: str = Query(...), text: str = Query(...),
                        store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """The project's topics most like ``text``, and the line an agent shows
    the operator: add to the match, or offer a new entry point. Writes nothing."""
    words = " ".join(text.split())[:400]
    if not words:
        raise HTTPException(status_code=422, detail="text is the name of the topic and why, in a few words")
    hits = E.similar(store, project.strip(), words)
    return {"similar": hits, "next": E.offer_line(words[:E.NAME_MAX], hits)}


def _fresh(store: ViewStore) -> None:
    """The command or the answer may be seconds old: the view and the kept
    messages first; a failure answers from the ledger as it is."""
    try:
        store.rebuild()
        keeplib.adopt(store)
    except Exception:  # noqa: BLE001
        log.warning("adopting kept messages failed on an entry point question", exc_info=True)


def _chat_of(body: Any) -> tuple[dict, str]:
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="send the body as a JSON object")
    who = identity_of(body)
    if not is_agent(who):
        raise HTTPException(status_code=422, detail="agent_id is required: the chat the #entrypoint was typed in")
    return body, who


@router.post("/api/entrypoints/ask")
def entrypoints_ask(body: Any = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """After the operator's #entrypoint: the topics it may mean, numbered,
    and the line the agent shows. Nothing is made until the operator answers
    (entrypointask.py). A command already answered answers what it opened."""
    body, who = _chat_of(body)
    cmd_id = str(body.get("id") or "").strip()
    if not cmd_id:
        raise HTTPException(status_code=422, detail="id is the id the #entrypoint notice named")
    _fresh(store)
    try:
        return A.ask(store, who, cmd_id, body.get("name"))
    except A.AskRefused as e:
        raise HTTPException(status_code=409, detail=str(e))
    except LookupError:
        raise not_found("#entrypoint command", cmd_id)


@router.post("/api/entrypoints/answer")
def entrypoints_answer(body: Any = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """The operator answered the question: the topic they chose by number,
    checked against their next message in the chat; an existing one opens a
    new version for this chat, the new-topic line makes the topic then."""
    body, who = _chat_of(body)
    try:
        number = A.parse_number(body.get("number"))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    _fresh(store)
    try:
        return A.answer(store, who, number, body.get("name"), str(body.get("id") or "").strip())
    except A.AskRefused as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/api/entrypoints/asks")
def entrypoints_asks(agent_id: str = Query(""), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """Every question with its lines and answer, newest first; reads only."""
    got = A.asks(store, agent_id.strip())
    return {"total": len(got), "asks": got}


@router.get("/api/entrypoints/shots/{shot_id}/file")
def entrypoints_shot_file(shot_id: str, store: ViewStore = Depends(get_store)) -> FileResponse:
    path = E.shot_file(store, shot_id)
    if path is None:
        raise not_found("screenshot", shot_id)
    return FileResponse(path, media_type=_MEDIA.get(path.suffix.lstrip(".").lower(), "application/octet-stream"),
                        headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})


@router.get("/api/entrypoints/{ep_id}/context")
def entrypoints_context(ep_id: str, request: Request, store: ViewStore = Depends(get_store)) -> Response:
    """The topic's context: its chats before and after (each with the turns
    that were the topic's), its tasks open and done, decisions, commits and
    files, artifacts and Publish cards, the spend, and the briefing."""
    _row(store, ep_id)
    etag = etag_for(f"ep-context:{ep_id}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r
    try:
        return json_response(E.context(store, ep_id), etag)
    except LookupError:
        raise not_found("entry point", ep_id)


@router.get("/api/entrypoints/{ep_id}/briefing")
def entrypoints_briefing(ep_id: str, store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    _row(store, ep_id)
    return {"id": ep_id, "text": E.context(store, ep_id)["briefing"]}


@router.get("/api/entrypoints/{ep_id}/command")
def entrypoints_command(ep_id: str, store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """What an operator's #entrypoint opened, by the id the hook named: a
    new topic or a new version of the topic the operator chose (or of the
    one named exactly), or nothing yet (``opened`` pending); the record as
    it is, the chat that writes it and the line of what to write. A topic's
    own id answers its last command."""
    try:
        keeplib.adopt(store)
    except Exception:  # noqa: BLE001 — answer from the ledger as it is
        log.warning("adopting kept messages failed on an entry point command", exc_info=True)
    try:
        return E.command_view(store, ep_id)
    except LookupError:
        raise not_found("entry point", ep_id)


@router.get("/api/entrypoints/{ep_id}/ports")
def entrypoints_ports(ep_id: str, store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """Whether each way in is up: a connect to its port on this computer,
    at most a second for all. A way elsewhere is not connected to. (A plain
    def: FastAPI runs it in a thread, never on the event loop.)"""
    _row(store, ep_id)
    return {"id": ep_id, "ways": E.check_ports(E.ways_of(store, ep_id))}


def _write(store: ViewStore, ep_id: str, fn, body: Any) -> Any:
    try:
        out = fn(store, ep_id, body)
    except LookupError:
        raise not_found("entry point", ep_id)
    except E.EntryRefused as exc:
        raise _refused(exc)
    store.rebuild()
    return out


@router.post("/api/entrypoints/{ep_id}/stops", status_code=201)
def entrypoints_stop(ep_id: str, response: Response, body: Any = Body(...),
                     store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    out = _write(store, ep_id, E.add_stop, body)
    if out["existing"]:
        response.status_code = 200
    return out


@router.post("/api/entrypoints/{ep_id}/stops/{stop_id}/remove")
def entrypoints_stop_remove(ep_id: str, stop_id: str, body: dict = Body(default={}),
                            store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    operator_only(body, "removing a message of where it stopped")
    try:
        E.remove_stop(store, ep_id, stop_id)
    except LookupError:
        raise not_found("message", stop_id)
    store.rebuild()
    return {"removed": stop_id}


@router.post("/api/entrypoints/{ep_id}/ways")
def entrypoints_way(ep_id: str, body: Any = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    if isinstance(body, dict) and "remove" in body:
        raise HTTPException(status_code=422, detail="remove a way in with POST /api/entrypoints/{id}/ways/{way_id}/remove")
    return _write(store, ep_id, E.put_way, body)


@router.post("/api/entrypoints/{ep_id}/ways/{way_id}/remove")
def entrypoints_way_remove(ep_id: str, way_id: str, body: dict = Body(default={}),
                           store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    operator_only(body, "removing a way in", "add a new way in with entrypoint_way, or tell the operator")
    try:
        E.remove_way(store, ep_id, way_id)
    except LookupError:
        raise not_found("way in", way_id)
    store.rebuild()
    return {"removed": way_id}


@router.post("/api/entrypoints/{ep_id}/shots", status_code=201)
def entrypoints_shot(ep_id: str, response: Response, body: Any = Body(...),
                     store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    out = _write(store, ep_id, E.add_shot, body)
    if out["existing"]:
        response.status_code = 200
    return out


@router.post("/api/entrypoints/{ep_id}/state")
def entrypoints_state(ep_id: str, body: Any = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    if written_by_agent(body):
        operator_only(body, "an entry point's state")
    return {"entrypoint": _write(store, ep_id, E.set_state, body)}


@router.post("/api/entrypoints/{ep_id}/name")
def entrypoints_name(ep_id: str, body: Any = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    if written_by_agent(body):
        operator_only(body, "an entry point's name")
    return {"entrypoint": _write(store, ep_id, E.set_name, body)}


@router.post("/api/tasks/{task_id}/topic")
def task_topic(task_id: str, body: Any = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """``{entrypoint_id}``: the task's topic, of the task's own project; "" clears."""
    try:
        out = E.set_task_topic(store, task_id, body)
    except LookupError as exc:
        missing = str(exc.args[0]) if exc.args else task_id
        raise not_found("entry point" if missing.startswith("ep_") else "task", missing)
    except E.EntryRefused as exc:
        raise _refused(exc)
    store.rebuild()
    return out


@router.get("/api/tasks/{task_id}/topic")
def task_topic_read(task_id: str, store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    return {"task_id": task_id, "topic": E.topic_of_task(store, task_id)}
