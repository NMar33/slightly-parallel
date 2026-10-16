"""Task board mutations: field updates with an append-only event history."""

from __future__ import annotations

from typing import Any

import bisect
import hashlib
import logging
import time
from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response

from .. import app_settings, limits
from ..csvio import append_if_absent, append_rows_raw, read_rows, rewrite_rows
from ..db import ViewStore
from ..docs_md import build_detail, read_detail, resolve_under
from ..frontmatter import block as fm_block
from ..entities import (
    DOC_ITEM_COLUMNS, ENTITIES, TASK_EVENT_COLUMNS, TASK_LINK_COLUMNS,
    is_done,
    TASK_LINK_KINDS, TASK_NOTE_COLUMNS,
)
from ..project_admin import TRASH_DIR, _archive_file, _split_rows, _stamp
from ..turns import (
    Turn, append_turn, build_task_doc, description_of, parse_task_doc,
    replace_turn, turn_ref,
)
from ..file_safety import acquire_flock, atomic_write, lock_path
from .deps import (
    AGENT_REFUSED, DONE_SQL, agents_by_id, attach_agent, create_answer, day_date, etag_for,
    get_store, iso_moment, json_response, maybe_304, not_found, refuse_agent, ymd,
)
from .lenses import ENUM_FIELDS, check_enum_fields, create_entity, doc_path, task_membership

TASK_STATUSES = ENUM_FIELDS["task"]["status"]

router = APIRouter()

_MUTABLE_FIELDS = {
    "status", "position", "assignee", "priority", "lane", "title", "tags",
    "due_date", "impact", "effort", "tokens", "novelty", "projects",
    "sprint_id", "resurface_on", "resurface_to", "resurface_every_days",
    "remember", "today_on", "stack_id",
    "auto_manage", "evidence_required", "evidence_prompt",
}
_DEFAULT_ACTOR = "operator"

# Switches only the operator throws. auto_manage lets a card move on an
# agent's report; resurface_* moves it on a date; evidence_* decides what a
# report must carry; stack_id chains cards. An agent that could set these
# could move its own card by a side door. sprint_id is planning: the
# contract says sprints are the operator's, and the create gate already
# drops it — the update gate used to let it through.
_OPERATOR_FIELDS = frozenset({
    "auto_manage", "evidence_required", "evidence_prompt",
    "resurface_on", "resurface_to", "resurface_every_days", "stack_id",
    "sprint_id",
})
# Keys an update body may carry that are not task columns.
_UPDATE_META_KEYS = frozenset({"actor", "agent_id", "description", "turn"})
TITLE_MAX = limits.MAX_TASK_TITLE
DESCRIPTION_MAX = limits.MAX_TASK_DESCRIPTION


# Server-side actors that are not agents (the board writes as "operator";
# stack promotion and resurfacing stamp their own names).
from .deps import identity_of  # the one reading, for every task gate
from .deps import HOUSE_ACTORS as _HOUSE_ACTORS  # noqa: E402 — the one list of house actors


def _append_events(
    store: ViewStore, task_id: str, actor: str, changes: list[tuple[str, str, str]]
) -> None:
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    rows = []
    for i, (field, old_v, new_v) in enumerate(changes):
        # The position in the batch and the actor are part of the seed:
        # two identical changes written in one second (the same body
        # edit twice, two "(updated)" markers) must not share an id —
        # the timeline keys on it.
        seed = f"{task_id}{ts}{i}{actor or _DEFAULT_ACTOR}{field}{new_v}".encode()
        event_id = "ev_" + hashlib.sha256(seed).hexdigest()[:10]
        rows.append([event_id, task_id, ts, actor or _DEFAULT_ACTOR, field, old_v, new_v])
    append_rows_raw(
        store.data_root / "task_events.csv", TASK_EVENT_COLUMNS, rows
    )


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
    if "title" in body and len(str(body.get("title") or "")) > TITLE_MAX:
        raise HTTPException(status_code=422, detail=f"title is at most {TITLE_MAX} characters")
    if "description" in body and len(str(body.get("description") or "")) > DESCRIPTION_MAX:
        raise HTTPException(status_code=422, detail=f"description is at most {DESCRIPTION_MAX} characters")
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

        if "description" in body or "turn" in body:
            md_ref, _ = doc_path(store, ent, target, task_id)
            target["md_ref"] = md_ref
            fm, turns = _task_doc(store, md_ref, target, task_id)
            try:
                if "description" in body:
                    turns = replace_turn(turns, str(body.get("description") or ""), 1)
                    changes.append(("description", "", "(updated)"))
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


def _task_doc(store: ViewStore, md_ref: str, row: dict, task_id: str) -> tuple[str, list[Turn]]:
    """(frontmatter, turns) of a task's document — a fresh frontmatter from
    the row when the file does not exist yet."""
    path = resolve_under(store.data_root, md_ref) if md_ref else None
    if path is not None and path.exists():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            text = ""
        # The parameter name ``frontmatter`` is taken in this module, so
        # the one parser comes in under its function name.
        fm, _ = fm_block(text)
        if text.startswith("---"):
            return fm, parse_task_doc(text)
    front = {k: v for k, v in row.items() if k not in ("l2", "l3", "l4") and v not in (None, "")}
    return build_detail(front, task_id).rstrip("\n"), []


def _write_task_doc(store: ViewStore, md_ref: str, frontmatter: str, turns: list[Turn]) -> None:
    md_path = resolve_under(store.data_root, md_ref)
    if md_path is None:
        # Callers take the ref from doc_path; this is the last check.
        raise HTTPException(status_code=422, detail="the task's document path is outside the data folder")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(md_path, build_task_doc(frontmatter, turns))


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
# Chat mentions and the task timeline — derived, never stored
# ---------------------------------------------------------------------------


@router.get("/api/tasks/mentions/summary")
def tasks_mentions_summary(
    request: Request,
    project: str | None = Query(None),
    store: ViewStore = Depends(get_store),
) -> Response:
    """Per task: how often its id appeared in captured chats, and the last
    time — enough for a chip on the card."""
    etag = etag_for(f"tasks:mentions:summary:{project}", store, "tasks", "chats")
    if (r := maybe_304(request, etag)) is not None:
        return r
    clauses, params = ["1=1"], []
    if project:
        clauses.append("project = ?")
        params.append(project)
    rows = store.query(
        "SELECT task_id, COUNT(*) AS n, MAX(at_ts) AS last_at, "
        "arg_max(agent_id, at_ts) AS last_agent, arg_max(role, at_ts) AS last_role "
        "FROM task_mentions WHERE " + " AND ".join(clauses) + " GROUP BY task_id",
        tuple(params),
    )
    attach_agent(store, rows, field="last_agent")
    return json_response({"mentions": {r["task_id"]: r for r in rows}}, etag)


@router.get("/api/tasks/{task_id}/mentions")
def tasks_mentions(
    task_id: str,
    request: Request,
    store: ViewStore = Depends(get_store),
) -> Response:
    """Every captured turn that names this task, newest first.

    Each row carries the agent behind it under ``agent`` (``null`` when the
    chat is gone): the names a reader shows instead of the raw id, and the
    tool, folder and session id a resume command is built from.
    """
    etag = etag_for(f"tasks:mentions:{task_id}", store, "tasks", "chats")
    if (r := maybe_304(request, etag)) is not None:
        return r
    rows = store.query(
        "SELECT task_id, project, agent_id, session_id, turn, at_ts AS at, role, excerpt "
        "FROM task_mentions WHERE task_id = ? ORDER BY at_ts DESC", (task_id,)
    )
    attach_agent(store, rows)
    return json_response({"total": len(rows), "mentions": rows}, etag)


_DONE_SQL = DONE_SQL  # a finished task in SQL, from the one list of done statuses (deps)

_WINDOW_DAYS = {"day": 1, "week": 7, "month": 30}


_iso_of = iso_moment  # '2608-19' + '02:47' → '2026-08-19T02:47:00' (deps)


