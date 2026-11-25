"""Messages between agents (tk_c1caab80; msgledger.py, msgdeliver.py).

``POST /api/messages`` sends one (``{to, text, reply_to?}``): an agent's
write comes through the MCP tool ``message`` (``agent_id`` stamped), the
operator's from Slightly Parallel's own page (no agent: ``from`` is
``operator``). A notice is typed into the chat's terminal when that is
safe, and otherwise waits for the next try or the chat's next prompt. The
body is read through the inbox.

``POST /api/messages/inbox`` (``{agent_id}``, the MCP tool ``messages``)
answers the chat's unread messages and marks them read, then its newest
read ones.

``GET /api/messages`` (``?agent_id=&project=&limit=``) is the ledger,
newest first, for a page to show: no write.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request

from .. import msgdeliver, msgledger
from ..actors import identity_of, is_agent, refuse_agent

router = APIRouter()


def _root(request: Request):
    return request.app.state.settings.data_root


@router.post("/api/messages", status_code=201)
def send(request: Request, body: dict = Body(...)) -> dict[str, Any]:
    """``{to, text, reply_to?, agent_id?}`` — a message to a chat."""
    root = _root(request)
    sender = identity_of(body) or msgledger.OPERATOR
    if sender != msgledger.OPERATOR and not is_agent(sender):
        sender = msgledger.OPERATOR
    to = str(body.get("to") or "").strip()
    text = msgledger.clean_text(str(body.get("text") or ""))
    reply_to = str(body.get("reply_to") or "").strip()
    if not to:
        raise HTTPException(status_code=422, detail="to is the agent_id of the chat the message is for")
    target = msgdeliver.chat_meta(root, to)
    if target is None:
        raise HTTPException(status_code=404, detail=f"no chat {to!r}: to is a chat's agent_id (cc-…, codex-…)")
    if to == sender:
        raise HTTPException(status_code=422, detail="a chat does not send a message to itself")
    if not text:
        raise HTTPException(status_code=422, detail="text is the message, and it is empty")
    if len(text) > msgledger.TEXT_MAX:
        raise HTTPException(status_code=422, detail=(
            f"a message is at most {msgledger.TEXT_MAX} characters ({len(text)} here): "
            "put the long part in a note (note_write) and send its id"))
    if reply_to:
        if not msgledger.ID_RE.match(reply_to) or msgledger.find(root, reply_to) is None:
            raise HTTPException(status_code=404, detail=f"reply_to {reply_to!r} is no message (msg_…)")
    project = str(target.get("project") or "")
    if sender != msgledger.OPERATOR:
        own = msgdeliver.chat_meta(root, sender)
        if own is not None and own.get("project"):
            project = str(own["project"])
    row = msgledger.add(root, project=project, from_agent=sender, to_agent=to, text=text, reply_to=reply_to)
    try:
        typed, why = msgdeliver.try_delivery(root, row["id"])
    except Exception as exc:  # noqa: BLE001 — the message is kept; the next round tries again
        typed, why = False, f"{type(exc).__name__}: {exc}"
    row = msgledger.find(root, row["id"]) or row
    waiting = ""
    if not row["delivered_via"]:
        if row["codex_thread"] and not row["codex_checked"]:
            waiting = "checking Codex thread history for the earlier send"
        else:
            waiting = f"awaiting delivery ({why}); available at Stop, on the next prompt or in the inbox"
    return {
        "message": row,
        "delivered_via": row["delivered_via"],
        "waiting": waiting,
        "typed": typed and row["delivered_via"] == "terminal",
    }


@router.post("/api/messages/inbox")
def inbox(request: Request, body: dict = Body(...), recent: int = Query(10, ge=0, le=100)) -> dict[str, Any]:
    """``{agent_id}`` — the chat's unread messages (marked read now), then its newest read ones."""
    who = identity_of(body)
    if not is_agent(who):
        refuse_agent("An inbox is a chat's", "the operator reads the messages on GET /api/messages")
    if not msgledger.AGENT_RE.match(who):
        raise HTTPException(status_code=422, detail="agent_id is a chat's agent_id")
    got = msgledger.inbox(_root(request), who, recent)
    return {**got, "how_to_reply": "MCP tool message {to: <from_agent>, text, reply_to: <id>}"}


@router.get("/api/messages")
def listing(request: Request, agent_id: str = Query(""), project: str = Query(""),
            limit: int = Query(100, ge=1, le=1000)) -> dict[str, Any]:
    """The ledger, newest first: one chat's (sent or received), one project's, or all."""
    rows = msgledger.read_rows(_root(request))
    if agent_id:
        rows = [r for r in rows if agent_id in (r["from_agent"], r["to_agent"])]
    if project:
        rows = [r for r in rows if r["project"] == project]
    rows.sort(key=lambda r: (r["sent_at"], r["id"]), reverse=True)
    return {"total": len(rows), "messages": rows[:limit]}


@router.get("/api/messages/{message_id}")
def detail(request: Request, message_id: str) -> dict[str, Any]:
    """Read one message and its reply thread without marking them read."""
    rows = msgledger.read_rows(_root(request))
    message = next((row for row in rows if row["id"] == message_id), None)
    if message is None:
        raise HTTPException(status_code=404, detail="No such message")
    participants = {message["from_agent"], message["to_agent"]}
    conversation = {row["id"]: row for row in rows if {row["from_agent"], row["to_agent"]} == participants}
    neighbors: dict[str, list[str]] = {}
    for row in conversation.values():
        parent = row["reply_to"]
        if parent in conversation:
            neighbors.setdefault(parent, []).append(row["id"])
            neighbors.setdefault(row["id"], []).append(parent)
    visited = {message_id}
    pending = [message_id]
    while pending:
        for related in neighbors.get(pending.pop(), []):
            if related not in visited:
                visited.add(related)
                pending.append(related)
    return {"message": message, "thread": [row for key, row in conversation.items() if key in visited]}
