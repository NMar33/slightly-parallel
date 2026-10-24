"""Task board mutations: field updates with an append-only event history."""

from __future__ import annotations

from typing import Any

import time

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response

from ..csvio import rewrite_rows
from ..db import ViewStore
from ..docs_md import resolve_under
from ..entities import (
    DOC_ITEM_COLUMNS, ENTITIES, TASK_EVENT_COLUMNS, TASK_LINK_COLUMNS,
    TASK_NOTE_COLUMNS,
)
from ..project_admin import TRASH_DIR, _archive_file, _split_rows, _stamp
from ..turns import (
    append_turn, description_of, replace_turn, turn_ref,
)
from ..file_safety import acquire_flock, lock_path
from .deps import (
    AGENT_REFUSED, etag_for, get_store, iso_moment, json_response, maybe_304,
    not_found, refuse_agent,
)
from .lenses import check_enum_fields, doc_path, task_membership
# What a task's status, archive and comeback date set off — whoever moves it:
# the board, an agent, #done, #undo (tasklib.py; the libraries call it there).
from ..tasklib import (  # noqa: F401
    AGENT_TAGS, AGENT_TAGS_MAX, AGENT_TITLE_MAX, DESCRIPTION_MAX, TASK_STATUSES, TITLE_MAX, _board_lanes,
    _gate_agent_create, _lane_for, _operator_command, _set_archived, _task_doc, _write_task_doc,
    after_status_change, create_task, maybe_resurface, resurface_sweep,
)


router = APIRouter()

_MUTABLE_FIELDS = {
    "status", "position", "assignee", "priority", "lane", "title", "tags",
    "due_date", "impact", "effort", "tokens", "novelty", "projects",
    "sprint_id", "resurface_on", "resurface_to", "resurface_every_days",
    "remember", "today_on", "stack_id",
    "auto_manage", "evidence_required", "evidence_prompt",
}

# Switches only the operator throws. auto_manage lets a card move on an
# agent's report; resurface_* moves it on a date; evidence_* decides what a
# report must carry; stack_id chains cards. An agent that could set these
# could move its own card by a side door. sprint_id is planning: the
# contract says sprints are the operator's, and the create gate already
# drops it — the update gate used to let it through.
_OPERATOR_FIELDS = frozenset({
    "auto_manage", "evidence_required", "evidence_prompt",
    "resurface_on", "resurface_to", "resurface_every_days", "stack_id",
    "sprint_id", "priority", "due_date",
})
# Keys an update body may carry that are not task columns.
_UPDATE_META_KEYS = frozenset({"actor", "agent_id", "description", "turn", "comment"})
#: Above an agent's comment, after the operator's text (the operator's wording).
COMMENT_MARK = "--- comment from agent:"
RESURFACE_EVERY_MAX = 36500   # a hundred years


# Server-side actors that are not agents (the board writes as "operator";
# stack promotion and resurfacing stamp their own names).
from .deps import identity_of  # the one reading, for every task gate
from ..taskevents import DEFAULT_ACTOR as _DEFAULT_ACTOR, append_events as _append_events  # noqa: E402
from .deps import HOUSE_ACTORS as _HOUSE_ACTORS  # noqa: E402 — the one list of house actors