@router.get("/api/tasks/timeline")
def tasks_timeline(
    request: Request,
    project: str = Query(...),
    window: str = Query("week"),
    limit: int = Query(10, ge=0, le=1000),
    store: ViewStore = Depends(get_store),
) -> Response:
    """Per task, everything that happened to it: creation, status changes and
    edits (task_events), and captured-chat mentions — for the task timeline.

    Tasks with any event inside the window, most recently active first,
    capped at ``limit`` (0 = all). Each task carries its full event list so
    the client can draw the status band that was already in force when the
    window opens.
    """
    # `all`: since the project's first event — the window opens there.
    days = None if window == "all" else _WINDOW_DAYS.get(window, 7)
    etag = etag_for(f"tasks:timeline:{project}:{days}:{limit}", store, "tasks", "chats")
    if (r := maybe_304(request, etag)) is not None:
        return r
    since = time.time() - (days if days is not None else 30) * 86400
    since_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(since))

    tasks = store.query(
        "SELECT id, title, status, priority, impact, effort, assignee, project, "
        "projects, created_date, created_time FROM tasks_mutual WHERE project = ? "
        "OR list_contains(string_split(COALESCE(projects, ''), ','), ?)",
        (project, project),
    )
    if not tasks:
        return json_response({"window": window, "since": since_iso, "tasks": []}, etag)
    ids = [t["id"] for t in tasks]
    ph = ",".join("?" * len(ids))
    events = store.query(
        f"SELECT task_id, timestamp, actor, field, old_value, new_value "
        f"FROM task_events_mutual WHERE task_id IN ({ph}) ORDER BY timestamp ASC",
        tuple(ids),
    )
    mentions = store.query(
        f"SELECT task_id, at_ts AS at, role, agent_id, session_id, turn, excerpt "
        f"FROM task_mentions WHERE task_id IN ({ph}) ORDER BY at_ts ASC",
        tuple(ids),
    )
    by: dict[str, list[dict]] = {t["id"]: [] for t in tasks}
    for t in tasks:
        created = _iso_of(t.get("created_date"), t.get("created_time"))
        if created:
            by[t["id"]].append({"at": created, "kind": "created"})
    for e in events:
        kind = "status" if e.get("field") == "status" else "edit"
        by[e["task_id"]].append({
            "at": str(e.get("timestamp") or ""), "kind": kind,
            "field": e.get("field"), "from": e.get("old_value"), "to": e.get("new_value"),
            "actor": e.get("actor"),
        })
    # The agent behind each mention rides along, so the timeline names it
    # and offers the resume the panel offers — one lookup for every task.
    agents = agents_by_id(store)
    for m in mentions:
        by[m["task_id"]].append({
            "at": str(m.get("at") or ""), "kind": "mention", "role": m.get("role"),
            "agent_id": m.get("agent_id"), "session_id": m.get("session_id"),
            "turn": m.get("turn"), "excerpt": m.get("excerpt"),
            "agent": agents.get(str(m.get("agent_id") or "")),
        })

    if days is None:
        first = min((e["at"] for evs in by.values() for e in evs if e["at"]), default="")
        if first:
            since_iso = first[:19]
    out = []
    for t in tasks:
        evs = sorted(by[t["id"]], key=lambda e: e["at"])
        last = max((e["at"] for e in evs), default="")
        if last < since_iso:
            continue
        out.append({**t, "events": evs, "last_at": last})
    out.sort(key=lambda x: x["last_at"], reverse=True)
    if limit:
        out = out[:limit]
    return json_response({"window": window, "since": since_iso, "tasks": out}, etag)


@router.get("/api/tasks/mentions/by-agent")
def tasks_mentions_by_agent(
    request: Request,
    project: str = Query(...),
    store: ViewStore = Depends(get_store),
) -> Response:
    """Per agent lane: every captured turn that named a task, with the task
    title — the marks on the agent timeline."""
    etag = etag_for(f"tasks:mentions:by-agent:{project}", store, "tasks", "chats")
    if (r := maybe_304(request, etag)) is not None:
        return r
    rows = store.query(
        "SELECT m.agent_id, m.task_id, COALESCE(t.title, '') AS title, "
        "m.at_ts AS at, m.role, m.session_id, m.turn "
        "FROM task_mentions m JOIN tasks_mutual t ON t.id = m.task_id "
        "WHERE m.project = ? ORDER BY m.at_ts ASC, m.turn ASC, CASE m.role WHEN 'user' THEN 0 ELSE 1 END",
        (project,),
    )
    by: dict[str, list[dict]] = {}
    for r in rows:
        by.setdefault(str(r["agent_id"]), []).append(
            {k: r[k] for k in ("task_id", "title", "at", "role", "session_id", "turn")}
        )
    return json_response({"agents": by}, etag)


# ---------------------------------------------------------------------------
# Links between tasks — blocks / relates / parent
# ---------------------------------------------------------------------------

_LINK_SELECT = (
    "SELECT l.id, l.from_id, l.to_id, l.kind, l.created_at, l.actor "
    "FROM task_links_mutual l"
)


def _task_brief(store: ViewStore, ids: set[str]) -> dict[str, dict]:
    if not ids:
        return {}
    ph = ",".join("?" * len(ids))
    rows = store.query(
        f"SELECT id, title, status, project, projects FROM tasks_mutual WHERE id IN ({ph})",
        tuple(ids),
    )
    return {r["id"]: r for r in rows}


def _resolve(store: ViewStore, links: list[dict]) -> list[dict]:
    ids = {l["from_id"] for l in links} | {l["to_id"] for l in links}
    brief = _task_brief(store, ids)
    out = []
    for l in links:
        out.append({
            **l,
            "from": brief.get(l["from_id"], {"id": l["from_id"], "title": "", "status": ""}),
            "to": brief.get(l["to_id"], {"id": l["to_id"], "title": "", "status": ""}),
        })
    return out


@router.get("/api/tasks/links")
def tasks_links_all(
    request: Request,
    project: str = Query(...),
    store: ViewStore = Depends(get_store),
) -> Response:
    """Every link touching a task of the project (home or member) — the
    board's overlay. Both endpoints are resolved (title, status, project)."""
    etag = etag_for(f"tasks:links:{project}", store, "tasks", "chats")
    if (r := maybe_304(request, etag)) is not None:
        return r
    rows = store.query(
        _LINK_SELECT + " WHERE l.from_id IN (SELECT id FROM tasks_mutual WHERE project = ? "
        "OR list_contains(string_split(COALESCE(projects, ''), ','), ?)) "
        "OR l.to_id IN (SELECT id FROM tasks_mutual WHERE project = ? "
        "OR list_contains(string_split(COALESCE(projects, ''), ','), ?)) "
        "ORDER BY l.created_at ASC",
        (project, project, project, project),
    )
    return json_response({"total": len(rows), "links": _resolve(store, rows)}, etag)


@router.get("/api/tasks/{task_id}/links")
def tasks_links(
    task_id: str,
    request: Request,
    store: ViewStore = Depends(get_store),
) -> Response:
    """Links of one task, both directions, resolved."""
    etag = etag_for(f"tasks:links:one:{task_id}", store, "tasks", "chats")
    if (r := maybe_304(request, etag)) is not None:
        return r
    rows = store.query(
        _LINK_SELECT + " WHERE l.from_id = ? OR l.to_id = ? ORDER BY l.created_at ASC",
        (task_id, task_id),
    )
    return json_response({"total": len(rows), "links": _resolve(store, rows)}, etag)


def _reaches(rows: list[dict], kind: str, start: str, goal: str) -> bool:
    """True when `goal` is reachable from `start` along `kind` edges."""
    nxt: dict[str, list[str]] = {}
    for r in rows:
        if r.get("kind") == kind:
            nxt.setdefault(str(r.get("from_id")), []).append(str(r.get("to_id")))
    seen, todo = {start}, [start]
    while todo:
        for n in nxt.get(todo.pop(), []):
            if n == goal:
                return True
            if n not in seen:
                seen.add(n)
                todo.append(n)
    return False


def _link_refusal(rows: list[dict], a: str, b: str, kind: str, store: ViewStore) -> str | None:
    """Why `a —kind→ b` would break the graph, or None. Blocks and parent
    are directed and must not loop; a task has one parent at most."""
    if kind == "blocks" and _reaches(rows, "blocks", b, a):
        return "that would make a loop: the other task already blocks this one"
    if kind == "parent":
        other = next((r for r in rows if r.get("kind") == "parent" and r.get("to_id") == b), None)
        if other is not None:
            title = (_task_brief(store, {str(other.get("from_id"))}).get(str(other.get("from_id"))) or {}).get("title")
            return f"that task is already a sub-task of {title or other.get('from_id')}"
        if _reaches(rows, "parent", b, a):
            return "that would make a loop: this task is already under the other one"
    return None


