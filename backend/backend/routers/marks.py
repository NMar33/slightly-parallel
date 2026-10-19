"""Important marks — the ★ on agents, tasks and messages (marklib.py).

A task's star is the one the board already had: the task's ``remember``
field ("worth remembering", the ☆ on a card and its filter). ``#important``
sets it, the ☆ clears it; marks.csv keeps the record of the tag so an old
message is not adopted again. Agents and messages live in marks.csv alone.

``GET /api/marks?project=`` answers every mark in force, each with what it
points at resolved (the task's title and status, the agent's name), after
adopting any new ``#important`` tag. ``POST /api/marks`` stars one thing by
hand and ``POST /api/marks/unmark`` takes the star off. Marking is the
operator's: an agent marks by being told ``#important`` in a chat.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from .. import marklib
from ..csvio import rewrite_rows
from ..db import ViewStore
from ..entities import ENTITIES
from .deps import adopt_when_changed, agents_by_id, get_store, operator_only
from ..taskevents import append_events as _append_events


def _set_remember(store: ViewStore, ids: set[str], value: str, actor: str = "operator") -> None:
    """Star or unstar tasks on the board, each change in the task's history."""
    ent = ENTITIES["task"]
    changed: list[tuple[str, str]] = []

    def mutate(rows: list[dict[str, str]]) -> bool:
        for r in rows:
            if r.get("id") in ids and (r.get("remember") or "") != value:
                changed.append((r["id"], r.get("remember") or ""))
                r["remember"] = value
        return bool(changed)

    rewrite_rows(store.data_root / ent.csv, ent.columns, mutate)
    for tid, old in changed:
        _append_events(store, tid, actor, [("remember", old, value)])
    if changed:
        store.rebuild()

router = APIRouter()


@router.get("/api/marks")
def marks_list(project: str = Query(""), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    # A task the tag names gets the board's star. marks.csv is one of the
    # store's file sources, so a rebuild moves every ETag that counts stars.
    added = adopt_when_changed(store, "marks", marklib.adopt)
    if added:
        fresh = {r["target"] for r in marklib.rows(store) if r["id"] in set(added) and r["kind"] == "task"}
        if fresh:
            _set_remember(store, fresh, "yes")
        store.rebuild()
    agents = agents_by_id(store)
    tagged = {r["target"]: r for r in marklib.rows(store) if r["kind"] == "task"}
    out: list[dict[str, Any]] = []
    for r in marklib.active(store, project):
        if r["kind"] == "task":
            continue  # the board's star answers for tasks, below
        item: dict[str, Any] = {**r, "turn": int(r.get("turn") or 0)}
        item["agent"] = agents.get(r["target"] if r["kind"] == "agent" else (r.get("agent_id") or ""))
        out.append(item)
    sql = "SELECT id, title, status, project, projects FROM tasks_mutual WHERE remember = 'yes'"
    params: tuple = ()
    if project:
        sql += " AND (project = ? OR list_contains(string_split(COALESCE(projects, ''), ','), ?))"
        params = (project, project)
    for t in store.query(sql, params):
        m = tagged.get(str(t["id"]), {})
        out.append({
            "id": m.get("id", ""), "kind": "task", "target": t["id"], "project": t["project"] or "",
            "agent_id": m.get("agent_id", ""), "session_id": m.get("session_id", ""),
            "turn": int(m.get("turn") or 0), "excerpt": m.get("excerpt", ""),
            "marked_at": m.get("marked_at", ""), "source": m.get("source", "board"), "removed_at": "",
            "task": t,
        })
    out.sort(key=lambda x: x.get("marked_at") or "", reverse=True)
    return {"total": len(out), "marks": out}


@router.post("/api/marks", status_code=201)
def marks_add(body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """``{kind, target, project?, agent_id?, session_id?, turn?, excerpt?, actor?}``."""
    # `agent_id` here is the chat's agent, not the writer: the writer is `actor`.
    operator_only({"actor": body.get("actor") or "operator"}, "Marking something important",
                  "the operator types #important in the chat")
    kind, target = str(body.get("kind") or ""), str(body.get("target") or "")
    if kind == "task":
        if not store.query_one("SELECT id FROM tasks_mutual WHERE id = ?", (target,)):
            raise HTTPException(status_code=404, detail=f"task not found: {target}")
        _set_remember(store, {target}, "yes")
        return {"mark": {"kind": "task", "target": target}}
    # The page names the chat's agent `chat_agent` (an `agent_id` would read
    # as that agent writing and be turned away before it got here).
    if body.get("chat_agent") and not body.get("agent_id"):
        body = {**body, "agent_id": body["chat_agent"]}
    try:
        row = marklib.mark(store, kind, target, body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    store.rebuild()
    return {"mark": row}


@router.post("/api/marks/unmark")
def marks_remove(body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """``{kind, target, actor?}`` — every mark in force on the target is removed."""
    operator_only({"actor": body.get("actor") or "operator"}, "Unmarking something important")
    kind, target = str(body.get("kind") or ""), str(body.get("target") or "")
    if kind not in marklib.KINDS or not target:
        raise HTTPException(status_code=422, detail="kind and target are required")
    n = marklib.unmark(store, kind, target)
    if n:
        store.rebuild()
    if kind == "task":
        _set_remember(store, {target}, "")
        # A task that is not on the board had no star to take off.
        if store.query_one("SELECT id FROM tasks_mutual WHERE id = ?", (target,)):
            n = max(n, 1)
    return {"removed": n}
