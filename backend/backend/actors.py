"""Who is writing — the operator's pages, the server's own hands, or an
agent — and the one refusal an agent gets for a write that is not its own.

Read by every gate: the routers (routers/deps.py re-exports these names),
the MCP check in server.py, and the libraries that write on a router's
behalf."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

# Actors that are the board itself, not an agent: the operator in the UI
# and the server's own hands (stacks, resurfacing). Everything else is an
# agent id, and a few writes are the operator's alone.
HOUSE_ACTORS: tuple[str, ...] = ("", "operator", "stack", "resurface")


def is_agent(actor: Any) -> bool:
    return str(actor or "") not in HOUSE_ACTORS


def identity_of(body: Any) -> str:
    """Who is writing. The one reading, for every gate and the MCP check.

    A body can carry ``actor`` and ``agent_id``. Routers used to read them in
    two different orders, so ``{actor: "operator", agent_id: "cc-x"}`` was an
    operator to one gate and an agent to the next — and to the check that
    keeps agents on the MCP path it was an operator, which let a raw HTTP
    write through. If either field names an agent, the writer is that agent.
    """
    if not isinstance(body, dict):
        return ""
    actor = str(body.get("actor") or "").strip()
    agent = str(body.get("agent_id") or "").strip()
    for who in (actor, agent):
        if who and is_agent(who):
            return who
    return actor or agent


def written_by_agent(body: Any) -> bool:
    return is_agent(identity_of(body))


# The one status an agent gets when a write is not its to make. It is 422
# and not 403 on purpose: the frontend and the MCP translator already branch
# on 422 for every refusal, and a published code is not changed under them.
AGENT_REFUSED = 422


def refuse_agent(reason: str, instead: str = "") -> None:
    """Raise the one refusal an agent gets — one status, one ``detail``.

    Five code paths used to raise this by hand (``operator_only`` here,
    ``lenses.refuse_agent_write``, ``skills._operator_only`` and a dozen
    inline raises), each spelling the status and the key itself. They all
    come through here now, so the shape an agent reads is one shape and a
    change to it is one edit. ``reason`` is the sentence; ``instead`` is
    what the agent does about it, appended after an em dash.
    """
    tail = f" — {instead}" if instead else ""
    raise HTTPException(status_code=AGENT_REFUSED, detail=f"{reason}{tail}")


def operator_only(body: Any, what: str, instead: str = "") -> None:
    """Refuse an agent. ``what`` is the act; ``instead`` is what an agent does."""
    if written_by_agent(body):
        refuse_agent(f"{what} is the operator's", instead)