@router.post("/api/tasks/{task_id}/link", status_code=201)
def tasks_link(
    task_id: str,
    response: Response,
    body: dict = Body(...),
    store: ViewStore = Depends(get_store),
) -> dict:
    """``{to, kind, actor?}`` — kind ∈ blocks | relates | parent. From the
    caller's side: A blocks B, A relates B, A is parent of B. Idempotent on
    (from, to, kind); a `relates` link is stored once whichever end asks."""
    to = str(body.get("to") or "").strip()
    kind = str(body.get("kind") or "").strip()
    actor = identity_of(body) or _DEFAULT_ACTOR
    if not to or to == task_id:
        raise HTTPException(status_code=422, detail="to must be another task id")
    if kind not in TASK_LINK_KINDS:
        raise HTTPException(status_code=422, detail=f"kind must be one of {', '.join(TASK_LINK_KINDS)}")
    known = _task_brief(store, {task_id, to})
    if task_id not in known or to not in known:
        raise HTTPException(status_code=422, detail="both tasks must exist")

    a, b = task_id, to
    if kind == "relates" and b < a:
        a, b = b, a  # canonical order for the symmetric kind
    csv_path = store.data_root / "task_links.csv"
    rows = read_rows(csv_path)
    for r in rows:
        if r.get("from_id") == a and r.get("to_id") == b and r.get("kind") == kind:
            # `created` is what the pages read; `existing` and the 200 are
            # the one rule every create follows (deps.create_answer).
            return create_answer({"link": r, "created": False}, response, existing=True)
    if (why := _link_refusal(rows, a, b, kind, store)) is not None:
        raise HTTPException(status_code=422, detail=why)
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    lid = "lk_" + hashlib.sha256(f"{a}|{b}|{kind}".encode()).hexdigest()[:8]
    row = {"id": lid, "from_id": a, "to_id": b, "kind": kind, "created_at": ts, "actor": actor}
    # The look above read the file a moment ago; this one is under the lock.
    raced = append_if_absent(
        csv_path, TASK_LINK_COLUMNS, row,
        lambda r: r.get("from_id") == a and r.get("to_id") == b and r.get("kind") == kind,
    )
    if raced is not None:
        return create_answer({"link": raced, "created": False}, response, existing=True)
    # Both timelines see it.
    _append_events(store, a, actor, [("link", "", f"{kind} → {b}")])
    _append_events(store, b, actor, [("link", "", f"{kind} ← {a}")])
    store.rebuild()
    return create_answer({"link": row, "created": True})


@router.post("/api/tasks/links/{link_id}/update")
def tasks_link_update(
    link_id: str,
    body: dict = Body(default={}),
    store: ViewStore = Depends(get_store),
) -> dict:
    """``{kind?, reverse?, actor?}`` — change a link's kind, or turn it
    around (the other task blocks / is the parent). The same rules as a new
    link: no loops, one parent, no duplicate. Answers the link as stored."""
    csv_path = store.data_root / "task_links.csv"
    # Decided on the rows under the lock: a decision made on a read taken
    # before it let a link deleted meanwhile answer "changed" and log
    # history, and two updates both pass the duplicate and loop checks.
    out: dict = {}

    def mutate(rows: list[dict[str, str]]) -> bool:
        cur = next((r for r in rows if r.get("id") == link_id), None)
        if cur is None:
            return False
        kind = str(body.get("kind") or cur["kind"]).strip()
        if kind not in TASK_LINK_KINDS:
            raise HTTPException(status_code=422, detail=f"kind must be one of {', '.join(TASK_LINK_KINDS)}")
        a, b = cur["from_id"], cur["to_id"]
        if body.get("reverse"):
            a, b = b, a
        if kind == "relates" and b < a:
            a, b = b, a
        if (a, b, kind) == (cur["from_id"], cur["to_id"], cur["kind"]):
            out.update(link=dict(cur), changed=False)
            return False
        others = [r for r in rows if r.get("id") != link_id]
        if any(r.get("from_id") == a and r.get("to_id") == b and r.get("kind") == kind for r in others):
            raise HTTPException(status_code=409, detail="that link already exists")
        if (why := _link_refusal(others, a, b, kind, store)) is not None:
            raise HTTPException(status_code=422, detail=why)
        # The id follows (from, to, kind), as a new link's would, so a later
        # create of the old shape is not mistaken for this one.
        new = {**cur, "id": "lk_" + hashlib.sha256(f"{a}|{b}|{kind}".encode()).hexdigest()[:8],
               "from_id": a, "to_id": b, "kind": kind}
        out.update(link=new, changed=True, was=f"{cur['kind']} {cur['from_id']} → {cur['to_id']}",
                   now=f"{kind} {a} → {b}", ends={a, b})
        cur.update(new)
        return True

    if csv_path.exists():
        rewrite_rows(csv_path, TASK_LINK_COLUMNS, mutate)
    if not out:
        raise not_found("link", link_id)
    if not out["changed"]:
        return {"link": out["link"], "changed": False}
    actor = identity_of(body) or _DEFAULT_ACTOR
    for tid in out["ends"]:
        _append_events(store, tid, actor, [("link", out["was"], out["now"])])
    store.rebuild()
    return {"link": out["link"], "changed": True}


@router.post("/api/tasks/links/{link_id}/delete")
def tasks_unlink(
    link_id: str,
    body: dict = Body(default={}),
    store: ViewStore = Depends(get_store),
) -> dict:
    csv_path = store.data_root / "task_links.csv"
    if not csv_path.exists():
        raise not_found("link", link_id)
    removed: list[dict] = []

    def mutate(rows: list[dict[str, str]]) -> bool:
        keep = [r for r in rows if r.get("id") != link_id]
        removed.extend(r for r in rows if r.get("id") == link_id)
        if not removed:
            return False
        rows[:] = keep
        return True

    rewrite_rows(csv_path, TASK_LINK_COLUMNS, mutate)
    if not removed:
        raise not_found("link", link_id)
    actor = identity_of(body) or _DEFAULT_ACTOR
    r = removed[0]
    _append_events(store, r["from_id"], actor, [("link", f"{r['kind']} → {r['to_id']}", "")])
    _append_events(store, r["to_id"], actor, [("link", f"{r['kind']} ← {r['from_id']}", "")])
    store.rebuild()
    return {"deleted": link_id}


# ---------------------------------------------------------------------------
# Archive (reversible) and delete (to .trash)
# ---------------------------------------------------------------------------


def _set_archived(store: ViewStore, task_id: str, value: str, actor: str) -> dict:
    ent = ENTITIES["task"]
    csv_path = store.data_root / ent.csv
    hit: list[dict] = []

    def mutate(rows: list[dict[str, str]]) -> bool:
        for r in rows:
            if r.get("id") == task_id:
                old = r.get("archived_at", "") or ""
                if old == value:
                    hit.append(r)
                    return False
                r["archived_at"] = value
                hit.append(r)
                return True
        return False

    if csv_path.exists():
        rewrite_rows(csv_path, ent.columns, mutate)
    if not hit:
        raise not_found("task", task_id)
    _append_events(store, task_id, actor, [("archived", "" if value else "yes", "yes" if value else "")])
    store.rebuild()
    return {"task_id": task_id, "archived_at": value}


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
        t["id"]: last.get(t["id"]) or _iso_of(t.get("created_date"), t.get("created_time"))
        for t in tasks
    }
    return json_response({"since": {k: v for k, v in since.items() if v}}, etag)


@router.get("/api/sprints/board")
def sprints_board(
    request: Request,
    project: str = Query(...),
    store: ViewStore = Depends(get_store),
) -> Response:
    """The board strip: every active sprint of the project with everything
    derived — tasks done/total, days left of the bet, human hours (timer
    entries on the sprint, share applied) and agent hours (captured sessions
    that mentioned any of the sprint's tasks)."""
    etag = etag_for(f"sprints:board:{project}", store, "tasks", "chats")
    if (r := maybe_304(request, etag)) is not None:
        return r
    sprints = store.query(
        "SELECT id, name, started_date, ended_date, time_budget_h, bet_days, status "
        "FROM sprints_mutual WHERE status = 'active' AND "
        "(projects = ? OR list_contains(string_split(COALESCE(projects, ''), ','), ?)) "
        "ORDER BY started_date ASC, id ASC",
        (project, project),
    )
    out = []
    today = time.strftime("%Y-%m-%d")
    sids = [str(sp["id"]) for sp in sprints]
    tasks_of = _by_sprint(store.query(
        f"SELECT id, status, archived_at, sprint_id FROM tasks_mutual WHERE sprint_id IN ({_ph(sids)})",
        tuple(sids),
    ), sids) if sids else {}
    # Human hours: stopped timer entries + the elapsed part of running ones
    # is the tracker's job; here the stored duration_min × share is enough.
    # Agent hours: sessions that mentioned any of the sprint's tasks. A
    # session counts once, whole — an approximation, labeled as such.
    clocks = _sprint_clocks_many(store, {sid: [str(t["id"]) for t in rows] for sid, rows in tasks_of.items()})
    for sp in sprints:
        sid = str(sp["id"])
        rows = tasks_of[sid]
        live = [t for t in rows if not (t.get("archived_at") or "")]
        done = sum(1 for t in live if is_done(t.get("status") or ""))
        human_min, agent_min = clocks[sid]
        # Days left of the bet, from the start date.
        days_left: int | None = None
        started = str(sp.get("started_date") or "")
        bet = sp.get("bet_days")
        try:
            if started and bet not in (None, ""):
                import datetime as _dt
                d0 = _dt.date.fromisoformat(f"20{started[:2]}-{started[2:4]}-{started[5:7]}") if len(started) == 7 else _dt.date.fromisoformat(started)
                days_left = int(bet) - (_dt.date.fromisoformat(today) - d0).days
        except (ValueError, TypeError):
            days_left = None
        out.append({
            "id": sid, "name": sp.get("name"), "started_date": started,
            "bet_days": bet, "days_left": days_left,
            "budget_h": sp.get("time_budget_h"),
            "tasks_total": len(live), "tasks_done": done,
            "human_min": round(human_min), "agent_min": round(agent_min),
        })
    unassigned = store.query_one(
        "SELECT COUNT(*) AS n FROM tasks_mutual WHERE (project = ? OR "
        "list_contains(string_split(COALESCE(projects, ''), ','), ?)) AND "
        "COALESCE(sprint_id, '') = '' AND COALESCE(archived_at, '') = ''",
        (project, project),
    )
    return json_response({"sprints": out, "no_sprint": int(unassigned["n"]) if unassigned else 0}, etag)


