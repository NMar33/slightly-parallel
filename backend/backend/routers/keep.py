"""Kept messages over HTTP — the interpretation an agent or the operator writes.

``POST /api/visions/{id}/interpretation`` (and ``/api/rules/…``,
``/api/problems/…``) with ``{"agent_id" | "actor", "text", "note"}``. An
agent's write is recorded as *interpreted*, the operator's as *edited*; each
is a version, and the current one is the entry's L2. Reading a kept row is
the lens detail (``GET /api/visions/{id}``), which carries the message, the
turns around it and the versions under ``kept``.

The capture hook hands out the id the moment the tagged message arrives,
before any list read has adopted it, so this route adopts before it looks.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException

from .. import examples, keeplib
from ..db import ViewStore
from ..entities import ENTITIES
from .deps import create_answer, get_store, refuse_agent, written_by_agent
from .integrate import sync_all_rules

router = APIRouter()

# Plain functions: FastAPI runs each on a worker thread. As coroutines they
# read rows, documents and chat logs on the event loop around the one call
# they handed to a thread, and every other request waited meanwhile.


def _register(kind: str) -> None:
    ent = ENTITIES[kind]

    def interpretation(
        item_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store),
    ) -> dict:
        sql = f"SELECT * FROM {ent.view} WHERE id = ?"
        row = store.query_one(sql, (item_id,))
        if row is None:
            keeplib.adopt(store)
            row = store.query_one(sql, (item_id,))
        if row is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"{kind} not found: {item_id} — read the id again in the "
                    f"[slightly-parallel] notice that named it, or find it with the MCP tool search."
                ),
            )
        if str(row.get("source") or "") not in keeplib.SOURCES:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"{item_id} was posted, not kept from a message, so it has no "
                    f"interpretation — change its text with the MCP tool update_entry"
                ),
            )
        try:
            keeplib.interpret(
                store, kind, row,
                str(body.get("text") or ""), str(body.get("note") or ""),
                by_agent=written_by_agent(body),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if kind == "rule":
            sync_all_rules(store)
        fresh = store.query_one(sql, (item_id,)) or row
        return {"metadata": fresh, "kept": keeplib.record(store, kind, fresh)}

    interpretation.__doc__ = (
        f"Write the interpretation of a kept {kind}: a new version, and the entry's L2."
    )
    router.add_api_route(
        f"/api/{ent.list_key}/{{item_id}}/interpretation", interpretation,
        methods=["POST"], name=f"{ent.list_key}_interpretation",
    )


for _kind in keeplib.KINDS:
    if _kind != "skill":  # a skill's text is a SKILL.md draft: routers/skills.py
        _register(_kind)


@router.post("/api/problems/{item_id}/rule", status_code=201)
def rule_from_problem(
    item_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store),
) -> dict:
    """``{text, title?}`` — the operator writes a rule on the basis of a problem.

    The problem is not changed. An agent cannot do this: a rule is the
    operator's correction, and an agent proposes one in chat instead.
    """
    if written_by_agent(body):
        refuse_agent("a rule from a problem is written by the operator",
                     "propose it in chat instead")
    view = ENTITIES["problem"].view
    row = store.query_one(f"SELECT * FROM {view} WHERE id = ?", (item_id,))
    if row is None:
        keeplib.adopt(store)
        row = store.query_one(f"SELECT * FROM {view} WHERE id = ?", (item_id,))
    if row is None:
        raise HTTPException(status_code=404, detail=f"problem not found: {item_id}")
    try:
        rid = keeplib.rule_from_problem(
            store, row,
            str(body.get("text") or ""), str(body.get("title") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    rule = store.query_one(f"SELECT * FROM {ENTITIES['rule'].view} WHERE id = ?", (rid,))
    return create_answer({"metadata": rule, "kept": keeplib.record(store, "rule", rule)})


@router.post("/api/examples/remove")
def examples_remove(store: ViewStore = Depends(get_store)) -> dict:
    """Take the example visions, rules, problems and skills out. Restore puts them back."""
    return {"removed": examples.remove(store)}


@router.get("/api/examples/state")
def examples_state(store: ViewStore = Depends(get_store)) -> dict:
    """``{present, removed, all}`` — example ids in the ledgers, taken out, and every one there is."""
    return examples.state(store)


@router.post("/api/examples/restore")
def examples_restore(store: ViewStore = Depends(get_store)) -> dict:
    """Put the removed examples back. ``{added: [...]}``."""
    return {"added": examples.restore(store)}
