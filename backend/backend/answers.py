"""The shapes every write answers in: a create's answer, a stable id, the
one wording for a missing thing. Routers re-export them (routers/deps.py)."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException


def create_answer(
    payload: dict[str, Any],
    response: Any = None,
    *,
    existing: bool = False,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """The one shape of an answer to a create.

    Two keys every create carries, whatever it wrapped the new thing in:

    * ``existing`` — true when the post found the thing already written and
      wrote nothing. A repeat also drops 201 to 200, so an agent retrying
      after a timeout can tell from the status alone whether it just made a
      duplicate. Four handlers did the downgrade and six detected the repeat
      and answered 201 anyway.
    * ``warnings`` — always a list, empty when there is nothing to say. It
      used to be present only when non-empty, so a caller could not tell
      "no warnings" from "this route has none", and had to test for the key
      before reading it.

    The wrapper word around the created thing is left alone: pages read
    ``note``, ``link``, ``board``, ``metadata`` by name, and renaming a key
    a page reads is a separate, larger move.
    """
    out = dict(payload)
    out["existing"] = existing
    out["warnings"] = list(warnings or [])
    if existing and response is not None:
        response.status_code = 200
    return out


def mint_id(prefix: str, *parts: str) -> str:
    """A stable short id from its parts: ``prefix`` + 8 hex of their hash."""
    import hashlib
    return prefix + hashlib.sha256("|".join(parts).encode()).hexdigest()[:8]


def not_found(kind: str, item_id: str) -> HTTPException:
    """The one wording for a missing thing: ``<kind> not found: <id>``."""
    return HTTPException(status_code=404, detail=f"{kind} not found: {item_id}")