@router.post("/api/sprints/{sprint_id}/delete")
def sprints_delete(sprint_id: str, store: ViewStore = Depends(get_store)) -> dict:
    """Delete a sprint that should not exist (mistakes — real endings use
    finish + retro): the row and its detail doc move to
    ``<data_root>/.trash/sprints/<id>-<stamp>/``; tasks pointing at it
    return to the backlog, each logged in its history."""
    ent = ENTITIES["sprint"]
    row = store.query_one("SELECT id, md_ref FROM sprints_mutual WHERE id = ?", (sprint_id,))
    if row is None:
        raise not_found("sprint", sprint_id)
    root = store.data_root
    trash = root / TRASH_DIR / "sprints" / f"{sprint_id}-{_stamp()}"
    trash.mkdir(parents=True, exist_ok=True)
    moved = _split_rows(root, trash, ent.csv, ent.columns, lambda r: r.get("id") == sprint_id)
    if row.get("md_ref") and _archive_file(root, trash, str(row["md_ref"])):
        pass
    # Tasks return to the backlog.
    freed: list[str] = []
    tasks_csv = root / "tasks.csv"
    if tasks_csv.exists():
        def strip(rows: list[dict[str, str]]) -> bool:
            changed = False
            for t in rows:
                if t.get("sprint_id") == sprint_id:
                    t["sprint_id"] = ""
                    freed.append(str(t.get("id") or ""))
                    changed = True
            return changed
        rewrite_rows(tasks_csv, ENTITIES["task"].columns, strip)
    for tid in freed:
        _append_events(store, tid, _DEFAULT_ACTOR, [("sprint_id", sprint_id, "")])
    store.rebuild()
    return {"deleted": sprint_id, "trash": str(trash), "sprint_rows": moved, "tasks_freed": len(freed)}


_ymd = ymd  # '2608-20' → '2026-08-20' (deps)


@router.get("/api/sprints/{sprint_id}/series")
def sprint_series(
    sprint_id: str, request: Request, store: ViewStore = Depends(get_store),
) -> Response:
    """Per-day series of one sprint, derived from the ledgers — feeds
    burn-ups, day heat, trend ghosts and the radar axes.

    For each day from ``started_date`` to today (or ``ended_date``):
    ``scope`` (member tasks — joins reconstructed from sprint_id events,
    tasks created into the sprint count from creation), ``done`` (members
    whose status reached done by that day), ``human_min`` (timer entries ×
    share), ``agent_min`` (captured sessions that mentioned member tasks —
    whole sessions, an approximation), ``events`` (task-history rows that
    day — the discipline-free activity signal).
    """
    etag = etag_for(f"sprints:series:{sprint_id}", store, "tasks", "chats")
    if (r := maybe_304(request, etag)) is not None:
        return r
    sp = store.query_one(
        "SELECT id, started_date, ended_date, status, bet_days FROM sprints_mutual WHERE id = ?",
        (sprint_id,),
    )
    if sp is None:
        raise not_found("sprint", sprint_id)
    import datetime as _dt
    try:
        d0 = _dt.date.fromisoformat(_ymd(str(sp.get("started_date") or "")))
    except ValueError:
        raise HTTPException(status_code=409, detail="sprint has no readable started_date")
    d_end = _dt.date.today()
    if str(sp.get("status")) == "ended" and sp.get("ended_date"):
        try:
            d_end = _dt.date.fromisoformat(_ymd(str(sp["ended_date"])))
        except ValueError:
            pass
    n_days = max((d_end - d0).days + 1, 1)
    dates = [d0 + _dt.timedelta(days=i) for i in range(n_days)]

    # Join and done day per member: the one reconstruction (_member_spans).
    spans = _member_spans(store, sprint_id, d0)
    ids = [t["id"] for t in spans]
    ph = ",".join("?" * len(ids)) if ids else "''"
    joined_days = sorted(_dt.date.fromisoformat(t["joined"]) for t in spans)
    done_days = sorted(_dt.date.fromisoformat(t["done"]) for t in spans if t["done"])
    ev = store.query(
        f"SELECT timestamp FROM task_events_mutual WHERE task_id IN ({ph})", tuple(ids),
    ) if ids else []
    entries = store.query(
        "SELECT created_date, started_at, duration_min, share_pct FROM time_entries_mutual "
        "WHERE sprint_id = ?", (sprint_id,),
    )
    sessions = store.query(
        f"SELECT created_date, duration_min FROM sessions WHERE id IN "
        f"(SELECT DISTINCT session_id FROM task_mentions WHERE task_id IN ({ph}))",
        tuple(ids),
    ) if ids else []

    # Each ledger is read into its days once. Every day used to walk every
    # row and parse its date again: days × rows for a long sprint.
    acts: dict[_dt.date, int] = {}
    for e in ev:
        if (d := day_date(str(e["timestamp"]))) is not None:
            acts[d] = acts.get(d, 0) + 1
    human: dict[_dt.date, float] = {}
    for e in entries:
        d = day_date(str(e.get("started_at") or "")) or day_date(str(e.get("created_date") or ""))
        if d is not None:
            human[d] = human.get(d, 0) + float(e.get("duration_min") or 0) * float(e.get("share_pct") or 100) / 100.0
    agent: dict[_dt.date, float] = {}
    for sess in sessions:
        if (d := day_date(str(sess.get("created_date") or ""))) is not None:
            agent[d] = agent.get(d, 0) + float(sess.get("duration_min") or 0)

    days = []
    for d in dates:
        days.append({
            "date": d.isoformat(),
            "scope": bisect.bisect_right(joined_days, d),
            "done": bisect.bisect_right(done_days, d),
            "human_min": round(human.get(d, 0)), "agent_min": round(agent.get(d, 0)),
            "events": acts.get(d, 0),
        })
    return json_response({"sprint_id": sprint_id, "days": days}, etag)


# ---------------------------------------------------------------------------
# Sprint timeline + dossier — the whole history, and one block's full story
# ---------------------------------------------------------------------------


_sprint_day = day_date  # the day of a stamp or a YYMM-DD, or None (deps)


def _ph(items) -> str:
    return ",".join("?" * len(items))


def _by_sprint(rows: list[dict], sids) -> dict[str, list[dict]]:
    """Rows of one read over several sprints, split by sprint, each in the
    order the read gave them."""
    out: dict[str, list[dict]] = {sid: [] for sid in sids}
    for r in rows:
        bucket = out.get(str(r.get("sprint_id") or ""))
        if bucket is not None:
            bucket.append(r)
    return out


def _events_of(store: ViewStore, task_ids: list[str]) -> list[dict]:
    """The history of these tasks, oldest first."""
    if not task_ids:
        return []
    return store.query(
        f"SELECT task_id, timestamp, field, old_value, new_value FROM task_events_mutual "
        f"WHERE task_id IN ({_ph(task_ids)}) ORDER BY timestamp ASC", tuple(task_ids),
    )


def _member_spans(store: ViewStore, sprint_id: str, d0) -> list[dict]:
    """Member tasks with their join and done dates, reconstructed from the
    event log (a task created aboard counts from creation; the last status
    word wins)."""
    return _member_spans_many(store, {sprint_id: d0})[sprint_id]


