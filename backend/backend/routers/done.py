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

from typing import Any

from fastapi import APIRouter, Depends, Query

from .. import donelib, nowlib
from ..db import ViewStore
from .deps import get_store

router = APIRouter()


@router.get("/api/done-tags")
def done_tags(agent_id: str = Query(""), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    store.rebuild()          # the #done message may be seconds old
    nowlib.adopt(store)      # a #now card the agent did not write, so #done finds it
    donelib.adopt(store)
    mine = [r for r in donelib.rows(store) if not agent_id or r.get("agent_id") == agent_id]
    if not mine:
        return {"found": False, "tasks": [], "next": "No #done is in this chat's captured messages yet."}
    turn = max(int(r.get("turn") or 0) for r in mine)
    latest = [r for r in mine if int(r.get("turn") or 0) == turn]
    if all(r.get("result") == "unnamed" for r in latest):
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
    ids = ", ".join(x["id"] for x in out)
    return {
        "found": True, "turn": turn, "tasks": out, "unnamed": False,
        "next": (f"Say in one line what moved ({ids}). Then task_report {{id, summary}} for each: "
                 "one line, what shipped — it is your account on the card, it moves nothing. "
                 "Where evidence is true, follow the answer's evidence_prompt with task_evidence."),
    }


@router.get("/api/tasks/{task_id}/done")
def task_done(task_id: str, store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    return {"task_id": task_id, "stretches": donelib.stretches(store, task_id),
            "reopened": donelib.reopened(store, task_id)}