@router.post("/api/tasks/{task_id}/update", status_code=200)
def tasks_update(
    task_id: str,
    body: dict = Body(...),
    store: ViewStore = Depends(get_store),
) -> dict:
    """Update mutable fields and/or the L2/L3/L4 body of one task.

    Every changed field appends one row to the ``task_events.csv`` history
    log. The CSV rewrite happens under the table's sidecar lock, so
    concurrent updates cannot lose each other's changes.
    """
    ent = ENTITIES["task"]
    check_enum_fields("task", body)
    csv_path = store.data_root / ent.csv
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail="tasks.csv not found")

    actor = identity_of(body)
    is_agent = actor not in _HOUSE_ACTORS
    if is_agent:
        held = sorted(k for k in body if k in _OPERATOR_FIELDS)
        if held:
            refuse_agent(
                f"{', '.join(held)} is the operator's switch",
                "an agent does not set it. Report your result instead: "
                f"MCP tool task_report {{id: \"{task_id}\", summary}}.",
            )
        if "turn" in body:
            # The rounds after the first are the operator's, added on the
            # card; an agent's way to the text is `description` (round 1).
            refuse_agent("a task's later rounds are the operator's",
                         "change the task's own text with `description`.")
    if "title" in body and len(str(body.get("title") or "")) > TITLE_MAX:
        raise HTTPException(status_code=422, detail=f"title is at most {TITLE_MAX} characters")
    every = str(body.get("resurface_every_days") or "").strip()
    if every.isdigit() and int(every) > RESURFACE_EVERY_MAX:
        # A day count past the calendar raised OverflowError: a 500. Text
        # that is not a number is stored and never acted on, as before.
        raise HTTPException(status_code=422,
                            detail=f"resurface_every_days is at most {RESURFACE_EVERY_MAX} days")
    if "description" in body and len(str(body.get("description") or "")) > DESCRIPTION_MAX:
        raise HTTPException(status_code=422, detail=f"description is at most {DESCRIPTION_MAX} characters")
    comment = str(body.get("comment") or "").strip()
    if "comment" in body and not comment:
        raise HTTPException(status_code=422, detail="a comment needs its text")
    if is_agent and "description" in body and store.query_one(
            "SELECT task_id FROM task_events_mutual WHERE task_id = ? AND field IN ('started', 'filed') "
            "AND new_value LIKE '%#now%'", (task_id,)):
        # The operator's #now message is the card's text, kept as written.
        refuse_agent("a #now task's text is the operator's message, kept as it was written",
                     f"add yours after it: task_update {{id: \"{task_id}\", comment}}")
    ignored = sorted(
        k for k in body
        if k not in _MUTABLE_FIELDS and k not in _UPDATE_META_KEYS and k not in ("l2", "l3", "l4", "body")
    )
    if any(k in body for k in ("l2", "l3", "l4", "body")):
        # Whoever sent it: a task has no levels. Said before anything moves.
        raise HTTPException(status_code=AGENT_REFUSED, detail=(
            "a task holds a title and a description: send `description` "
            "(the task's text). Adding the next round is the operator's act."
        ))
    changes: list[tuple[str, str, str]] = []
    # What the status change sets off on other cards. Written after the
    # rewrite lands: a refused update used to leave a stack event behind.
    side_events: list[tuple[str, str, list[tuple[str, str, str]]]] = []

    def mutate(rows: list[dict[str, str]]) -> bool:
        target = next((r for r in rows if r.get("id") == task_id), None)
        if target is None:
            raise not_found("task", task_id)
        # Task status belongs to the operator. An agent may move a card
        # only when the task opts in (auto_manage) — and the honest path
        # even then is POST /api/tasks/{id}/report, which moves it to
        # review and stamps the badge.
        # The one exception: "drop it" — an agent may archive a card it
        # created in the `agent` column (/task) when the user waves it off.
        own_drop = (
            is_agent
            and str(body.get("status") or "") == "done-archived"
            and str(target.get("status") or "") == "agent"
            and str(target.get("agent_id") or "") == actor
        )
        if is_agent and "status" in body and not own_drop and str(target.get("auto_manage") or "") != "yes":
            refuse_agent(
                "task status belongs to the operator: this task does not "
                "allow auto-manage. Report your result instead: "
                f"MCP tool task_report {{id: \"{task_id}\", summary}}."
            )
        if not is_agent and "status" in body:
            # The operator's verdict clears the agent's pending report.
            for stamp_field in ("agent_done_at", "agent_done_by", "agent_done_note"):
                old = str(target.get(stamp_field) or "")
                if old:
                    target[stamp_field] = ""
                    changes.append((stamp_field, old, ""))
        for k, v in body.items():
            if k not in _MUTABLE_FIELDS:
                continue
            new_v = str(v) if v is not None else ""
            if k == "projects":
                # Membership can grow or shrink but never loses the home project.
                new_v = task_membership(str(target.get("project") or ""), v)
            old_v = target.get(k, "") or ""
            if new_v != old_v:
                changes.append((k, old_v, new_v))
            target[k] = new_v

        old_status = next((old for f, old, _new in changes if f == "status"), None)
        after_status_change(store, rows, target, old_status, changes, deferred=side_events)

        if "description" in body or "turn" in body or comment:
            md_ref, _ = doc_path(store, ent, target, task_id)
            target["md_ref"] = md_ref
            fm, turns = _task_doc(store, md_ref, target, task_id)
            try:
                if "description" in body:
                    turns = replace_turn(turns, str(body.get("description") or ""), 1)
                    changes.append(("description", "", "(updated)"))
                if comment:
                    # Each comment goes after the text and the comments before it.
                    text = description_of(turns).rstrip()
                    mark = COMMENT_MARK if is_agent else "--- comment:"
                    grown = f"{text}\n\n{mark}\n{comment}" if text else f"{mark}\n{comment}"
                    if len(grown) > DESCRIPTION_MAX:
                        raise HTTPException(status_code=422, detail=(
                            f"the text with this comment is over {DESCRIPTION_MAX} characters: write it shorter"))
                    turns = replace_turn(turns, grown, 1)
                    changes.append(("comment", "", "(added)"))
                if "turn" in body:
                    spec = body.get("turn") if isinstance(body.get("turn"), dict) else {"text": body.get("turn")}
                    n = spec.get("n")
                    try:
                        at = int(n) if n else None
                    except (TypeError, ValueError):
                        raise HTTPException(status_code=422, detail="turn.n must be a whole number") from None
                    turns = replace_turn(turns, str(spec.get("text") or ""), at)
                    changes.append(("turn", str(n or (turns[-1].n if turns else 1)), "(edited)"))
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc))
            _write_task_doc(store, md_ref, fm, turns)
        return bool(changes)

    rewrite_rows(csv_path, ent.columns, mutate)

    for other_id, other_actor, other_changes in side_events:
        _append_events(store, other_id, other_actor, other_changes)
    if changes:
        _append_events(store, task_id, actor, changes)

    store.rebuild()
    updated = store.query_one(
        "SELECT * FROM tasks_mutual WHERE id = ?", (task_id,)
    )
    out: dict[str, Any] = {"task": updated or {}}
    if ignored:
        # Named, so a misspelt field is not a silent no-op.
        out["ignored"] = ignored
    return out