def _member_spans_many(store: ViewStore, starts: dict, events: list[dict] | None = None) -> dict[str, list[dict]]:
    """``_member_spans`` for several sprints (id → start day) from one read
    of their tasks and one of the tasks' history. ``events`` is that history
    when the caller has already read it."""
    if not starts:
        return {}
    sids = list(starts)
    members = _by_sprint(store.query(
        f"SELECT id, title, status, created_date, sprint_id FROM tasks_mutual "
        f"WHERE sprint_id IN ({_ph(sids)}) AND COALESCE(archived_at, '') = ''", tuple(sids),
    ), sids)
    if events is None:
        events = _events_of(store, [str(t["id"]) for rows in members.values() for t in rows])
    by_task: dict[str, list[dict]] = {}
    for e in events:
        by_task.setdefault(str(e["task_id"]), []).append(e)
    out: dict[str, list[dict]] = {}
    for sid in sids:
        d0 = starts[sid]
        joined: dict = {}
        done_on: dict = {}
        for t in members[sid]:
            tid = str(t["id"])
            joined[tid] = _sprint_day(str(t.get("created_date") or "")) or d0
            for e in by_task.get(tid, ()):
                d = _sprint_day(str(e["timestamp"]))
                if d is None:
                    continue
                if e["field"] == "sprint_id" and str(e.get("new_value") or "") == sid:
                    joined[tid] = d
                if e["field"] == "status":
                    if is_done(e.get("new_value") or ""):
                        done_on.setdefault(tid, d)
                    else:
                        done_on.pop(tid, None)
            if is_done(t.get("status") or ""):
                done_on.setdefault(tid, joined[tid])
        out[sid] = [
            {
                "id": str(t["id"]), "title": t.get("title"), "status": t.get("status"),
                "joined": joined[str(t["id"])].isoformat(),
                "done": done_on[str(t["id"])].isoformat() if str(t["id"]) in done_on else None,
            }
            for t in members[sid]
        ]
    return out


def _sessions_of(store: ViewStore, task_ids: dict[str, list[str]]) -> dict[str, list[dict]]:
    """Per sprint, the captured sessions that mentioned any of its tasks —
    each session once, whole."""
    every = sorted({t for ids in task_ids.values() for t in ids})
    out: dict[str, list[dict]] = {sid: [] for sid in task_ids}
    if not every:
        return out
    said: dict[str, set[str]] = {}
    for m in store.query(
        f"SELECT DISTINCT task_id, session_id FROM task_mentions WHERE task_id IN ({_ph(every)})",
        tuple(every),
    ):
        if m["session_id"] is not None:
            said.setdefault(str(m["task_id"]), set()).add(str(m["session_id"]))
    wanted = sorted({s for ss in said.values() for s in ss})
    if not wanted:
        return out
    rows = store.query(
        f"SELECT id, created_date, duration_min FROM sessions WHERE id IN ({_ph(wanted)})", tuple(wanted),
    )
    for sid, ids in task_ids.items():
        mine = {s for t in ids for s in said.get(t, ())}
        out[sid] = [r for r in rows if str(r["id"]) in mine]
    return out


def _sprint_clocks(store: ViewStore, sprint_id: str, task_ids: list[str]) -> tuple[float, float]:
    return _sprint_clocks_many(store, {sprint_id: task_ids})[sprint_id]


def _sprint_clocks_many(
    store: ViewStore, task_ids: dict[str, list[str]], sessions: dict[str, list[dict]] | None = None,
) -> dict[str, tuple[float, float]]:
    """Human minutes (timer entries × share) and agent minutes (sessions that
    mentioned the tasks) per sprint, from one read of each ledger."""
    if not task_ids:
        return {}
    sids = list(task_ids)
    human = {
        str(r["sprint_id"]): float(r["m"] or 0)
        for r in store.query(
            "SELECT sprint_id, COALESCE(SUM(COALESCE(duration_min, 0) * COALESCE(share_pct, 100) / 100.0), 0) AS m "
            f"FROM time_entries_mutual WHERE sprint_id IN ({_ph(sids)}) GROUP BY sprint_id", tuple(sids),
        )
    }
    if sessions is None:
        sessions = _sessions_of(store, task_ids)
    out: dict[str, tuple[float, float]] = {}
    for sid in sids:
        agent = sum(float(s["duration_min"]) for s in sessions.get(sid, ()) if s.get("duration_min") is not None)
        out[sid] = (round(human.get(sid, 0.0)), round(agent))
    return out


@router.get("/api/sprints/timeline")
def sprints_timeline(
    request: Request, project: str = Query(...), store: ViewStore = Depends(get_store),
) -> Response:
    """Every sprint of the project — active and settled — with its window,
    bet, task spans and clocks. Feeds the Overview gantt in one call."""
    etag = etag_for(f"sprints:timeline:{project}", store, "tasks", "chats")
    if (r := maybe_304(request, etag)) is not None:
        return r
    rows = store.query(
        "SELECT id, name, status, started_date, ended_date, bet_days, time_budget_h "
        "FROM sprints_mutual WHERE projects = ? OR "
        "list_contains(string_split(COALESCE(projects, ''), ','), ?) "
        "ORDER BY started_date ASC, id ASC", (project, project),
    )
    starts = {}
    for sp in rows:
        d0 = _sprint_day(str(sp.get("started_date") or ""))
        if d0 is not None:
            starts[str(sp["id"])] = d0
    spans = _member_spans_many(store, starts)
    clocks = _sprint_clocks_many(store, {sid: [t["id"] for t in ts] for sid, ts in spans.items()})
    out = []
    for sp in rows:
        d0 = starts.get(str(sp["id"]))
        if d0 is None:
            continue
        d_end = _sprint_day(str(sp.get("ended_date") or "")) if str(sp.get("status")) == "ended" else None
        tasks = spans[str(sp["id"])]
        human, agent = clocks[str(sp["id"])]
        out.append({
            "id": sp["id"], "name": sp.get("name"), "status": sp.get("status"),
            "started": d0.isoformat(), "ended": d_end.isoformat() if d_end else None,
            "bet_days": sp.get("bet_days"), "budget_h": sp.get("time_budget_h"),
            "tasks": tasks, "human_min": human, "agent_min": agent,
        })
    return json_response({"sprints": out}, etag)


