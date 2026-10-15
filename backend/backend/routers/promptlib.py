"""The prompt library — list, read, rewrite, name, archive.

The engine is ``backend.promptlib``. Two things shape this router.

Harvesting rides the read. ``GET /api/prompt-library`` adopts any ``#prompt`` the
chat logs have grown since the last look, so a prompt tagged mid-conversation
is in the library by the time the operator opens the page — no cron, no
button, and no agent asked to write anything down.

Nothing is destroyed. Editing appends a version; the captured original stays
version 1 forever. "Delete" is archive, and archived rows keep their document.
A library that can lose the prompt that worked is not a library.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response

from .. import promptlib
from .. import limits
from ..db import ViewStore
from ..date_utils import today_yymm_dd
from .deps import (
    adopt_when_changed, etag_for, get_store, json_response, maybe_304, not_found,
    refuse_agent, written_by_agent,
)
from .lenses import OPERATOR_ONLY
from .sessions_api import git_for_sessions

router = APIRouter()

# Plain functions: FastAPI runs each on a worker thread. As coroutines they
# read rows, documents and chat logs on the event loop around the one call
# they handed to a thread, and every other request waited meanwhile.

_MAX_TEXT = limits.MAX_TEXT
AGENTS_DO_NOT_WRITE_PROMPTS = OPERATOR_ONLY["prompt"]


# DuckDB hands back NULL for an empty VARCHAR, and a page that does
# `tags.split(" ")` on that shows a crash card instead of the library. Text
# columns leave here as strings, always.
_TEXT_FIELDS = ("title", "project", "agent_id", "tags", "status", "source",
                "session_id", "archived_at", "created_date", "created_time")


def _clean(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for f in _TEXT_FIELDS:
        out[f] = str(out.get(f) or "")
    out["marks"] = promptlib.parse_marks(out.get("marks"))
    for f in ("versions_n", "source_turn"):
        out[f] = int(out.get(f) or 0)
    return out


def _row(store: ViewStore, prompt_id: str) -> dict[str, Any]:
    row = store.query_one("SELECT * FROM prompts_mutual WHERE id = ?", (prompt_id,))
    if row is None:
        raise not_found("prompt", prompt_id)
    return _clean(row)


def _detail(store: ViewStore, row: dict[str, Any]) -> dict[str, Any]:
    pid = str(row["id"])
    front, versions = promptlib.read_doc(store.data_root, pid)
    ratings = promptlib.ratings_for(store, pid)
    sends = []
    # The sends behind the count, each one openable in the chat it belongs
    # to, carrying the plain facts of what followed and the operator's
    # judgement of it. A number the operator cannot check is a number they
    # have to believe, and this page asks for enough belief already.
    for s in promptlib.sends(store, versions):
        s["facts"] = promptlib.facts_for(store, s)
        s["rating"] = ratings.get((s["session_id"], s["turn"]))
        s.pop("body", None)
        sends.append(s)
    by_version = promptlib.version_ratings(store, pid)
    return {
        "prompt": row,
        "versions": [{**v.as_dict(), "rating": by_version.get(v.n)} for v in versions],
        "current": versions[-1].as_dict() if versions else None,
        "metrics": promptlib.metrics(store, versions),
        "sends": sends,
        "rollup": promptlib.rollup(sends, versions),
        "scales": {**promptlib.SCALES, "score": [promptlib.SCORE_MIN, promptlib.SCORE_MAX]},
        "mark_names": promptlib.mark_names(store),
    }


def _made(store: ViewStore, versions: list, metrics: dict[str, Any]) -> dict[str, int]:
    sessions = sorted({str(s["session_id"]) for s in promptlib.sends(store, versions)})
    totals = {"commits": 0, "files": 0, "add": 0, "del": 0, "tasks": len(metrics.get("tasks") or [])}
    for g in git_for_sessions(store, sessions).values():
        for k in ("commits", "files", "add", "del"):
            totals[k] += int(g.get(k) or 0)
    return totals


@router.get("/api/prompt-library")
def prompts_list(
    request: Request,
    project: str = Query(""),
    status: str = Query("active"),
    q: str = Query(""),
    store: ViewStore = Depends(get_store),
) -> Response:
    """The library, newest first, each row carrying its use count.

    Adopts first: the page is the only place this feature is seen, so it is
    the right place to notice that the operator tagged something an hour ago.
    """
    added = adopt_when_changed(store, "prompts", promptlib.adopt)
    etag = etag_for(f"prompts:{project}:{status}:{q}:{len(added)}", store)
    if not added and (r := maybe_304(request, etag)) is not None:
        return r

    where = []
    args: list[Any] = []
    if project:
        where.append("project = ?")
        args.append(project)
    if status in promptlib.STATUSES:
        where.append("status = ?")
        args.append(status)
    sql = "SELECT * FROM prompts_mutual"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_date DESC, created_time DESC"
    rows = store.query(sql, tuple(args))

    needle = q.strip().lower()
    out = []
    for row in rows:
        _, versions = promptlib.read_doc(store.data_root, str(row["id"]))
        text = versions[-1].text if versions else ""
        if needle and needle not in (str(row.get("title") or "") + " " + text).lower():
            continue
        current = versions[-1] if versions else None
        rated = promptlib.version_ratings(store, str(row["id"])).get(current.n) if current else None
        metrics = promptlib.metrics(store, versions)
        out.append({
            **_clean(row),
            "preview": text[:400],
            "chars": len(text),
            "words": len(text.split()),
            "metrics": metrics,
            # The current wording's judgement, for a list that shows it.
            "current_rating": rated,
            "current_version": current.n if current else 0,
            # What the prompt caused, summed over the distinct sessions it was
            # sent in: commits and files from git, tasks it mentioned.
            "made": _made(store, versions, metrics),
        })
    return json_response({
        "prompts": out,
        "adopted": added,
        "mark_names": promptlib.mark_names(store),
        "counts": {
            s: len(store.query(
                "SELECT id FROM prompts_mutual WHERE status = ?", (s,)))
            for s in promptlib.STATUSES
        },
    }, etag)


@router.get("/api/prompt-library/marks")
def prompt_marks(store: ViewStore = Depends(get_store)) -> dict:
    """Every send of every prompt, by session then turn — for any chat reader
    to tag the turns that were a prompt. Registered before ``/{prompt_id}``."""
    return {"marks": promptlib.all_marks(store)}


@router.get("/api/prompt-library/candidates")
def prompt_candidates(store: ViewStore = Depends(get_store)) -> dict:
    """Messages sent again and again that were never filed.

    Registered before ``/{prompt_id}``, or "candidates" would be read as an
    id. This is the library's other door: the tag asks the operator to know a
    message matters before it has proved that it does, and a prompt usually
    earns its place on the fourth send.
    """
    return {
        "candidates": promptlib.candidates(store),
        "min_sends": promptlib.CANDIDATE_SENDS,
    }


@router.post("/api/prompt-library/candidates/{cluster}/keep")
def prompt_candidate_keep(
    cluster: str, store: ViewStore = Depends(get_store),
) -> dict:
    """File one — the newest wording becomes version 1, the sends stay behind it."""
    try:
        pid = promptlib.adopt_candidate(store, cluster)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _detail(store, _row(store, pid))


@router.get("/api/prompt-library/{prompt_id}")
def prompt_detail(prompt_id: str, store: ViewStore = Depends(get_store)) -> dict:
    """One prompt: every version, the notes on each, and where it was used."""
    return _detail(store, _row(store, prompt_id))


@router.post("/api/prompt-library/{prompt_id}/version")
def prompt_version(
    prompt_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store),
) -> dict:
    """``{text, note}`` — a rewrite, kept beside the ones before it.

    ``note`` is the evolution record: not what changed (the diff says that)
    but why it was worth changing. A rewrite identical to the current text
    is not recorded — an empty entry in a history is a lie about it.
    """
    row = _row(store, prompt_id)
    text = str(body.get("text") or "")
    if len(text) > _MAX_TEXT:
        raise HTTPException(status_code=422, detail=f"a prompt is at most {_MAX_TEXT} characters")
    try:
        promptlib.add_version(
            store, prompt_id, text, str(body.get("note") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _detail(store, _row(store, str(row["id"])))


@router.post("/api/prompt-library/{prompt_id}/runs/{session_id}/{turn}")
def prompt_rate_run(
    prompt_id: str, session_id: str, turn: int,
    body: dict = Body(...), store: ViewStore = Depends(get_store),
) -> dict:
    """``{task_success, regression, intervention, score, note}`` — judge one run.

    Any subset; a null clears that field. Steps outside the scales are
    refused rather than stored, because a rollup is only as honest as the
    values it counts.
    """
    _row(store, prompt_id)
    try:
        promptlib.rate_run(
            store, prompt_id, session_id, turn, body,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _detail(store, _row(store, prompt_id))


@router.post("/api/prompt-library/{prompt_id}/versions/{n}/rating")
def prompt_rate_version(
    prompt_id: str, n: int, body: dict = Body(...), store: ViewStore = Depends(get_store),
) -> dict:
    """``{task_success, regression, intervention, score, note}`` — judge one wording."""
    _row(store, prompt_id)
    _, versions = promptlib.read_doc(store.data_root, prompt_id)
    if not any(v.n == n for v in versions):
        raise not_found("version", str(n))
    try:
        promptlib.rate_version(store, prompt_id, n, body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _detail(store, _row(store, prompt_id))


@router.post("/api/prompt-library/{prompt_id}/update")
def prompt_update(
    prompt_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store),
) -> dict:
    """``{title, tags, status}`` — the row's own fields, not its text."""
    _row(store, prompt_id)
    fields: dict[str, Any] = {}
    if "title" in body:
        fields["title"] = str(body["title"] or "").strip()[:limits.MAX_TITLE]
    if "tags" in body:
        tags = body["tags"]
        if isinstance(tags, list):
            tags = " ".join(str(t) for t in tags)
        fields["tags"] = str(tags or "").strip()[:limits.MAX_TITLE]
    marks = None
    if "marks" in body:
        marks = body["marks"]
        if not isinstance(marks, dict):
            raise HTTPException(status_code=422, detail="marks must be an object")
    if "status" in body:
        status = str(body["status"] or "")
        if status not in promptlib.STATUSES:
            raise HTTPException(
                status_code=422,
                detail=f"status must be one of: {', '.join(promptlib.STATUSES)}",
            )
        fields["status"] = status
        # Archiving is the only "delete" here, and it is stamped so the row
        # can say when it left rather than merely that it is gone.
        fields["archived_at"] = today_yymm_dd() if status == "archived" else ""
    if not fields and marks is None:
        raise HTTPException(status_code=422, detail="nothing to update: send title, tags, marks or status")
    promptlib.set_fields(store, prompt_id, fields, marks)
    return _detail(store, _row(store, prompt_id))


@router.post("/api/prompt-library")
def prompt_create(
    body: dict = Body(...), store: ViewStore = Depends(get_store),
) -> dict:
    """Write one by hand — the same library, without waiting to tag a message.

    The generic lens create for this entity lives at ``POST /api/prompts``
    and has its own gate; this route is a second door into the same table, so
    it repeats the gate rather than inheriting it.
    """
    if written_by_agent(body):
        refuse_agent(AGENTS_DO_NOT_WRITE_PROMPTS)
    text = str(body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="text is required")
    if len(text) > _MAX_TEXT:
        raise HTTPException(status_code=422, detail=f"a prompt is at most {_MAX_TEXT} characters")
    created = promptlib.write_by_hand(
        store,
        str(body.get("title") or ""), text,
        str(body.get("project") or ""), str(body.get("tags") or ""),
    )
    return _detail(store, _row(store, created))
