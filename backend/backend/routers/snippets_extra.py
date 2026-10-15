"""Snippet mutations: update and delete (terminal command shortcuts)."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException

from ..csvio import rewrite_rows
from ..db import ViewStore
from ..entities import ENTITIES
from .deps import get_store, not_found

router = APIRouter()

_MUTABLE_FIELDS = {"label", "command", "position"}


@router.post("/api/snippets/{snippet_id}/update", status_code=200)
def snippets_update(
    snippet_id: str,
    body: dict = Body(...),
    store: ViewStore = Depends(get_store),
) -> dict:
    ent = ENTITIES["snippet"]
    csv_path = store.data_root / ent.csv
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail="snippets.csv not found")

    def mutate(rows: list[dict[str, str]]) -> bool:
        target = next((r for r in rows if r.get("id") == snippet_id), None)
        if target is None:
            raise not_found("snippet", snippet_id)
        changed = False
        for k, v in body.items():
            if k in _MUTABLE_FIELDS:
                new_v = str(v) if v is not None else ""
                if target.get(k, "") != new_v:
                    target[k] = new_v
                    changed = True
        return changed

    rewrite_rows(csv_path, ent.columns, mutate)
    store.rebuild()
    updated = store.query_one(
        "SELECT * FROM snippets_mutual WHERE id = ?", (snippet_id,)
    )
    return {"snippet": updated or {}}


@router.post("/api/snippets/{snippet_id}/delete", status_code=200)
def snippets_delete(
    snippet_id: str,
    store: ViewStore = Depends(get_store),
) -> dict:
    ent = ENTITIES["snippet"]
    csv_path = store.data_root / ent.csv
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail="snippets.csv not found")

    def mutate(rows: list[dict[str, str]]) -> bool:
        before = len(rows)
        rows[:] = [r for r in rows if r.get("id") != snippet_id]
        if len(rows) == before:
            raise not_found("snippet", snippet_id)
        return True

    rewrite_rows(csv_path, ent.columns, mutate)
    store.rebuild()
    return {"deleted": snippet_id}