@router.post("/api/tasks/{task_id}/turn", status_code=201)
def tasks_add_turn(
    task_id: str,
    body: dict = Body(...),
    store: ViewStore = Depends(get_store),
) -> dict:
    """Add the next round of instruction to a task.

    The same task, worked on again: the text is appended to the
    description behind a turn marker (see ``backend/turns.py``) rather
    than replacing what is there, and the reference it will be copied
    under — ``tk_….2`` — comes back in ``ref``. A ``turn`` row lands in the
    task's event log, so the rounds are visible in its history.
    """
    text = str(body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="a turn needs text: send text")
    row = store.query_one("SELECT * FROM tasks_mutual WHERE id = ?", (task_id,))
    if not row:
        raise not_found("task", task_id)

    md_ref = str(row.get("md_ref") or "")
    if not md_ref or resolve_under(store.data_root, md_ref) is None:
        # A task created without text has no document yet (or its row points
        # outside the data root) — the update path mints one; go through it
        # with an empty description first.
        tasks_update(task_id, {"description": "", "actor": identity_of(body) or _DEFAULT_ACTOR}, store)
        row = store.query_one("SELECT * FROM tasks_mutual WHERE id = ?", (task_id,)) or row
        md_ref = str(row.get("md_ref") or "")
    date = str(body.get("created_date") or "").strip() or time.strftime("%y%m-%d")
    stamp = str(body.get("created_time") or "").strip() or time.strftime("%H:%M")
    # Read, append and write under the lock tasks_update writes the document
    # under: two turns at once each read the document, and the second write
    # dropped the first one's turn.
    with acquire_flock(lock_path(store.data_root / ENTITIES["task"].csv)):
        fm, turns = _task_doc(store, md_ref, row, task_id)
        before = len(turns)
        try:
            turns = append_turn(turns, text, date, stamp)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        _write_task_doc(store, md_ref, fm, turns)

    # Who wrote it, read the one way (deps.identity_of): an agent's write
    # names itself in agent_id, and was logged as the operator's.
    actor = identity_of(body) or _DEFAULT_ACTOR
    _append_events(store, task_id, actor, [("turn", str(before), str(len(turns)))])
    store.rebuild()
    updated = store.query_one("SELECT * FROM tasks_mutual WHERE id = ?", (task_id,))
    return {
        "task": updated or {},
        "turn": len(turns),
        "ref": turn_ref(task_id, len(turns)),
        "description": description_of(turns),
        "turns": [t.as_dict() for t in turns],
    }