@router.get("/api/sprints/{sprint_id}/dossier")
def sprint_dossier(
    sprint_id: str, request: Request, store: ViewStore = Depends(get_store),
) -> Response:
    """One block's full story: the bet and how it ran, the tasks, both
    clocks, the agents that worked it, and — when the project folder is a
    git repo — the commits and lines written inside the window. Everything
    derived on read; whatever cannot be known says so."""
    etag = etag_for(f"sprints:dossier:{sprint_id}", store, "tasks", "chats")
    if (r := maybe_304(request, etag)) is not None:
        return r
    sp = store.query_one("SELECT * FROM sprints_mutual WHERE id = ?", (sprint_id,))
    if sp is None:
        raise not_found("sprint", sprint_id)
    import datetime as _dt
    d0 = _sprint_day(str(sp.get("started_date") or ""))
    if d0 is None:
        raise HTTPException(status_code=409, detail="sprint has no readable started_date")
    ended = _sprint_day(str(sp.get("ended_date") or "")) if str(sp.get("status")) == "ended" else None
    d_end = ended or _dt.date.today()
    ran_days = (d_end - d0).days
    bet = int(sp.get("bet_days") or 0)

    tasks = _member_spans(store, sprint_id, d0)
    task_ids = [t["id"] for t in tasks]
    human_min, agent_min = _sprint_clocks(store, sprint_id, task_ids)

    # The fleet: which agents worked the block's tasks, and how much.
    agents: list[dict] = []
    if task_ids:
        ph = ",".join("?" * len(task_ids))
        agents = store.query(
            f"SELECT s.agent_id, COUNT(DISTINCT s.id) AS sessions_n, "
            f"COALESCE(SUM(s.duration_min), 0) AS minutes, COALESCE(SUM(s.turns_n), 0) AS turns "
            f"FROM sessions s WHERE s.id IN "
            f"(SELECT DISTINCT session_id FROM task_mentions WHERE task_id IN ({ph})) "
            f"GROUP BY s.agent_id ORDER BY minutes DESC", tuple(task_ids),
        )

    # Activity counted inside the window (events are discipline-free).
    events_n = 0
    if task_ids:
        ph = ",".join("?" * len(task_ids))
        ev = store.query(
            f"SELECT timestamp FROM task_events_mutual WHERE task_id IN ({ph})", tuple(task_ids),
        )
        events_n = sum(1 for e in ev if (d := _sprint_day(str(e["timestamp"]))) and d0 <= d <= d_end)
    home = str(sp.get("projects") or "").split(",")[0].strip()
    win = (d0.isoformat(), d_end.isoformat())
    scans_n = store.query_one(
        "SELECT COUNT(*) AS n FROM scans_mutual WHERE project = ? AND created_date BETWEEN ? AND ?",
        (home, f"{win[0][2:4]}{win[0][5:7]}-{win[0][8:10]}", f"{win[1][2:4]}{win[1][5:7]}-{win[1][8:10]}"),
    )
    decisions_n = store.query_one(
        "SELECT COUNT(*) AS n FROM decisions_mutual WHERE project = ? AND created_date BETWEEN ? AND ?",
        (home, f"{win[0][2:4]}{win[0][5:7]}-{win[0][8:10]}", f"{win[1][2:4]}{win[1][5:7]}-{win[1][8:10]}"),
    )

    # Git, honestly: only when the registered folder is a repo.
    from ..file_entries import git as run_git, project_repo
    git: dict = {"available": False}
    repo = project_repo(store, home) if home else None
    if repo is not None:
        log = run_git(
            repo, "log", "--numstat", "--pretty=%H",
            f"--since={d0.isoformat()} 00:00", f"--until={d_end.isoformat()} 23:59",
        )
        if log is not None:
            commits = 0
            adds = dels = 0
            files: set = set()
            for line in log.splitlines():
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) == 3:
                    a, d, path = parts
                    if a.isdigit():
                        adds += int(a)
                    if d.isdigit():
                        dels += int(d)
                    files.add(path)
                elif len(line) == 40 and all(c in "0123456789abcdef" for c in line):
                    commits += 1
            git = {
                "available": True, "commits": commits,
                "lines_add": adds, "lines_del": dels, "files_touched": len(files),
                "window": {"from": d0.isoformat(), "to": d_end.isoformat()},
            }

    l2, l3, l4 = read_detail(store.data_root, str(sp.get("md_ref") or ""))
    return json_response({
        "sprint": {
            "id": sp["id"], "name": sp.get("name"), "status": sp.get("status"),
            "started": d0.isoformat(), "ended": ended.isoformat() if ended else None,
            "bet_days": bet, "budget_h": sp.get("time_budget_h"),
            "ran_days": ran_days, "over_days": max(0, ran_days - bet) if bet else 0,
        },
        "tasks": tasks, "human_min": human_min, "agent_min": agent_min,
        "agents": agents, "events_n": events_n,
        "scans_n": int(scans_n["n"]) if scans_n else 0,
        "decisions_n": int(decisions_n["n"]) if decisions_n else 0,
        "git": git, "l2": l2, "l3": l3, "l4": l4,
    }, etag)


# ---------------------------------------------------------------------------
# Bring it back — scheduled resurfacing
# ---------------------------------------------------------------------------


def resurface_sweep(store: ViewStore) -> int:
    """Move every task whose ``resurface_on`` date has arrived back onto
    the board — to ``resurface_to`` (todo by default) — clearing the date,
    stamping ``resurfaced_at`` (the card glows for a while), and logging
    the move in the task's history as actor ``resurface``. Returns how
    many came back. Cheap when nothing is due."""
    import datetime as _dt
    today = _dt.date.today().isoformat()
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    moved: list[tuple[str, str, str]] = []

    def mutate(rows: list[dict[str, str]]) -> bool:
        changed = False
        for r in rows:
            due = str(r.get("resurface_on") or "").strip()
            if not due or due > today or (r.get("archived_at") or ""):
                continue
            target = str(r.get("resurface_to") or "").strip() or "todo"
            if target not in TASK_STATUSES:
                # The column is enum-checked on write; an old row may still
                # hold a stray value, and a card must land where a filter finds it.
                target = "todo"
            old = str(r.get("status") or "")
            r["status"] = target
            r["resurface_on"] = ""
            r["resurfaced_at"] = now
            moved.append((str(r.get("id") or ""), old, target))
            changed = True
        return changed

    csv_path = store.data_root / "tasks.csv"
    if csv_path.exists():
        rewrite_rows(csv_path, ENTITIES["task"].columns, mutate)
    for tid, old, new in moved:
        _append_events(store, tid, "resurface", [("status", old, new), ("resurface_on", "due", "")])
    if moved:
        store.rebuild()
    return len(moved)


_SWEEP_INTERVAL_SEC = 600
_last_sweep = 0.0


def maybe_resurface(store: ViewStore) -> None:
    """Throttled sweep — runs at most every ten minutes, invoked from the
    request path so resurfacing needs no cron and no browser."""
    global _last_sweep
    nowts = time.time()
    if nowts - _last_sweep < _SWEEP_INTERVAL_SEC:
        return
    _last_sweep = nowts
    try:
        resurface_sweep(store)
    except Exception:  # noqa: BLE001 — the sweep must never break a request
        # …but hiding the reason forever is how real faults stay unfixed.
        logging.getLogger("sp.resurface").exception("resurface sweep failed")


@router.get("/api/sprints/deck")
def sprints_deck(
    request: Request,
    days: int = Query(0, ge=0, le=120),
    store: ViewStore = Depends(get_store),
) -> Response:
    """Every running block of every project, with everything the cross-project
    board needs in one call: derived clocks, the day's plan, the tasks
    themselves, any timer currently running on the block, and how long since
    anything happened to it. One request so a page can be dense without being
    slow."""
    etag = etag_for(f"sprints:deck:{days}", store, "tasks", "chats")
    if (r := maybe_304(request, etag)) is not None:
        return r
    import datetime as _dt
    today = _dt.date.today()
    sprints = store.query(
        "SELECT id, name, projects, started_date, time_budget_h, bet_days, status, md_ref "
        "FROM sprints_mutual WHERE status = 'active' ORDER BY started_date ASC, id ASC"
    )
    open_timers = store.query(
        "SELECT id, project, sprint_id, started_at, paused_at, paused_total_sec, share_pct, note "
        "FROM time_entries_mutual WHERE COALESCE(ended_at, '') = ''"
    )
    # Every ledger is read once for all the blocks, then split by block.
    sids = [str(sp["id"]) for sp in sprints]
    rows_of = _by_sprint(store.query(
        "SELECT id, title, status, position, today_on, stack_id, priority, assignee, sprint_id "
        f"FROM tasks_mutual WHERE sprint_id IN ({_ph(sids)}) AND COALESCE(archived_at, '') = '' "
        "ORDER BY COALESCE(TRY_CAST(position AS DOUBLE), 0) ASC", tuple(sids),
    ), sids) if sids else {}
    # One read of the blocks' task history serves everything below.
    events = _events_of(store, [str(t["id"]) for rows in rows_of.values() for t in rows])
    # When each task joined the block and when it landed — the two dates
    # a cumulative flow is read with: the gap between them is lead time,
    # and a task still open since its join date is work in flight.
    spans_of = _member_spans_many(store, {
        str(sp["id"]): _sprint_day(str(sp.get("started_date") or "")) or today for sp in sprints
    }, events)
    ids_of = {sid: [str(t["id"]) for t in rows] for sid, rows in rows_of.items()}
    sessions_of = _sessions_of(store, ids_of)
    clocks = _sprint_clocks_many(store, ids_of, sessions_of)
    entries_of = _by_sprint(store.query(
        "SELECT sprint_id, created_date, started_at, duration_min, share_pct "
        f"FROM time_entries_mutual WHERE sprint_id IN ({_ph(sids)})", tuple(sids),
    ), sids) if sids and days > 0 else {}

    blocks: list[dict] = []
    for sp in sprints:
        sid = str(sp["id"])
        rows = rows_of[sid]
        mine = {str(t["id"]) for t in rows}
        task_events = [e for e in events if str(e["task_id"]) in mine]
        tasks = _deck_tasks(rows, task_events, {x["id"]: x for x in spans_of[sid]})
        human_min, agent_min = clocks[sid]
        stamps = [e["timestamp"] for e in task_events if e["timestamp"] is not None]
        block = _deck_block(sp, tasks, today, human_min, agent_min if tasks else 0.0,
                            str(max(stamps) or "") if stamps else "")
        if days > 0:
            block["series"] = _deck_series(
                today, days, rows, task_events, entries_of[sid], sessions_of[sid] if tasks else [],
                {t["id"]: t["joined"] for t in tasks},
            )
        timer = next((t for t in open_timers if str(t.get("sprint_id") or "") == sid), None)
        block["timer"] = ({
            "id": str(timer["id"]), "started_at": timer.get("started_at"),
            "paused_at": timer.get("paused_at"),
            "paused_total_sec": timer.get("paused_total_sec"),
            "share_pct": timer.get("share_pct"), "note": timer.get("note"),
        } if timer else None)
        blocks.append(block)
    # Projects that have blocks, plus their unassigned backlog depth.
    codes = sorted({b["project"] for b in blocks if b["project"]})
    settled = store.query(
        "SELECT id, name, projects, started_date, ended_date, bet_days, time_budget_h "
        "FROM sprints_mutual WHERE status = 'ended' ORDER BY ended_date DESC LIMIT 12"
    )
    return json_response({
        "today": today.isoformat(),
        "projects": codes,
        "backlog": _deck_backlog(store, codes),
        "blocks": blocks,
        "running_elsewhere": [
            {"id": str(t["id"]), "project": t.get("project"), "sprint_id": t.get("sprint_id"),
             "started_at": t.get("started_at"), "paused_at": t.get("paused_at"),
             "paused_total_sec": t.get("paused_total_sec"), "share_pct": t.get("share_pct")}
            for t in open_timers
        ],
        "settled": [{
            "id": str(s["id"]), "name": s.get("name"),
            "project": str(s.get("projects") or "").split(",")[0].strip(),
            "started_date": s.get("started_date"), "ended_date": s.get("ended_date"),
            "bet_days": s.get("bet_days"), "budget_h": s.get("time_budget_h"),
        } for s in settled],
    }, etag)


