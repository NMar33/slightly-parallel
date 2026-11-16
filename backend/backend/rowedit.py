"""Change one row of a ledger by id, under its lock, and rebuild — the shape
every router that edits a ledger of its own wrote out, and the libraries
that edit on their behalf (timelib) now share. routers/deps re-exports it."""

from __future__ import annotations

from typing import Callable

from .answers import not_found
from .csvio import rewrite_rows
from .db import ViewStore


def rewrite_one(
    store: ViewStore, csv_name: str, columns: tuple[str, ...], row_id: str,
    change: Callable[[list[dict[str, str]], dict[str, str]], bool], what: str,
) -> dict[str, str]:
    """Change one row of a ledger by id, under its lock, and rebuild.

    ``change(rows, row)`` edits the row (or the list, to delete it) and
    says whether anything changed. A missing row is the one 404
    (``not_found``). The shape was written out in every router that edits
    a ledger of its own.
    """
    csv_path = store.data_root / csv_name
    hit: list[dict[str, str]] = []

    def mutate(rows: list[dict[str, str]]) -> bool:
        for r in rows:
            if r.get("id") == row_id:
                hit.append(r)
                return change(rows, r)
        return False

    if csv_path.exists():
        rewrite_rows(csv_path, columns, mutate)
    if not hit:
        raise not_found(what, row_id)
    store.rebuild()
    return hit[0]