@router.get("/api/tasks/{task_id}/events")
def tasks_events(
    task_id: str,
    request: Request,
    limit: int = Query(200, ge=1, le=2000),
    store: ViewStore = Depends(get_store),
) -> Response:
    """History log for one task — every field change appended by /update."""
    etag = etag_for(f"tasks:events:{task_id}:{limit}", store, "tasks", "chats")
    if (r := maybe_304(request, etag)) is not None:
        return r
    rows = store.query(
        "SELECT * FROM task_events_mutual WHERE task_id = ? "
        "ORDER BY timestamp DESC LIMIT ?",
        (task_id, limit),
    )
    # Rows written before ids carried their batch position could share an
    # id (the same body edit twice in one second). The log keeps them;
    # the timeline gets one line per id.
    seen: set[str] = set()
    events = []
    for r in rows:
        rid = str(r.get("event_id") or r.get("id") or "")
        if rid and rid in seen:
            continue
        seen.add(rid)
        events.append(r)
    return json_response({"total": len(events), "events": events}, etag)


# ---------------------------------------------------------------------------
# Archive (reversible) and delete (to .trash)
# ---------------------------------------------------------------------------


@router.post("/api/tasks/{task_id}/archive")
def tasks_archive(task_id: str, body: dict = Body(default={}), store: ViewStore = Depends(get_store)) -> dict:
    """Hide the task from the board, keep everything; reversible."""
    return _set_archived(store, task_id, time.strftime("%Y-%m-%dT%H:%M:%S"), identity_of(body) or _DEFAULT_ACTOR)


@router.post("/api/tasks/{task_id}/restore")
def tasks_restore(task_id: str, body: dict = Body(default={}), store: ViewStore = Depends(get_store)) -> dict:
    return _set_archived(store, task_id, "", identity_of(body) or _DEFAULT_ACTOR)


@router.post("/api/tasks/{task_id}/delete")
def tasks_delete(task_id: str, store: ViewStore = Depends(get_store)) -> dict:
    """Move the task — row, detail doc, events, links, story notes — to
    ``<data_root>/.trash/tasks/<id>-<stamp>/``, recoverable by moving back.
    Doc blocks that used its notes keep a placeholder."""
    ent = ENTITIES["task"]
    row = store.query_one("SELECT id, md_ref FROM tasks_mutual WHERE id = ?", (task_id,))
    if row is None:
        raise not_found("task", task_id)
    root = store.data_root
    trash = root / TRASH_DIR / "tasks" / f"{task_id}-{_stamp()}"
    trash.mkdir(parents=True, exist_ok=True)
    moved: dict[str, int] = {}
    moved["task"] = _split_rows(root, trash, ent.csv, ent.columns, lambda r: r.get("id") == task_id)
    if row.get("md_ref") and _archive_file(root, trash, str(row["md_ref"])):
        moved["detail_doc"] = 1
    moved["events"] = _split_rows(root, trash, "task_events.csv", TASK_EVENT_COLUMNS, lambda r: r.get("task_id") == task_id)
    moved["links"] = _split_rows(root, trash, "task_links.csv", TASK_LINK_COLUMNS,
                                 lambda r: task_id in (r.get("from_id"), r.get("to_id")))
    note_ids: set[str] = set()
    moved["notes"] = _split_rows(root, trash, "task_notes.csv", TASK_NOTE_COLUMNS,
                                 lambda r: r.get("task_id") == task_id,
                                 lambda r: note_ids.add(str(r.get("id") or "")))
    items_csv = root / "doc_items.csv"
    if note_ids and items_csv.exists():
        def strip(rows: list[dict[str, str]]) -> bool:
            changed = False
            for it in rows:
                if it.get("note_id") in note_ids:
                    it["note_id"] = ""
                    it["text"] = it.get("text") or "(note removed with its task)"
                    changed = True
            return changed
        rewrite_rows(items_csv, DOC_ITEM_COLUMNS, strip)
    store.rebuild()
    return {"deleted": task_id, "trash": str(trash), "moved": moved}


