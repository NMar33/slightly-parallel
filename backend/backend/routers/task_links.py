"""Links between tasks: blocks, relates, parent."""

from __future__ import annotations

import hashlib
import time

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response

from ..csvio import append_if_absent, read_rows, rewrite_rows
from ..db import ViewStore
from ..entities import TASK_LINK_COLUMNS, TASK_LINK_KINDS
from .deps import create_answer, etag_for, get_store, identity_of, json_response, maybe_304, not_found
from ..taskevents import DEFAULT_ACTOR as _DEFAULT_ACTOR, append_events as _append_events

router = APIRouter()


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
