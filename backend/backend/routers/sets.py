"""Sets — named, ordered groups of kept entries, saved for reuse.

A set is how the operator hands a chosen mix to an agent: visions from any
project and any tag, in the order they should be read. Sets live in
``sets.json`` at the data root, like boards, so they are the same in every
browser and a later Integrate can write one into an agent's files.

``{id, name, kind, items: [entry ids], created_at, updated_at}``. ``kind``
names the ledger the items come from — vision today; rules and problems
take the same shape. Items are ids, not copies: a set always reads the
current interpretation.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response

from .. import limits
from ..db import ViewStore
from ..file_safety import edit_json, safe_read_json
from .deps import etag_for, get_store, json_response, maybe_304, not_found
from ..date_utils import now_iso

router = APIRouter()
SETS_FILE = "sets.json"
KINDS = ("vision", "rule", "problem", "entrypoint")
MAX_NAME = limits.MAX_SET_NAME
MAX_ITEMS = 500


def _rows(data: Any) -> list[dict[str, Any]]:
    rows = data.get("sets") if isinstance(data, dict) else None
    return [s for s in rows if isinstance(s, dict) and s.get("id")] if isinstance(rows, list) else []


def _read(store: ViewStore) -> list[dict[str, Any]]:
    try:
        return _rows(safe_read_json(store.data_root / SETS_FILE))
    except (OSError, ValueError):
        return []


def _edit(store: ViewStore, change) -> Any:
    """Read-modify-write sets.json under one lock (file_safety.edit_json).
    ``change(rows)`` mutates the list and returns what the route answers."""
    answer: list[Any] = []

    def apply(data: dict) -> dict:
        rows = _rows(data)
        answer.append(change(rows))
        return {"sets": rows}

    edit_json(store.data_root / SETS_FILE, apply)
    return answer[0]




def _name(raw: Any) -> str:
    name = " ".join(str(raw or "").split())
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    if len(name) > MAX_NAME:
        raise HTTPException(status_code=422, detail=f"name is at most {MAX_NAME} characters")
    return name


def _items(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        raise HTTPException(status_code=422, detail="items must be a list of entry ids")
    out: list[str] = []
    for x in raw:
        s = str(x).strip()
        if s and s not in out:
            out.append(s)
    if len(out) > MAX_ITEMS:
        raise HTTPException(status_code=422, detail=f"a set holds at most {MAX_ITEMS} entries")
    return out


def _find(rows: list[dict[str, Any]], set_id: str) -> dict[str, Any]:
    found = next((s for s in rows if s.get("id") == set_id), None)
    if found is None:
        raise not_found("set", set_id)
    return found


@router.get("/api/sets")
def sets_list(
    request: Request, kind: str = Query(""), store: ViewStore = Depends(get_store),
) -> Response:
    """Saved sets in the order they were made, optionally of one kind."""
    rows = [s for s in _read(store) if not kind or s.get("kind") == kind]
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()[:12]
    etag = etag_for(f"sets:{kind}:{digest}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r
    return json_response({"total": len(rows), "sets": rows}, etag)


@router.post("/api/sets", status_code=201)
def sets_create(body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    """``{name, kind, items?}`` — names may repeat; the id is minted."""
    kind = str(body.get("kind") or "")
    if kind not in KINDS:
        raise HTTPException(status_code=422, detail=f"kind must be one of: {', '.join(KINDS)}")
    now = now_iso()
    row = {
        "id": "ks_" + secrets.token_hex(4),
        "name": _name(body.get("name")),
        "kind": kind,
        "items": _items(body.get("items", [])),
        "created_at": now,
        "updated_at": now,
    }
    def add(rows: list[dict[str, Any]]) -> dict:
        rows.append(row)
        return dict(row)

    return {**_edit(store, add), "existing": False, "warnings": []}


@router.post("/api/sets/{set_id}/update")
def sets_update(set_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    """``{name?, items?}`` — items replace the list, in the order given."""
    def change(rows: list[dict[str, Any]]) -> dict:
        row = _find(rows, set_id)
        if "name" in body:
            row["name"] = _name(body["name"])
        if "items" in body:
            row["items"] = _items(body["items"])
        row["updated_at"] = now_iso()
        return dict(row)

    return _edit(store, change)


@router.post("/api/sets/{set_id}/delete")
def sets_delete(set_id: str, store: ViewStore = Depends(get_store)) -> dict:
    """Forget the set. The entries in it are not touched."""
    def drop(rows: list[dict[str, Any]]) -> dict:
        _find(rows, set_id)
        rows[:] = [s for s in rows if s.get("id") != set_id]
        return {"deleted": set_id}

    return _edit(store, drop)