def _deck_tasks(rows: list[dict], task_events: list[dict], spans: dict[str, dict]) -> list[dict]:
    """The block's cards with their join, landing and how long each has sat
    where it is: the last status change, or its join if it has never moved
    (a number for "stuck")."""
    since: dict[str, str] = {}
    for e in task_events:
        if e["field"] == "status":
            since[str(e["task_id"])] = str(e["timestamp"])
    return [{
        "id": str(t["id"]), "title": t.get("title"), "status": t.get("status"),
        "today_on": t.get("today_on"), "stack_id": t.get("stack_id"),
        "priority": t.get("priority"), "assignee": t.get("assignee"),
        "joined": (spans.get(str(t["id"])) or {}).get("joined"),
        "done_on": (spans.get(str(t["id"])) or {}).get("done"),
        "status_since": since.get(str(t["id"]))
            or (spans.get(str(t["id"])) or {}).get("joined"),
    } for t in rows]


def _deck_block(sp: dict, tasks: list[dict], today, human_min, agent_min, last_at: str) -> dict:
    """One block's counts, clocks and days, without its series and timer."""
    started = str(sp.get("started_date") or "")
    days_left = None
    ran_days = None
    try:
        d0 = _sprint_day(started)
        if d0 is not None:
            ran_days = (today - d0).days
            if sp.get("bet_days") not in (None, ""):
                days_left = int(sp["bet_days"]) - ran_days
    except (ValueError, TypeError):
        pass
    return {
        "id": str(sp["id"]), "name": sp.get("name"),
        "project": str(sp.get("projects") or "").split(",")[0].strip(),
        "started_date": started, "bet_days": sp.get("bet_days"),
        "days_left": days_left, "ran_days": ran_days,
        "budget_h": sp.get("time_budget_h"),
        "tasks_total": len(tasks),
        "tasks_done": sum(1 for t in tasks if is_done(t["status"] or "")),
        "tasks_doing": sum(1 for t in tasks if str(t["status"] or "").lower() in ("doing", "review")),
        "today_n": sum(1 for t in tasks if str(t.get("today_on") or "") == today.isoformat()),
        "human_min": human_min, "agent_min": agent_min,
        "last_event_at": last_at, "tasks": tasks, "series": [],
    }


def _deck_series(today, days: int, rows: list[dict], task_events: list[dict],
                 entries: list[dict], sessions: list[dict], joined: dict[str, str]) -> list[dict]:
    """The daily rhythm of a block over the last ``days``: what landed, what
    was worked, how much noise it made, and where every task stood."""
    import datetime as _dt
    first = today - _dt.timedelta(days=days - 1)
    buckets = {
        (first + _dt.timedelta(days=i)).isoformat(): {
            "date": (first + _dt.timedelta(days=i)).isoformat(),
            "done": 0, "human_min": 0, "agent_min": 0, "events": 0,
            "bands": {},
        }
        for i in range(days)
    }
    if rows:
        for e in task_events:
            d = _sprint_day(str(e["timestamp"]))
            key = d.isoformat() if d else ""
            if key not in buckets:
                continue
            buckets[key]["events"] += 1
            if e["field"] == "status" and is_done(e.get("new_value") or ""):
                buckets[key]["done"] += 1
        _deck_bands(buckets, first, rows, [e for e in task_events if e["field"] == "status"], joined)
    for e in entries:
        d = _sprint_day(str(e.get("started_at") or "")) or _sprint_day(str(e.get("created_date") or ""))
        key = d.isoformat() if d else ""
        if key in buckets:
            buckets[key]["human_min"] += round(
                float(e.get("duration_min") or 0) * float(e.get("share_pct") or 100) / 100.0
            )
    for sess in sessions:
        d = _sprint_day(str(sess.get("created_date") or ""))
        key = d.isoformat() if d else ""
        if key in buckets:
            buckets[key]["agent_min"] += round(float(sess.get("duration_min") or 0))
    return list(buckets.values())


def _deck_bands(buckets: dict[str, dict], first, rows: list[dict], status_events: list[dict],
                joined: dict[str, str]) -> None:
    """Cumulative flow: where every member task stood on each day, replayed
    from its status events. A day's bands are the shape of the work in
    flight — a fat middle is a queue before Done. A task counts from the
    day it joined the block (``joined``, from the member spans)."""
    import datetime as _dt
    joined_on: dict[str, _dt.date] = {}
    moves: dict[str, list[tuple[_dt.date, str]]] = {}
    for t in rows:
        tid = str(t["id"])
        # The rows carry no created_date: reading it here put every task
        # on the block from the window's first day.
        joined_on[tid] = _sprint_day(str(joined.get(tid) or "")) or first
        moves[tid] = []
    # Replay every status change in order, then read each day off it.
    for e in status_events:
        d = _sprint_day(str(e["timestamp"]))
        if d is None:
            continue
        moves.setdefault(str(e["task_id"]), []).append(
            (d, str(e.get("new_value") or "").lower())
        )
        # The first move also reveals where the task started.
        tid = str(e["task_id"])
        if len(moves[tid]) == 1 and e.get("old_value"):
            moves[tid].insert(0, (joined_on.get(tid, first), str(e["old_value"]).lower()))
    current = {str(t["id"]): str(t.get("status") or "").lower() for t in rows}
    for key, bucket in buckets.items():
        day = _dt.date.fromisoformat(key)
        bands: dict[str, int] = {}
        for t in rows:
            tid = str(t["id"])
            if joined_on.get(tid, first) > day:
                continue
            past = [st for (d, st) in moves.get(tid, []) if d <= day]
            # No move by this day: the task still sat where it was
            # made, which is its first known status.
            status = past[-1] if past else (
                moves[tid][0][1] if moves.get(tid) else current.get(tid, "")
            )
            status = "done" if is_done(status) else (status or "unclassified")
            bands[status] = bands.get(status, 0) + 1
        bucket["bands"] = bands


def _deck_backlog(store: ViewStore, codes: list[str]) -> dict[str, int]:
    """Per project, the open tasks in no sprint, from one read."""
    if not codes:
        return {}
    rows = store.query(
        "SELECT project, projects FROM tasks_mutual WHERE "
        "COALESCE(sprint_id, '') = '' AND COALESCE(archived_at, '') = '' AND "
        "LOWER(COALESCE(status, '')) NOT IN " + _DONE_SQL
    )
    return {
        code: sum(
            1 for r in rows
            if r.get("project") == code or code in str(r.get("projects") or "").split(",")
        )
        for code in codes
    }


# ---------------------------------------------------------------------------
# The task's own create and detail — tasks speak `description` and `turns`,
# not the generic l2/l3/l4. On a router of their own (``detail_router``)
# that server.py includes after every literal /api/tasks/… route (this
# file's and story.py's notes) and before the generic lens router, so
# ``/api/tasks/{task_id}`` neither shadows a literal path nor loses to
# the generic detail.
# ---------------------------------------------------------------------------

detail_router = APIRouter()

# /task — an agent's own card. It lands in the `agent` column (the folded
# strip before To do), carries 1–3 tags from this closed set, and nothing
# the operator owns: the column is the review, the tag the one judgment.
AGENT_TAGS = ("ag_debt", "ag_bug", "ag_followup", "ag_idea", "ag_decision")
AGENT_TAGS_MAX = 3
AGENT_TITLE_MAX = limits.MAX_AGENT_TASK_TITLE
_AGENT_CREATE_FIELDS = frozenset({
    "created_date", "created_time", "project", "projects", "agent_id",
    "title", "description", "tags", "lane", "assignee", "status", "today_on",
})


