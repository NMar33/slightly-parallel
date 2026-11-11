"""#done — the operator's verdict typed in the chat (donelib.py).

- ``GET /api/done-tags?agent_id=`` — applies every #done not applied yet and
  answers what this agent's latest #done did: the tasks it closed, each with
  its stretch of the chat, or ``unnamed`` when the chat named no task. The
  MCP tool ``task_done`` reads it right after the notice; the board applies
  the same tags on its next read, so a #done stands even if no agent asks.
- ``POST /api/done-tags`` ``{agent_id, proposals}`` — the same answer; with
  proposals, the next tasks are offered (nextlib.py): each with the
  project's similar open tasks, and the line the agent shows.
- ``POST /api/next-tasks/make`` ``{agent_id, numbers}`` — makes the tasks the
  operator chose, checked against their next message in the chat.
- ``GET /api/next-tasks?project=&agent_id=`` — every offer and its answer.
- ``GET /api/tasks/{task_id}/done`` — the task's stretches, counted: turns,
  chats, minutes, from its first message to the #done; and whether it was
  reopened after.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from .. import donelib, entrypointlib, nextlib, nowlib
from ..csvio import as_int
from ..db import ViewStore
from .deps import get_store

router = APIRouter()
log = logging.getLogger("sp.done")


@router.get("/api/done-tags")
def done_tags(agent_id: str = Query(""), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    got = _latest_done(store, agent_id)
    got.pop("project", None)     # for the offer only (the POST)
    return got


def _latest_done(store: ViewStore, agent_id: str) -> dict[str, Any]:
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
                    "evidence": str(t.get("evidence_required") or "") == "yes", "stretch": stretch,
                    "topic": entrypointlib.topic_of_task(store, r["task_id"])})
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
    return {"found": True, "turn": turn, "tasks": out, "unnamed": False, "next": step + _topic_step(out),
            "project": latest[0].get("project") or ""}


def _topic_step(tasks: list[dict[str, Any]]) -> str:
    """The entry point part of the answer: one "where it stopped" message
    for each topic a moved task belongs to (one per topic, not per task);
    for a moved task with no topic, set one when its work belongs to one.
    A task moved before (already) is asked nothing: its message was asked then."""
    moved = [t for t in tasks if t.get("result") == "moved"]
    if not moved:
        return ""
    topics: dict[str, list[str]] = {}
    names: dict[str, str] = {}
    for t in moved:
        tp = t.get("topic")
        if tp and tp.get("state") != "dead":
            topics.setdefault(tp["id"], []).append(t["id"])
            names[tp["id"]] = tp.get("name") or tp["id"]
    out = ""
    for ep, ids in topics.items():
        out += (f" Then entrypoint_stop {{id: \"{ep}\", task_id: \"{ids[0]}\", text}} — one message for the topic "
                f"«{names[ep]}»: where its work stopped now, one or two plain sentences.")
    loose = [t["id"] for t in moved if not t.get("topic")]
    if loose:
        out += (f" {', '.join(loose)} has no topic: if its work belongs to an entry point of this project (the "
                "MCP tool entrypoints lists them), set it with task_topic and add that one message. Offer a new "
                "entry point only when something new to open appeared or a way to open one changed "
                "(entrypoint_offer first).")
    return out


@router.get("/api/tasks/{task_id}/done")
def task_done(task_id: str, store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    return {"task_id": task_id, "stretches": donelib.stretches(store, task_id),
            "reopened": donelib.reopened(store, task_id)}


@router.post("/api/done-tags")
def done_tags_with_proposals(body: Any = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """The same answer as the GET; with ``proposals`` (at most three
    ``{title, line}``), the next tasks are offered (nextlib.py): each comes
    back with the project's similar open tasks and the line to show."""
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="send the body as a JSON object: {agent_id, proposals}")
    agent_id = str(body.get("agent_id") or "")
    raw = body.get("proposals")
    proposals: list[dict[str, str]] = []
    if nextlib.proposals_given(raw):
        try:
            proposals = nextlib.parse_proposals(raw)
        except ValueError as e:
            # Refused before anything is applied: a refusal writes nothing.
            raise HTTPException(status_code=422, detail=str(e))
    got = _latest_done(store, agent_id)
    if not proposals:
        got.pop("project", None)
        return got
    moved = [t["id"] for t in got.get("tasks") or [] if t.get("result") == "moved"]
    why = ("this #done is not applied yet: send the proposals again with the next task_done" if got.get("pending")
           else "no task was closed by this chat's latest #done" if not moved else "")
    project = str(got.pop("project", "") or "")
    if why:
        return {**got, "proposals_ignored": why}
    try:
        offered = nextlib.offer(store, agent_id, project, int(got["turn"]), moved, proposals)
    except nextlib.NextRefused as e:
        return {**got, "proposals_ignored": str(e)}
    return {**got, **offered, "next": (
        _topic_step(got.get("tasks") or []).strip() + " "
        "Show the operator this line as it is, as the last line of your reply: " + offered["show"]
        + " Where a similar task is the same thing, leave that proposal out and call task_done again "
        "with the rest, so the numbers match; name the task that is already on the board instead. "
        "When the operator answers, call next_tasks with the numbers they chose.")}


@router.post("/api/next-tasks/make")
def next_tasks_make(body: Any = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """The operator answered the offer: make the tasks they chose by number,
    checked against their next message in the chat."""
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="send the body as a JSON object: {agent_id, numbers}")
    agent_id = str(body.get("agent_id") or "")
    if not agent_id.strip():
        raise HTTPException(status_code=422, detail="agent_id is required: the chat whose offer is answered")
    try:
        numbers = nextlib.parse_numbers(body.get("numbers"))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    store.rebuild()          # the operator's answer may be seconds old
    try:
        return nextlib.make(store, agent_id, numbers)
    except nextlib.NextRefused as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/api/next-tasks")
def next_tasks_list(project: str = Query(""), agent_id: str = Query(""),
                    store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """Every offer with its answer, for the two-week check; reads only."""
    got = nextlib.offers(store, project, agent_id)
    return {"total": len(got), "offers": got}
