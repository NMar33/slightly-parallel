"""A refusal names every reason, not just the first that fired (tk_90c1ba5f).

A check used to return on its first failure: an agent fixed one thing, sent
again, met the next and guessed its way through. Checks that do not depend
on each other now ``add`` their reason to a ``Reasons`` and raise once at
the end, every reason in one answer.

The answer keeps the shape every client reads: ``detail`` is text, one line
per reason (``reason — what to do``), and the status is the first reason's.
The reasons are ordered from the most general to the most specific, so the
first one is also the one an old client acts on. ONE reason gives the same
``detail`` as before, to the byte. The JSON adds ``reasons``: one object per
reason (``reason``, ``instead``, ``code``, and ``field`` when it is about
one field). The MCP translator numbers them (mcp.py ``Api._call``).

Two stops come before anything is collected, and each is the only reason:
a missing entity (404), and no access (403) — a non-member learns nothing
more about a project it may not write, so the other checks are not run.
Checks that depend on an earlier one (a malformed body, braces before the
project they name) stay single.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse


@dataclass(frozen=True)
class Reason:
    """One reason a write was refused and what to do about it."""

    reason: str
    instead: str = ""
    status: int = 422
    code: str = "refused"
    field: str | None = None

    def line(self) -> str:
        """The reason as ``detail`` has always spelled it (actors.refuse_agent)."""
        return f"{self.reason} — {self.instead}" if self.instead else self.reason

    def wire(self) -> dict[str, Any]:
        out: dict[str, Any] = {"reason": self.reason, "instead": self.instead, "code": self.code}
        if self.field is not None:
            out["field"] = self.field
        return out


def detail_of(reasons: Iterable[Reason]) -> str:
    """Every reason's line, one per line: one reason is that line alone."""
    return "\n".join(r.line() for r in reasons)


class Refused(HTTPException):
    """An HTTPException carrying every reason; ``detail`` stays text."""

    def __init__(self, reasons: Iterable[Reason], headers: dict[str, str] | None = None) -> None:
        self.reasons = list(reasons)
        if not self.reasons:
            raise ValueError("a refusal needs at least one reason")
        super().__init__(status_code=self.reasons[0].status, detail=detail_of(self.reasons),
                         headers=headers)

    def body(self) -> dict[str, Any]:
        return {"detail": self.detail, "reasons": [r.wire() for r in self.reasons]}


class Reasons:
    """The reasons a check collects before it answers."""

    def __init__(self) -> None:
        self.items: list[Reason] = []

    def add(self, reason: str, instead: str = "", status: int = 422, code: str = "refused",
            field: str | None = None) -> Reasons:
        self.items.append(Reason(reason, instead, status, code, field))
        return self

    def add_pair(self, pair: tuple[str, str] | None, status: int = 422, code: str = "refused",
                 field: str | None = None) -> Reasons:
        """A ``(reason, instead)`` helper's answer (refuse_agent's two halves,
        tasklib.own_card_refusal, titlelib.agent_refusal); None adds nothing."""
        if pair is not None:
            self.add(pair[0], pair[1], status, code, field)
        return self

    def extend(self, other: Reasons | Iterable[Reason]) -> Reasons:
        self.items.extend(other.items if isinstance(other, Reasons) else other)
        return self

    def __bool__(self) -> bool:
        return bool(self.items)

    def __len__(self) -> int:
        return len(self.items)

    @property
    def detail(self) -> str:
        return detail_of(self.items)

    @property
    def status(self) -> int:
        return self.items[0].status if self.items else 200

    def lines(self) -> list[str]:
        return [r.line() for r in self.items]

    def refused(self) -> Refused:
        return Refused(self.items)

    def raise_if_any(self) -> None:
        if self.items:
            raise Refused(self.items)

    def as_response(self) -> JSONResponse:
        """The answer below FastAPI (the ASGI gate cannot raise)."""
        return JSONResponse(Refused(self.items).body(), status_code=self.status)


def refused_response(exc: Refused) -> JSONResponse:
    """server.py's handler: the usual ``detail`` plus ``reasons``."""
    return JSONResponse(exc.body(), status_code=exc.status_code, headers=exc.headers)
