"""An agent's projects: read them, and the operator's join, leave and task
level (tk_d1d25a4d step 2; note nt_9de63b9e §3, spec nt_27a4fff5).

Only the operator writes here. The home stays at the origin until routing
and accounting follow it (steps 3 and 8); the rows the project delete and
the one-chat move write are theirs alone, by value and by op. Every refusal
is one line and writes nothing; every answer carries the operator summary.
"""

from __future__ import annotations

import csv
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from .. import chatmove
from .. import membership_fold as mf
from .. import memberships
from ..db import ViewStore
from ..file_safety import FileSafetyError
from .deps import get_store, not_found, operator_only

router = APIRouter()

VALUE_MAX = 200
BUSY = "the membership ledger is held by a project delete or a chat move; try again in a moment"


def _agent(store: ViewStore, agent_id: str) -> dict[str, Any]:
    raw = next((a for a in store.agents() if a.get("agent_id") == agent_id), None)
    if raw is None:
        raise not_found("agent", agent_id)
    return raw


def _text(body: dict, key: str) -> str:
    """A field that is one text value, or 422 naming the shape (P16)."""
    v = body.get(key)
    if v is None:
        return ""
    if not isinstance(v, str):
        raise HTTPException(status_code=422, detail=f"{key} is one text value, not a {type(v).__name__}")
    return v.strip()


@router.get("/api/agents/{agent_id}/membership")
def membership(agent_id: str, store: ViewStore = Depends(get_store)) -> dict:
    """The agent's projects, home and task level, with the operator summary."""
    return memberships.summary(store, _agent(store, agent_id))


@router.post("/api/agents/{agent_id}/membership")
def membership_write(
    agent_id: str,
    body: Any = Body(...),
    store: ViewStore = Depends(get_store),
) -> dict:
    """``{op, project?, value?}``: ``join`` / ``leave`` a project, or set the
    task ``level`` (value 1–3). ``home`` is refused until steps 3 and 8."""
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail=f"the body is one object {{op, project?, value?}}, not a {type(body).__name__}")
    operator_only(body, "Changing an agent's projects", "ask the operator")
    op = _text(body, "op")
    project = _text(body, "project")
    raw_value = body.get("value")
    if isinstance(raw_value, int) and not isinstance(raw_value, bool) and op == "level":
        value = str(raw_value)
    else:
        value = _text(body, "value")
    if op == "moved":
        raise HTTPException(status_code=422, detail="moved is written by the chat move: POST /api/agents/{id}/move-chat")
    if op not in memberships.ROUTE_OPS:
        raise HTTPException(status_code=422, detail=f"op is one of: {', '.join(memberships.ROUTE_OPS)}")
    if value == mf.DELETED or value.startswith(mf.MOVED_FROM.strip()):
        raise HTTPException(status_code=422, detail=f"«{value}» is written by the project delete or the chat move, not here")
    if len(value) > VALUE_MAX or any(ord(c) < 32 for c in value):
        raise HTTPException(status_code=422, detail=f"value is one line of at most {VALUE_MAX} characters")
    if op in ("join", "leave", "home") and not project:
        raise HTTPException(status_code=422, detail=f"{op} needs a project")
    agent = _agent(store, agent_id)
    if agent.get("helper") is True:
        raise HTTPException(status_code=409, detail=f"{agent_id} is a helper chat: it goes where its parent goes (step 5)")
    if op == "home":
        raise HTTPException(status_code=409, detail=memberships.HOME_WAITS)
    if op == "level" and value not in ("1", "2", "3"):
        raise HTTPException(status_code=422, detail="level is 1, 2 or 3")
    try:
        row = memberships.write(store.data_root, agent_id, op, project if op != "level" else "", value)
    except memberships.Refused as r:
        raise HTTPException(status_code=r.status, detail=r.detail) from None
    except FileSafetyError:
        raise HTTPException(status_code=503, detail=BUSY) from None
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        # P17: a ledger that cannot be read refuses the write.
        raise HTTPException(status_code=503, detail=memberships.UNREADABLE.format(type(exc).__name__)) from None
    store.rebuild()
    return {**memberships.summary(store, _agent(store, agent_id)), "row": row}


@router.post("/api/agents/{agent_id}/move-chat")
def move_chat(
    agent_id: str,
    body: Any = Body(...),
    store: ViewStore = Depends(get_store),
) -> dict:
    """``{to}``: move the agent's chat folder from its origin to ``to``, one
    of its member projects — the operator's way out of a project delete that
    a member's chat holds back (chatmove.py). Every check refuses in one
    line and writes nothing; the answer states what the move changes."""
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail=f"the body is one object {{to}}, not a {type(body).__name__}")
    operator_only(body, "Moving a chat between projects",
                  "ask the operator to move it from the project delete dialog")
    to = _text(body, "to")
    if not to:
        raise HTTPException(status_code=422, detail="to names the project the chat moves to")
    _agent(store, agent_id)
    try:
        out = chatmove.move(store.data_root, agent_id, to)
    except chatmove.MoveRefused as r:
        raise HTTPException(status_code=r.status, detail=r.detail) from None
    except memberships.LedgerUnreadable as bad:
        raise HTTPException(status_code=503, detail=bad.detail) from None
    except memberships.Refused as r:
        raise HTTPException(status_code=r.status, detail=r.detail) from None
    except FileSafetyError:
        raise HTTPException(status_code=503, detail=BUSY) from None
    store.rebuild()
    return out