@router.get("/api/tasks/status-since")
def tasks_status_since(
    request: Request,
    project: str = Query(...),
    store: ViewStore = Depends(get_store),
) -> Response:
    """Per task: when it entered its current column — the last status change
    from the event log, else its creation moment. Feeds the aging corner."""
    etag = etag_for(f"tasks:status-since:{project}", store, "tasks", "chats")
    if (r := maybe_304(request, etag)) is not None:
        return r
    tasks = store.query(
        "SELECT id, created_date, created_time FROM tasks_mutual WHERE project = ? "
        "OR list_contains(string_split(COALESCE(projects, ''), ','), ?)",
        (project, project),
    )
    if not tasks:
        return json_response({"since": {}}, etag)
    ids = [t["id"] for t in tasks]
    ph = ",".join("?" * len(ids))
    last = {
        r["task_id"]: str(r["ts"])
        for r in store.query(
            f"SELECT task_id, MAX(timestamp) AS ts FROM task_events_mutual "
            f"WHERE field = 'status' AND task_id IN ({ph}) GROUP BY task_id",
            tuple(ids),
        )
    }
    since = {
        t["id"]: last.get(t["id"]) or iso_moment(t.get("created_date"), t.get("created_time"))
        for t in tasks
    }
    return json_response({"since": {k: v for k, v in since.items() if v}}, etag)


# ---------------------------------------------------------------------------
# Bring it back — scheduled resurfacing
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# The task's own create and detail — tasks speak `description` and `turns`,
# not the generic l2/l3/l4. On a router of their own (``detail_router``)
# that server.py includes after every literal /api/tasks/… route (this
# file's and story.py's notes) and before the generic lens router, so
# ``/api/tasks/{task_id}`` neither shadows a literal path nor loses to
# the generic detail.
# ---------------------------------------------------------------------------

detail_router = APIRouter()

@detail_router.post("/api/tasks", status_code=201)
def tasks_create(
    response: Response,
    body: dict = Body(...),
    store: ViewStore = Depends(get_store),
) -> dict:
    """Create a task. Text goes in `description`; turns come later via
    POST /api/tasks/{id}/turn. Idempotent on the minted id: the same
    payload again answers 200 with ``existing: true``. An agent's create
    goes through the /task gate (tasklib.create_task)."""
    out = create_task(store, body)
    if out["existing"]:
        response.status_code = 200
    return out


@detail_router.get("/api/tasks/{task_id}")
def tasks_detail(
    task_id: str,
    request: Request,
    store: ViewStore = Depends(get_store),
) -> Response:
    """One task: its row, its description (turn 1) and every round."""
    etag = etag_for(f"tasks:detail:{task_id}", store, "tasks", "chats")
    if (r := maybe_304(request, etag)) is not None:
        return r
    row = store.query_one("SELECT * FROM tasks_mutual WHERE id = ?", (task_id,))
    if row is None:
        raise not_found("task", task_id)
    _fm, turns = _task_doc(store, str(row.get("md_ref") or ""), row, task_id)
    return json_response({
        "metadata": row,
        "description": description_of(turns),
        "turns": [t.as_dict() for t in turns],
        "turns_n": len(turns),
    }, etag)
