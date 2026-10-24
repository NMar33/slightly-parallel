"""Chat mentions of tasks and the task timeline: derived from the chats, never stored."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Query, Request, Response

from .. import taskthread
from ..db import ViewStore
from .deps import (
    DONE_SQL, agents_by_id, attach_agent, etag_for, get_store, iso_moment, json_response,
    maybe_304,
)

router = APIRouter()


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
    full: bool = Query(False, description="also `turns`: each turn once, with its whole text"),
    store: ViewStore = Depends(get_store),
) -> Response:
    """Every captured turn that names this task, newest first.

    Each row carries the agent behind it under ``agent`` (``null`` when the
    chat is gone): the names a reader shows instead of the raw id, and the
    tool, folder and session id a resume command is built from.

    With ``full=1`` the answer also has the task's thread (taskthread.py):
    ``turns``, each once, with ``why`` it is there (``mention``, ``done`` —
    inside a #done stretch — or ``next`` — up to the next task), the sides
    that named it (``roles``), the operator's message (``said``) and the
    agent's reply (``reply``) whole; and ``done_turns`` / ``next_turns``,
    how many turns each adds, and ``has_done``.
    """
    # The thread also reads done.csv and now.csv, which sit in "rest".
    areas = ("tasks", "chats", "rest") if full else ("tasks", "chats")
    etag = etag_for(f"tasks:mentions:{task_id}:{int(full)}", store, *areas)
    if (r := maybe_304(request, etag)) is not None:
        return r
    rows = store.query(
        "SELECT task_id, project, agent_id, session_id, turn, at_ts AS at, role, excerpt "
        "FROM task_mentions WHERE task_id = ? ORDER BY at_ts DESC", (task_id,)
    )
    attach_agent(store, rows)
    out: dict = {"total": len(rows), "mentions": rows}
    if full:
        out.update(taskthread.thread(store, task_id, rows))
    return json_response(out, etag)


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
