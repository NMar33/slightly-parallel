"""Reading the store's views the way pages and libraries both do: a view
that may not exist yet, and the agent behind a row.

Out of routers/deps.py so a library can use them without importing a router
(routers re-export them from there)."""

from __future__ import annotations

from typing import Any

from .db import ViewStore


# What a row about an agent's work needs to carry so a reader can name the
# agent and pick its chat back up: the fields the one labelling rule reads
# (frontend utils/agentLabel), and the origin the capture hook recorded —
# tool, folder and full session id, which a resume command is built from.
# The label is not computed here: one rule, and it lives where the name is
# drawn. A chat captured before the hook recorded origin carries empty
# strings, which is how a reader knows to offer no resume.
AGENT_ORIGIN_FIELDS: tuple[str, ...] = (
    "agent_id", "agent_name", "chat_title", "created_date",
    "tool", "cwd", "session_ref", "agent_group",
)


def agents_by_id(store: ViewStore) -> dict[str, dict[str, str]]:
    """One pass over the agents the store already parsed."""
    return {
        str(a.get("agent_id") or ""): {
            k: str(a.get(k) or "") for k in AGENT_ORIGIN_FIELDS
        }
        for a in store.agents()
    }


def attach_agent(store: ViewStore, rows: list[dict[str, Any]], field: str = "agent_id") -> None:
    """Put the agent behind each row under ``agent`` (None when it is gone)."""
    by_id = agents_by_id(store)
    for r in rows:
        r["agent"] = by_id.get(str(r.get(field) or ""))


def rows_or_empty(store: ViewStore, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """A query against a view that may not exist yet (no CSV behind it). A
    missing view is an empty ledger; any other failure is a real one."""
    try:
        return store.query(sql, params)
    except Exception as exc:  # noqa: BLE001
        if "does not exist" in str(exc) or "Catalog" in type(exc).__name__:
            return []
        raise


def clean(row: dict[str, Any]) -> dict[str, Any]:
    """Drop NULLs so Pydantic model defaults win for optional fields."""
    return {k: v for k, v in row.items() if v is not None}
