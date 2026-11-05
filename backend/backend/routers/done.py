"""#done — the operator's verdict typed in the chat (donelib.py).

- ``GET /api/done-tags?agent_id=`` — applies every #done not applied yet and
  answers what this agent's latest #done did: the tasks it closed, each with
  its stretch of the chat, or ``unnamed`` when the chat named no task. The
  MCP tool ``task_done`` reads it right after the notice; the board applies
  the same tags on its next read, so a #done stands even if no agent asks.
- ``GET /api/tasks/{task_id}/done`` — the task's stretches, counted: turns,
  chats, minutes, from its first message to the #done; and whether it was
  reopened after.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import donelib, nowlib
from ..csvio import as_int
from ..db import ViewStore
from .deps import get_store

router = APIRouter()
log = logging.getLogger("sp.done")


@router.get("/api/done-tags")
def done_tags(agent_id: str = Query(""), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    if not agent_id.strip():
        # Turn numbers are per chat: without the chat, every chat's #done
        # would be read as one.
        raise HTTPException(status_code=422, detail="agent_id is required: the chat whose #done is asked for")
    store.rebuild()          # the #done message may be seconds old
    for name, adopt in (("now", nowlib.adopt),      # a #now card the agent did not write, so #done finds it
                        ("done", donelib.adopt)):
        try:
            adopt(store)
        except Exception:
            # The answer comes from the ledger as it is; the log says what failed.
            log.warning("adoption %r failed on #done; answering from the ledger", name, exc_info=True)
    mine = [r for r in donelib.rows(store) if r.get("agent_id") == agent_id]
    newest = store.query_one("SELECT max(turn) AS turn FROM done_tags WHERE agent_id = ?", (agent_id,)) or {}
    if newest.get("turn") is not None and as_int(newest.get("turn")) > max((as_int(r.get("turn")) for r in mine), default=0):
        # The chat's latest #done has no ledger row yet: its card is still
        # being written, or its adoption failed above. Not the one before it.
        return {"found": True, "turn": as_int(newest.get("turn")), "tasks": [], "pending": True,
                "next": "This #done is not applied yet (its task card is still being written). "
                        "Call task_done again in a moment; say nothing about tasks until then."}
    if not mine:
        return {"found": False, "tasks": [], "next": "No #done is in this chat's captured messages yet."}
    turn = max(as_int(r.get("turn")) for r in mine)
    latest = [r for r in mine if as_int(r.get("turn")) == turn]
    if all(r.get("result") == "unnamed" for r in latest):
        typed = store.query_one("SELECT tasks FROM done_tags WHERE agent_id = ? AND turn = ?", (agent_id, turn)) or {}
        ids = [x for x in str(typed.get("tasks") or "").split(",") if x]
        if ids:
            return {"found": True, "turn": turn, "tasks": [], "unnamed": True, "unknown": ids,
                    "next": f"{', '.join(ids)} is not a task on the board: nothing moved. Tell the operator, "
                            "in one line; they answer with the right id."}
        return {"found": True, "turn": turn, "tasks": [], "unnamed": True,
                "next": "No task was named in this chat since the last #done. Ask the operator "
                        "which task is done; they answer with #done tk_…"}
    out = []
    for r in latest:
        t = store.query_one("SELECT id, title, status, evidence_required FROM tasks_mutual WHERE id = ?",
                            (r["task_id"],)) or {}
        # Turn numbers are per agent: the stretch of this agent's turn, not another's.
        stretch = next((s for s in donelib.stretches(store, r["task_id"])
                        if s["end"] == turn and s["agent_id"] == r["agent_id"]), None)
        out.append({"id": r["task_id"], "title": t.get("title") or "", "status": t.get("status") or "",
                    "result": r["result"], "from_status": r.get("from_status") or "",
                    "evidence": str(t.get("evidence_required") or "") == "yes", "stretch": stretch})
    moved = [x["id"] for x in out if x["result"] in ("moved", "already")]
    archived = [x["id"] for x in out if x["result"] == "archived"]
    ids = ", ".join(moved)
    if not moved:
        step = f"Say in one line that {', '.join(archived)} is archived: nothing moved, and no report is taken on it."
    else:
        step = (f"Say in one line what moved ({ids}). Then task_report {{id, summary}} for each of them: "
                "one line, what shipped — it is your account on the card, it moves nothing. "
                "Where evidence is true, follow the answer's evidence_prompt with task_evidence."
                + (f" {', '.join(archived)} is archived: say so, no report." if archived else ""))
    return {"found": True, "turn": turn, "tasks": out, "unnamed": False, "next": step}


@router.get("/api/tasks/{task_id}/done")
def task_done(task_id: str, store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    return {"task_id": task_id, "stretches": donelib.stretches(store, task_id),
            "reopened": donelib.reopened(store, task_id)}