def _operator_command(store: ViewStore, agent: str) -> tuple[str, str]:
    """(command, lane) of the operator's latest message in the agent's chat:
    ``#now {ui} …`` → ("now", "ui"); no chat, or no command → ("", "")."""
    from ..sessions import _operator_text, chat_path, parse_turns, task_command
    path = chat_path(store, agent)
    if path is None:
        return "", ""
    try:
        turns = parse_turns(path)
    except OSError:
        return "", ""
    for t in reversed(turns):
        text = _operator_text(t)
        if text:
            return task_command(text)
    return "", ""


def _board_lanes(store: ViewStore, project: str) -> list[str]:
    """The lanes the project's board shows: every assignee (lane) a live card has."""
    rows = store.query(
        "SELECT lane, assignee, archived_at FROM tasks_mutual WHERE project = ?", (project,))
    seen: dict[str, str] = {}
    for r in rows:
        if str(r.get("archived_at") or "").strip():
            continue
        name = str(r.get("lane") or r.get("assignee") or "").strip()
        if name:
            seen.setdefault(name.lower(), name)
    return sorted(seen.values(), key=str.lower)


def _lane_for(store: ViewStore, project: str, command: str, named: str) -> str:
    """The lane an agent's card lands in. Named in the message: one the board
    has, matched without case; else #now's own lane from Settings, and
    #task's none (the card shows under "unassigned")."""
    lanes = _board_lanes(store, project)
    if named:
        for lane in lanes:
            if lane.lower() == named.lower():
                return lane
        refuse_agent(
            f"the lane {named!r} is not on the board",
            ("the board's lanes: " + ", ".join(lanes) if lanes else "the board has no lanes yet")
            + " — ask the operator which, in one line; a new lane is made on the board",
        )
    if command == "now":
        return str(app_settings.load(store.data_root).get("tasks.now_lane") or "Now").strip() or "Now"
    return ""


def _gate_agent_create(body: dict, store: ViewStore) -> list[str]:
    """Apply the /task contract to an agent's create; return the fields dropped.

    A house actor (the board) passes untouched. The operator's message
    decides the column and the lane: ``#task`` → the `agent` column,
    ``#now`` → `doing`, with the lane named in braces or #now's own.
    """
    agent = identity_of(body)
    if agent in _HOUSE_ACTORS:
        return []
    command, named = _operator_command(store, agent)
    status = str(body.get("status") or "").strip() or ("doing" if command == "now" else "agent")
    if command == "now" and status != "doing":
        refuse_agent(
            "the operator wrote #now: this task starts in `doing`",
            f"send status \"doing\" (or none), not {status!r}",
        )
    if command != "now" and status != "agent":
        refuse_agent(
            "an agent creates tasks only in the `agent` column",
            f"send status \"agent\" (or none), not {status!r}; the operator "
            "classifies the card from there"
            + ("" if command else " (#now in the operator's message starts a task in `doing`)"),
        )
    body["status"] = status
    # The lane comes from the operator's message, never from the agent.
    lane = _lane_for(store, str(body.get("project") or ""), command, named)
    dropped = {k for k in ("lane", "assignee") if str(body.pop(k, None) or "").strip()}
    if lane:
        body["lane"] = body["assignee"] = lane
    if command == "now":
        body["today_on"] = date.today().isoformat()
    title = str(body.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=422, detail="an agent task needs a title")
    if len(title) > AGENT_TITLE_MAX:
        raise HTTPException(
            status_code=422,
            detail=f"an agent task title is at most {AGENT_TITLE_MAX} characters ({len(title)} sent)",
        )
    tags = [t.strip() for t in str(body.get("tags") or "").split(",") if t.strip()]
    bad = [t for t in tags if t not in AGENT_TAGS]
    if not tags or bad:
        raise HTTPException(
            status_code=422,
            detail=(
                ("unknown tag(s) " + ", ".join(bad) + " — " if bad else "an agent task needs tags — ")
                + f"1–{AGENT_TAGS_MAX} of: " + ", ".join(AGENT_TAGS)
            ),
        )
    if len(tags) > AGENT_TAGS_MAX:
        raise HTTPException(
            status_code=422,
            detail=f"an agent task carries at most {AGENT_TAGS_MAX} tags ({len(tags)} sent)",
        )
    body["tags"] = ",".join(tags)
    ignored = sorted(k for k in list(body) if k not in _AGENT_CREATE_FIELDS)
    for k in ignored:
        body.pop(k, None)
    return sorted(set(ignored) | dropped)


@detail_router.post("/api/tasks", status_code=201)
def tasks_create(
    response: Response,
    body: dict = Body(...),
    store: ViewStore = Depends(get_store),
) -> dict:
    """Create a task. Text goes in `description`; turns come later via
    POST /api/tasks/{id}/turn. Idempotent on the minted id: the same
    payload again answers 200 with ``existing: true``. An agent's create
    goes through the /task gate (see `_gate_agent_create`)."""
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="body must be a JSON object")
    if any(k in body for k in ("l2", "l3", "l4")):
        raise HTTPException(
            status_code=422,
            detail="a task holds title and description — send its text as description",
        )
    started_now = identity_of(body) not in _HOUSE_ACTORS and _operator_command(store, identity_of(body))[0] == "now"
    ignored = _gate_agent_create(body, store)
    if len(str(body.get("title") or "")) > TITLE_MAX:
        raise HTTPException(status_code=422, detail=f"title is at most {TITLE_MAX} characters")
    description = str(body.pop("description", "") or "").strip()
    if len(description) > DESCRIPTION_MAX:
        raise HTTPException(status_code=422, detail=f"description is at most {DESCRIPTION_MAX} characters")
    out = create_entity(store, ENTITIES["task"], body, seed_extra=description)
    if out.get("existing"):
        response.status_code = 200
    meta = dict(out.get("metadata") or {})
    task_id = str(meta.get("id") or "")
    md_ref = str(meta.get("md_ref") or "")
    fm, turns = _task_doc(store, md_ref, meta, task_id)
    if description and not turns and md_ref:
        turns = [Turn(1, "", "", description)]
        _write_task_doc(store, md_ref, fm, turns)
        store.rebuild()
    if started_now and not out.get("existing"):
        # The card's history says where it came from: the operator's #now
        # in the chat, and the agent that wrote it down.
        _append_events(store, task_id, _DEFAULT_ACTOR, [("started", "", f"in the chat, with #now (written by {identity_of(body)})")])
        store.rebuild()
    result = {
        "metadata": meta,
        "description": description_of(turns),
        "turns": [t.as_dict() for t in turns],
        "turns_n": len(turns),
    }
    if ignored:
        result["ignored"] = ignored
    return create_answer(result, existing=bool(out.get("existing")),
                         warnings=out.get("warnings"))


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


def after_status_change(store: ViewStore, rows: list[dict[str, str]], target: dict[str, str],
                        old_status: str | None, changes: list[tuple[str, str, str]],
                        deferred: list | None = None) -> None:
    """What a status change sets off, whoever made it — the board, the
    editor, an agent's POST, a #done in a chat (donelib):

    - a stack advances: when a member leaves its column, the next one there
      becomes the head and is stamped;
    - a repeating task re-arms: done + every-days sets the comeback date.

    Called inside a rewrite that can still be refused, pass ``deferred``:
    the events for other cards are put there instead of written.
    """
    stack_id = str(target.get("stack_id") or "").strip()
    if stack_id and old_status is not None:
        def _pos(r: dict[str, str]) -> float:
            try:
                return float(r.get("position") or 0)
            except ValueError:
                return 0.0
        waiting = [
            r for r in rows
            if r is not target
            and str(r.get("stack_id") or "") == stack_id
            and str(r.get("status") or "") == old_status
            and not (r.get("archived_at") or "")
        ]
        if waiting:
            head = min(waiting, key=_pos)
            stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
            head["stack_head_at"] = stamp
            event = (str(head.get("id") or ""), "stack", [("stack_head_at", "", stamp)])
            if deferred is not None:
                # The caller writes it once its own rewrite has landed.
                deferred.append(event)
            else:
                _append_events(store, *event)
    every = str(target.get("resurface_every_days") or "").strip()
    if every.isdigit() and is_done(target.get("status") or "") \
            and not str(target.get("resurface_on") or "").strip():
        import datetime as _dt
        due = (_dt.date.today() + _dt.timedelta(days=int(every))).isoformat()
        target["resurface_on"] = due
        changes.append(("resurface_on", "", due))
